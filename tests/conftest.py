from __future__ import annotations

import os
import socket
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import pytest
import pytest_asyncio

from indexer.describe import describe_file
from indexer.scan import init_db, scan_tree
from tests.helpers.telnet_client import BbsClient

REPO_ROOT = Path(__file__).resolve().parents[1]


def _pattern_bytes(size: int, seed: int) -> bytes:
    block = bytes((seed + idx) % 256 for idx in range(256))
    repeat = (size // len(block)) + 1
    return (block * repeat)[:size]


def _build_sample_archive(root: Path) -> dict[str, Path]:
    files: dict[str, Path] = {}

    archivers = root / "archivers"
    archivers.mkdir(parents=True, exist_ok=True)
    for idx in range(1, 26):
        path = archivers / f"ARC{idx:02d}.TXT"
        path.write_text(f"Archive fixture {idx}\n", encoding="utf-8")

    comm = root / "comm"
    comm.mkdir(parents=True, exist_ok=True)
    termutil = comm / "TERMUTIL.TXT"
    termutil.write_text(
        "Portable terminal utility fixture for search and detail tests.\n",
        encoding="utf-8",
    )
    files["termutil"] = termutil

    transfer = root / "transfer"
    transfer.mkdir(parents=True, exist_ok=True)

    rawbin = transfer / "RAWBIN.BIN"
    rawbin.write_bytes(_pattern_bytes(4096, 17))
    files["raw"] = rawbin

    xmbin = transfer / "XMBIN.BIN"
    xmbin.write_bytes(_pattern_bytes(48 * 1024 + 37, 31))
    files["xmodem"] = xmbin

    kmbin = transfer / "KMBIN.BIN"
    kmbin.write_bytes(_pattern_bytes(12 * 1024 + 19, 63))
    files["kermit"] = kmbin

    zmbin = transfer / "ZMBIN.BIN"
    zmbin.write_bytes(_pattern_bytes(8 * 1024 + 11, 95))
    files["zmodem"] = zmbin

    return files


def _build_database(root: Path, db_path: Path) -> None:
    conn = init_db(str(db_path))
    scan_tree(str(root), conn)

    rows = conn.execute(
        "SELECT path, filename FROM files WHERE described = 0 ORDER BY path"
    ).fetchall()
    for path, filename in rows:
        conn.execute(
            "UPDATE files SET description = ?, described = 1 WHERE path = ?",
            (describe_file(path, filename), path),
        )

    conn.commit()
    conn.close()


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _wait_for_port(port: int, proc: subprocess.Popen[str], timeout: float = 10.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            output = proc.stdout.read() if proc.stdout else ""
            raise RuntimeError(f"BBS server exited early:\n{output}")

        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            try:
                sock.connect(("127.0.0.1", port))
                return
            except OSError:
                time.sleep(0.1)

    output = proc.stdout.read() if proc.stdout else ""
    raise RuntimeError(f"Timed out waiting for BBS server on port {port}:\n{output}")


@pytest.fixture(scope="session")
def sample_archive(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    root = tmp_path_factory.mktemp("cpm_fixture")
    db_path = tmp_path_factory.mktemp("db_fixture") / "index.db"

    files = _build_sample_archive(root)
    _build_database(root, db_path)

    return {
        "root": root,
        "db_path": db_path,
        "files": files,
    }


@pytest.fixture(scope="session")
def bbs_server(sample_archive: dict[str, object]) -> dict[str, object]:
    env_host = os.environ.get("BBS_HOST")
    if env_host:
        return {
            "host": env_host,
            "port": int(os.environ.get("BBS_PORT", "2323")),
            "root": sample_archive["root"],
            "files": sample_archive["files"],
        }

    port = _free_port()
    proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "server.main",
            "--db",
            str(sample_archive["db_path"]),
            "--cpm-root",
            str(sample_archive["root"]),
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env={**os.environ, "PYTHONUNBUFFERED": "1"},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        _wait_for_port(port, proc)
        yield {
            "host": "127.0.0.1",
            "port": port,
            "root": sample_archive["root"],
            "files": sample_archive["files"],
        }
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)


@pytest_asyncio.fixture
async def bbs_client(bbs_server: dict[str, object]) -> BbsClient:
    client = BbsClient(str(bbs_server["host"]), int(bbs_server["port"]))
    await client.connect()
    try:
        yield client
    finally:
        await client.close()
