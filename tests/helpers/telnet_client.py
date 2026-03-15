from __future__ import annotations

import asyncio
import inspect

import telnetlib3

from tests.helpers.ansi_parser import visible_text


class BbsClient:
    """Byte-oriented telnet client for navigating the BBS and running transfers."""

    def __init__(self, host: str, port: int) -> None:
        self.host = host
        self.port = port
        self.reader = None
        self.writer = None
        self._screen_buffer = bytearray()

    async def connect(self) -> None:
        self.reader, self.writer = await telnetlib3.open_connection(
            self.host,
            self.port,
            encoding=False,
            force_binary=True,
            connect_maxwait=1.0,
        )

    async def close(self) -> None:
        if self.writer is None:
            return
        self.writer.close()
        await asyncio.sleep(0)

    async def _drain(self) -> None:
        if self.writer is None:
            return
        drain = getattr(self.writer, "drain", None)
        if drain is None:
            return
        result = drain()
        if inspect.isawaitable(result):
            await result

    @property
    def screen_text(self) -> str:
        return visible_text(bytes(self._screen_buffer))

    def clear_screen(self) -> None:
        self._screen_buffer.clear()

    async def send_text(self, text: str) -> None:
        await self.write_raw(text.encode("ascii"))

    async def send_line(self, text: str = "") -> None:
        await self.send_text(text + "\r")

    async def write_raw(self, data: bytes) -> None:
        if self.writer is None:
            raise RuntimeError("Client is not connected")
        self.writer.write(data.replace(b"\xff", b"\xff\xff"))
        await self._drain()

    async def read_raw(self, size: int = 4096, timeout: float = 5.0) -> bytes:
        if self.reader is None:
            raise RuntimeError("Client is not connected")
        return await asyncio.wait_for(self.reader.read(size), timeout=timeout)

    async def read_exactly(self, size: int, timeout: float = 10.0) -> bytes:
        deadline = asyncio.get_running_loop().time() + timeout
        buf = bytearray()

        while len(buf) < size:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError(f"Timed out reading {size} bytes")
            chunk = await self.read_raw(size - len(buf), timeout=remaining)
            if not chunk:
                raise EOFError(f"Connection closed after {len(buf)} of {size} bytes")
            buf.extend(chunk)

        return bytes(buf)

    async def read_until_quiet(
        self,
        *,
        idle: float = 0.2,
        timeout: float = 2.0,
        capture_screen: bool = True,
    ) -> bytes:
        deadline = asyncio.get_running_loop().time() + timeout
        buf = bytearray()

        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                chunk = await self.read_raw(timeout=min(idle, remaining))
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            buf.extend(chunk)
            if capture_screen:
                self._screen_buffer.extend(chunk)

        return bytes(buf)

    async def read_until_text(self, expected: str, timeout: float = 5.0) -> str:
        deadline = asyncio.get_running_loop().time() + timeout

        while expected not in self.screen_text:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise AssertionError(
                    f"Did not receive {expected!r}. Current screen:\n{self.screen_text}"
                )
            chunk = await self.read_raw(timeout=remaining)
            if not chunk:
                break
            self._screen_buffer.extend(chunk)

        if expected not in self.screen_text:
            raise AssertionError(
                f"Did not receive {expected!r}. Current screen:\n{self.screen_text}"
            )

        return self.screen_text
