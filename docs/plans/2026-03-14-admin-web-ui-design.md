# CP/M Software Depot — Admin Web UI Design

**Date:** 2026-03-14
**Owner:** Patrick (Scout Dog AI Studios)

---

## 1. Purpose

A web-based admin interface for managing the CP/M Software Depot BBS. This is a single-operator tool — not a public-facing site. It runs alongside the telnet server in the same container, served on port 8080, replacing the bare `python3 -m http.server` mirror.

**Use cases:**
- Browse and search the indexed file catalog
- Edit file descriptions and metadata
- Upload new files (including extract from ZIP/DSK archives)
- Monitor active telnet sessions, recent connections, and server logs
- Trigger the indexer pipeline on demand
- View indexer status and output

---

## 2. Architecture

### Process Model

Single Python process running both the telnet server and FastAPI in the same asyncio event loop. Uvicorn hosts FastAPI; telnetlib3 runs alongside it.

Benefits:
- Shared memory for session tracking (no IPC)
- Single process to manage, no supervisor needed
- Monitor feature reads telnet session state directly from memory

### Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Backend | FastAPI + uvicorn | REST API, websocket streams, static file serving |
| Frontend | React (SPA) | Admin interface, built at Docker image build time |
| Database | SQLite (WAL mode) | Shared with telnet server, concurrent read/write safe |
| File ops | Filesystem + cpmtools | Direct manipulation of `/data/cpm`, DSK extraction |

### Container Changes

- Dockerfile adds: Node.js (build stage only), cpmtools, uvicorn + fastapi
- `entrypoint.sh` changes: remove `http.server` background process; `main.py` now starts both telnet and web
- Port 8080 now serves the admin UI instead of a static directory listing

```
[Browser]  ==(HTTP :8080)==>  [FastAPI]  ==> SQLite / filesystem / telnet session dict
[Telnet]   ==(TCP :2323)===>  [telnetlib3]  ==> SQLite / filesystem
                              └── same asyncio loop, same process
```

---

## 3. Pages & Navigation

Sidebar navigation styled like a terminal menu. Five sections:

### 3.1 Files (default landing page)

- Table view of all indexed files: filename, category, size, description preview
- Search/filter bar across filename and description
- Click a row to open edit panel: modify description, change category, delete
- Bulk actions: select multiple, move to category, delete

### 3.2 Upload

- Drag-and-drop zone or file picker
- Target category selector (dropdown of existing areas)
- Extract toggle for ZIP/DSK files:
  - Uploads archive, extracts server-side to staging directory
  - Shows extracted contents for review (table with checkboxes)
  - User selects files to keep, confirms commit to catalog
- Auto-triggers indexer after upload/extract

### 3.3 Monitor

- Active telnet sessions: client IP, connect time, current screen/state, duration
- Recent connections list: last 50 with connect/disconnect times
- Scrolling log viewer: tails server log in real-time via websocket

### 3.4 Indexer

- Status of last run: timestamp, files scanned, descriptions extracted
- "Run Now" button to trigger scan.py + describe.py
- Live output stream while running (websocket)

### 3.5 Settings

- Sparse for now. A place to land future configuration.

---

## 4. API Design

### Files

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/files` | List files. Query params: `search`, `area`, `page`, `per_page` |
| GET | `/api/files/{path}` | Single file detail (metadata + full description) |
| PATCH | `/api/files/{path}` | Update description or category |
| DELETE | `/api/files/{path}` | Remove file from disk and database |

### Upload & Extract

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/upload` | Multipart file upload with target area |
| POST | `/api/extract` | Upload ZIP/DSK, extract to staging, return file list |
| POST | `/api/extract/commit` | Confirm extracted files, move to target area |

### Categories

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/categories` | List all areas with file counts |

### Monitor

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/sessions` | Active telnet sessions |
| GET | `/api/connections` | Recent connection history |
| WS | `/api/logs` | Websocket stream tailing server log |

### Indexer

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/indexer/status` | Last run timestamp, file counts |
| POST | `/api/indexer/run` | Trigger scan + describe pipeline |
| WS | `/api/indexer/output` | Stream indexer stdout while running |

---

## 5. File Extract Workflow

### ZIP files

1. User uploads `.zip` via Upload page
2. Server extracts to `/data/staging/{uuid}/`
3. UI shows table of extracted files with checkboxes: filename, size, detected type
4. User selects files to keep, picks target category
5. "Commit" moves selected files into `/data/cpm/{area}/`, deletes staging dir
6. Indexer runs automatically on new files

### DSK (disk image) files

1. Same staging flow, but uses `cpmtools` (`cpmls`, `cpmcp`) to read the CP/M filesystem
2. Extract contents to staging dir, present for review, commit to category
3. Requires `cpmtools` package in Dockerfile

### Edge cases

- **Duplicate filenames:** Warning shown, user can skip or overwrite
- **Nested archives:** Top-level extraction only. User can re-upload inner archives.
- **Cleanup:** Staging dirs older than 24 hours purged on server start

---

## 6. Frontend Aesthetic

Terminal/CRT visual language throughout. No modern UI patterns.

### Colors

| Role | Value | Description |
|------|-------|-------------|
| Background | `#0a0a0a` | Near-black |
| Primary text | `#33ff33` | Phosphor green |
| Secondary text | `#00aa00` | Dim green |
| Accent | `#ffaa00` | Amber (selections, buttons) |
| Error | `#ff3333` | Red |
| Borders | `#1a3a1a` | Subtle dark green |

### Typography

- `IBM Plex Mono` primary, `Courier New` fallback
- Monospace everywhere. No sans-serif.

### UI Elements

- Sidebar nav: terminal menu style (`> FILES`, `  UPLOAD`, `  MONITOR`)
- Tables: ASCII-style borders or simple ruled lines
- Buttons: terminal command style (`[ RUN INDEXER ]`, `[ DELETE ]`)
- Subtle CRT scanline overlay + text glow (toggle-able)
- Log/indexer output: raw terminal rendering, scrolling monospace

### Interactions

- Minimal animation — things appear, no slides or fades
- Status messages inline: `> File uploaded successfully.`
- Destructive confirmations: `Delete ARC521.LBR? [Y/N]`

---

## 7. Session Tracking

The telnet server registers/deregisters sessions in a shared in-memory dict:

```python
# Shared between telnet server and FastAPI
active_sessions: dict[str, SessionInfo] = {}

@dataclass
class SessionInfo:
    peer_ip: str
    peer_port: int
    connected_at: datetime
    current_state: str  # WELCOME, CATEGORIES, FILE_LIST, etc.
```

The telnet `Session` class updates `current_state` on every state transition. FastAPI reads this dict for `/api/sessions`. Connection history is logged to SQLite for `/api/connections`.

---

## 8. Docker Changes

### Dockerfile (multi-stage)

```
# Stage 1: Build React app
FROM node:20-slim AS frontend
COPY admin-ui/ /build/
RUN cd /build && npm ci && npm run build

# Stage 2: Runtime
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends lrzsz cpmtools
RUN pip install --no-cache-dir telnetlib3 blessed fastapi uvicorn python-multipart
COPY --from=frontend /build/dist /app/admin-ui/dist
COPY indexer/ /app/indexer/
COPY server/ /app/server/
COPY entrypoint.sh /app/
```

### docker-compose.yml

No changes to ports. Port 8080 now serves admin UI instead of static files.

---

## 9. Project Structure (new/changed files)

```
server/
  main.py          — unified entry point: telnet + FastAPI in same event loop
  api.py           — FastAPI app, all REST/WS endpoints
  sessions.py      — shared session registry (active_sessions dict)
admin-ui/
  package.json
  src/
    App.tsx
    pages/
      Files.tsx
      Upload.tsx
      Monitor.tsx
      Indexer.tsx
      Settings.tsx
    components/
      Sidebar.tsx
      FileTable.tsx
      FileEditor.tsx
      LogViewer.tsx
      ExtractReview.tsx
      Terminal.tsx    — shared CRT-styled container component
```

---

## 10. No Auth (for now)

Single operator on a private NAS. No authentication layer. If the admin port is ever exposed, add HTTP basic auth or a simple token — but that's out of scope for v1.
