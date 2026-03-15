# Emulation Lab Design

This repository now has a dedicated sub-project for emulator-driven validation:
[subprojects/emulation-lab](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/README.md).

The recommended approach is an adapter-based lab with one proving path first:
`z80pack + CP/M 2.2 + Kermit + image staging + AUX bridge`. That is the
smallest design that solves the current `retro_bbs` Tier 3 problem without
locking the repo into a one-off CP/M harness.

The detailed materials live here:

- [README](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/README.md)
- [SPEC](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/SPEC.md)
- [RESEARCH](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/RESEARCH.md)
- [ROADMAP](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/ROADMAP.md)
- [retro_bbs profile](/Users/patrickmcfadin/local_projects/retro_bbs/subprojects/emulation-lab/profiles/retro_bbs.md)
- [implementation plan](./2026-03-14-emulation-lab-implementation-plan.md)
