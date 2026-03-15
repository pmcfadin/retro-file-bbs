"""Unit tests for z80pack cpmrecv-killing and held_fds behaviour.

These tests exercise:
  - Z80packAdapter._kill_cpmrecv: finds and terminates cpmrecv children
  - Z80packAdapter._kill_cpmrecv: handles ProcessLookupError gracefully
  - Z80packAdapter._kill_cpmrecv: is a no-op on non-Linux (no /proc)
  - Z80packAdapter.stop: closes held_fds after process termination
  - RunningGuest.held_fds: defaults to None
"""
from __future__ import annotations

import os
import signal
import subprocess
import textwrap
import time
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from emulation.adapters.z80pack import Z80packAdapter
from emulation.session import RunningGuest


# ---------------------------------------------------------------------------
# RunningGuest.held_fds default
# ---------------------------------------------------------------------------

def test_running_guest_held_fds_defaults_to_none(tmp_path) -> None:
    """RunningGuest.held_fds must default to None (field added by this task)."""
    mock_process = MagicMock(spec=subprocess.Popen)
    from emulation.artifacts import ArtifactLayout
    from emulation.session import PreparedGuest

    layout = ArtifactLayout(
        root=tmp_path,
        metadata_json=tmp_path / "m.json",
        command_txt=tmp_path / "cmd.txt",
        console_transcript=tmp_path / "console.log",
        aux_from_guest=tmp_path / "afg.bin",
        aux_to_guest=tmp_path / "atg.bin",
        exports_dir=tmp_path / "exports",
    )
    prepared = PreparedGuest(
        workdir=tmp_path,
        run_dir=tmp_path,
        boot_disk=tmp_path / "a.dsk",
        work_disk=tmp_path / "b.dsk",
        artifacts=layout,
        command=("cpmsim",),
        env={},
        metadata={},
    )
    running = RunningGuest(
        prepared=prepared,
        process=mock_process,
        console_master_fd=3,
        control_channels={},
    )
    assert running.held_fds is None


# ---------------------------------------------------------------------------
# _kill_cpmrecv: no-op when /proc is absent
# ---------------------------------------------------------------------------

def test_kill_cpmrecv_no_proc_is_noop() -> None:
    """On non-Linux systems (no /proc), _kill_cpmrecv returns without error."""
    with patch("emulation.adapters.z80pack.Path") as mock_path_cls:
        mock_proc_root = MagicMock()
        mock_proc_root.is_dir.return_value = False

        def path_side_effect(arg):
            if arg == "/proc":
                return mock_proc_root
            return Path(arg)

        mock_path_cls.side_effect = path_side_effect
        # Should complete without raising
        Z80packAdapter._kill_cpmrecv(12345)


# ---------------------------------------------------------------------------
# _kill_cpmrecv: kills matching child, skips non-matching
# ---------------------------------------------------------------------------

def _make_proc_dir(proc_root: Path, pid: int, ppid: int, name: str) -> None:
    entry = proc_root / str(pid)
    entry.mkdir(parents=True, exist_ok=True)
    status = textwrap.dedent(f"""\
        Name:\t{name}
        PPid:\t{ppid}
        State:\tS (sleeping)
    """)
    (entry / "status").write_text(status)


def test_kill_cpmrecv_kills_matching_child(tmp_path) -> None:
    """_kill_cpmrecv sends SIGTERM to a child whose Name==cpmrecv and PPid matches."""
    parent_pid = 1000
    cpmrecv_pid = 1001
    other_pid = 1002

    _make_proc_dir(tmp_path, cpmrecv_pid, parent_pid, "cpmrecv")
    _make_proc_dir(tmp_path, other_pid, parent_pid, "cpmsim")

    killed: list[tuple[int, int]] = []

    def fake_kill(pid: int, sig: int) -> None:
        killed.append((pid, sig))

    with patch("emulation.adapters.z80pack.Path") as mock_path_cls, \
         patch("emulation.adapters.z80pack.os.kill", side_effect=fake_kill):

        def path_side_effect(arg):
            if arg == "/proc":
                real = Path(str(tmp_path))
                return real
            return Path(arg)

        mock_path_cls.side_effect = path_side_effect

        # Re-patch Path("/proc") directly to return our tmp_path
        with patch.object(
            Path,
            "__new__",
            side_effect=lambda cls, *a, **kw: object.__new__(cls),
        ):
            pass  # skip nested patch; use a simpler approach below

    # Simpler: patch the module-level Path to return tmp_path for "/proc"
    import emulation.adapters.z80pack as z80mod

    original_path = z80mod.Path

    class PatchedPath:
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "/proc":
                return original_path(str(tmp_path))
            return original_path(*args, **kwargs)

    killed2: list[tuple[int, int]] = []

    def fake_kill2(pid: int, sig: int) -> None:
        killed2.append((pid, sig))

    with patch.object(z80mod, "Path", PatchedPath), \
         patch.object(z80mod.os, "kill", side_effect=fake_kill2):
        Z80packAdapter._kill_cpmrecv(parent_pid)

    assert (cpmrecv_pid, signal.SIGTERM) in killed2, (
        f"Expected SIGTERM to cpmrecv pid {cpmrecv_pid}, got {killed2}"
    )
    # other_pid (cpmsim) must NOT be killed
    assert not any(pid == other_pid for pid, _ in killed2), (
        f"Should not have killed non-cpmrecv pid {other_pid}, got {killed2}"
    )


def test_kill_cpmrecv_skips_unrelated_ppid(tmp_path) -> None:
    """_kill_cpmrecv does not kill cpmrecv processes belonging to other parents."""
    parent_pid = 2000
    unrelated_cpmrecv_pid = 2001

    _make_proc_dir(tmp_path, unrelated_cpmrecv_pid, 9999, "cpmrecv")

    import emulation.adapters.z80pack as z80mod
    original_path = z80mod.Path

    class PatchedPath:
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "/proc":
                return original_path(str(tmp_path))
            return original_path(*args, **kwargs)

    killed: list[tuple[int, int]] = []

    with patch.object(z80mod, "Path", PatchedPath), \
         patch.object(z80mod.os, "kill", side_effect=lambda p, s: killed.append((p, s))):
        Z80packAdapter._kill_cpmrecv(parent_pid)

    assert killed == [], f"Should not kill unrelated cpmrecv, got {killed}"


# ---------------------------------------------------------------------------
# _kill_cpmrecv: graceful handling of ProcessLookupError
# ---------------------------------------------------------------------------

def test_kill_cpmrecv_handles_process_lookup_error(tmp_path) -> None:
    """_kill_cpmrecv catches ProcessLookupError (process already gone)."""
    parent_pid = 3000
    cpmrecv_pid = 3001

    _make_proc_dir(tmp_path, cpmrecv_pid, parent_pid, "cpmrecv")

    import emulation.adapters.z80pack as z80mod
    original_path = z80mod.Path

    class PatchedPath:
        def __new__(cls, *args, **kwargs):
            if args and args[0] == "/proc":
                return original_path(str(tmp_path))
            return original_path(*args, **kwargs)

    def raise_process_lookup(pid: int, sig: int) -> None:
        raise ProcessLookupError(f"No such process: {pid}")

    # Should not raise
    with patch.object(z80mod, "Path", PatchedPath), \
         patch.object(z80mod.os, "kill", side_effect=raise_process_lookup):
        Z80packAdapter._kill_cpmrecv(parent_pid)


# ---------------------------------------------------------------------------
# stop(): held_fds are closed after process termination
# ---------------------------------------------------------------------------

def _make_running_guest(tmp_path: Path, held_fds: list[int] | None) -> RunningGuest:
    from emulation.artifacts import ArtifactLayout
    from emulation.session import PreparedGuest

    layout = ArtifactLayout(
        root=tmp_path,
        metadata_json=tmp_path / "m.json",
        command_txt=tmp_path / "cmd.txt",
        console_transcript=tmp_path / "console.log",
        aux_from_guest=tmp_path / "afg.bin",
        aux_to_guest=tmp_path / "atg.bin",
        exports_dir=tmp_path / "exports",
    )
    prepared = PreparedGuest(
        workdir=tmp_path,
        run_dir=tmp_path,
        boot_disk=tmp_path / "a.dsk",
        work_disk=tmp_path / "b.dsk",
        artifacts=layout,
        command=("cpmsim",),
        env={},
        metadata={},
    )
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.poll.return_value = 0  # already exited
    return RunningGuest(
        prepared=prepared,
        process=mock_process,
        console_master_fd=3,
        control_channels={},
        held_fds=held_fds,
    )


def test_stop_closes_held_fds(tmp_path) -> None:
    """stop() must close all fds in held_fds after the process is terminated."""
    closed_fds: list[int] = []

    def fake_close(fd: int) -> None:
        closed_fds.append(fd)

    running = _make_running_guest(tmp_path, held_fds=[10, 11])
    adapter = Z80packAdapter.__new__(Z80packAdapter)

    import emulation.adapters.z80pack as z80mod

    with patch.object(z80mod.os, "close", side_effect=fake_close), \
         patch.object(z80mod.time, "sleep"):
        adapter.stop(running)

    assert 10 in closed_fds, "fd 10 should have been closed"
    assert 11 in closed_fds, "fd 11 should have been closed"


def test_stop_with_no_held_fds(tmp_path) -> None:
    """stop() must not raise when held_fds is None."""
    running = _make_running_guest(tmp_path, held_fds=None)
    adapter = Z80packAdapter.__new__(Z80packAdapter)

    import emulation.adapters.z80pack as z80mod

    with patch.object(z80mod.os, "close") as mock_close, \
         patch.object(z80mod.time, "sleep"):
        adapter.stop(running)

    mock_close.assert_not_called()


def test_stop_closes_held_fds_even_if_os_close_raises(tmp_path) -> None:
    """stop() must attempt to close all held_fds even if some raise OSError."""
    closed_fds: list[int] = []

    def fake_close(fd: int) -> None:
        if fd == 10:
            raise OSError("bad fd")
        closed_fds.append(fd)

    running = _make_running_guest(tmp_path, held_fds=[10, 11])
    adapter = Z80packAdapter.__new__(Z80packAdapter)

    import emulation.adapters.z80pack as z80mod

    with patch.object(z80mod.os, "close", side_effect=fake_close), \
         patch.object(z80mod.time, "sleep"):
        adapter.stop(running)  # must not raise

    assert 11 in closed_fds, "fd 11 should still be closed despite fd 10 raising OSError"
