from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
import os
from pathlib import Path

import telnetlib3

from emulation.artifacts import append_bytes


@dataclass
class _PumpDiagnostics:
    bytes_transferred: int = 0
    chunks: int = 0
    first_payload_hex: str | None = None
    first_payload_text: str | None = None
    last_payload_hex: str | None = None
    last_payload_text: str | None = None
    termination: str = "not-started"


class AuxTelnetBridge:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        auxin: Path,
        auxout: Path,
        to_guest_transcript: Path,
        from_guest_transcript: Path,
    ) -> None:
        self._host = host
        self._port = port
        self._auxin = auxin
        self._auxout = auxout
        self._to_guest_transcript = to_guest_transcript
        self._from_guest_transcript = from_guest_transcript
        self._tasks: list[asyncio.Task[None]] = []
        self._reader = None
        self._writer = None
        self._fd_from_guest: int | None = None
        self._fd_to_guest: int | None = None
        self._started = False
        self._guest_to_bbs = _PumpDiagnostics()
        self._bbs_to_guest = _PumpDiagnostics()

    def _payload_preview(self, payload: bytes, limit: int = 96) -> tuple[str, str]:
        sample = payload[:limit]
        return sample.hex(), sample.decode("utf-8", errors="replace")

    def _record_payload(self, diagnostics: _PumpDiagnostics, payload: bytes) -> None:
        payload_hex, payload_text = self._payload_preview(payload)
        diagnostics.bytes_transferred += len(payload)
        diagnostics.chunks += 1
        diagnostics.last_payload_hex = payload_hex
        diagnostics.last_payload_text = payload_text
        if diagnostics.first_payload_hex is None:
            diagnostics.first_payload_hex = payload_hex
            diagnostics.first_payload_text = payload_text

    def _set_termination(self, diagnostics: _PumpDiagnostics, reason: str) -> None:
        diagnostics.termination = reason

    def diagnostics_snapshot(self) -> dict[str, object]:
        return {
            "started": self._started,
            "host": self._host,
            "port": self._port,
            "auxin": str(self._auxin),
            "auxout": str(self._auxout),
            "to_guest_transcript": str(self._to_guest_transcript),
            "from_guest_transcript": str(self._from_guest_transcript),
            "guest_to_bbs": asdict(self._guest_to_bbs),
            "bbs_to_guest": asdict(self._bbs_to_guest),
        }

    async def _wait_for_pipe(self, path: Path, timeout: float = 5.0) -> None:
        deadline = asyncio.get_running_loop().time() + timeout
        while not path.exists():
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out waiting for AUX pipe at {path}")
            await asyncio.sleep(min(0.1, remaining))

    async def start(self) -> None:
        self._reader, self._writer = await telnetlib3.open_connection(
            self._host,
            self._port,
            encoding=False,
            force_binary=True,
            connect_maxwait=1.0,
        )
        await self._wait_for_pipe(self._auxout)
        await self._wait_for_pipe(self._auxin)
        self._fd_from_guest = await asyncio.to_thread(os.open, str(self._auxout), os.O_RDONLY)
        self._fd_to_guest = await asyncio.to_thread(os.open, str(self._auxin), os.O_WRONLY)
        self._started = True
        self._tasks = [
            asyncio.create_task(self._pump_guest_to_bbs()),
            asyncio.create_task(self._pump_bbs_to_guest()),
        ]

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self._fd_from_guest is not None:
            os.close(self._fd_from_guest)
            self._fd_from_guest = None
        if self._fd_to_guest is not None:
            os.close(self._fd_to_guest)
            self._fd_to_guest = None
        if self._writer is not None:
            self._writer.close()
            wait_closed = getattr(self._writer, "wait_closed", None)
            if callable(wait_closed):
                await wait_closed()
            await asyncio.sleep(0)

    async def _pump_guest_to_bbs(self) -> None:
        assert self._writer is not None
        assert self._fd_from_guest is not None
        self._set_termination(self._guest_to_bbs, "running")
        try:
            while True:
                payload = await asyncio.to_thread(os.read, self._fd_from_guest, 1024)
                if not payload:
                    self._set_termination(self._guest_to_bbs, "guest-eof")
                    return
                # OUTMDM translates CR→LF to survive z80pack's CR filter;
                # restore to CRLF for the BBS telnet session.
                payload = payload.replace(b'\n', b'\r\n')
                self._record_payload(self._guest_to_bbs, payload)
                append_bytes(self._from_guest_transcript, payload)
                self._writer.write(payload)
                await self._writer.drain()
        except asyncio.CancelledError:
            self._set_termination(self._guest_to_bbs, "cancelled")
            raise
        except Exception as exc:
            self._set_termination(
                self._guest_to_bbs,
                f"error:{type(exc).__name__}: {exc}",
            )
            raise

    async def _pump_bbs_to_guest(self) -> None:
        assert self._reader is not None
        assert self._fd_to_guest is not None
        self._set_termination(self._bbs_to_guest, "running")
        try:
            while True:
                payload = await self._reader.read(1024)
                if not payload:
                    self._set_termination(self._bbs_to_guest, "bbs-eof")
                    return
                self._record_payload(self._bbs_to_guest, payload)
                append_bytes(self._to_guest_transcript, payload)
                await asyncio.to_thread(os.write, self._fd_to_guest, payload)
        except asyncio.CancelledError:
            self._set_termination(self._bbs_to_guest, "cancelled")
            raise
        except Exception as exc:
            self._set_termination(
                self._bbs_to_guest,
                f"error:{type(exc).__name__}: {exc}",
            )
            raise
