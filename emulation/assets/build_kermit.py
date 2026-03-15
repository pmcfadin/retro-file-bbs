#!/usr/bin/env python3
"""Merge official CP/M Kermit HEX sources into a COM image.

This mirrors the MLOAD flow documented by the CP/M Kermit manual:
system-independent `CPSKER.HEX` plus the chosen system overlay
(`CPVGEN.HEX` for the retro_bbs profile) become `KERM411.COM`.
"""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys


if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from emulation.assets.retro_bbs import KERMIT_GENERIC_OVERLAY_HEX, KERMIT_MAIN_HEX


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cpsker", type=Path, required=True)
    parser.add_argument("--overlay", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--skip-sha256-check", action="store_true")
    return parser.parse_args()


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_sha256(path: Path, expected: str) -> None:
    actual = sha256_file(path)
    if actual != expected:
        raise SystemExit(
            f"{path} sha256 mismatch: expected {expected}, got {actual}"
        )


def parse_intel_hex(path: Path) -> dict[int, int]:
    memory: dict[int, int] = {}
    upper = 0

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise SystemExit(f"{path} is not Intel HEX: {line[:40]!r}")

        count = int(line[1:3], 16)
        address = int(line[3:7], 16)
        record_type = int(line[7:9], 16)
        payload = bytes.fromhex(line[9 : 9 + count * 2])

        if record_type == 0:
            base = (upper << 16) + address
            for offset, value in enumerate(payload):
                memory[base + offset] = value
        elif record_type == 1:
            break
        elif record_type == 4:
            upper = int.from_bytes(payload, "big")

    return memory


def merge_hex_sources(cpsker: Path, overlay: Path) -> bytes:
    memory = parse_intel_hex(cpsker)
    memory.update(parse_intel_hex(overlay))

    if 0x100 not in memory:
        raise SystemExit("Merged image has no 0x0100 origin; refusing to build COM")

    end = max(memory) + 1
    return bytes(memory.get(address, 0) for address in range(0x100, end))


def main() -> int:
    args = parse_args()

    if not args.skip_sha256_check:
        verify_sha256(args.cpsker, KERMIT_MAIN_HEX.sha256)
        verify_sha256(args.overlay, KERMIT_GENERIC_OVERLAY_HEX.sha256)

    payload = merge_hex_sources(args.cpsker, args.overlay)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(payload)

    print(f"wrote {args.out}")
    print(f"sha256 {sha256_file(args.out)}")
    print(f"bytes {len(payload)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
