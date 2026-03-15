#!/usr/bin/env python3
"""Patch Kermit-80 CPVGEN overlay for z80pack direct-port AUX I/O.

The Generic CP/M 2.2 overlay (CPVGEN) uses BIOS CONSTAT/CONIN with IOBYTE
switching for serial I/O.  z80pack's CP/M 2.2 BIOS ignores IOBYTE in its
CONSTAT routine, so Kermit's CONNECT polling loop never detects incoming
AUX data.

This patcher replaces the overlay's serial routines with direct IN/OUT
instructions targeting z80pack's documented I/O ports:

    AUX data    = port 5  (IN: non-blocking read, returns 0x1A if empty;
                           OUT: write byte)

Port 5 IN (auxd_in in simio.c) uses O_NONBLOCK on the auxin FIFO.
When no data is available, read() returns EAGAIN and the handler returns
0x1A (CP/M EOF sentinel).  The patched INPMDM uses this: read port 5,
if result == 0x1A treat as "no data" and return A=0.

Port assignments from z80pack cpmsim/srcsim/simio.c at commit 91fd28eb.
"""

from __future__ import annotations

from pathlib import Path

# ---------------------------------------------------------------------------
# z80pack I/O ports (from simio.c at pinned commit 91fd28eb)
# ---------------------------------------------------------------------------
AUX_STATUS_PORT = 0x04
AUX_DATA_PORT = 0x05

# ---------------------------------------------------------------------------
# Overlay addresses (from CPVGEN.HEX parsed into the merged KERM411.COM)
#
# The overlay JMP table lives at 0x7008 in the COM address space.
# These targets were confirmed by parsing the actual overlay HEX data.
# ---------------------------------------------------------------------------
OUTMDM_ADDR = 0x72F9  # JMP target from table entry at 0x700B
INPMDM_ADDR = 0x7305  # JMP target from table entry at 0x700E

COM_ORIGIN = 0x0100

# Original bytes at outmdm (12 bytes: PUSH HL; PUSH BC; LD A,(prtfun);
# LD C,A; CALL BDOS; POP BC; POP HL; RET)
OUTMDM_ORIGINAL = bytes([
    0xE5,                   # PUSH HL
    0xC5,                   # PUSH BC
    0x3A, 0xDA, 0x72,       # LD A,(72DAH)  ; prtfun
    0x4F,                   # LD C,A
    0xCD, 0x05, 0x00,       # CALL 0005H    ; BDOS
    0xC1,                   # POP BC
    0xE1,                   # POP HL
    0xC9,                   # RET
])

# Original bytes at inpmdm (9 bytes: CALL bconst; OR A; RET Z;
# CALL bconin; RET)
INPMDM_ORIGINAL = bytes([
    0xCD, 0x12, 0x71,       # CALL 7112H    ; bconst
    0xB7,                   # OR A
    0xC8,                   # RET Z
    0xCD, 0x15, 0x71,       # CALL 7115H    ; bconin
    0xC9,                   # RET
])

# ---------------------------------------------------------------------------
# Replacement routines
# ---------------------------------------------------------------------------

# New outmdm: CR→LF translation before OUT.
# z80pack auxd_out drops CR (0x0D); translate to LF (0x0A) which passes through.
# The bridge adds LF→CRLF on the BBS side if needed.
_OUTMDM_CODE = bytes([
    0x7B,                           # LD A,E        — character in E
    0xFE, 0x0D,                     # CP 0DH        — is it CR?
    0x20, 0x02,                     # JR NZ,.send   — no, send as-is
    0x3E, 0x0A,                     # LD A,0AH      — yes, translate to LF
    # .send:
    0xD3, AUX_DATA_PORT,            # OUT (5),A     — write to AUX port
    0xC9,                           # RET
])
OUTMDM_PATCH = _OUTMDM_CODE.ljust(len(OUTMDM_ORIGINAL), b'\x00')

# New inpmdm: IN A,(AUX_DATA) — non-blocking, returns 0x1A when empty.
# If 0x1A, return A=0 (no data).  Otherwise return the byte in A.
# NOP-pad to 9 bytes.
_INPMDM_CODE = bytes([
    0xDB, AUX_DATA_PORT,            # IN A,(5)  — non-blocking read
    0xFE, 0x1A,                     # CP 1AH    — "no data" sentinel?
    0xC0,                           # RET NZ    — real data, return in A
    0xAF,                           # XOR A     — no data, return A=0
    0xC9,                           # RET
])
INPMDM_PATCH = _INPMDM_CODE.ljust(len(INPMDM_ORIGINAL), b'\x00')


def patch_kermit_for_z80pack(com_data: bytes) -> bytes:
    """Apply z80pack AUX port patches to a merged KERM411.COM image.

    Parameters
    ----------
    com_data : bytes
        Raw COM image built from CPSKER.HEX + CPVGEN.HEX (origin 0x0100).

    Returns
    -------
    bytes
        Patched COM image with direct-port AUX I/O.

    Raises
    ------
    ValueError
        If the expected original bytes are not found at the overlay
        addresses, indicating the input binary does not match the
        expected CPVGEN overlay.
    """
    data = bytearray(com_data)

    outmdm_off = OUTMDM_ADDR - COM_ORIGIN
    inpmdm_off = INPMDM_ADDR - COM_ORIGIN

    # Verify original bytes before patching
    actual_outmdm = bytes(data[outmdm_off:outmdm_off + len(OUTMDM_ORIGINAL)])
    if actual_outmdm != OUTMDM_ORIGINAL:
        raise ValueError(
            f"outmdm at 0x{OUTMDM_ADDR:04X}: expected {OUTMDM_ORIGINAL.hex()}, "
            f"got {actual_outmdm.hex()}"
        )

    actual_inpmdm = bytes(data[inpmdm_off:inpmdm_off + len(INPMDM_ORIGINAL)])
    if actual_inpmdm != INPMDM_ORIGINAL:
        raise ValueError(
            f"inpmdm at 0x{INPMDM_ADDR:04X}: expected {INPMDM_ORIGINAL.hex()}, "
            f"got {actual_inpmdm.hex()}"
        )

    # Apply patches
    data[outmdm_off:outmdm_off + len(OUTMDM_PATCH)] = OUTMDM_PATCH
    data[inpmdm_off:inpmdm_off + len(INPMDM_PATCH)] = INPMDM_PATCH

    return bytes(data)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Patch KERM411.COM for z80pack direct-port AUX I/O"
    )
    parser.add_argument("input", type=Path, help="Input KERM411.COM")
    parser.add_argument("output", type=Path, help="Output patched COM file")
    args = parser.parse_args()

    com_data = args.input.read_bytes()
    patched = patch_kermit_for_z80pack(com_data)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(patched)

    changed = sum(a != b for a, b in zip(com_data, patched))
    print(f"Patched {changed} bytes in {args.output}")
    print(f"  outmdm @ 0x{OUTMDM_ADDR:04X}: direct OUT ({AUX_DATA_PORT}),A")
    print(f"  inpmdm @ 0x{INPMDM_ADDR:04X}: direct IN A,({AUX_DATA_PORT}), 0x1A sentinel")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
