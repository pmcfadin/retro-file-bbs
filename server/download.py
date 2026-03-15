"""download.py — file transfer helpers for telnet-backed downloads."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import os
import shutil
import sys

# IAC byte (Interpret As Command) in the telnet protocol — must be doubled
# when sending binary data to avoid misinterpretation by the telnet layer.
_IAC: bytes = b"\xff"
_IAC_ESCAPED: bytes = b"\xff\xff"

# Chunk size for streaming reads and writes.
_CHUNK_SIZE: int = 1024

_KERMIT_MARK = 0x01
_KERMIT_QUOTE = ord("#")
_KERMIT_8BIT = ord("&")
_KERMIT_SEQ_MOD = 64
_KERMIT_RETRIES = 12
_KERMIT_DATA_CHUNK = 80


def _escape_iac(data: bytes) -> bytes:
    """Double any 0xFF (IAC) bytes so they survive the telnet transport layer."""
    return data.replace(_IAC, _IAC_ESCAPED)


async def _drain_writer(writer) -> None:
    """Await writer.drain() when the transport exposes it."""
    drain = getattr(writer, "drain", None)
    if drain is None:
        return
    result = drain()
    if inspect.isawaitable(result):
        await result


async def _write_binary(writer, data: bytes) -> None:
    """Write binary bytes through a telnetlib3 writer."""
    payload = _escape_iac(data)
    transport = getattr(writer, "transport", None)
    if transport is not None:
        transport.write(payload)
        return

    writer.write(payload.decode("latin-1"))
    await _drain_writer(writer)


def _validate_file(filepath: str, label: str) -> bool:
    """Return True when filepath exists, logging otherwise."""
    if os.path.isfile(filepath):
        return True

    print(f"[download] {label}: file not found: {filepath}", file=sys.stderr)
    return False


def _available_command(*candidates: str) -> str | None:
    """Return the first installed executable name from candidates."""
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


def _kermit_tochar(value: int) -> int:
    return value + 32


def _kermit_checksum(body: bytes) -> int:
    total = sum(body)
    return ((total + ((total & 0xC0) >> 6)) & 0x3F) + 32


def _kermit_encode_byte(value: int) -> bytes:
    parts = bytearray()
    low = value & 0x7F

    if value & 0x80:
        parts.append(_KERMIT_8BIT)

    if low < 32 or low == 127:
        parts.extend((_KERMIT_QUOTE, low ^ 64))
    elif low in (_KERMIT_QUOTE, _KERMIT_8BIT):
        parts.extend((_KERMIT_QUOTE, low))
    else:
        parts.append(low)

    return bytes(parts)


def _kermit_encode_data(data: bytes) -> bytes:
    encoded = bytearray()
    for value in data:
        encoded.extend(_kermit_encode_byte(value))
    return bytes(encoded)


def _kermit_build_packet(sequence: int, packet_type: str, data: bytes = b"") -> bytes:
    body = bytes((_kermit_tochar(sequence % _KERMIT_SEQ_MOD), ord(packet_type))) + data
    length = _kermit_tochar(len(body) + 1)
    checksum = _kermit_checksum(bytes((length,)) + body)
    return bytes((_KERMIT_MARK, length)) + body + bytes((checksum,))


async def _reader_read_byte(reader, timeout: float = 1.0) -> int:
    payload = await asyncio.wait_for(reader.read(1), timeout=timeout)
    if not payload:
        raise EOFError("Connection closed during Kermit transfer")
    if isinstance(payload, str):
        return payload.encode("latin-1", errors="ignore")[0]
    return payload[0]


async def _read_kermit_packet(reader, timeout: float = 1.0) -> tuple[int, str, bytes]:
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("Timed out waiting for Kermit packet")
        marker = await _reader_read_byte(reader, timeout=remaining)
        if marker == _KERMIT_MARK:
            break

    length_char = await _reader_read_byte(reader, timeout=1.0)
    length = length_char - 32
    packet = bytearray()
    while len(packet) < length:
        packet.append(await _reader_read_byte(reader, timeout=1.0))

    sequence = packet[0] - 32
    packet_type = chr(packet[1])
    data = bytes(packet[2:-1])
    checksum = packet[-1]
    body = bytes((length_char,)) + bytes(packet[:-1])
    if checksum != _kermit_checksum(body):
        raise ValueError("Invalid Kermit checksum from receiver")

    return sequence, packet_type, data


async def _send_kermit_packet(
    reader,
    writer,
    sequence: int,
    packet_type: str,
    data: bytes = b"",
) -> bool:
    packet = _kermit_build_packet(sequence, packet_type, data)

    for _ in range(_KERMIT_RETRIES):
        await _write_binary(writer, packet)
        try:
            resp_seq, resp_type, _ = await _read_kermit_packet(reader, timeout=1.5)
        except (EOFError, TimeoutError, ValueError):
            continue

        if resp_seq != (sequence % _KERMIT_SEQ_MOD):
            continue

        if resp_type == "Y":
            return True
        if resp_type == "N":
            continue
        if resp_type == "E":
            return False

    return False


def _kermit_chunk_stream(handle) -> list[bytes]:
    chunks: list[bytes] = []
    pending = bytearray()

    while True:
        byte = handle.read(1)
        if not byte:
            if pending:
                chunks.append(bytes(pending))
            return chunks

        encoded = _kermit_encode_byte(byte[0])
        if pending and len(pending) + len(encoded) > _KERMIT_DATA_CHUNK:
            chunks.append(bytes(pending))
            pending.clear()

        pending.extend(encoded)


async def _pump_process_stdout(proc, writer) -> None:
    """Relay subprocess stdout to the telnet client."""
    assert proc.stdout is not None

    while True:
        chunk = await proc.stdout.read(_CHUNK_SIZE)
        if not chunk:
            break
        await _write_binary(writer, chunk)


async def _pump_client_input(reader, proc) -> None:
    """Relay telnet client input to a subprocess stdin stream."""
    if reader is None or proc.stdin is None:
        return

    while True:
        payload = await reader.read(1)
        if not payload:
            break

        if isinstance(payload, str):
            data = payload.encode("latin-1", errors="ignore")
        else:
            data = payload

        if not data:
            continue

        proc.stdin.write(data)
        await proc.stdin.drain()


async def _run_transfer_command(
    label: str,
    argv: list[str],
    filepath: str,
    writer,
    reader=None,
) -> bool:
    """Run an external transfer program and bridge it to the telnet session."""
    if not _validate_file(filepath, label):
        return False

    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        print(
            f"[download] {label}: missing transfer command: {argv[0]}",
            file=sys.stderr,
        )
        return False
    except OSError as exc:
        print(f"[download] {label}: failed to launch {argv[0]}: {exc}", file=sys.stderr)
        return False

    stdout_task = asyncio.create_task(_pump_process_stdout(proc, writer))
    stderr_task = (
        asyncio.create_task(proc.stderr.read()) if proc.stderr is not None else None
    )
    stdin_task = (
        asyncio.create_task(_pump_client_input(reader, proc))
        if reader is not None
        else None
    )

    try:
        returncode = await proc.wait()
        await stdout_task
    except asyncio.CancelledError:
        proc.kill()
        raise
    except Exception as exc:
        print(f"[download] {label}: transfer bridge error: {exc}", file=sys.stderr)
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        return False
    finally:
        if stdin_task is not None:
            stdin_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await stdin_task

        if proc.stdin is not None and not proc.stdin.is_closing():
            proc.stdin.close()

    stderr_output = b""
    if stderr_task is not None:
        stderr_output = await stderr_task

    if returncode != 0:
        detail = stderr_output.decode("latin-1", errors="replace").strip()
        if detail:
            print(
                f"[download] {label}: {argv[0]} exited with code {returncode}: {detail}",
                file=sys.stderr,
            )
        else:
            print(
                f"[download] {label}: {argv[0]} exited with code {returncode}",
                file=sys.stderr,
            )
        return False

    return True


async def zmodem_send(filepath: str, reader, writer) -> bool:
    """Send a file to the client using ZMODEM via the ``sz`` program."""
    command = _available_command("sz", "lsz")
    if command is None:
        print("[download] zmodem_send: missing transfer command: sz", file=sys.stderr)
        return False
    return await _run_transfer_command(
        "zmodem_send",
        [command, "--binary", "-q", filepath],
        filepath,
        writer,
        reader=reader,
    )


async def xmodem_send(filepath: str, reader, writer) -> bool:
    """Send a file to the client using XMODEM-CRC via the ``sx`` program."""
    command = _available_command("sx", "lsx")
    if command is None:
        print("[download] xmodem_send: missing transfer command: sx", file=sys.stderr)
        return False
    return await _run_transfer_command(
        "xmodem_send",
        [command, "-q", filepath],
        filepath,
        writer,
        reader=reader,
    )


async def kermit_send(filepath: str, reader, writer) -> bool:
    """Send a file to the client using a minimal Kermit sender."""
    if not _validate_file(filepath, "kermit_send"):
        return False

    send_init = bytes(
        (
            _kermit_tochar(94),
            _kermit_tochar(5),
            _kermit_tochar(0),
            _kermit_tochar(0),
            ord("#"),
            ord("&"),
            ord("1"),
            ord("N"),
            _kermit_tochar(0),
        )
    )

    sequence = 0
    if not await _send_kermit_packet(reader, writer, sequence, "S", send_init):
        print("[download] kermit_send: receiver did not ACK send-init", file=sys.stderr)
        return False

    sequence = (sequence + 1) % _KERMIT_SEQ_MOD
    filename = os.path.basename(filepath).encode("ascii", errors="replace")
    if not await _send_kermit_packet(reader, writer, sequence, "F", filename):
        print("[download] kermit_send: receiver did not ACK file header", file=sys.stderr)
        return False

    sequence = (sequence + 1) % _KERMIT_SEQ_MOD
    try:
        with open(filepath, "rb") as handle:
            for data_chunk in _kermit_chunk_stream(handle):
                if not await _send_kermit_packet(reader, writer, sequence, "D", data_chunk):
                    print(
                        "[download] kermit_send: receiver did not ACK data packet",
                        file=sys.stderr,
                    )
                    return False
                sequence = (sequence + 1) % _KERMIT_SEQ_MOD
    except OSError as exc:
        print(f"[download] kermit_send: failed to read file: {exc}", file=sys.stderr)
        return False

    if not await _send_kermit_packet(reader, writer, sequence, "Z"):
        print("[download] kermit_send: receiver did not ACK EOF", file=sys.stderr)
        return False

    sequence = (sequence + 1) % _KERMIT_SEQ_MOD
    if not await _send_kermit_packet(reader, writer, sequence, "B"):
        print("[download] kermit_send: receiver did not ACK break packet", file=sys.stderr)
        return False

    return True


async def raw_send(filepath: str, writer) -> bool:
    """Send a file to the client as a raw binary stream over telnet."""
    if not _validate_file(filepath, "raw_send"):
        return False

    try:
        with open(filepath, "rb") as fh:
            while True:
                chunk = fh.read(_CHUNK_SIZE)
                if not chunk:
                    break
                await _write_binary(writer, chunk)
        return True
    except IOError as exc:
        print(f"[download] raw_send: I/O error: {exc}", file=sys.stderr)
        return False
    except Exception as exc:
        print(f"[download] raw_send: unexpected error: {exc}", file=sys.stderr)
        return False
