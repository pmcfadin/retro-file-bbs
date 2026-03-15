from __future__ import annotations

import asyncio
import binascii

from tests.helpers.telnet_client import BbsClient

SOH = 0x01
STX = 0x02
EOT = 0x04
ACK = 0x06
NAK = 0x15
CAN = 0x18
CRC_REQUEST = ord("C")

KERMIT_MARK = 0x01


async def _read_byte(client: BbsClient, timeout: float) -> int:
    return (await client.read_exactly(1, timeout=timeout))[0]


async def _read_until_any_byte(
    client: BbsClient,
    candidates: set[int],
    timeout: float,
) -> int:
    deadline = asyncio.get_running_loop().time() + timeout
    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError(f"Timed out waiting for one of: {sorted(candidates)}")
        value = await _read_byte(client, remaining)
        if value in candidates:
            return value


def _kermit_tochar(value: int) -> int:
    return value + 32


def _kermit_unchar(value: int) -> int:
    return value - 32


def _kermit_checksum(body: bytes) -> int:
    total = sum(body)
    return ((total + ((total & 0xC0) >> 6)) & 0x3F) + 32


def _build_kermit_ack(sequence: int, data: bytes = b"") -> bytes:
    body = bytes((_kermit_tochar(sequence), ord("Y"))) + data
    length = _kermit_tochar(len(body) + 1)
    checksum = _kermit_checksum(bytes((length,)) + body)
    return bytes((KERMIT_MARK, length)) + body + bytes((checksum,))


def _decode_kermit_data(data: bytes) -> bytes:
    decoded = bytearray()
    idx = 0
    eight_bit = False

    while idx < len(data):
        value = data[idx]
        idx += 1

        if value == ord("&"):
            eight_bit = True
            continue

        if value == ord("#"):
            if idx >= len(data):
                break
            value = data[idx]
            idx += 1
            if value not in (ord("#"), ord("&")):
                value ^= 64

        if eight_bit:
            value |= 0x80
            eight_bit = False

        decoded.append(value)

    return bytes(decoded)


async def receive_xmodem(
    client: BbsClient,
    expected_size: int,
    timeout: float = 12.0,
) -> bytes:
    payload = bytearray()
    expected_block = 1
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("Timed out receiving XMODEM payload")

        await client.write_raw(bytes((CRC_REQUEST,)))
        try:
            start = await _read_until_any_byte(
                client,
                {SOH, STX, EOT, CAN},
                timeout=min(0.5, remaining),
            )
        except TimeoutError:
            continue

        if start == CAN:
            raise AssertionError("XMODEM sender cancelled the transfer")

        if start == EOT:
            await client.write_raw(bytes((ACK,)))
            return bytes(payload[:expected_size])

        packet_size = 128 if start == SOH else 1024
        block_number = await _read_byte(client, timeout=1.0)
        block_inverse = await _read_byte(client, timeout=1.0)
        if block_inverse != (0xFF - block_number):
            await client.write_raw(bytes((NAK,)))
            continue

        block = await client.read_exactly(packet_size, timeout=1.5)
        transmitted_crc = await client.read_exactly(2, timeout=1.0)
        expected_crc = binascii.crc_hqx(block, 0).to_bytes(2, "big")
        if transmitted_crc != expected_crc:
            await client.write_raw(bytes((NAK,)))
            continue

        if block_number == expected_block:
            payload.extend(block)
            expected_block = (expected_block + 1) % 256

        await client.write_raw(bytes((ACK,)))


async def receive_kermit(client: BbsClient, timeout: float = 10.0) -> bytes:
    payload = bytearray()
    deadline = asyncio.get_running_loop().time() + timeout

    while True:
        remaining = deadline - asyncio.get_running_loop().time()
        if remaining <= 0:
            raise TimeoutError("Timed out receiving Kermit payload")

        mark = await _read_until_any_byte(client, {KERMIT_MARK}, timeout=remaining)
        if mark != KERMIT_MARK:
            continue

        length_char = await _read_byte(client, timeout=1.0)
        length = _kermit_unchar(length_char)
        packet = await client.read_exactly(length, timeout=1.5)

        sequence = _kermit_unchar(packet[0])
        packet_type = chr(packet[1])
        data = packet[2:-1]
        checksum = packet[-1]
        body = bytes((length_char,)) + packet[:-1]
        if checksum != _kermit_checksum(body):
            raise AssertionError("Kermit checksum mismatch")

        if packet_type == "S":
            await client.write_raw(_build_kermit_ack(sequence))
        elif packet_type == "F":
            await client.write_raw(_build_kermit_ack(sequence))
        elif packet_type == "D":
            payload.extend(_decode_kermit_data(data))
            await client.write_raw(_build_kermit_ack(sequence))
        elif packet_type == "Z":
            await client.write_raw(_build_kermit_ack(sequence))
        elif packet_type == "B":
            await client.write_raw(_build_kermit_ack(sequence))
            return bytes(payload)
        elif packet_type == "E":
            raise AssertionError(f"Kermit sender reported an error: {data!r}")
        else:
            raise AssertionError(f"Unexpected Kermit packet type {packet_type!r}")
