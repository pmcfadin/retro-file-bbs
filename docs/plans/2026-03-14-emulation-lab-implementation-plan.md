# Emulation Lab Implementation Plan

## Decision

Build the emulation stack in two steps, not one.

Phase 1 should prove one real path end to end:

`z80pack + CP/M 2.2 + cpmtools staging + Kermit + AUX bridge + retro_bbs journey`

Phase 2 should extract that working path into a cleaner reusable lab surface.

This keeps the first delivery small enough to finish while still aligning with
the adapter-based design in
[docs/plans/2026-03-14-emulation-lab-design.md](./2026-03-14-emulation-lab-design.md)
and
[subprojects/emulation-lab/SPEC.md](../../subprojects/emulation-lab/SPEC.md).

## Scope Guardrails

- Do not add QEMU, DOSBox-X, RunCPM, or CP/M 3.0 in Phase 1.
- Do not build a generic capability registry before the first `retro_bbs`
  profile is green.
- Do not split the test topology into multiple containers unless the current
  pytest-driven path proves insufficient.
- Keep `subprojects/emulation-lab/` as design and research documentation.
  Runtime code should live in the main repo codebase.

## Research Team

| Track | Owner | Scope | Deliverable |
|---|---|---|---|
| Architecture and phase control | Researcher A | Confirm package boundaries, what belongs in Phase 1, and what must wait for Phase 2 | Final module layout, phase gates, deferred list |
| CP/M asset provenance | Researcher B | Select the canonical CP/M 2.2 base image, disk geometry, `diskdefs`, and Kermit build | Asset manifest with provenance, checksums, and staging instructions |
| z80pack control surface | Researcher C | Verify `cpmsim` launch behavior, console handling, AUX named pipes, timeout model, and cleanup needs | Adapter notes, bridge notes, teardown rules |
| Test and artifact integration | Researcher D | Reuse existing `pytest`, `bbs_server`, and transfer helpers without overbuilding a second framework | Phase 1 fixture plan, artifact layout, local run flow |

## Recommended Repository Shape

Phase 1 should add a narrow runtime package and keep the scenario logic in the
tests:

```text
emulation/
  __init__.py
  artifacts.py
  session.py
  adapters/
    __init__.py
    base.py
    z80pack.py
  images/
    __init__.py
    cpm.py
  profiles/
    __init__.py
    retro_bbs.py
tests/
  helpers/
    emulation.py
  tier3_emulation/
    test_boot_smoke.py
    test_retro_bbs_kermit_e2e.py
```

Boundary rules:

- adapter code owns emulator lifecycle, host channels, transcripts, and teardown
- profile code owns guest metadata, staged assets, prompts, and expected files
- tests own the user journey, assertions, and failure expectations

## Implementation Plan

## Phase 0: Research Lock

Objective:
- remove the unresolved external dependencies before writing adapter code

Work:
- choose one canonical CP/M 2.2 image and document provenance
- record the exact `cpmtools` disk definition needed for that image
- choose one Kermit-80 build that works with the selected image
- define where third-party assets live and how checksums are verified
- decide whether any z80pack-native helper tools are required beyond
  `cpmtools`

Exit criteria:
- one written asset manifest exists
- every external artifact has provenance and checksum
- the team can stage Kermit into the chosen image without manual guesswork

## Phase 1: Harness Foundation

Objective:
- establish the host-side execution surface for emulator-driven tests

Work:
- extend [Dockerfile.test](../../Dockerfile.test) with build dependencies for
  `z80pack` and `cpmtools`
- add the `emulation/` package skeleton
- implement per-run work directories and artifact retention helpers
- define a minimal adapter base contract for `prepare`, `start`, `stop`,
  `console`, `control_channels`, and artifact import or export
- add a pytest helper that can start the BBS and one emulator session in the
  same test process

Exit criteria:
- tests can create an isolated emulator work directory
- artifacts are written to a predictable location
- adapter lifecycle teardown is reliable on success, failure, and timeout

## Phase 2: z80pack Boot Path

Objective:
- prove that the repo can boot CP/M under `z80pack` and drive the console

Work:
- implement `Z80packAdapter`
- launch `cpmsim` headlessly from pytest
- capture raw console transcript
- detect the `A>` prompt with stable timeout handling
- add a smoke test for `boot -> A> -> KERMIT -> EXIT`

Exit criteria:
- one local smoke test passes repeatedly
- failed runs retain command line, console transcript, and workdir contents

## Phase 3: Image Staging and AUX Bridge

Objective:
- make file staging and BBS connectivity deterministic

Work:
- implement CP/M image import and export helpers with `cpmtools`
- stage Kermit and any helper binaries into the guest image before boot
- bridge `/tmp/.z80pack/cpmsim.auxin` and `/tmp/.z80pack/cpmsim.auxout` to the
  running BBS
- capture raw AUX transcript
- add hard timeout and cleanup rules for hung bridge or guest sessions

Exit criteria:
- staged files are visible inside the guest without manual intervention
- the AUX bridge can connect to the BBS and shut down cleanly
- image artifacts and transcripts are preserved on failure

## Phase 4: `retro_bbs` End-to-End Proof

Objective:
- prove the real user journey inside the guest

Work:
- automate `boot -> KERMIT -> SET PORT AUX -> CONNECT`
- navigate the BBS menus from inside the guest
- trigger a Kermit download from the BBS
- receive the file inside CP/M
- return to `A>` and execute the downloaded program
- assert expected output and absence of CP/M runtime errors

Exit criteria:
- one full `retro_bbs` emulator-driven test passes locally
- reruns require no manual cleanup
- failures preserve enough artifacts to debug guest, bridge, and host behavior

## Phase 5: Core Lab Extraction

Objective:
- convert the proven path into a reusable lab foundation

Work:
- separate the `retro_bbs` specifics from the generic runner surface
- add profile loading and capability declaration
- prepare for a second backend without rewriting Phase 1 code

Exit criteria:
- the `retro_bbs` profile still passes after extraction
- a second profile can be added without structural rewrite

## Deferred Until After Phase 1

- QEMU adapter
- DOSBox-X adapter
- RunCPM support for Tier 3 workflows
- CP/M 3.0 matrix coverage
- CI matrix expansion
- snapshot support
- generalized capability scheduling

## Dependency-Ordered Task List

### Task 1: Lock external assets

- document the canonical CP/M 2.2 image
- record provenance, license status, and checksum
- record the matching `diskdefs` entry and image geometry
- acquire one validated Kermit-80 binary and checksum it

Depends on:
- nothing

### Task 2: Define asset layout

- choose repo paths for base images, staged binaries, manifests, and generated
  work images
- write one manifest file that maps profile name to image and guest assets

Depends on:
- Task 1

### Task 3: Extend the test runtime

- update [Dockerfile.test](../../Dockerfile.test) to build or install
  `z80pack` and install `cpmtools`
- confirm pytest can still run the current Tier 1 and Tier 2 suites

Depends on:
- Task 2

### Task 4: Create the emulation package skeleton

- add `emulation/adapters/base.py`
- add `emulation/artifacts.py`
- add `emulation/session.py`
- add `emulation/images/cpm.py`
- add `emulation/profiles/retro_bbs.py`

Depends on:
- Task 3

### Task 5: Implement artifact and workdir management

- create per-run directories
- save emulator command line and environment metadata
- preserve logs and extracted outputs on failure

Depends on:
- Task 4

### Task 6: Implement the `z80pack` adapter

- launch and stop `cpmsim`
- expose console access
- expose AUX control channels
- enforce hard timeouts and teardown

Depends on:
- Task 5

### Task 7: Implement CP/M image staging

- import Kermit and helper files into the guest image
- export selected files after the run
- validate image contents before boot

Depends on:
- Task 6

### Task 8: Implement the AUX bridge

- connect z80pack AUX named pipes to the running BBS session
- capture raw bridge transcripts
- handle disconnect, retry, and teardown paths

Depends on:
- Task 6

### Task 9: Add emulator pytest helpers

- create a shared fixture or helper for starting the BBS and emulator together
- keep reuse of [tests/conftest.py](../../tests/conftest.py) as the default
  path

Depends on:
- Tasks 6, 7, and 8

### Task 10: Add the boot smoke test

- boot CP/M
- detect `A>`
- launch Kermit
- exit back to `A>`

Depends on:
- Task 9

### Task 11: Add the full `retro_bbs` journey test

- connect through AUX
- navigate the BBS
- receive a file with Kermit
- run the downloaded file
- assert expected output and no CP/M errors

Depends on:
- Task 10

### Task 12: Document local operation

- describe required host tools
- describe how to run Tier 3 tests locally
- describe where artifacts land and how to inspect them

Depends on:
- Task 11

## Immediate Next Three Moves

1. Close the asset questions first. The canonical image and Kermit build are
   the highest-risk blockers.
2. Reuse the existing pytest and `bbs_server` flow before introducing a more
   complex compose-based topology.
3. Ship the `boot -> A> -> KERMIT -> EXIT` smoke test before attempting the
   full BBS journey.
