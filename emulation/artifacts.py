from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


@dataclass(frozen=True)
class ArtifactLayout:
    root: Path
    metadata_json: Path
    command_txt: Path
    console_transcript: Path
    aux_from_guest: Path
    aux_to_guest: Path
    exports_dir: Path


def create_artifact_layout(
    *,
    base_dir: Path | None = None,
    prefix: str = "emulation",
) -> ArtifactLayout:
    parent = base_dir
    if parent is not None:
        parent.mkdir(parents=True, exist_ok=True)
        root = parent / f"{prefix}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"
        root.mkdir(parents=True, exist_ok=False)
    else:
        root = Path(tempfile.mkdtemp(prefix=f"{prefix}-"))

    exports_dir = root / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)
    return ArtifactLayout(
        root=root,
        metadata_json=root / "metadata.json",
        command_txt=root / "command.txt",
        console_transcript=root / "console.log",
        aux_from_guest=root / "aux-from-guest.bin",
        aux_to_guest=root / "aux-to-guest.bin",
        exports_dir=exports_dir,
    )


def append_bytes(path: Path, payload: bytes) -> None:
    if not payload:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(payload)


def write_command(path: Path, command: tuple[str, ...]) -> None:
    path.write_text(" ".join(command) + os.linesep, encoding="utf-8")


def write_metadata(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + os.linesep, encoding="utf-8")


def layout_metadata(layout: ArtifactLayout) -> dict[str, str]:
    data = asdict(layout)
    return {key: str(value) for key, value in data.items()}
