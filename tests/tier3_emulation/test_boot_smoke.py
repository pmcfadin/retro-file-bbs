from __future__ import annotations

from tests.helpers.emulation import start_retro_bbs_session


def test_boots_cpm_and_launches_kermit(tmp_path) -> None:
    with start_retro_bbs_session(tmp_path) as session:
        console = session.console
        transcript = console.read_until("A>", timeout=10.0).decode("utf-8", errors="replace")
        assert "CP/M Vers. 2.2" in transcript

        console.write("b:\r")
        console.read_until("B>", timeout=5.0)

        console.write("kermit\r")
        banner = console.read_until("Generic CP/M-80", timeout=10.0).decode(
            "utf-8",
            errors="replace",
        )
        assert "Generic CP/M-80" in banner
