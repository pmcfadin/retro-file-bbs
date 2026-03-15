from __future__ import annotations

from abc import ABC, abstractmethod
import errno
import os
from pathlib import Path
import select
import time

from emulation.artifacts import append_bytes
from emulation.session import PreparedGuest, RunningGuest


class ConsoleChannel:
    def __init__(self, master_fd: int, transcript_path: Path) -> None:
        self._master_fd = master_fd
        self._transcript_path = transcript_path
        self._buffer = bytearray()
        os.set_blocking(master_fd, False)

    def write(self, data: bytes | str) -> None:
        payload = data.encode("ascii") if isinstance(data, str) else data
        os.write(self._master_fd, payload)

    def read_available(self, timeout: float = 0.25) -> bytes:
        ready, _, _ = select.select([self._master_fd], [], [], timeout)
        if not ready:
            return b""
        try:
            chunk = os.read(self._master_fd, 4096)
        except OSError as exc:
            if exc.errno == errno.EIO:
                return b""
            raise
        append_bytes(self._transcript_path, chunk)
        self._buffer.extend(chunk)
        return chunk

    def read_until(self, expected: bytes | str, timeout: float = 10.0) -> bytes:
        needle = expected.encode("ascii") if isinstance(expected, str) else expected
        deadline = time.monotonic() + timeout
        while needle not in self._buffer:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"Timed out waiting for {needle!r}. Transcript tail:\n"
                    f"{bytes(self._buffer[-512:]).decode('utf-8', errors='replace')}"
                )
            self.read_available(timeout=min(0.25, remaining))
        return bytes(self._buffer)

    def tail_text(self, size: int = 512) -> str:
        return bytes(self._buffer[-size:]).decode("utf-8", errors="replace")

    def close(self) -> None:
        try:
            os.close(self._master_fd)
        except OSError:
            pass


class Adapter(ABC):
    @abstractmethod
    def prepare(self, *args, **kwargs) -> PreparedGuest:
        raise NotImplementedError

    @abstractmethod
    def start(self, prepared: PreparedGuest) -> RunningGuest:
        raise NotImplementedError

    @abstractmethod
    def stop(self, running: RunningGuest) -> None:
        raise NotImplementedError

    @abstractmethod
    def console(self, running: RunningGuest) -> ConsoleChannel:
        raise NotImplementedError
