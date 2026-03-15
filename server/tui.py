"""tui.py — Raw ANSI TUI rendering for the CP/M Software Depot BBS.

Uses raw ANSI escape codes written directly to the telnetlib3 writer.
No external dependencies (no blessed, no curses).
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# ANSI escape constants
# ---------------------------------------------------------------------------

ESC = "\033"
CLEAR = f"{ESC}[2J{ESC}[H"

CYAN = f"{ESC}[36m"
BRIGHT_CYAN = f"{ESC}[96m"
YELLOW = f"{ESC}[33m"
BRIGHT_YELLOW = f"{ESC}[93m"
WHITE = f"{ESC}[37m"
BRIGHT_WHITE = f"{ESC}[97m"
GREEN = f"{ESC}[32m"
BRIGHT_GREEN = f"{ESC}[92m"
RED = f"{ESC}[31m"
RESET = f"{ESC}[0m"
BOLD = f"{ESC}[1m"

# Box-drawing characters (ASCII for CP/M terminal compatibility)
TL = "+"
TR = "+"
BL = "+"
BR = "+"
HORIZ = "-"
VERT = "|"
LMID = "+"
RMID = "+"

BOX_WIDTH = 78  # inner content width inside an 80-col terminal


# ---------------------------------------------------------------------------
# Writer wrapper — bypass telnetlib3 encoding, always send UTF-8
# ---------------------------------------------------------------------------


class Utf8Writer:
    """Wraps a telnetlib3 TelnetWriter to always encode as UTF-8.

    telnetlib3 negotiates encoding with the client and may fall back to
    ASCII, which cannot encode Unicode box-drawing characters.  This wrapper
    writes UTF-8 bytes directly to the underlying asyncio transport,
    bypassing the telnet encoding layer.  UTF-8 never produces 0xFF bytes,
    so IAC escaping is not needed for display text.
    """

    def __init__(self, writer: object) -> None:
        self._writer = writer

    def write(self, text: str) -> None:
        self._writer.transport.write(text.encode("utf-8"))

    def close(self) -> None:
        self._writer.close()

    def get_extra_info(self, *args, **kwargs):
        return self._writer.get_extra_info(*args, **kwargs)

    @property
    def transport(self):
        return self._writer.transport


# ---------------------------------------------------------------------------
# Low-level helpers
# ---------------------------------------------------------------------------


def clear_screen(writer: object) -> None:
    """Send clear-screen sequence."""
    writer.write(CLEAR)


def write_line(writer: object, text: str = "") -> None:
    """Write text followed by CRLF (telnet line ending)."""
    writer.write(text + "\r\n")


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def format_size(size_bytes: int) -> str:
    """Return human-readable size: NB, NK, or NM."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes // 1024}K"
    else:
        return f"{size_bytes // (1024 * 1024)}M"


def truncate(text: str, max_len: int) -> str:
    """Truncate text with '...' if longer than max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def paginate(
    items: list, page: int, per_page: int
) -> tuple[list, str, int]:
    """Return (page_items, page_str, total_pages) for the given page."""
    total = len(items)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    end = start + per_page
    page_str = f"Page {page} of {total_pages}"
    return items[start:end], page_str, total_pages


# ---------------------------------------------------------------------------
# Box drawing
# ---------------------------------------------------------------------------


def _horiz_line(width: int) -> str:
    """Return a horizontal line of HORIZ chars of given width."""
    return HORIZ * width


def draw_header(writer: object, title: str, right_text: str = "") -> None:
    """Draw the top border: ┌─ Title ──────────────────── right_text ─┐

    Total line width = BOX_WIDTH + 2 (for the ┌ and ┐).
    """
    total = BOX_WIDTH + 2  # 80 chars total
    # Build the title segment: "─ Title "
    if title:
        title_seg = f"{HORIZ} {title} "
    else:
        title_seg = HORIZ

    # Build right segment: " right_text ─"
    if right_text:
        right_seg = f" {right_text} {HORIZ}"
    else:
        right_seg = HORIZ

    # Raw lengths (no ANSI codes in title_seg or right_seg)
    used = 1 + len(title_seg) + len(right_seg) + 1  # TL + segs + TR
    fill = total - used
    if fill < 0:
        fill = 0

    line = (
        CYAN + TL + title_seg + _horiz_line(fill) + right_seg + TR + RESET
    )
    write_line(writer, line)


def draw_footer(writer: object) -> None:
    """Draw the bottom border: └──────────────────────────────────────┘"""
    total = BOX_WIDTH + 2
    line = CYAN + BL + _horiz_line(total - 2) + BR + RESET
    write_line(writer, line)


def draw_separator(writer: object) -> None:
    """Draw an interior separator: ├──────────────────────────────────┤"""
    total = BOX_WIDTH + 2
    line = CYAN + LMID + _horiz_line(total - 2) + RMID + RESET
    write_line(writer, line)


def draw_blank_line(writer: object) -> None:
    """Draw an empty box line: │                                      │"""
    content = " " * BOX_WIDTH
    line = CYAN + VERT + RESET + content + CYAN + VERT + RESET
    write_line(writer, line)


def draw_content_line(writer: object, content: str, pad: bool = True) -> None:
    """Draw a single content line inside the box borders.

    Content must be plain text or ANSI-escaped text.  We pad visible
    characters to BOX_WIDTH, accounting for invisible ANSI escape sequences.
    """
    # Measure visible length (strip ANSI codes for measurement)
    import re

    ansi_escape = re.compile(r"\x1b\[[0-9;]*m")
    visible = ansi_escape.sub("", content)
    visible_len = len(visible)

    if pad and visible_len < BOX_WIDTH:
        content = content + " " * (BOX_WIDTH - visible_len)

    line = CYAN + VERT + RESET + content + CYAN + VERT + RESET
    write_line(writer, line)


def draw_box(
    writer: object,
    title: str,
    content_lines: list[str],
    right_text: str = "",
) -> None:
    """Draw a complete box with title, content lines, and bottom border."""
    draw_header(writer, title, right_text)
    draw_blank_line(writer)
    for line in content_lines:
        draw_content_line(writer, line)
    draw_blank_line(writer)
    draw_footer(writer)


# ---------------------------------------------------------------------------
# Colour helpers for content lines
# ---------------------------------------------------------------------------


def col(color: str, text: str) -> str:
    """Wrap text in a colour code followed by RESET."""
    return f"{color}{text}{RESET}"
