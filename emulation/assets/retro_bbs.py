from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AssetFile:
    filename: str
    source_url: str
    sha256: str
    provenance: str
    purpose: str


@dataclass(frozen=True)
class DiskFormat:
    cpmtools_name: str
    local_diskdefs_name: str
    seclen: int
    tracks: int
    sectrk: int
    blocksize: int
    maxdir: int
    skew: int
    boottrk: int
    os_version: str
    image_size_bytes: int
    provenance: str

    @property
    def local_diskdefs_path(self) -> Path:
        return Path(__file__).with_name("retro_bbs.diskdefs")


@dataclass(frozen=True)
class KermitBuildPlan:
    output_filename: str
    main_hex: AssetFile
    overlay_hex: AssetFile
    merge_tool: str
    merge_reference: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class AssetPlan:
    immutable_boot_disk: AssetFile
    mutable_work_disk_seed: AssetFile
    disk_format: DiskFormat
    kermit_build: KermitBuildPlan
    staging_steps: tuple[str, ...]
    provenance_status: str
    blockers: tuple[str, ...]
    risks: tuple[str, ...]


Z80PACK_COMMIT = "91fd28eb04e675c2127df88ed3f40675e15282e2"
Z80PACK_BASE_URL = (
    f"https://raw.githubusercontent.com/udo-munk/z80pack/{Z80PACK_COMMIT}/"
    "cpmsim/disks/library"
)

Z80PACK_CPM22_BOOT_DISK = AssetFile(
    filename="cpm22-1.dsk",
    source_url=f"{Z80PACK_BASE_URL}/cpm22-1.dsk",
    sha256="86ac7cb1bdd6bac05fe6299b50f94cb26a047022ce00135fbecf7bbc5d3303d2",
    provenance=(
        "z80pack upstream cpmsim/disks/library/cpm22-1.dsk at commit "
        f"{Z80PACK_COMMIT}; cpmsim/cpm22 mounts it as drive A."
    ),
    purpose="Immutable CP/M 2.2 boot disk for the retro_bbs z80pack profile.",
)

Z80PACK_CPM22_WORK_DISK = AssetFile(
    filename="cpm22-2.dsk",
    source_url=f"{Z80PACK_BASE_URL}/cpm22-2.dsk",
    sha256="30d3f145e86179801a72963f7ddd59ef83a1c045d3d19901d0a4a697b26a8a7a",
    provenance=(
        "z80pack upstream cpmsim/disks/library/cpm22-2.dsk at commit "
        f"{Z80PACK_COMMIT}; cpmsim/cpm22 mounts it as drive B."
    ),
    purpose=(
        "Seed disk for per-run mutable staging. Copy this to the test workdir "
        "before importing Kermit or exported guest files."
    ),
)

RETRO_BBS_DISK_FORMAT = DiskFormat(
    cpmtools_name="ibm-3740",
    local_diskdefs_name="retro-bbs-z80pack-cpm22",
    seclen=128,
    tracks=77,
    sectrk=26,
    blocksize=1024,
    maxdir=64,
    skew=6,
    boottrk=2,
    os_version="2.2",
    image_size_bytes=256_256,
    provenance=(
        "Matches cpmtools' ibm-3740 entry and z80pack cpmsim CP/M 2.2 BIOS "
        "disk parameter block (26x128 sectors, 77 tracks, 2 boot tracks)."
    ),
)

KERMIT_MAIN_HEX = AssetFile(
    filename="cpsker.hex",
    source_url="https://www.columbia.edu/kermit/ftp/cpm80/cpsker.hex",
    sha256="683ceefef5a08f3a2aeaa2ca0ee74c9bdea25dd16a4fbc02fc094ccfd041bcd0",
    provenance=(
        "Official Columbia University CP/M Kermit distribution, system-"
        "independent module for Kermit-80 4.11."
    ),
    purpose="System-independent Kermit-80 image used as the base for KERM411.COM.",
)

KERMIT_GENERIC_OVERLAY_HEX = AssetFile(
    filename="cpvgen.hex",
    source_url="https://www.columbia.edu/kermit/ftp/cpm80/cpvgen.hex",
    sha256="7c0772023fb0bf84ea418f5bd55cb6d45aba0df41d7ebebd85ae237763b2f0cd",
    provenance=(
        "Official Columbia University CP/M Kermit distribution, Generic CP/M "
        "2.2 overlay with IOBYTE support."
    ),
    purpose="Generic CP/M 2.2 overlay to merge with CPSKER.HEX for z80pack.",
)

KERMIT_BUILD_PLAN = KermitBuildPlan(
    output_filename="KERM411.COM",
    main_hex=KERMIT_MAIN_HEX,
    overlay_hex=KERMIT_GENERIC_OVERLAY_HEX,
    merge_tool="python3 emulation/assets/build_kermit.py",
    merge_reference=(
        "CP/M Kermit manual: merge CPSKER + CPVGEN with MLOAD to produce "
        "KERM411.COM. The local helper mirrors that MLOAD overlay flow."
    ),
    notes=(
        "Use the Generic CP/M 2.2 overlay (CPVGEN), not a hardware-specific build.",
        "Rename the merged output to KERMIT.COM when staging into the guest disk.",
        "Keep the boot disk immutable; stage KERMIT.COM onto the mutable B: disk.",
    ),
)

RETRO_BBS_ASSET_PLAN = AssetPlan(
    immutable_boot_disk=Z80PACK_CPM22_BOOT_DISK,
    mutable_work_disk_seed=Z80PACK_CPM22_WORK_DISK,
    disk_format=RETRO_BBS_DISK_FORMAT,
    kermit_build=KERMIT_BUILD_PLAN,
    staging_steps=(
        "Copy cpm22-2.dsk into the per-run workdir before modifying it.",
        (
            "Build KERM411.COM from official CPSKER.HEX + CPVGEN.HEX with "
            "`python3 emulation/assets/build_kermit.py --cpsker <path> "
            "--overlay <path> --out <path>/KERM411.COM`."
        ),
        (
            "Import the built file onto the mutable work disk with cpmtools using "
            "`-f ibm-3740` (or the local retro-bbs-z80pack-cpm22 alias): "
            "`cpmcp -f ibm-3740 <work-disk> <host-path>/KERM411.COM 0:KERMIT.COM`."
        ),
        "Verify the staged guest file with `cpmls -f ibm-3740 <work-disk>`.",
        (
            "Boot z80pack with cpm22-1.dsk as immutable drive A and the staged copy "
            "of cpm22-2.dsk as mutable drive B."
        ),
    ),
    provenance_status="locked",
    blockers=(),
    risks=(
        (
            "The official Columbia Kermit URLs intermittently serve a Cloudflare "
            "challenge to automated clients. Provenance is locked, but runtime code "
            "should avoid a live fetch during tests."
        ),
    ),
)
