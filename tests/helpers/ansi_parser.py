from __future__ import annotations

import re

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")


def strip_ansi(text: str) -> str:
    """Remove ANSI control sequences from text."""
    return _ANSI_RE.sub("", text)


def visible_text(data: bytes) -> str:
    """Decode UTF-8 screen bytes and strip terminal control sequences."""
    text = data.decode("utf-8", errors="ignore").replace("\r", "")
    return strip_ansi(text)
