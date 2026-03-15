from __future__ import annotations

from dataclasses import dataclass

from emulation.assets import RETRO_BBS_ASSET_PLAN


@dataclass(frozen=True)
class RetroBbsProfile:
    name: str = "retro_bbs"
    guest_family: str = "cpm"
    guest_os: str = "cpm22"
    adapter: str = "z80pack"
    disk_format: str = RETRO_BBS_ASSET_PLAN.disk_format.cpmtools_name
    staged_guest_files: tuple[str, ...] = ("KERMIT.COM",)
    required_capabilities: tuple[str, ...] = (
        "console-text",
        "serial-byte-stream",
        "disk-image-import",
        "disk-image-export",
        "headless-boot",
    )
