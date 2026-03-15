from __future__ import annotations

import pytest

from tests.helpers.journey import goto_main_menu, open_download_menu
from tests.helpers.transfers import available_command


async def test_zmodem_offer_header_is_emitted(bbs_client) -> None:
    if available_command("sz", "lsz") is None:
        pytest.skip("No ZMODEM sender is installed")

    await goto_main_menu(bbs_client)
    await open_download_menu(bbs_client, "C", 4, "ZMBIN.BIN")

    bbs_client.clear_screen()
    await bbs_client.send_text("Z")
    payload = await bbs_client.read_until_quiet(capture_screen=False, timeout=3.0)

    assert b"rz\r" in payload or b"**\x18B0" in payload
