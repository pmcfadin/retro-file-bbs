from __future__ import annotations

import asyncio
import contextlib
import shutil
from pathlib import Path

from tests.helpers.telnet_client import BbsClient


def available_command(*candidates: str) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


async def _pump_bbs_to_process(client: BbsClient, proc) -> None:
    assert proc.stdin is not None

    while True:
        try:
            chunk = await client.read_raw(timeout=0.25)
        except asyncio.TimeoutError:
            continue

        if not chunk:
            break

        proc.stdin.write(chunk)
        await proc.stdin.drain()


async def _pump_process_to_bbs(client: BbsClient, proc) -> None:
    assert proc.stdout is not None

    while True:
        chunk = await proc.stdout.read(1024)
        if not chunk:
            break
        await client.write_raw(chunk)


async def run_receiver(
    client: BbsClient,
    argv: list[str],
    download_dir: Path,
    *,
    timeout: float = 30.0,
) -> str:
    proc = await asyncio.create_subprocess_exec(
        *argv,
        cwd=str(download_dir),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    to_proc = asyncio.create_task(_pump_bbs_to_process(client, proc))
    from_proc = asyncio.create_task(_pump_process_to_bbs(client, proc))

    try:
        await asyncio.wait_for(proc.wait(), timeout=timeout)
        await asyncio.wait_for(from_proc, timeout=5.0)
    finally:
        to_proc.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await to_proc

    stderr_output = b""
    if proc.stderr is not None:
        stderr_output = await proc.stderr.read()

    if proc.returncode != 0:
        detail = stderr_output.decode("utf-8", errors="replace")
        raise AssertionError(f"Receiver {argv[0]} failed with {proc.returncode}: {detail}")

    await client.read_until_quiet()
    return stderr_output.decode("utf-8", errors="replace")
