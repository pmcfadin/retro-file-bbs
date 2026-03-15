from __future__ import annotations

import asyncio

import pytest

from emulation.bridges.aux import AuxTelnetBridge
from tests.helpers.emulation import start_retro_bbs_session


async def _read_until(console, expected: str, timeout: float) -> str:
    output = await asyncio.to_thread(console.read_until, expected, timeout)
    return output.decode("utf-8", errors="replace")


async def _write(console, data: str) -> None:
    await asyncio.to_thread(console.write, data)


async def test_retro_bbs_kermit_e2e(bbs_server, tmp_path) -> None:
    with start_retro_bbs_session(tmp_path) as session:
        console = session.console
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
            to_guest_transcript=session.prepared.artifacts.aux_to_guest,
            from_guest_transcript=session.prepared.artifacts.aux_from_guest,
        )

        await bridge.start()
        try:
            # Enter Kermit CONNECT mode and wait for BBS welcome screen
            await _write(console, "connect\r")
            await _read_until(console, "Press [ENTER] to continue...", timeout=8.0)

            # Send Enter — this is the guest→BBS round trip under test.
            # The keystroke travels: console → Kermit OUTMDM (CR→LF) →
            # z80pack port 5 → auxout FIFO → bridge (LF→CRLF) → BBS.
            await _write(console, "\r")

            # Wait for the BBS to respond with the Main Menu.
            # This proves the full round trip: the BBS received our Enter,
            # processed it, and sent back a new screen that traveled
            # BBS → bridge → auxin → z80pack → Kermit INPMDM → console.
            screen = await _read_until(console, "Main Menu", timeout=8.0)
        finally:
            await bridge.stop()

        assert "Main Menu" in screen
        assert session.prepared.artifacts.aux_to_guest.exists()
        assert session.prepared.artifacts.aux_from_guest.exists()
