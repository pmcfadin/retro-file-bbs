# CP/M Software Depot — Implementation Tasks

Ordered by dependency. Each task builds on the previous.

---

## Task 1: Project Scaffolding & Cleanup

**Remove Synchronet artifacts, set up new project structure.**

- Delete `sbbs/` directory
- Delete `indexer/sync_synchronet.py`
- Create `server/` directory with empty `__init__.py`
- Update `.dockerignore` for new structure
- Keep: `indexer/scan.py`, `indexer/describe.py`, `cpm/`

**Files:** `sbbs/`, `indexer/sync_synchronet.py`, `server/__init__.py`, `.dockerignore`
**Depends on:** nothing
**Complexity:** low

---

## Task 2: Telnet Server Skeleton

**Async telnetlib3 server that accepts connections and echoes input.**

- `server/main.py`: telnetlib3 async server on configurable port (default 2323)
- Connection handler with per-session state
- Terminal negotiation: NAWS (window size), TTYPE (terminal type)
- Argument parsing: `--db`, `--cpm-root`, `--port`
- Graceful shutdown on SIGTERM/SIGINT

**Files:** `server/main.py`
**Depends on:** Task 1
**Complexity:** medium

---

## Task 3: TUI Rendering Framework

**ANSI screen rendering: boxes, colors, pagination helpers.**

- `server/tui.py`: box drawing with ─│┌┐└┘ characters
- Color constants: cyan borders, yellow highlights, white text (ANSI escape codes)
- `draw_box(width, height, title)` — render bordered screen
- `draw_table(headers, rows, widths)` — columnar layout
- `paginate(items, page, per_page)` — return page slice + "Page N of M" string
- `clear_screen()`, `move_cursor(row, col)`, `status_bar(text)`
- Support for 80x24 minimum terminal size

**Files:** `server/tui.py`
**Depends on:** Task 2
**Complexity:** medium

---

## Task 4: Data Layer (Browser Module)

**SQLite query functions for browsing categories and files.**

- `server/browser.py`: all database access for the TUI
- `get_categories(db_path)` → list of `(area, file_count, description)` sorted alphabetically
- `get_files(db_path, area, page, per_page)` → paginated file list with total count
- `get_file_detail(db_path, path)` → full file record
- `get_total_stats(db_path)` → `(total_files, total_categories)`
- Category display names and descriptions (hardcoded mapping for the 12 known areas)

**Files:** `server/browser.py`
**Depends on:** Task 1 (needs existing SQLite schema from scan.py)
**Complexity:** low

---

## Task 5: Welcome Screen

**Banner art + stats display + press Enter to continue.**

- Render CP/M ASCII art banner (from spec mockup §4.1)
- Show dynamic stats: category count, file count (from browser.get_total_stats)
- Wait for Enter keypress
- Transition to category list

**Files:** `server/main.py` (state machine), `server/tui.py` (welcome renderer)
**Depends on:** Tasks 3, 4
**Complexity:** low

---

## Task 6: Category Browser (Main Menu)

**List all categories with file counts, select to browse.**

- Render category list screen (spec mockup §4.2)
- Letter-key selection (A–L maps to category)
- Show: letter, category name, file count, one-line description
- [S] for search, [Q] for quit
- Transition to file listing on selection

**Files:** `server/main.py` (state machine), `server/tui.py` (category renderer)
**Depends on:** Tasks 4, 5
**Complexity:** low

---

## Task 7: File Listing with Pagination

**Paginated file list within a category.**

- Render file listing screen (spec mockup §4.3)
- Show: number, filename, size (human-readable), one-line description
- 20 files per page
- Navigation: [N]ext page, [P]rev page, [B]ack to categories
- Number selection → file detail view
- [S] for search from file listing

**Files:** `server/main.py` (state machine), `server/tui.py` (file list renderer)
**Depends on:** Tasks 4, 6
**Complexity:** medium

---

## Task 8: File Detail View

**Full file info with description and download option.**

- Render file detail screen (spec mockup §4.4)
- Show: filename, category, size (bytes + human), modified date
- Full multi-line description (up to 10 lines from describe.py)
- HTTP mirror URL (if enabled)
- Navigation: [D]ownload, [B]ack to listing

**Files:** `server/main.py` (state machine), `server/tui.py` (detail renderer)
**Depends on:** Tasks 4, 7
**Complexity:** low

---

## Task 9: Search

**Keyword search across filenames and descriptions.**

- `server/search.py`: SQLite LIKE queries with wildcard wrapping
- `search_files(db_path, query, page, per_page)` → paginated results with area column
- Minimum 2-character query, max 50 characters
- Render search results screen (spec mockup §4.5)
- Shows area column in addition to filename/size/description
- Navigation: [#] view file, [S] new search, [B]ack, [Q]uit
- Accessible from category list and file listing via [S] key

**Files:** `server/search.py`, `server/main.py` (state machine), `server/tui.py` (search renderer)
**Depends on:** Tasks 4, 7
**Complexity:** medium

---

## Task 10: ZMODEM Download

**File transfers via lrzsz subprocess.**

- `server/download.py`: ZMODEM and raw transfer implementations
- `zmodem_send(filepath, transport)` — spawn `sz` subprocess, pipe to telnet transport
- `raw_send(filepath, transport)` — stream file bytes directly
- Download prompt screen (spec mockup §4.6): [Z]MODEM, [R]aw, [C]ancel
- Error handling: file not found, transfer interrupted, sz not available
- Return to file detail after transfer completes or fails

**Files:** `server/download.py`, `server/main.py` (state machine), `server/tui.py` (download prompt)
**Depends on:** Task 8
**Complexity:** high

---

## Task 11: Dockerfile & docker-compose.yml

**Container setup for the new architecture.**

- `Dockerfile`: Python 3.11-slim base, install lrzsz, pip install telnetlib3 + blessed
- Copy indexer/ and server/ into image
- `docker-compose.yml`: single service, ports 2323 + 8080, bind-mount cpm/ read-only
- `entrypoint.sh`: run indexer pipeline, start HTTP mirror (background), start telnet server
- Named volume for SQLite database persistence

**Files:** `Dockerfile`, `docker-compose.yml`, `entrypoint.sh`
**Depends on:** Tasks 2–10 (needs working server)
**Complexity:** low

---

## Task 12: HTTP Mirror

**Static file server on port 8080.**

- Python `http.server` serving `/data/cpm` directory
- Launched as background process in entrypoint.sh
- Directory listing enabled for browser browsing
- No authentication required

**Files:** `entrypoint.sh`
**Depends on:** Task 11
**Complexity:** low

---

## Task 13: End-to-End Testing

**Manual test plan + smoke test script.**

- Connect via SyncTERM to host:2323
- Verify: welcome screen → Enter → category list
- Verify: select category → file listing with pagination
- Verify: select file → detail view with description
- Verify: search → results across categories
- Verify: ZMODEM download completes successfully
- Verify: raw download completes successfully
- Verify: HTTP mirror serves files at :8080
- Verify: [Q] disconnects cleanly from any screen
- Optional: simple pytest script that connects via telnetlib3 client and asserts screen content

**Files:** `tests/test_smoke.py` (optional)
**Depends on:** Tasks 11, 12
**Complexity:** medium

---

## Summary

| Task | Description | Complexity | Depends on |
|------|-------------|-----------|------------|
| 1 | Project scaffolding & cleanup | Low | — |
| 2 | Telnet server skeleton | Medium | 1 |
| 3 | TUI rendering framework | Medium | 2 |
| 4 | Data layer (browser module) | Low | 1 |
| 5 | Welcome screen | Low | 3, 4 |
| 6 | Category browser | Low | 4, 5 |
| 7 | File listing + pagination | Medium | 4, 6 |
| 8 | File detail view | Low | 4, 7 |
| 9 | Search | Medium | 4, 7 |
| 10 | ZMODEM download | High | 8 |
| 11 | Dockerfile + compose | Low | 2–10 |
| 12 | HTTP mirror | Low | 11 |
| 13 | End-to-end testing | Medium | 11, 12 |

**Critical path:** 1 → 2 → 3 → 5 → 6 → 7 → 8 → 10 → 11 → 13

**Parallelizable:** Tasks 3 and 4 can run in parallel after Task 1.
