from __future__ import annotations

import pytest

from tests.helpers.file_integrity import sha256_file
from tests.helpers.journey import goto_main_menu, open_download_menu
from tests.helpers.protocols import receive_xmodem
from tests.helpers.transfers import available_command


async def test_xmodem_transfer_preserves_file_contents(
    bbs_client, bbs_server, tmp_path
) -> None:
    await goto_main_menu(bbs_client)
    await open_download_menu(bbs_client, "C", 3, "XMBIN.BIN")

    download_dir = tmp_path / "xmodem"
    download_dir.mkdir()
    target = download_dir / "XMBIN.BIN"

    if available_command("sx", "lsx") is None:
        pytest.skip("No XMODEM sender is installed")

    bbs_client.clear_screen()
    await bbs_client.send_text("X")
    target.write_bytes(
        await receive_xmodem(
            bbs_client,
            bbs_server["files"]["xmodem"].stat().st_size,
            timeout=20.0,
        )
    )

    assert target.exists()
    assert sha256_file(target) == sha256_file(bbs_server["files"]["xmodem"])
