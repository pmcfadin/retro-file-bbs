# CP/M Software Depot — Technical Spec v3

**Owner:** Patrick (Scout Dog AI Studios)
**Version:** 3.0 — Custom Telnet File Browser

---

## 1. Goal & Scope

Run a telnet file-browsing server inside a container that serves a CP/M software archive. Users connect via any telnet client (SyncTERM, netrunner, PuTTY, xterm+telnet) and navigate ANSI menus to browse categories, read file descriptions, search, and download files via ZMODEM or raw transfer.

**Explicitly:** No BBS engine. No Synchronet, Mystic, or any third-party BBS software. This is a purpose-built Python telnet application that does one thing well: serve files.

**In scope (v3):**
- Telnet file browser with ANSI TUI
- Category browsing with paginated file listings
- Keyword search across filenames and descriptions
- ZMODEM and raw file downloads
- HTTP static file mirror on port 8080
- Automated indexer pipeline (existing scan.py + describe.py)

**Out of scope:** User accounts, messaging, chat, uploads, FidoNet, QWK networking, FTP.

---

## 2. Architecture

```
[Client: SyncTERM / telnet]  ==(TCP :2323)==>  [Docker Container]
                                                 ├─ telnetlib3 server (Python)
                                                 │   ├─ TUI renderer (blessed)
                                                 │   ├─ File browser (SQLite queries)
                                                 │   ├─ Search engine
                                                 │   └─ ZMODEM downloads (lrzsz subprocess)
                                                 ├─ Indexer pipeline (runs at startup)
                                                 │   ├─ scan.py   → SQLite
                                                 │   └─ describe.py → SQLite
                                                 ├─ HTTP static server (:8080)
                                                 └─ Volumes:
                                                     ├─ /data/cpm (bind-mount, read-only)
                                                     └─ /data/index.db (SQLite)
```

**Components:**

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Telnet server | telnetlib3 (async) | Accept connections, manage sessions |
| TUI rendering | blessed | ANSI colors, box drawing, cursor control |
| Data layer | SQLite (stdlib) | File metadata, search, pagination |
| Downloads | lrzsz (`sz`) | ZMODEM file transfer via subprocess |
| HTTP mirror | Python http.server | Static file serving on :8080 |
| Indexer | scan.py + describe.py | Catalog files, extract descriptions |

---

## 3. User Flows

### 3.1 Connect → Welcome

1. User telnets to host:2323
2. Server detects terminal type (ANSI assumed, graceful ASCII fallback)
3. Welcome screen displays: banner art, system info, file stats
4. User presses Enter → category list (main menu)

### 3.2 Browse Categories

1. Category list shows all 12 areas with file counts
2. User types a number or letter to select a category
3. → File listing for that category

### 3.3 Browse Files in Category

1. File listing shows: filename, size, one-line description
2. 20 files per page, with [N]ext / [P]rev / [B]ack navigation
3. User types a file number → file detail view
4. User types [S] → search mode
5. User types [B] → back to category list

### 3.4 File Detail View

1. Shows: filename, size, date, full multi-line description
2. Options: [D]ownload, [B]ack to listing
3. If HTTP mirror is enabled, shows download URL

### 3.5 Search

1. User enters search keywords (min 2 characters)
2. Search matches against filename and description (LIKE query)
3. Results displayed as paginated file listing
4. User can select a file → detail view
5. [B]ack returns to previous screen

### 3.6 Download

1. User selects [D]ownload from file detail
2. Prompt: [Z]MODEM, [R]aw, or [C]ancel
3. ZMODEM: subprocess `sz` with file path, client receives
4. Raw: stream file bytes directly over telnet connection
5. Return to file detail after transfer

### 3.7 Quit

1. [Q] from any screen → goodbye message → disconnect

---

## 4. Screen Mockups

All screens use single-line box drawing (─│┌┐└┘), cyan/yellow/white palette.
Terminal width: 80 columns. Height: 24 lines minimum.

### 4.1 Welcome Screen

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│     ██████╗██████╗ ██╗███╗   ███╗                                            │
│    ██╔════╝██╔══██╗██║████╗ ████║                                            │
│    ██║     ██████╔╝██║██╔████╔██║                                            │
│    ██║     ██╔═══╝ ██║██║╚██╔╝██║                                            │
│    ╚██████╗██║     ██║██║ ╚═╝ ██║                                            │
│     ╚═════╝╚═╝     ╚═╝╚═╝     ╚═╝                                           │
│               S O F T W A R E   D E P O T                                    │
│                                                                              │
│                   ── Serving the CP/M Community ──                           │
│                                                                              │
│    12 Categories  ·  299 Files  ·  ZMODEM Downloads                          │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                   Press [ENTER] to continue...                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Colors: Banner text in bright cyan, "SOFTWARE DEPOT" in yellow, stats in white, border in cyan.

### 4.2 Category List (Main Menu)

```
┌─ CP/M Software Depot ────────────────────────────────────────────────────────┐
│                                                                              │
│   #   Category         Files   Description                                   │
│  ─── ──────────────── ─────── ──────────────────────────────────────────     │
│   A   Archivers           22   Archive/compression tools (ARC, LBR, etc.)    │
│   B   Comm                18   Communications & modem programs               │
│   C   Editors             15   Text editors & word processors                │
│   D   FAQ                  8   Frequently asked questions & guides           │
│   E   Printer             12   Printer utilities & drivers                   │
│   F   Prod                25   Productivity & office tools                   │
│   G   Programming         45   Compilers, assemblers, & dev tools            │
│   H   Sys                 38   System utilities & OS patches                 │
│   I   Texts               20   Documentation & reference material            │
│   J   Transfer            14   File transfer protocols & tools               │
│   K   Unsorted            52   Uncategorized files                           │
│   L   Zutils              30   Z-System utilities                            │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│   [A-L] Select category   [S] Search   [Q] Quit                             │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Colors: Header in bright cyan, letters in yellow, category names in white, file counts in cyan.

### 4.3 File Listing

```
┌─ Archivers ──────────────────────────────────────────────── Page 1 of 2 ─────┐
│                                                                              │
│   #  Filename         Size    Description                                    │
│  ── ──────────────── ─────── ────────────────────────────────────────────    │
│   1  ARC521.LBR        32K   ARC file archiver v5.21 for CP/M               │
│   2  CRUNCH28.LBR      16K   File cruncher/uncruncher v2.8                   │
│   3  DELBR12.COM        4K   Extract files from LBR libraries                │
│   4  LT31.LBR          24K   Library tool v3.1 — create/manage LBR          │
│   5  LSWEEP14.LBR      20K   Sweep utility for LBR file management          │
│   6  NULU152.LBR       48K   New Utility for LBR files v1.52                 │
│   7  UNARC16.COM        8K   Extract ARC archives                            │
│   8  UNZIP101.COM      12K   Extract ZIP archives under CP/M                 │
│   9  ZIPFILES.TXT       2K   Guide to ZIP format under CP/M                  │
│  10  ARCE.COM           6K   ARC file extraction utility                     │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│   [#] View file   [N]ext   [P]rev   [S] Search   [B]ack   [Q]uit            │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

Colors: Header/category name in yellow, filenames in bright white, sizes in cyan, descriptions in white.

### 4.4 File Detail View

```
┌─ File Detail ────────────────────────────────────────────────────────────────┐
│                                                                              │
│   Filename:  ARC521.LBR                                                      │
│   Category:  Archivers                                                       │
│   Size:      32,768 bytes (32K)                                              │
│   Modified:  1987-03-15                                                      │
│                                                                              │
│  ─────────────────────────────────────────────────────────────────────────   │
│                                                                              │
│   ARC File Archiver v5.21 for CP/M-80                                        │
│                                                                              │
│   Full-featured archive utility supporting creation,                         │
│   extraction, and management of .ARC format files.                           │
│   Compatible with MS-DOS ARC format. Supports                                │
│   Squeeze and Crunch compression methods.                                    │
│                                                                              │
│   Originally by System Enhancement Associates,                               │
│   CP/M port by Howard Goldstein.                                             │
│                                                                              │
│  ─────────────────────────────────────────────────────────────────────────   │
│   HTTP: http://host:8080/cpm/archivers/ARC521.LBR                           │
│                                                                              │
│   [D]ownload   [B]ack                                                        │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.5 Search Results

```
┌─ Search Results: "arc" ──────────────────────────────── 5 matches found ─────┐
│                                                                              │
│   #  Filename         Size   Area          Description                        │
│  ── ──────────────── ────── ──────────── ──────────────────────────────────  │
│   1  ARC521.LBR       32K   Archivers    ARC file archiver v5.21            │
│   2  ARCE.COM          6K   Archivers    ARC extraction utility              │
│   3  UNARC16.COM       8K   Archivers    Extract ARC archives               │
│   4  MARC.COM          4K   Zutils       Member ARC — ZCPR3 archive tool    │
│   5  ARCZ.DOC          3K   Texts        Guide to ARC tools under CP/M      │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│                                                                              │
│   [#] View file   [S] New search   [B]ack   [Q]uit                           │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 4.6 Download Prompt

```
┌─ Download ───────────────────────────────────────────────────────────────────┐
│                                                                              │
│   File: ARC521.LBR (32K)                                                     │
│                                                                              │
│   Select transfer protocol:                                                  │
│                                                                              │
│     [Z] ZMODEM  (recommended — use with SyncTERM)                            │
│     [R] Raw     (direct binary transfer)                                     │
│     [C] Cancel                                                               │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Indexer Pipeline

Carried forward from v2. The indexer is proven and unchanged.

### 5.1 scan.py

Walks the CP/M file archive directory tree. For each file:
- Records path, area (top-level directory name), filename, size, mtime
- Upserts into SQLite `files` table
- Skips unchanged files (same mtime + size) for incremental updates

### 5.2 describe.py

For each undescribed file in the database:
1. **ZIP archives:** Extract FILE_ID.DIZ, then README/DOC/TXT
2. **LBR archives:** Parse 32-byte directory entries, extract descriptive files
3. **ARC archives:** Parse header blocks, look for FILE_ID.DIZ/README
4. **Sibling files:** Check for companion .DOC/.TXT/README in same directory
5. **Heuristic fallback:** Generate one-liner from filename tokens

Output: normalized text (72 cols, 10 lines max, control chars stripped).

### 5.3 SQLite Schema

```sql
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    area TEXT NOT NULL,
    filename TEXT NOT NULL,
    size INTEGER NOT NULL,
    mtime REAL NOT NULL,
    description TEXT DEFAULT '',
    described INTEGER DEFAULT 0
);
```

### 5.4 Categories (12 areas)

| Area | Description |
|------|-------------|
| archivers | Archive & compression tools |
| comm | Communications & modem programs |
| editors | Text editors & word processors |
| faq | FAQs & guides |
| printer | Printer utilities & drivers |
| prod | Productivity & office tools |
| programming | Compilers, assemblers, dev tools |
| sys | System utilities & OS patches |
| texts | Documentation & reference |
| transfer | File transfer protocols & tools |
| unsorted | Uncategorized files |
| zutils | Z-System utilities |

---

## 6. Tech Stack

| Dependency | Version | Purpose |
|-----------|---------|---------|
| Python | 3.11+ | Runtime |
| telnetlib3 | latest | Async telnet server (RFC 854) |
| blessed | latest | Terminal capabilities, ANSI rendering |
| lrzsz | system pkg | ZMODEM transfers (`sz` binary) |
| SQLite | stdlib | File metadata database |

**No other external dependencies.** The indexer uses stdlib only.

---

## 7. Docker Setup

### 7.1 Dockerfile

```dockerfile
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends lrzsz && \
    rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir telnetlib3 blessed

COPY indexer/ /app/indexer/
COPY server/  /app/server/
COPY entrypoint.sh /app/

WORKDIR /app
RUN chmod +x entrypoint.sh

EXPOSE 2323 8080

ENTRYPOINT ["/app/entrypoint.sh"]
```

### 7.2 docker-compose.yml

```yaml
services:
  cpmdepot:
    build: .
    container_name: cpmdepot
    ports:
      - "2323:2323"   # telnet
      - "8080:8080"   # HTTP mirror
    volumes:
      - ./cpm:/data/cpm:ro
      - index_data:/data
    environment:
      - TZ=America/Los_Angeles
    restart: unless-stopped

volumes:
  index_data:
```

### 7.3 entrypoint.sh

```bash
#!/bin/bash
set -e

DB_PATH="/data/index.db"
CPM_ROOT="/data/cpm"

echo "=== CP/M Software Depot ==="

# Run indexer pipeline
if [ -d "$CPM_ROOT" ]; then
    echo "Step 1/2: Scanning file areas..."
    python3 /app/indexer/scan.py "$CPM_ROOT" "$DB_PATH"

    echo "Step 2/2: Extracting descriptions..."
    python3 /app/indexer/describe.py "$DB_PATH"
else
    echo "Warning: No CP/M files at $CPM_ROOT"
fi

# Start HTTP mirror in background
echo "Starting HTTP mirror on :8080..."
python3 -m http.server 8080 --directory "$CPM_ROOT" &

# Start telnet server
echo "Starting telnet server on :2323..."
exec python3 /app/server/main.py --db "$DB_PATH" --cpm-root "$CPM_ROOT" --port 2323
```

---

## 8. HTTP Mirror

A simple static file server on port 8080, serving the CP/M archive directory directly.

- Uses Python's built-in `http.server` module (no additional dependencies)
- Read-only access to the same bind-mounted `/data/cpm` directory
- Directory listing enabled for browser-based browsing
- File detail view shows the corresponding HTTP URL for out-of-band downloads

---

## 9. Server Application Structure

```
server/
  main.py       — telnetlib3 server entry point, connection handler
  tui.py        — ANSI screen rendering: boxes, colors, pagination
  browser.py    — Category/file browsing logic, SQLite queries
  search.py     — Keyword search across filename + description
  download.py   — ZMODEM (sz subprocess) and raw transfer
```

### 9.1 main.py

- Creates async telnetlib3 server on port 2323
- Each connection gets a session with its own state machine
- States: WELCOME → CATEGORIES → FILE_LIST → FILE_DETAIL → SEARCH → DOWNLOAD
- Handles terminal negotiation (NAWS for window size, TTYPE for terminal type)

### 9.2 tui.py

- Box drawing with single-line Unicode characters (─│┌┐└┘)
- Color palette: cyan borders, yellow highlights, white text
- Pagination helper: given items + page size, renders page N of M
- Clear screen, cursor positioning, status bar

### 9.3 browser.py

- `get_categories()` → list of (area, file_count) from SQLite
- `get_files(area, page, per_page)` → paginated file list
- `get_file_detail(path)` → full file metadata
- `get_total_stats()` → total files, total categories for welcome screen

### 9.4 search.py

- `search_files(query, page, per_page)` → results matching filename OR description
- Uses SQLite LIKE with wildcards: `WHERE filename LIKE ? OR description LIKE ?`
- Minimum 2-character query

### 9.5 download.py

- `zmodem_send(filepath, writer)` → subprocess `sz` with file path
- `raw_send(filepath, writer)` → stream bytes directly over connection
- Error handling for missing files, transfer failures

---

## 10. Acceptance Criteria

1. **Container starts:** `docker compose up --build` succeeds; telnet server listens on host :2323.
2. **Welcome screen:** Connect via SyncTERM/telnet → see banner with file stats → press Enter.
3. **Category browsing:** Category list shows 12 areas with file counts → select one → paginated file listing.
4. **File details:** Select a file → see full description, size, date, download options.
5. **Search:** Press [S] → enter keyword → see matching results across all categories.
6. **ZMODEM download:** Select file → choose ZMODEM → successful transfer via SyncTERM.
7. **Raw download:** Select file → choose Raw → file transfers over telnet connection.
8. **HTTP mirror:** Same file accessible at `http://host:8080/archivers/ARC521.LBR`.
9. **Pagination:** Categories with >20 files show paged listings with next/prev navigation.
10. **No login required:** No username, password, email, or registration prompts of any kind.
11. **Performance:** Page rendering ≤ 500ms; search results ≤ 1s for full catalog.
12. **Graceful disconnect:** [Q] from any screen → goodbye → clean connection close.

---

## 11. Deliverables

- `docker-compose.yml` — single-container setup
- `Dockerfile` — Python 3.11-slim + lrzsz + telnetlib3 + blessed
- `entrypoint.sh` — indexer pipeline + server startup
- `server/main.py` — telnet server entry point
- `server/tui.py` — ANSI TUI rendering
- `server/browser.py` — file browsing logic
- `server/search.py` — keyword search
- `server/download.py` — ZMODEM/raw transfers
- `indexer/scan.py` — file scanner (existing, unchanged)
- `indexer/describe.py` — description extractor (existing, unchanged)

---

End of Spec v3 (Custom Telnet File Browser)
