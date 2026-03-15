"""main.py — Telnet server entry point for the CP/M Software Depot BBS.

Usage:
    python3 server/main.py --db /data/index.db --cpm-root /data/cpm [--port 2323]
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import logging
import os
import re
import signal
import sqlite3
import sys

import telnetlib3

from server.browser import (
    CATEGORY_INFO,
    get_categories,
    get_file_detail,
    get_files,
    get_total_stats,
)
from server.search import search_files
from server import tui
from server.tui import (
    BOLD,
    BRIGHT_CYAN,
    BRIGHT_WHITE,
    BRIGHT_YELLOW,
    CYAN,
    RESET,
    WHITE,
    YELLOW,
    Utf8Writer,
    col,
    format_size,
    truncate,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PER_PAGE = 20
CATEGORY_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

# ASCII / block-letter banner (fits in 78 chars, bright cyan)
BANNER_LINES = [
    r"     ██████╗██████╗ ██╗███╗   ███╗",
    r"    ██╔════╝██╔══██╗██║████╗ ████║",
    r"    ██║     ██████╔╝██║██╔████╔██║",
    r"    ██║     ██╔═══╝ ██║██║╚██╔╝██║",
    r"    ╚██████╗██║     ██║██║ ╚═╝ ██║",
    r"     ╚═════╝╚═╝     ╚═╝╚═╝     ╚═╝",
]


# ---------------------------------------------------------------------------
# Session
# ---------------------------------------------------------------------------


class Session:
    """Manages one telnet connection's state machine."""

    def __init__(
        self,
        reader: telnetlib3.TelnetReader,
        writer: telnetlib3.TelnetWriter,
        db_path: str,
        cpm_root: str,
    ) -> None:
        self.reader = reader
        self.writer = Utf8Writer(writer)
        self._raw_writer = writer  # keep for download module (needs raw transport)
        self.db_path = db_path
        self.cpm_root = cpm_root

        # State machine
        self.state = "WELCOME"
        self.current_area = ""
        self.current_page = 1
        self.current_file: str | None = None  # path string
        self.search_query = ""
        self.search_page = 1

        # Terminal dimensions (updated via NAWS)
        self.width = 80
        self.height = 24

        # Category list cache (refreshed on every CATEGORIES render)
        self._categories: list[tuple[str, int, str]] = []

        # The list of files on the current FILE_LIST page
        self._current_files: list[dict] = []
        self._current_total = 0

        # Search results cache
        self._search_results: list[dict] = []
        self._search_total = 0

        # Where should B go from SEARCH_RESULTS?
        self._search_back_state = "CATEGORIES"

        # Where should B go from FILE_DETAIL?
        self._detail_back_state = "FILE_LIST"

    # ------------------------------------------------------------------
    # Database helpers
    # ------------------------------------------------------------------

    def _open_db(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------------
    # Low-level I/O
    # ------------------------------------------------------------------

    def write(self, text: str) -> None:
        self.writer.write(text)

    def writeln(self, text: str = "") -> None:
        tui.write_line(self.writer, text)

    async def read_char(self) -> str | None:
        """Read exactly one character; return None on EOF."""
        try:
            ch = await self.reader.read(1)
            if not ch:
                return None
            return ch
        except Exception:
            return None

    async def read_line(self, prompt: str = "") -> str | None:
        """Display prompt and read a line of input (until Enter).

        Handles backspace.  Returns None on EOF/disconnect.
        """
        if prompt:
            self.write(prompt)

        buf: list[str] = []
        while True:
            ch = await self.read_char()
            if ch is None:
                return None
            if ch in ("\r", "\n"):
                self.writeln()
                return "".join(buf).strip()
            elif ch in ("\x08", "\x7f"):  # backspace / DEL
                if buf:
                    buf.pop()
                    self.write("\x08 \x08")  # erase character on screen
            elif ch.isprintable():
                buf.append(ch)
                self.write(ch)

    # ------------------------------------------------------------------
    # Screen renderers
    # ------------------------------------------------------------------

    def _render_welcome(self) -> None:
        """Render the welcome screen with banner and stats."""
        tui.clear_screen(self.writer)

        with self._open_db() as db:
            total_files, total_cats = get_total_stats(db)

        tui.draw_header(self.writer, "CP/M Software Depot")
        tui.draw_blank_line(self.writer)

        for line in BANNER_LINES:
            padded = f"  {line}"
            tui.draw_content_line(
                self.writer, col(BRIGHT_CYAN, padded)
            )

        tui.draw_blank_line(self.writer)

        depot_line = "               S O F T W A R E   D E P O T"
        tui.draw_content_line(self.writer, col(YELLOW, depot_line))
        tui.draw_blank_line(self.writer)

        tagline = "                  ── Serving the CP/M Community ──"
        tui.draw_content_line(self.writer, col(WHITE, tagline))
        tui.draw_blank_line(self.writer)

        stats = (
            f"    {col(BRIGHT_CYAN, str(total_cats))} Categories"
            f"  ·  {col(BRIGHT_CYAN, str(total_files))} Files"
            f"  ·  {col(WHITE, 'Z/X/K/Raw Downloads')}"
        )
        tui.draw_content_line(self.writer, stats)

        # Fill remaining lines (24 total: 1 header + 1 blank + 6 banner +
        # 1 blank + depot + blank + tagline + blank + stats + blank*3 +
        # continue + blank + footer = 24)
        for _ in range(4):
            tui.draw_blank_line(self.writer)

        continue_line = "                   Press [ENTER] to continue..."
        tui.draw_content_line(
            self.writer, col(BRIGHT_YELLOW, continue_line)
        )
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    def _render_categories(self) -> None:
        """Render the category list / main menu."""
        tui.clear_screen(self.writer)

        with self._open_db() as db:
            self._categories = get_categories(db)

        tui.draw_header(self.writer, "CP/M Software Depot — Main Menu")
        tui.draw_blank_line(self.writer)

        # Column header
        header = (
            f"   {col(BOLD + WHITE, '#'  )}"
            f"   {col(BOLD + WHITE, 'Category'      ):<18}"
            f"  {col(BOLD + WHITE, 'Files'):>5}"
            f"   {col(BOLD + WHITE, 'Description')}"
        )
        tui.draw_content_line(self.writer, header)

        sep = (
            "  ─── ────────────────────── "
            "──────── ─────────────────────────────────────────"
        )
        tui.draw_content_line(self.writer, col(CYAN, sep))

        for idx, (area, count, description) in enumerate(self._categories):
            if idx >= len(CATEGORY_LETTERS):
                break
            letter = CATEGORY_LETTERS[idx]
            display_name, _ = CATEGORY_INFO.get(area, (area.title(), ""))
            desc_trunc = truncate(description, 38)

            row = (
                f"   {col(BRIGHT_YELLOW, letter)}"
                f"   {col(BRIGHT_WHITE, display_name):<18}"
                f"  {col(CYAN, str(count)):>5}"
                f"   {col(WHITE, desc_trunc)}"
            )
            tui.draw_content_line(self.writer, row)

        # Fill to keep box consistent
        lines_used = len(self._categories)
        for _ in range(max(0, 10 - lines_used)):
            tui.draw_blank_line(self.writer)

        tui.draw_blank_line(self.writer)
        footer_text = col(BRIGHT_YELLOW, "[A-L]") + col(WHITE, " Select category   ") + col(BRIGHT_YELLOW, "[S]") + col(WHITE, " Search   ") + col(BRIGHT_YELLOW, "[Q]") + col(WHITE, " Quit")
        tui.draw_content_line(self.writer, "   " + footer_text)
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    def _render_file_list(self) -> None:
        """Render the paginated file listing for the current area."""
        tui.clear_screen(self.writer)

        display_name, description = CATEGORY_INFO.get(
            self.current_area, (self.current_area.title(), "")
        )

        with self._open_db() as db:
            files, total = get_files(
                db, self.current_area, self.current_page, PER_PAGE
            )

        self._current_files = files
        self._current_total = total

        total_pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
        page_str = f"Page {self.current_page} of {total_pages}"

        tui.draw_header(self.writer, display_name, page_str)
        tui.draw_blank_line(self.writer)

        # Column header
        header = (
            f"   {col(BOLD + WHITE, '#'):>3}"
            f"  {col(BOLD + WHITE, 'Filename'):<18}"
            f"  {col(BOLD + WHITE, 'Size'):>7}"
            f"  {col(BOLD + WHITE, 'Description')}"
        )
        tui.draw_content_line(self.writer, header)

        sep = "  ── ────────────────── ─────── ─────────────────────────────────────────"
        tui.draw_content_line(self.writer, col(CYAN, sep))

        for i, f in enumerate(files, start=1):
            num = (self.current_page - 1) * PER_PAGE + i
            fname = truncate(f["filename"], 18)
            size_str = format_size(f["size"])
            # First line of description only
            desc_first = (f.get("description") or "").split("\n")[0]
            desc_trunc = truncate(desc_first, 36)

            row = (
                f"  {col(BRIGHT_YELLOW, str(num)):>3}"
                f"  {col(BRIGHT_WHITE, fname):<18}"
                f"  {col(CYAN, size_str):>7}"
                f"  {col(WHITE, desc_trunc)}"
            )
            tui.draw_content_line(self.writer, row)

        for _ in range(max(0, PER_PAGE - len(files))):
            tui.draw_blank_line(self.writer)

        tui.draw_blank_line(self.writer)
        footer_text = (
            col(BRIGHT_YELLOW, "[#]") + col(WHITE, " View file   ")
            + col(BRIGHT_YELLOW, "[N]") + col(WHITE, "ext   ")
            + col(BRIGHT_YELLOW, "[P]") + col(WHITE, "rev   ")
            + col(BRIGHT_YELLOW, "[S]") + col(WHITE, " Search   ")
            + col(BRIGHT_YELLOW, "[B]") + col(WHITE, "ack   ")
            + col(BRIGHT_YELLOW, "[Q]") + col(WHITE, "uit")
        )
        tui.draw_content_line(self.writer, "   " + footer_text)
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    def _render_file_detail(self) -> None:
        """Render the file detail view."""
        tui.clear_screen(self.writer)

        if self.current_file is None:
            tui.draw_box(self.writer, "Error", ["No file selected."])
            return

        with self._open_db() as db:
            detail = get_file_detail(db, self.current_file)

        if detail is None:
            tui.draw_box(self.writer, "Error", ["File not found in database."])
            return

        tui.draw_header(self.writer, "File Detail")
        tui.draw_blank_line(self.writer)

        def field(label: str, value: str) -> None:
            padded_label = f"{label}:"
            line = (
                f"   {col(BRIGHT_YELLOW, padded_label):<14}"
                f"  {col(BRIGHT_WHITE, value)}"
            )
            tui.draw_content_line(self.writer, line)

        field("Filename", detail["filename"])

        display_name, _ = CATEGORY_INFO.get(
            detail["area"], (detail["area"].title(), "")
        )
        field("Category", display_name)

        size_bytes = detail["size"]
        size_human = format_size(size_bytes)
        field("Size", f"{size_bytes:,} bytes ({size_human})")

        # Format mtime
        try:
            mtime_str = datetime.datetime.fromtimestamp(
                detail["mtime"]
            ).strftime("%Y-%m-%d")
        except Exception:
            mtime_str = "Unknown"
        field("Modified", mtime_str)

        tui.draw_blank_line(self.writer)
        tui.draw_separator(self.writer)
        tui.draw_blank_line(self.writer)

        # Full description
        description = detail.get("description") or "(no description available)"
        desc_lines = description.split("\n")
        for dline in desc_lines[:12]:  # cap at 12 lines
            tui.draw_content_line(
                self.writer, "   " + col(WHITE, truncate(dline, 72))
            )

        tui.draw_blank_line(self.writer)
        tui.draw_separator(self.writer)

        # HTTP URL
        rel_path = os.path.relpath(self.current_file, self.cpm_root)
        http_url = f"http://host:8080/{rel_path}"
        tui.draw_content_line(
            self.writer,
            "   " + col(CYAN, "HTTP: ") + col(WHITE, truncate(http_url, 68)),
        )
        tui.draw_blank_line(self.writer)

        footer_text = (
            col(BRIGHT_YELLOW, "[D]") + col(WHITE, "ownload   ")
            + col(BRIGHT_YELLOW, "[B]") + col(WHITE, "ack")
        )
        tui.draw_content_line(self.writer, "   " + footer_text)
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    def _render_search_input(self) -> None:
        """Render search input prompt screen."""
        tui.clear_screen(self.writer)
        tui.draw_header(self.writer, "Search CP/M Software Depot")
        tui.draw_blank_line(self.writer)
        tui.draw_content_line(
            self.writer,
            "   " + col(WHITE, "Enter search keywords (minimum 2 characters).")
        )
        tui.draw_content_line(
            self.writer,
            "   " + col(WHITE, "Matches filename and description.  Leave blank to cancel.")
        )
        tui.draw_blank_line(self.writer)
        # The actual prompt is written inline during _handle_search_input

    def _render_search_results(self) -> None:
        """Render the search results screen."""
        tui.clear_screen(self.writer)

        total_pages = max(
            1, (self._search_total + PER_PAGE - 1) // PER_PAGE
        )
        page_str = f"Page {self.search_page} of {total_pages}"
        header_right = f"{self._search_total} match{'es' if self._search_total != 1 else ''} found"

        tui.draw_header(
            self.writer,
            f'Search Results: "{self.search_query}"',
            header_right,
        )
        tui.draw_blank_line(self.writer)

        # Column header
        header = (
            f"   {col(BOLD + WHITE, '#'):>3}"
            f"  {col(BOLD + WHITE, 'Filename'):<18}"
            f"  {col(BOLD + WHITE, 'Size'):>6}"
            f"  {col(BOLD + WHITE, 'Area'):<12}"
            f"  {col(BOLD + WHITE, 'Description')}"
        )
        tui.draw_content_line(self.writer, header)

        sep = "  ── ────────────────── ────── ──────────── ─────────────────────────────"
        tui.draw_content_line(self.writer, col(CYAN, sep))

        for i, f in enumerate(self._search_results, start=1):
            num = (self.search_page - 1) * PER_PAGE + i
            fname = truncate(f["filename"], 18)
            size_str = format_size(f["size"])
            area_display, _ = CATEGORY_INFO.get(
                f.get("area", ""), (f.get("area", "").title(), "")
            )
            area_trunc = truncate(area_display, 12)
            desc_first = (f.get("description") or "").split("\n")[0]
            desc_trunc = truncate(desc_first, 28)

            row = (
                f"  {col(BRIGHT_YELLOW, str(num)):>3}"
                f"  {col(BRIGHT_WHITE, fname):<18}"
                f"  {col(CYAN, size_str):>6}"
                f"  {col(WHITE, area_trunc):<12}"
                f"  {col(WHITE, desc_trunc)}"
            )
            tui.draw_content_line(self.writer, row)

        for _ in range(max(0, PER_PAGE - len(self._search_results))):
            tui.draw_blank_line(self.writer)

        tui.draw_blank_line(self.writer)
        footer_text = (
            col(BRIGHT_YELLOW, "[#]") + col(WHITE, " View file   ")
            + col(BRIGHT_YELLOW, "[N]") + col(WHITE, "ext   ")
            + col(BRIGHT_YELLOW, "[P]") + col(WHITE, "rev   ")
            + col(BRIGHT_YELLOW, "[S]") + col(WHITE, " New search   ")
            + col(BRIGHT_YELLOW, "[B]") + col(WHITE, "ack   ")
            + col(BRIGHT_YELLOW, "[Q]") + col(WHITE, "uit")
        )
        tui.draw_content_line(self.writer, "   " + footer_text)
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    def _render_download(self) -> None:
        """Render the download protocol selection screen."""
        tui.clear_screen(self.writer)

        if self.current_file is None:
            tui.draw_box(self.writer, "Error", ["No file selected."])
            return

        with self._open_db() as db:
            detail = get_file_detail(db, self.current_file)

        fname = detail["filename"] if detail else os.path.basename(self.current_file)
        size_str = format_size(detail["size"]) if detail else "?"

        tui.draw_header(self.writer, "Download")
        tui.draw_blank_line(self.writer)
        tui.draw_content_line(
            self.writer,
            f"   {col(BRIGHT_YELLOW, 'File:')} {col(BRIGHT_WHITE, fname)} {col(CYAN, '(' + size_str + ')')}"
        )
        tui.draw_blank_line(self.writer)
        tui.draw_content_line(
            self.writer, "   " + col(WHITE, "Select transfer protocol:")
        )
        tui.draw_blank_line(self.writer)
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[Z]") + col(WHITE, " ZMODEM  ") + col(CYAN, "(recommended — use with SyncTERM)")
        )
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[X]") + col(WHITE, " XMODEM  ") + col(CYAN, "(portable, CRC-based transfer)")
        )
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[K]") + col(WHITE, " Kermit  ") + col(CYAN, "(7-bit safe terminal transfer)")
        )
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[R]") + col(WHITE, " Raw     ") + col(CYAN, "(direct binary transfer)")
        )
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[C]") + col(WHITE, " Cancel")
        )
        tui.draw_blank_line(self.writer)
        tui.draw_content_line(
            self.writer,
            "     " + col(BRIGHT_YELLOW, "[Q]") + col(WHITE, " Quit")
        )
        tui.draw_blank_line(self.writer)
        tui.draw_footer(self.writer)

    # ------------------------------------------------------------------
    # State machine handlers
    # ------------------------------------------------------------------

    async def _handle_welcome(self) -> str:
        """Wait for any key on the welcome screen."""
        self._render_welcome()
        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            if ch in ("\r", "\n", " "):
                return "CATEGORIES"
            # Any other key also advances
            return "CATEGORIES"

    async def _handle_categories(self) -> str:
        """Render categories and process key input."""
        self._render_categories()
        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            ch_upper = ch.upper()

            if ch_upper == "Q":
                return "QUIT"
            elif ch_upper == "S":
                self._search_back_state = "CATEGORIES"
                return "SEARCH_INPUT"
            elif ch_upper in CATEGORY_LETTERS:
                idx = CATEGORY_LETTERS.index(ch_upper)
                if idx < len(self._categories):
                    self.current_area = self._categories[idx][0]
                    self.current_page = 1
                    return "FILE_LIST"

    async def _handle_file_list(self) -> str:
        """Render file list and process key input."""
        self._render_file_list()

        # Buffer for multi-digit number entry
        num_buf: list[str] = []

        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            ch_upper = ch.upper()

            if ch.isdigit():
                num_buf.append(ch)
                self.write(ch)  # echo
                continue

            if ch in ("\r", "\n") and num_buf:
                # Process buffered number
                num = int("".join(num_buf))
                num_buf.clear()
                self.writeln()
                local_idx = num - (self.current_page - 1) * PER_PAGE - 1
                if 0 <= local_idx < len(self._current_files):
                    self.current_file = self._current_files[local_idx]["path"]
                    self._detail_back_state = "FILE_LIST"
                    return "FILE_DETAIL"
                else:
                    self.writeln(
                        f"   Invalid selection. Enter 1-{len(self._current_files)}."
                    )
                continue

            # Clear number buffer on non-digit/non-enter
            if num_buf:
                num_buf.clear()

            if ch_upper == "N":
                total_pages = max(
                    1, (self._current_total + PER_PAGE - 1) // PER_PAGE
                )
                if self.current_page < total_pages:
                    self.current_page += 1
                    return "FILE_LIST"
            elif ch_upper == "P":
                if self.current_page > 1:
                    self.current_page -= 1
                    return "FILE_LIST"
            elif ch_upper == "S":
                self._search_back_state = "FILE_LIST"
                return "SEARCH_INPUT"
            elif ch_upper == "B":
                return "CATEGORIES"
            elif ch_upper == "Q":
                return "QUIT"

    async def _handle_file_detail(self) -> str:
        """Render file detail and process key input."""
        self._render_file_detail()
        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            ch_upper = ch.upper()

            if ch_upper == "D":
                return "DOWNLOAD"
            elif ch_upper == "B":
                return self._detail_back_state
            elif ch_upper == "Q":
                return "QUIT"

    async def _handle_search_input(self) -> str:
        """Prompt for search query and execute search."""
        self._render_search_input()

        prompt = col(tui.BRIGHT_YELLOW, "   Search: ") + tui.RESET
        query = await self.read_line(prompt)

        if query is None:
            return "QUIT"

        if not query:
            # User cancelled
            return self._search_back_state

        if len(query) < 2:
            tui.draw_content_line(
                self.writer,
                col(tui.RED, "   Query must be at least 2 characters.  Press any key...")
            )
            await self.read_char()
            return "SEARCH_INPUT"

        self.search_query = query
        self.search_page = 1

        with self._open_db() as db:
            results, total = search_files(db, query, self.search_page, PER_PAGE)

        self._search_results = results
        self._search_total = total
        return "SEARCH_RESULTS"

    async def _handle_search_results(self) -> str:
        """Render search results and process key input."""
        self._render_search_results()

        num_buf: list[str] = []

        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            ch_upper = ch.upper()

            if ch.isdigit():
                num_buf.append(ch)
                self.write(ch)
                continue

            if ch in ("\r", "\n") and num_buf:
                num = int("".join(num_buf))
                num_buf.clear()
                self.writeln()
                local_idx = num - (self.search_page - 1) * PER_PAGE - 1
                if 0 <= local_idx < len(self._search_results):
                    self.current_file = self._search_results[local_idx]["path"]
                    self._detail_back_state = "SEARCH_RESULTS"
                    return "FILE_DETAIL"
                else:
                    self.writeln(
                        f"   Invalid selection. Enter 1-{len(self._search_results)}."
                    )
                continue

            if num_buf:
                num_buf.clear()

            if ch_upper == "N":
                total_pages = max(
                    1, (self._search_total + PER_PAGE - 1) // PER_PAGE
                )
                if self.search_page < total_pages:
                    self.search_page += 1
                    with self._open_db() as db:
                        self._search_results, _ = search_files(
                            db, self.search_query, self.search_page, PER_PAGE
                        )
                    return "SEARCH_RESULTS"
            elif ch_upper == "P":
                if self.search_page > 1:
                    self.search_page -= 1
                    with self._open_db() as db:
                        self._search_results, _ = search_files(
                            db, self.search_query, self.search_page, PER_PAGE
                        )
                    return "SEARCH_RESULTS"
            elif ch_upper == "S":
                return "SEARCH_INPUT"
            elif ch_upper == "B":
                return self._search_back_state
            elif ch_upper == "Q":
                return "QUIT"

    async def _handle_download(self) -> str:
        """Render download prompt and initiate transfer."""
        self._render_download()

        while True:
            ch = await self.read_char()
            if ch is None:
                return "QUIT"
            ch_upper = ch.upper()

            if ch_upper == "C":
                return "FILE_DETAIL"
            elif ch_upper == "Q":
                return "QUIT"

            if self.current_file is None:
                return "FILE_DETAIL"

            filepath = self.current_file
            if not os.path.isfile(filepath):
                self.writeln(
                    col(tui.RED, "\r\n   Error: file not found on disk.  Press any key...")
                )
                await self.read_char()
                return "FILE_DETAIL"

            if ch_upper == "Z":
                try:
                    from server.download import zmodem_send
                    if not await zmodem_send(filepath, self.reader, self._raw_writer):
                        self.writeln(
                            col(tui.RED, "   ZMODEM transfer failed.  Press any key...")
                        )
                        await self.read_char()
                except ImportError:
                    self.writeln(
                        col(tui.RED, "\r\n   Download module not available.  Press any key...")
                    )
                    await self.read_char()
                return "FILE_DETAIL"

            elif ch_upper == "X":
                try:
                    from server.download import xmodem_send
                    if not await xmodem_send(filepath, self.reader, self._raw_writer):
                        self.writeln(
                            col(tui.RED, "   XMODEM transfer failed.  Press any key...")
                        )
                        await self.read_char()
                except ImportError:
                    self.writeln(
                        col(tui.RED, "\r\n   Download module not available.  Press any key...")
                    )
                    await self.read_char()
                return "FILE_DETAIL"

            elif ch_upper == "K":
                try:
                    from server.download import kermit_send
                    if not await kermit_send(filepath, self.reader, self._raw_writer):
                        self.writeln(
                            col(tui.RED, "   Kermit transfer failed.  Press any key...")
                        )
                        await self.read_char()
                except ImportError:
                    self.writeln(
                        col(tui.RED, "\r\n   Download module not available.  Press any key...")
                    )
                    await self.read_char()
                return "FILE_DETAIL"

            elif ch_upper == "R":
                try:
                    from server.download import raw_send
                    if not await raw_send(filepath, self._raw_writer):
                        self.writeln(
                            col(tui.RED, "   Raw transfer failed.  Press any key...")
                        )
                        await self.read_char()
                except ImportError:
                    self.writeln(
                        col(tui.RED, "\r\n   Download module not available.  Press any key...")
                    )
                    await self.read_char()
                return "FILE_DETAIL"

    # ------------------------------------------------------------------
    # Main session loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Run the session state machine until QUIT or disconnect."""
        state_handlers = {
            "WELCOME": self._handle_welcome,
            "CATEGORIES": self._handle_categories,
            "FILE_LIST": self._handle_file_list,
            "FILE_DETAIL": self._handle_file_detail,
            "SEARCH_INPUT": self._handle_search_input,
            "SEARCH_RESULTS": self._handle_search_results,
            "DOWNLOAD": self._handle_download,
        }

        while self.state != "QUIT":
            handler = state_handlers.get(self.state)
            if handler is None:
                log.warning("Unknown state: %s — resetting to CATEGORIES", self.state)
                self.state = "CATEGORIES"
                continue
            try:
                next_state = await handler()
            except Exception as exc:
                log.exception("Error in state %s: %s", self.state, exc)
                next_state = "CATEGORIES"

            if next_state is None:
                next_state = "QUIT"
            self.state = next_state

        # Goodbye
        tui.clear_screen(self.writer)
        tui.draw_box(
            self.writer,
            "Goodbye",
            [
                "",
                "   " + col(BRIGHT_CYAN, "Thank you for using the CP/M Software Depot!"),
                "",
                "   " + col(WHITE, "Goodbye and happy hacking."),
                "",
            ],
        )
        try:
            self.writer.close()
        except Exception:
            pass
        log.info("Session ended cleanly.")


# ---------------------------------------------------------------------------
# Telnet shell coroutine
# ---------------------------------------------------------------------------


async def shell(
    reader: telnetlib3.TelnetReader,
    writer: telnetlib3.TelnetWriter,
    db_path: str,
    cpm_root: str,
) -> None:
    """Called by telnetlib3 for each incoming connection."""
    peer = writer.get_extra_info("peername", default=("?", 0))
    log.info("Connection from %s:%s", peer[0], peer[1])

    session = Session(reader, writer, db_path, cpm_root)
    try:
        await session.run()
    except Exception as exc:
        log.exception("Unhandled exception in session: %s", exc)
    finally:
        try:
            writer.close()
        except Exception:
            pass
        log.info("Connection closed: %s:%s", peer[0], peer[1])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CP/M Software Depot — Telnet BBS Server"
    )
    parser.add_argument(
        "--db",
        required=True,
        metavar="PATH",
        help="Path to SQLite database file",
    )
    parser.add_argument(
        "--cpm-root",
        required=True,
        metavar="PATH",
        help="Path to CP/M file archive root directory",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=2323,
        metavar="PORT",
        help="Telnet listen port (default: 2323)",
    )
    return parser.parse_args()


async def main_async(db_path: str, cpm_root: str, port: int) -> None:
    """Async main: create server, run until signal."""
    loop = asyncio.get_event_loop()

    def make_shell(reader: telnetlib3.TelnetReader, writer: telnetlib3.TelnetWriter) -> "asyncio.Task":
        return asyncio.ensure_future(shell(reader, writer, db_path, cpm_root))

    server = await telnetlib3.create_server(
        host="",
        port=port,
        shell=make_shell,
        encoding="utf-8",
        connect_maxwait=5.0,
    )

    log.info("CP/M Software Depot listening on port %d", port)

    stop_event = asyncio.Event()

    def _handle_signal() -> None:
        log.info("Shutdown signal received.")
        stop_event.set()

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, _handle_signal)

    await stop_event.wait()

    log.info("Shutting down server...")
    server.close()
    await server.wait_closed()
    log.info("Server stopped.")


def main() -> None:
    args = parse_args()

    if not os.path.isfile(args.db):
        log.warning("Database not found at %s — server will start anyway.", args.db)

    try:
        asyncio.run(main_async(args.db, args.cpm_root, args.port))
    except KeyboardInterrupt:
        log.info("Interrupted.")


if __name__ == "__main__":
    main()
