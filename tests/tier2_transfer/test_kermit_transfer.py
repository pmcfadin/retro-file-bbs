from __future__ import annotations

import pytest

from tests.helpers.file_integrity import sha256_file
from tests.helpers.journey import goto_main_menu, open_download_menu
from tests.helpers.protocols import receive_kermit
from tests.helpers.transfers import available_command


async def test_kermit_transfer_preserves_file_contents(
    bbs_client, bbs_server, tmp_path
) -> None:
    await goto_main_menu(bbs_client)
    await open_download_menu(bbs_client, "C", 1, "KMBIN.BIN")

    command = available_command("gkermit", "kermit")
    if command is None:
        pytest.skip("No Kermit sender is installed")

    bbs_client.clear_screen()
    await bbs_client.send_text("K")
    received = await receive_kermit(bbs_client, timeout=20.0)

    target = tmp_path / "KMBIN.BIN"
    target.write_bytes(received[: bbs_server["files"]["kermit"].stat().st_size])
    assert sha256_file(target) == sha256_file(bbs_server["files"]["kermit"])
