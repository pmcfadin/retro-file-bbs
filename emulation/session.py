from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess

from emulation.artifacts import ArtifactLayout


@dataclass(frozen=True)
class PreparedGuest:
    workdir: Path
    run_dir: Path
    boot_disk: Path
    work_disk: Path
    artifacts: ArtifactLayout
    command: tuple[str, ...]
    env: dict[str, str]
    metadata: dict[str, object]


@dataclass
class RunningGuest:
    prepared: PreparedGuest
    process: subprocess.Popen[bytes]
    console_master_fd: int
    control_channels: dict[str, Path]
    held_fds: list[int] | None = None
