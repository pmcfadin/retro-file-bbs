"""sessions.py — Shared session registry between telnet and FastAPI."""

from __future__ import annotations

import datetime
from collections import deque
from dataclasses import dataclass, field


@dataclass
class SessionInfo:
    """Represents one active telnet session."""
    session_id: str
    peer_ip: str
    peer_port: int
    connected_at: datetime.datetime = field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc)
    )
    current_state: str = "WELCOME"


# Module-level shared state
active_sessions: dict[str, SessionInfo] = {}
connection_history: deque[dict] = deque(maxlen=200)


def register_session(session_id: str, peer_ip: str, peer_port: int) -> SessionInfo:
    """Register a new telnet session."""
    info = SessionInfo(
        session_id=session_id,
        peer_ip=peer_ip,
        peer_port=peer_port,
    )
    active_sessions[session_id] = info
    connection_history.append({
        "session_id": session_id,
        "peer_ip": peer_ip,
        "peer_port": peer_port,
        "connected_at": info.connected_at.isoformat(),
        "event": "connect",
    })
    return info


def deregister_session(session_id: str) -> None:
    """Remove a session from the active registry."""
    info = active_sessions.pop(session_id, None)
    if info:
        connection_history.append({
            "session_id": session_id,
            "peer_ip": info.peer_ip,
            "peer_port": info.peer_port,
            "disconnected_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "event": "disconnect",
        })


def update_session_state(session_id: str, state: str) -> None:
    """Update the current state of a session."""
    if session_id in active_sessions:
        active_sessions[session_id].current_state = state
