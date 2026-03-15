from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from emulation import RetroBbsProfile, Z80packAdapter
from emulation.adapters.base import ConsoleChannel
from emulation.session import PreparedGuest, RunningGuest


@dataclass
class ManagedSession:
    adapter: Z80packAdapter
    profile: RetroBbsProfile
    prepared: PreparedGuest
    running: RunningGuest
    console: ConsoleChannel


@contextmanager
def start_retro_bbs_session(base_dir: Path) -> ManagedSession:
    adapter = Z80packAdapter()
    profile = RetroBbsProfile()
    prepared = adapter.prepare(profile, base_dir=base_dir)
    running = adapter.start(prepared)
    console = adapter.console(running)
    try:
        yield ManagedSession(
            adapter=adapter,
            profile=profile,
            prepared=prepared,
            running=running,
            console=console,
        )
    finally:
        console.close()
        adapter.stop(running)
