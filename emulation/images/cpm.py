from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib import request

from emulation.assets import KERMIT_BUILD_PLAN, RETRO_BBS_ASSET_PLAN, AssetFile
from emulation.assets.build_kermit import merge_hex_sources, verify_sha256
from emulation.assets.patch_kermit_z80pack import patch_kermit_for_z80pack


@dataclass(frozen=True)
class StagedDiskSet:
    boot_disk: Path
    work_disk: Path
    kermit_com: Path


def _cache_root() -> Path:
    root = Path(tempfile.gettempdir()) / "retro_bbs_emulation_cache"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _candidate_urls(asset: AssetFile) -> tuple[str, ...]:
    urls = [asset.source_url]
    if asset.filename.endswith(".hex"):
        urls.append(
            f"https://ftp.zx.net.nz/pub/mirror/kermit.columbia.edu/pub/kermit/a/{asset.filename}"
        )
    return tuple(dict.fromkeys(urls))


def _download_asset(asset: AssetFile, target: Path) -> Path:
    last_error: Exception | None = None
    for url in _candidate_urls(asset):
        try:
            req = request.Request(url, headers={"User-Agent": "retro-bbs-emulation/1.0"})
            with request.urlopen(req, timeout=30) as response, target.open("wb") as handle:
                shutil.copyfileobj(response, handle)
            if _sha256_file(target) != asset.sha256:
                raise RuntimeError(f"{asset.filename} sha256 mismatch after downloading {url}")
            return target
        except Exception as exc:  # pragma: no cover - exercised in integration
            last_error = exc
    raise RuntimeError(f"Unable to download {asset.filename}: {last_error}")


def _ensure_asset(asset: AssetFile) -> Path:
    cached = _cache_root() / asset.filename
    if cached.exists():
        if _sha256_file(cached) == asset.sha256:
            return cached
        cached.unlink()
    return _download_asset(asset, cached)


def _build_kermit(output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    cpsker = _ensure_asset(KERMIT_BUILD_PLAN.main_hex)
    overlay = _ensure_asset(KERMIT_BUILD_PLAN.overlay_hex)
    verify_sha256(cpsker, KERMIT_BUILD_PLAN.main_hex.sha256)
    verify_sha256(overlay, KERMIT_BUILD_PLAN.overlay_hex.sha256)

    kermit_path = output_dir / KERMIT_BUILD_PLAN.output_filename
    merged = merge_hex_sources(cpsker, overlay)
    patched = patch_kermit_for_z80pack(merged)
    kermit_path.write_bytes(patched)
    return kermit_path


def stage_retro_bbs_disks(work_root: Path) -> StagedDiskSet:
    work_root.mkdir(parents=True, exist_ok=True)
    boot_seed = _ensure_asset(RETRO_BBS_ASSET_PLAN.immutable_boot_disk)
    work_seed = _ensure_asset(RETRO_BBS_ASSET_PLAN.mutable_work_disk_seed)
    boot_disk = work_root / RETRO_BBS_ASSET_PLAN.immutable_boot_disk.filename
    work_disk = work_root / RETRO_BBS_ASSET_PLAN.mutable_work_disk_seed.filename
    shutil.copy2(boot_seed, boot_disk)
    shutil.copy2(work_seed, work_disk)

    kermit_path = _build_kermit(work_root / "host")
    subprocess.run(
        [
            "cpmcp",
            "-f",
            RETRO_BBS_ASSET_PLAN.disk_format.cpmtools_name,
            str(work_disk),
            str(kermit_path),
            "0:KERMIT.COM",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        [
            "cpmls",
            "-f",
            RETRO_BBS_ASSET_PLAN.disk_format.cpmtools_name,
            str(work_disk),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return StagedDiskSet(boot_disk=boot_disk, work_disk=work_disk, kermit_com=kermit_path)
