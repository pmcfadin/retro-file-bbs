# Emulation Lab: retro_bbs Phase 0-1

This document covers the current local workflow for the scoped path:
`z80pack + CP/M 2.2 + cpmtools staging + Kermit + AUX bridge + retro_bbs tests`.

## Scope

Included in this slice:

- z80pack `cpmsim` as the only emulator runtime
- upstream z80pack CP/M 2.2 disk images as the canonical boot/work seeds
- `cpmtools` staging for `KERMIT.COM`
- host-side AUX bridge wiring to the existing pytest `bbs_server` fixture
- Tier 3 smoke coverage that boots CP/M and launches Kermit

Explicitly out of scope for this slice:

- QEMU
- DOSBox-X
- RunCPM Tier 3
- CP/M 3.0
- generic capability registry
- CI matrix expansion

## Local Run Instructions

Prefer a predictable pytest temp root so the per-run emulator artifacts survive
after the test exits.

### Docker Runtime

Build the test image:

```bash
docker build -f Dockerfile.test . -t retro-bbs:test-runtime
```

Create a host-side parent directory for pytest artifacts:

```bash
mkdir -p .tmp
```

Run the smoke test:

```bash
docker run --rm \
  -v "$PWD/.tmp:/artifacts" \
  retro-bbs:test-runtime \
  tests/tier3_emulation/test_boot_smoke.py -q --basetemp=/artifacts/pytest
```

Run the dedicated AUX diagnostics test:

```bash
docker run --rm \
  -v "$PWD/.tmp:/artifacts" \
  retro-bbs:test-runtime \
  tests/tier3_emulation/diagnostics_aux_connect/test_connect_probe.py \
  -q --basetemp=/artifacts/pytest
```

Run the minimal guest-side AUX reader proof:

```bash
docker run --rm \
  -v "$PWD/.tmp:/artifacts" \
  retro-bbs:test-runtime \
  tests/tier3_emulation/diagnostics_aux_connect/test_aux_echo_probe.py \
  -q --basetemp=/artifacts/pytest
```

Run the end-to-end journey test:

```bash
docker run --rm \
  -v "$PWD/.tmp:/artifacts" \
  retro-bbs:test-runtime \
  tests/tier3_emulation/test_retro_bbs_kermit_e2e.py \
  -q -rxX --basetemp=/artifacts/pytest
```

This journey test is intentionally still `xfail`. A successful run currently
means "the known blocker reproduced and the artifacts were captured," not that
the Kermit path passed.

### Host Runtime

If you run pytest directly on the host instead of through `Dockerfile.test`, the
current code expects:

- `cpmsim` to resolve either from `Z80PACK_HOME` or from `PATH`
- `cpmtools` installed so `cpmcp` and `cpmls` are available
- Python packages `pytest`, `pytest-asyncio`, `pexpect`, and `telnetlib3`

The Tier 3 tests start the local Python BBS fixture automatically unless
`BBS_HOST` is already set. Typical host commands are:

```bash
python -m pytest tests/tier3_emulation/test_boot_smoke.py \
  -q --basetemp=.tmp/pytest
```

```bash
python -m pytest tests/tier3_emulation/diagnostics_aux_connect/test_connect_probe.py \
  -q --basetemp=.tmp/pytest
```

```bash
python -m pytest tests/tier3_emulation/diagnostics_aux_connect/test_aux_echo_probe.py \
  -q --basetemp=.tmp/pytest
```

```bash
python -m pytest tests/tier3_emulation/test_retro_bbs_kermit_e2e.py \
  -q -rxX --basetemp=.tmp/pytest
```

## Artifact Layout

Each emulator run creates a per-run artifact directory under the supplied
`tmp_path`, so using `--basetemp` makes the results easy to find. Search for the
run roots with:

```bash
find .tmp/pytest -type d -name 'z80pack-*'
```

The layout is:

- `metadata.json`: run metadata, staged disk paths, and artifact paths
- `command.txt`: launched emulator command
- `console.log`: captured CP/M console transcript
- `aux-to-guest.bin`: bytes bridged from the BBS into z80pack AUX
- `aux-from-guest.bin`: bytes bridged from z80pack AUX to the BBS
- `exports/`: reserved for future guest-exported files

The z80pack adapter also stages additional working state under the same run
directory:

- `guest/`: copied boot and work disks plus the rebuilt `KERMIT.COM`
- `runner/`: the `cpmsim` symlink and the `disks/drivea.dsk` and `disks/driveb.dsk`
  links used for the actual launch

For the current blocker investigation, inspect the artifacts in this order:

1. `metadata.json` to confirm the selected z80pack home, staged disks, and
   rebuilt `KERMIT.COM` path.
2. `console.log` to confirm the guest booted to `A>`, switched to `B>`, launched
   Kermit, and then stalled after `CONNECT`.
3. `aux-to-guest.bin` to verify whether remote bytes reached the guest-side AUX
   path. The dedicated diagnostics test currently proves this file contains the
   BBS welcome data, including `Press [ENTER] to continue...`.
4. `aux-from-guest.bin` to confirm whether the guest emitted any AUX traffic
   back toward the BBS during the probe.

The diagnostics test also writes `aux-connect-diagnostics.json` beside the other
artifacts. It captures bridge snapshots before and after `CONNECT`, byte counts,
welcome-marker checks, and a summarized failure mode such as
`bbs-bytes-reach-aux-to-guest-but-not-console`.

The AUX echo probe is simpler: it stages a tiny CP/M `AUXECHO.COM` program onto
the mutable work disk, maps `RDR:` to `UR1:`, injects a short payload directly
into z80pack AUX, and proves the guest console can display that payload. It does
not involve Kermit or the BBS.

## z80pack-Specific Kermit Overlay Patch

The Generic CP/M 2.2 overlay (CPVGEN) uses BIOS CONSTAT/CONIN with IOBYTE
switching for serial I/O. z80pack's CP/M 2.2 BIOS always checks port 0
(console) in its CONSTAT routine regardless of the IOBYTE setting, so Kermit's
CONNECT polling loop never detected incoming AUX data.

The fix is `emulation/assets/patch_kermit_z80pack.py`, which patches two
routines in the merged KERM411.COM binary:

- **INPMDM** (at 0x7305): replaced with `IN A,(5)` — a non-blocking read from
  z80pack's AUX data port. Returns the byte if available, or A=0 if the port
  returns 0x1A (the "pipe empty" sentinel from simio.c's auxd_in).
- **OUTMDM** (at 0x72F9): replaced with `LD A,E; OUT (5),A` — direct write to
  z80pack's AUX data port.

Port assignments (from simio.c at pinned commit 91fd28eb):
- Port 5: AUX data (IN: non-blocking read via O_NONBLOCK FIFO, OUT: write)
- Port 4: AUX EOF flag (not useful for polling; returns 0 until a read fails)

The patch is applied automatically during `_build_kermit()` in
`emulation/images/cpm.py`. It verifies the original overlay bytes before
patching and raises `ValueError` if the binary doesn't match.

### Verified Gates

1. **Boot smoke**: CP/M boots, Kermit launches and shows "Generic CP/M-80" banner
2. **AUX echo probe**: guest-side BDOS reader still consumes AUX bytes correctly
3. **Kermit CONNECT**: BBS welcome including "Press [ENTER] to continue..." is now
   visible on the CP/M console through Kermit's CONNECT mode
4. **Connect probe diagnostics**: `failure_mode` is `welcome-visible`

### Remaining E2E xfail

The end-to-end test (`test_retro_bbs_kermit_e2e.py`) still xfails because:
- `aux-from-guest.bin` is never created: z80pack's `auxd_out` (port 5 OUT)
  silently drops CR (0x0D) characters, so the `\r` keypress sent during
  CONNECT never reaches the BBS via the bridge, and no transcript file is
  written.

This is a guest→BBS direction issue (CR stripping in simio.c). The BBS→guest
direction works fully. The xfail marker should stay until the full round-trip
path is verified.

## Prior Blocker (Resolved)

The previous blocker was inside the guest integration boundary between the
CP/M 2.2 BIOS serial path and Kermit's CONNECT behavior. Root cause: the
CPVGEN overlay's `inpmdm` called BIOS CONSTAT, which always checks port 0
(console status) — never port 4/5 (AUX). The z80pack-specific overlay patch
resolves this by bypassing BIOS entirely with direct I/O port instructions.
