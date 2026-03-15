from __future__ import annotations

import os
from pathlib import Path
import subprocess
import threading
import time

import pytest

from emulation import RetroBbsProfile, Z80packAdapter


AUX_ECHO_COM = bytes(
    (
        0x0E,
        0x03,
        0xCD,
        0x05,
        0x00,
        0xFE,
        0x1A,
        0xCA,
        0x13,
        0x01,
        0x5F,
        0x0E,
        0x02,
        0xCD,
        0x05,
        0x00,
        0xC3,
        0x00,
        0x01,
        0xC9,
    )
)
PAYLOAD = b"HELLO AUX PATH\r\n\x1a"


def _stage_aux_echo(prepared, profile: RetroBbsProfile) -> None:
    host_dir = prepared.workdir / "guest" / "host"
    host_dir.mkdir(parents=True, exist_ok=True)
    program_path = host_dir / "AUXECHO.COM"
    program_path.write_bytes(AUX_ECHO_COM)
    subprocess.run(
        [
            "cpmcp",
            "-f",
            profile.disk_format,
            str(prepared.work_disk),
            str(program_path),
            "0:AUXECHO.COM",
        ],
        check=True,
        capture_output=True,
        text=True,
    )


@pytest.mark.tier3_emulation
def test_aux_echo_probe_reads_aux_input(tmp_path) -> None:
    adapter = Z80packAdapter()
    profile = RetroBbsProfile()
    prepared = adapter.prepare(profile, base_dir=tmp_path)
    _stage_aux_echo(prepared, profile)
    running = adapter.start(prepared)
    console = adapter.console(running)

    def inject_payload() -> None:
        fd = os.open(str(running.control_channels["auxin"]), os.O_WRONLY)
        try:
            os.write(fd, PAYLOAD)
        finally:
            os.close(fd)

    try:
        console.read_until("A>", timeout=10.0)
        console.write("stat rdr:=ur1:\r")
        time.sleep(0.5)
        console.read_available(timeout=0.2)

        console.write("b:\r")
        console.read_until("B>", timeout=5.0)

        writer = threading.Thread(target=inject_payload, daemon=True)
        writer.start()
        time.sleep(0.3)

        console.write("auxecho\r")
        echoed = console.read_until("HELLO AUX PATH", timeout=5.0).decode(
            "utf-8",
            errors="replace",
        )
        assert "HELLO AUX PATH" in echoed
        console.read_until("B>", timeout=5.0)
        writer.join(timeout=2.0)
    finally:
        console.close()
        adapter.stop(running)
