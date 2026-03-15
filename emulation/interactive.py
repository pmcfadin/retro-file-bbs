#!/usr/bin/env python3
"""Interactive CP/M session with Kermit CONNECT to a BBS.

Boots a z80pack CP/M 2.2 guest with Kermit staged on B:, then gives
you an interactive terminal. The AUX bridge connects to the BBS
telnet server in the background.

Usage:
    python -m emulation.interactive --host localhost --port 2323

Once at the CP/M prompt:
    B:              (switch to drive B)
    KERMIT          (launch Kermit-80)
    CONNECT         (enter terminal mode — you're on the BBS)
    Ctrl-\\ C       (return to Kermit prompt)
    QUIT            (exit Kermit back to CP/M)
"""
from __future__ import annotations

import argparse
import asyncio
import os
import select
import signal
import sys
import termios
import tty
from pathlib import Path

from emulation import RetroBbsProfile, Z80packAdapter
from emulation.bridges.aux import AuxTelnetBridge
from emulation.artifacts import create_artifact_layout


def _set_raw(fd: int) -> list:
    """Put terminal in raw mode, return original settings."""
    old = termios.tcgetattr(fd)
    tty.setraw(fd)
    return old


def _restore_term(fd: int, old: list) -> None:
    termios.tcsetattr(fd, termios.TCSAFLUSH, old)


async def _run_bridge(bridge: AuxTelnetBridge, stop_event: asyncio.Event) -> None:
    await bridge.start()
    await stop_event.wait()
    await bridge.stop()


def interactive_session(host: str, port: int) -> None:
    """Run an interactive CP/M session with BBS bridge."""
    tmp = Path("/tmp/retro-bbs-interactive")
    tmp.mkdir(exist_ok=True)

    adapter = Z80packAdapter()
    profile = RetroBbsProfile()
    prepared = adapter.prepare(profile, base_dir=tmp)
    running = adapter.start(prepared)
    master_fd = running.console_master_fd

    print("\033[2J\033[H", end="")  # clear screen
    print("=== CP/M Software Depot — Interactive Session ===")
    print(f"BBS server: {host}:{port}")
    print()
    print("Booting CP/M 2.2...")
    print("Once at A>, type:  B:  then  KERMIT  then  CONNECT")
    print("To return to Kermit: Ctrl-\\ C")
    print("To quit: press 'q' or Ctrl-C at any time outside CONNECT")
    print()

    # Set up bridge
    artifacts = prepared.artifacts
    bridge = AuxTelnetBridge(
        host=host,
        port=port,
        auxin=running.control_channels["auxin"],
        auxout=running.control_channels["auxout"],
        to_guest_transcript=artifacts.aux_to_guest,
        from_guest_transcript=artifacts.aux_from_guest,
    )

    stop_event = asyncio.Event()
    loop = asyncio.new_event_loop()

    # Start bridge in background thread
    import threading

    def bridge_thread():
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_bridge(bridge, stop_event))

    bt = threading.Thread(target=bridge_thread, daemon=True)
    bt.start()

    # Interactive terminal relay
    stdin_fd = sys.stdin.fileno()
    old_settings = _set_raw(stdin_fd)

    try:
        os.set_blocking(master_fd, False)
        while True:
            rlist, _, _ = select.select([stdin_fd, master_fd], [], [], 0.05)

            if stdin_fd in rlist:
                data = os.read(stdin_fd, 1024)
                if not data:
                    break
                os.write(master_fd, data)

            if master_fd in rlist:
                try:
                    data = os.read(master_fd, 4096)
                    if not data:
                        break
                    os.write(sys.stdout.fileno(), data)
                except OSError:
                    break

            # Check if z80pack died
            if running.process.poll() is not None:
                break
    except KeyboardInterrupt:
        pass
    finally:
        _restore_term(stdin_fd, old_settings)
        loop.call_soon_threadsafe(stop_event.set)
        bt.join(timeout=3)
        adapter.stop(running)
        print("\n\nSession ended.")


def main():
    parser = argparse.ArgumentParser(description="Interactive CP/M BBS session")
    parser.add_argument("--host", default="localhost", help="BBS host (default: localhost)")
    parser.add_argument("--port", type=int, default=2323, help="BBS port (default: 2323)")
    args = parser.parse_args()
    interactive_session(args.host, args.port)


if __name__ == "__main__":
    main()
