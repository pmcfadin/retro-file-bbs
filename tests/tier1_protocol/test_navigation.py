from __future__ import annotations

from tests.helpers.journey import goto_main_menu, open_category


async def test_welcome_screen_shows_stats(bbs_client) -> None:
    screen = await bbs_client.read_until_text("Press [ENTER] to continue...")
    assert "CP/M Software Depot" in screen
    assert "3 Categories" in screen
    assert "30 Files" in screen
    assert "Z/X/K/Raw Downloads" in screen


async def test_category_pagination_and_back_navigation(bbs_client) -> None:
    await goto_main_menu(bbs_client)

    screen = await open_category(bbs_client, "A", "ARC20.TXT")
    assert "ARC01.TXT" in screen
    assert "ARC20.TXT" in screen

    bbs_client.clear_screen()
    await bbs_client.send_text("N")
    screen = await bbs_client.read_until_text("ARC25.TXT")
    assert "ARC21.TXT" in screen
    assert "ARC25.TXT" in screen

    bbs_client.clear_screen()
    await bbs_client.send_text("P")
    await bbs_client.read_until_text("ARC20.TXT")

    bbs_client.clear_screen()
    await bbs_client.send_text("B")
    screen = await bbs_client.read_until_text("Transfer")
    assert "Archivers" in screen
    assert "Transfer" in screen


async def test_search_detail_and_download_menu(bbs_client) -> None:
    await goto_main_menu(bbs_client)

    bbs_client.clear_screen()
    await bbs_client.send_text("S")
    await bbs_client.read_until_text("Enter search keywords")
    await bbs_client.send_line("TERMUTIL")

    screen = await bbs_client.read_until_text("TERMUTIL.TXT")
    assert "TERMUTIL.TXT" in screen
    assert 'Search Results: "TERMUTIL"' in screen

    bbs_client.clear_screen()
    await bbs_client.send_line("1")
    screen = await bbs_client.read_until_text("TERMUTIL.TXT")
    assert "TERMUTIL.TXT" in screen
    assert "File Detail" in screen
    assert "Comm" in screen

    bbs_client.clear_screen()
    await bbs_client.send_text("D")
    screen = await bbs_client.read_until_text("Select transfer protocol:")
    assert "XMODEM" in screen
    assert "Kermit" in screen
    assert "ZMODEM" in screen
    assert "Raw" in screen


async def test_quit_from_main_menu_disconnects_cleanly(bbs_client) -> None:
    await goto_main_menu(bbs_client)
    bbs_client.clear_screen()
    await bbs_client.send_text("Q")
    screen = await bbs_client.read_until_text("Goodbye")
    assert "happy hacking" in screen
