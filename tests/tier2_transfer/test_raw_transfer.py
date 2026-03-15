from __future__ import annotations

from tests.helpers.journey import goto_main_menu, open_download_menu


async def test_raw_transfer_preserves_binary_bytes(bbs_client, bbs_server) -> None:
    await goto_main_menu(bbs_client)
    await open_download_menu(bbs_client, "C", 2, "RAWBIN.BIN")

    expected = bbs_server["files"]["raw"].read_bytes()

    bbs_client.clear_screen()
    await bbs_client.send_text("R")
    payload = await bbs_client.read_exactly(len(expected), timeout=20.0)

    assert payload == expected

    screen = await bbs_client.read_until_text("File Detail")
    assert "RAWBIN.BIN" in screen
