from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest

from emulation.bridges.aux import AuxTelnetBridge
from tests.helpers.emulation import start_retro_bbs_session

WELCOME_TEXT = "Press [ENTER] to continue..."
WELCOME_BYTES = WELCOME_TEXT.encode("ascii")


async def _read_until(console, expected: str, timeout: float) -> str:
    output = await asyncio.to_thread(console.read_until, expected, timeout)
    return output.decode("utf-8", errors="replace")


async def _write(console, data: str) -> None:
    await asyncio.to_thread(console.write, data)


def _read_bytes(path: Path) -> bytes:
    if not path.exists():
        return b""
    return path.read_bytes()


def _write_report(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + os.linesep, encoding="utf-8")


def _failure_mode(
    *,
    aux_to_guest: bytes,
    console_contains_welcome: bool,
) -> str:
    if WELCOME_BYTES in aux_to_guest and console_contains_welcome:
        return "welcome-visible"
    if WELCOME_BYTES in aux_to_guest:
        return "bbs-bytes-reach-aux-to-guest-but-not-console"
    if aux_to_guest:
        return "bbs-bytes-reach-aux-to-guest-without-welcome-marker"
    return "no-bbs-bytes-reached-aux-to-guest"


@pytest.mark.tier3_emulation
async def test_connect_probe_captures_aux_gate(bbs_server, tmp_path) -> None:
    with start_retro_bbs_session(tmp_path) as session:
        artifacts = session.prepared.artifacts
        console = session.console
        report_path = artifacts.root / "aux-connect-diagnostics.json"

        await _read_until(console, "A>", timeout=10.0)

        await _write(console, "b:\r")
        await _read_until(console, "B>", timeout=5.0)

        await _write(console, "kermit\r")
        banner = await _read_until(console, "Generic CP/M-80", timeout=10.0)
        assert "Generic CP/M-80" in banner

        bridge = AuxTelnetBridge(
            host=str(bbs_server["host"]),
            port=int(bbs_server["port"]),
            auxin=session.running.control_channels["auxin"],
            auxout=session.running.control_channels["auxout"],
            to_guest_transcript=artifacts.aux_to_guest,
            from_guest_transcript=artifacts.aux_from_guest,
        )

        connect_error: str | None = None
        pre_connect_snapshot: dict[str, object] | None = None
        bridge_started = False

        try:
            await bridge.start()
            bridge_started = True
            pre_connect_snapshot = bridge.diagnostics_snapshot()

            await _write(console, "connect\r")
            await asyncio.sleep(1.0)

            try:
                await _read_until(console, WELCOME_TEXT, timeout=4.0)
            except TimeoutError as exc:
                connect_error = str(exc)
                await asyncio.sleep(0.5)
        finally:
            if bridge_started:
                await bridge.stop()

        aux_to_guest = _read_bytes(artifacts.aux_to_guest)
        aux_from_guest = _read_bytes(artifacts.aux_from_guest)
        console_tail = console.tail_text(2048)
        console_contains_welcome = WELCOME_TEXT in console_tail
        post_connect_snapshot = bridge.diagnostics_snapshot()

        report = {
            "artifact_root": str(artifacts.root),
            "console_transcript": str(artifacts.console_transcript),
            "aux_to_guest": str(artifacts.aux_to_guest),
            "aux_from_guest": str(artifacts.aux_from_guest),
            "pre_connect_bridge": pre_connect_snapshot,
            "post_connect_bridge": post_connect_snapshot,
            "aux_to_guest_bytes": len(aux_to_guest),
            "aux_from_guest_bytes": len(aux_from_guest),
            "aux_to_guest_contains_welcome": WELCOME_BYTES in aux_to_guest,
            "console_contains_welcome": console_contains_welcome,
            "console_tail": console_tail,
            "connect_error": connect_error,
            "failure_mode": _failure_mode(
                aux_to_guest=aux_to_guest,
                console_contains_welcome=console_contains_welcome,
            ),
        }
        _write_report(report_path, report)

        assert report_path.exists()
