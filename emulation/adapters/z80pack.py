from __future__ import annotations

import os
from pathlib import Path
import pty
import shutil
import signal
import subprocess
import time

from emulation.adapters.base import Adapter, ConsoleChannel
from emulation.artifacts import create_artifact_layout, layout_metadata, write_command, write_metadata
from emulation.images.cpm import stage_retro_bbs_disks
from emulation.profiles.retro_bbs import RetroBbsProfile
from emulation.session import PreparedGuest, RunningGuest


class Z80packAdapter(Adapter):
    def __init__(self, *, z80pack_home: Path | None = None) -> None:
        self._z80pack_home = z80pack_home

    def _normalize_z80pack_home(self, candidate: Path) -> Path:
        resolved = candidate.expanduser().resolve()
        if resolved.is_file() and resolved.name == "cpmsim":
            return resolved.parents[1]
        if (resolved / "cpmsim" / "cpmsim").exists():
            return resolved
        if resolved.name == "cpmsim" and (resolved / "cpmsim").exists():
            return resolved.parent
        raise FileNotFoundError(f"Could not resolve z80pack home from {resolved}")

    def _resolve_z80pack_home(self) -> Path:
        if self._z80pack_home is not None:
            return self._normalize_z80pack_home(self._z80pack_home)

        env_home = os.environ.get("Z80PACK_HOME")
        if env_home:
            return self._normalize_z80pack_home(Path(env_home))

        cpmsim = shutil.which("cpmsim")
        if cpmsim:
            return self._normalize_z80pack_home(Path(cpmsim))

        raise FileNotFoundError("Could not resolve z80pack home; set Z80PACK_HOME")

    def prepare(
        self,
        profile: RetroBbsProfile,
        *,
        base_dir: Path | None = None,
    ) -> PreparedGuest:
        z80pack_home = self._resolve_z80pack_home()
        cpmsim_bin = z80pack_home / "cpmsim" / "cpmsim"
        if not cpmsim_bin.exists():
            raise FileNotFoundError(f"cpmsim binary not found at {cpmsim_bin}")

        artifacts = create_artifact_layout(base_dir=base_dir, prefix="z80pack")
        staged = stage_retro_bbs_disks(artifacts.root / "guest")

        run_dir = artifacts.root / "runner"
        (run_dir / "disks").mkdir(parents=True, exist_ok=True)
        (run_dir / "cpmsim").symlink_to(cpmsim_bin)
        (run_dir / "disks" / "drivea.dsk").symlink_to(staged.boot_disk)
        (run_dir / "disks" / "driveb.dsk").symlink_to(staged.work_disk)

        command = (str(run_dir / "cpmsim"),)
        env = {**os.environ}
        metadata: dict[str, object] = {
            "adapter": "z80pack",
            "profile": profile.name,
            "z80pack_home": str(z80pack_home),
            "boot_disk": str(staged.boot_disk),
            "work_disk": str(staged.work_disk),
            "kermit_path": str(staged.kermit_com),
            "artifacts": layout_metadata(artifacts),
        }
        write_command(artifacts.command_txt, command)
        write_metadata(artifacts.metadata_json, metadata)
        return PreparedGuest(
            workdir=artifacts.root,
            run_dir=run_dir,
            boot_disk=staged.boot_disk,
            work_disk=staged.work_disk,
            artifacts=artifacts,
            command=command,
            env=env,
            metadata=metadata,
        )

    def start(self, prepared: PreparedGuest) -> RunningGuest:
        master_fd, slave_fd = pty.openpty()

        # Pre-create AUX FIFOs and hold auxout open for reading.
        # z80pack's init_io() forks a cpmrecv child that also reads auxout;
        # we kill it after boot so the bridge is the sole consumer.
        # Holding a reader fd prevents z80pack's open(O_WRONLY) from blocking
        # and avoids SIGPIPE after cpmrecv is killed.
        auxin_path = Path("/tmp/.z80pack/cpmsim.auxin")
        auxout_path = Path("/tmp/.z80pack/cpmsim.auxout")
        auxin_path.parent.mkdir(exist_ok=True)
        for p in (auxin_path, auxout_path):
            if not p.exists():
                os.mkfifo(p, 0o666)
        auxout_reader_fd = os.open(str(auxout_path), os.O_RDONLY | os.O_NONBLOCK)

        process = subprocess.Popen(
            prepared.command,
            stdin=slave_fd,
            stdout=slave_fd,
            stderr=slave_fd,
            cwd=prepared.run_dir,
            env=prepared.env,
            start_new_session=True,
        )
        os.close(slave_fd)

        # Kill the cpmrecv child that z80pack forks to drain auxout.
        time.sleep(0.3)
        self._kill_cpmrecv(process.pid)

        return RunningGuest(
            prepared=prepared,
            process=process,
            console_master_fd=master_fd,
            control_channels={
                "auxin": auxin_path,
                "auxout": auxout_path,
            },
            held_fds=[auxout_reader_fd],
        )

    @staticmethod
    def _kill_cpmrecv(parent_pid: int) -> None:
        """Kill the cpmrecv process forked by z80pack's init_io().

        z80pack forks cpmrecv to drain the auxout FIFO into a text file.
        We need the bridge to be the sole reader, so we kill cpmrecv after
        z80pack has finished opening the pipe.
        """
        proc_root = Path("/proc")
        if not proc_root.is_dir():
            return
        for entry in proc_root.iterdir():
            if not entry.name.isdigit():
                continue
            try:
                status = (entry / "status").read_text()
            except (PermissionError, FileNotFoundError, OSError):
                continue
            ppid = None
            name = None
            for line in status.splitlines():
                if line.startswith("PPid:"):
                    ppid = int(line.split()[1])
                elif line.startswith("Name:"):
                    name = line.split()[1]
            if ppid == parent_pid and name == "cpmrecv":
                try:
                    os.kill(int(entry.name), signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def stop(self, running: RunningGuest) -> None:
        if running.process.poll() is None:
            try:
                os.killpg(running.process.pid, signal.SIGTERM)
                running.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    os.killpg(running.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                running.process.wait(timeout=5)
        for fd in (running.held_fds or []):
            try:
                os.close(fd)
            except OSError:
                pass
        time.sleep(0.1)

    def console(self, running: RunningGuest) -> ConsoleChannel:
        return ConsoleChannel(
            running.console_master_fd,
            running.prepared.artifacts.console_transcript,
        )
