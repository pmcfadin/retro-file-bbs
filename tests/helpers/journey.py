from __future__ import annotations

from tests.helpers.telnet_client import BbsClient


async def goto_main_menu(client: BbsClient) -> str:
    await client.read_until_text("Press [ENTER] to continue...")
    await client.send_line()
    return await client.read_until_text("Main Menu")


async def open_category(client: BbsClient, letter: str, expected: str) -> str:
    client.clear_screen()
    await client.send_text(letter)
    return await client.read_until_text(expected)


async def open_file_detail(client: BbsClient, number: int, filename: str) -> str:
    client.clear_screen()
    await client.send_line(str(number))
    screen = await client.read_until_text(filename)
    assert "File Detail" in screen
    assert filename in screen
    return screen


async def open_download_menu(
    client: BbsClient,
    category_letter: str,
    file_number: int,
    filename: str,
) -> str:
    await open_category(client, category_letter, filename)
    await open_file_detail(client, file_number, filename)
    client.clear_screen()
    await client.send_text("D")
    screen = await client.read_until_text("Select transfer protocol:")
    assert filename in screen
    return screen
