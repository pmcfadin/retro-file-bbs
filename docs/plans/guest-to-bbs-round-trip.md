# Plan: Guest→BBS Round-Trip Fix (CR Stripping in z80pack auxd_out)

## Context

The retro_bbs emulation stack (z80pack + CP/M 2.2 + Kermit-80 + AUX bridge)
has a working **BBS→guest** path: the BBS welcome screen renders on the CP/M
console through Kermit's CONNECT mode. This was fixed by patching the CPVGEN
overlay's INPMDM/OUTMDM routines to use z80pack's direct AUX I/O ports
(see `emulation/assets/patch_kermit_z80pack.py`).

The **guest→BBS** direction is broken. When the user presses a key during
Kermit CONNECT, the keystroke never reaches the BBS. The E2E test
(`test_retro_bbs_kermit_e2e.py`) xfails on line 61:

```python
assert session.prepared.artifacts.aux_from_guest.exists()
```

The `aux-from-guest.bin` transcript file is never created because zero bytes
flow from guest to BBS.

## Root Cause

z80pack's `auxd_out` function (port 5 OUT handler in `simio.c` at commit
`91fd28eb`) silently drops three byte values before writing to the auxout FIFO:

```c
static void auxd_out(BYTE data)
{
    if ((data == 0) || (data == 0x1a))   // drops NUL and CP/M EOF
        return;
    if (data != '\r')                     // drops CR (0x0D)
        if (write(auxout, (char *) &data, 1) != 1)
            LOGE(TAG, "can't write to auxout pipe");
}
```

When a user presses Enter in Kermit CONNECT mode:
1. Console delivers CR (0x0D) to Kermit
2. Kermit calls OUTMDM with E=0x0D
3. Patched OUTMDM does `LD A,E; OUT (5),A` → calls `auxd_out(0x0D)`
4. `auxd_out` sees `data == '\r'` → silently drops it
5. Nothing reaches the auxout FIFO → bridge sees zero bytes

This means **any byte the guest sends that is NUL, CR, or 0x1A will be
silently dropped by the emulator**. For a terminal session, CR is the most
critical loss since it's the primary "confirm" key.

## Approach Options

### Option A: OUTMDM Patch — CR→LF Translation (Simplest)

Patch the OUTMDM routine in the Kermit overlay to translate CR (0x0D) to LF
(0x0A) before writing to port 5. z80pack passes LF through to the FIFO. The
host-side bridge or BBS can handle LF as a line ending.

New OUTMDM Z80 assembly (fits in the existing 12-byte slot at 0x72F9):

```asm
outmdm:
    ld a, e         ; 7B        — character in E
    cp 0dh          ; FE 0D     — is it CR?
    jr nz, .send    ; 20 02     — no, send as-is
    ld a, 0ah       ; 3E 0A     — yes, translate to LF
.send:
    out (5), a      ; D3 05     — write to AUX port
    ret             ; C9
                    ; 00 00 00 00 00  — NOP pad
```

Total: 10 bytes + 2 pad = 12 bytes. Fits exactly.

**Pros**: Minimal change, no host-side modifications needed.
**Cons**: Lossy — real CR bytes become LF. May need the bridge to translate
LF back to CR if the BBS expects CR or CRLF.

### Option B: Bridge-Side Workaround — Inject via Alternative Path

Instead of relying on z80pack's auxout FIFO for the guest→BBS direction,
have the bridge intercept console keystrokes (from the PTY) while Kermit is
in CONNECT mode and forward them directly to the BBS telnet socket.

**Pros**: Bypasses z80pack's auxd_out filtering entirely.
**Cons**: Complex, breaks the clean separation between console and serial
channels, requires the bridge to know when CONNECT mode starts/stops.

### Option C: Custom z80pack Build — Remove CR Stripping

Build z80pack from source with the CR stripping removed from `auxd_out`.
The Dockerfile.test already builds z80pack from source at a pinned commit.
A small sed patch or a maintained fork could remove the `if (data != '\r')`
check.

**Pros**: Cleanest fix, preserves full byte fidelity.
**Cons**: Diverges from upstream z80pack, adds maintenance burden for a
single-line change.

## Recommended Approach

Start with **Option A** (CR→LF translation in OUTMDM). It's the smallest
change, stays within the existing overlay patcher, and matches the pattern
already established for INPMDM. If the BBS needs CR specifically, add a
LF→CR translation in the bridge's `_pump_guest_to_bbs` method.

If Option A proves insufficient (e.g., the BBS requires literal CR, or other
byte values cause problems), escalate to **Option C** since the build
infrastructure already exists.

## Implementation Steps

### Step 1: Update OUTMDM Patch

Edit `emulation/assets/patch_kermit_z80pack.py`:
- Replace `_OUTMDM_CODE` with the CR→LF translating version
- Update `OUTMDM_ORIGINAL` verification bytes remain unchanged (they match
  the pre-patch CPVGEN overlay, not our current patch)

Note: `patch_kermit_for_z80pack()` always patches from the ORIGINAL merged
binary (before any patches), so the verification bytes do NOT need updating.

### Step 2: Verify Bridge Receives Bytes

Run the connect probe test and check:
- `aux_from_guest_bytes` > 0 in the diagnostics JSON
- `guest_to_bbs` diagnostics show the translated LF byte

```bash
docker build -f Dockerfile.test . -t retro-bbs:test-runtime
docker run --rm -v "$PWD/.tmp:/artifacts" retro-bbs:test-runtime \
  tests/tier3_emulation/diagnostics_aux_connect/test_connect_probe.py \
  -q --basetemp=/artifacts/pytest
```

Then inspect:
```bash
find .tmp/pytest -name aux-connect-diagnostics.json | xargs cat | python3 -m json.tool
```

### Step 3: Bridge LF→CR Translation (If Needed)

If the BBS server expects CR (or CRLF) line endings but receives LF, add a
translation in `emulation/bridges/aux.py` in `_pump_guest_to_bbs()`:

```python
payload = payload.replace(b'\n', b'\r\n')  # or b'\r' depending on BBS
```

Test this by checking whether the BBS advances past the welcome screen when
the guest sends Enter.

### Step 4: Update E2E Test

If the round-trip works:
1. Verify `aux-from-guest.bin` is created and contains bytes
2. Verify the BBS responds (e.g., advances past the welcome screen)
3. Update the xfail reason in `test_retro_bbs_kermit_e2e.py` to reflect the
   new state, OR remove xfail entirely if the full path passes

If removing xfail: also update the xfail reason in
`docs/emulation-lab-retro-bbs.md`.

### Step 5: Run Full Gate Suite

```bash
docker run --rm -v "$PWD/.tmp:/artifacts" retro-bbs:test-runtime \
  tests/tier3_emulation/ -v --basetemp=/artifacts/pytest
```

All tests must pass (3 passed + 0-1 xfailed acceptable).

### Step 6: Stop Conditions

**If all gates pass**: Update docs, commit, list remaining work.

**If blocked**: Stop with the exact blocker. Likely blockers:
- BBS doesn't accept LF as Enter → try bridge-side LF→CR translation
- Other bytes besides CR are needed but also stripped → escalate to Option C
- Bridge `_pump_guest_to_bbs` never receives data → debug FIFO open order

## Critical Files

| File | Role |
|------|------|
| `emulation/assets/patch_kermit_z80pack.py` | Overlay patcher (edit OUTMDM here) |
| `emulation/images/cpm.py` | Build pipeline (no changes expected) |
| `emulation/bridges/aux.py` | Host-side bridge (LF→CR translation if needed) |
| `tests/tier3_emulation/test_retro_bbs_kermit_e2e.py` | E2E test (update xfail) |
| `tests/tier3_emulation/diagnostics_aux_connect/test_connect_probe.py` | Diagnostics |
| `docs/emulation-lab-retro-bbs.md` | Documentation |

## z80pack auxd_out Reference

From `simio.c` at pinned commit `91fd28eb`:

```c
static void auxd_out(BYTE data)
{
#ifdef PIPES
    if ((data == 0) || (data == 0x1a))
        return;
    if (data != '\r')
        if (write(auxout, (char *) &data, 1) != 1)
            LOGE(TAG, "can't write to auxout pipe");
#else
    // file-based fallback (not used in our config)
#endif
}
```

Dropped bytes: `0x00` (NUL), `0x0D` (CR), `0x1A` (CP/M EOF).
Everything else passes through to the auxout named pipe at
`/tmp/.z80pack/cpmsim.auxout`.

## What This Task Will NOT Do

- Modify the BBS→guest direction (already working)
- Change the INPMDM patch (already working)
- Modify z80pack source (unless escalating to Option C)
- Expand Tier 3 test coverage beyond the existing tests
- Touch `subprojects/emulation-lab/` (docs-only there)
