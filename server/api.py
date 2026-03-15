"""api.py — FastAPI app providing the admin web UI API."""

from __future__ import annotations

import asyncio
import datetime
import logging
import os
import shutil
import sqlite3
import uuid
from dataclasses import dataclass

from fastapi import FastAPI, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from server.browser import CATEGORY_INFO, get_categories, get_file_detail, get_files
from server.search import search_files
from server.sessions import active_sessions, connection_history

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config (set by main.py before startup)
# ---------------------------------------------------------------------------

DB_PATH: str = ""
CPM_ROOT: str = ""

_wal_initialized = False

# ---------------------------------------------------------------------------
# Indexer state
# ---------------------------------------------------------------------------


@dataclass
class IndexerStatus:
    running: bool = False
    last_run: str | None = None
    last_result: str | None = None
    file_count: int = 0
    category_count: int = 0


indexer_status = IndexerStatus()
_indexer_subscribers: list[asyncio.Queue] = []

# ---------------------------------------------------------------------------
# Log broadcast
# ---------------------------------------------------------------------------

_log_subscribers: list[asyncio.Queue] = []


class WebSocketLogHandler(logging.Handler):
    """Push log records to all connected WebSocket subscribers."""

    def emit(self, record: logging.LogRecord) -> None:
        msg = self.format(record)
        for q in list(_log_subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass


# ---------------------------------------------------------------------------
# DB helper
# ---------------------------------------------------------------------------


def _open_db() -> sqlite3.Connection:
    global _wal_initialized
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    if not _wal_initialized:
        db.execute("PRAGMA journal_mode=WAL")
        _wal_initialized = True
    return db


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _ws_broadcast(websocket: WebSocket, subscribers: list[asyncio.Queue]) -> None:
    """Shared WebSocket broadcast loop: subscribe, relay messages, cleanup."""
    await websocket.accept()
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)
    subscribers.append(queue)
    try:
        while True:
            msg = await queue.get()
            await websocket.send_text(msg)
    except WebSocketDisconnect:
        pass
    finally:
        subscribers.remove(queue)


async def _stream_subprocess(cmd: list[str], subscribers: list[asyncio.Queue]) -> int:
    """Run a subprocess, streaming stdout lines to WebSocket subscribers.

    Returns the process exit code.
    """
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    if proc.stdout is not None:
        while True:
            line = await proc.stdout.readline()
            if not line:
                break
            text = line.decode(errors="replace").rstrip()
            for q in list(subscribers):
                try:
                    q.put_nowait(text)
                except asyncio.QueueFull:
                    pass
    return await proc.wait()


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class FilePatch(BaseModel):
    description: str | None = None
    area: str | None = None


class ExtractCommit(BaseModel):
    staging_id: str
    area: str
    files: list[str]


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(title="CP/M Software Depot Admin", docs_url="/api/docs")


# --- Categories ---

@app.get("/api/categories")
def api_categories():
    with _open_db() as db:
        cats = get_categories(db)
    return [
        {
            "area": area,
            "count": count,
            "description": desc,
            "display_name": CATEGORY_INFO.get(area, (area.title(), ""))[0],
        }
        for area, count, desc in cats
    ]


# --- Files ---

@app.get("/api/files")
def api_files(
    area: str | None = None,
    search: str | None = None,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
):
    with _open_db() as db:
        if search:
            files, total = search_files(db, search, page, per_page)
        elif area:
            files, total = get_files(db, area, page, per_page)
        else:
            files, total = get_files(db, None, page, per_page)

    total_pages = max(1, (total + per_page - 1) // per_page)
    return {
        "files": files,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
    }


@app.get("/api/files/{path:path}")
def api_file_detail(path: str):
    full_path = os.path.join(CPM_ROOT, path)
    with _open_db() as db:
        detail = get_file_detail(db, full_path)
    if detail is None:
        raise HTTPException(404, "File not found")
    return detail


@app.patch("/api/files/{path:path}")
def api_file_patch(path: str, patch: FilePatch):
    full_path = os.path.join(CPM_ROOT, path)
    with _open_db() as db:
        existing = get_file_detail(db, full_path)
        if existing is None:
            raise HTTPException(404, "File not found")

        updates = []
        params = []
        if patch.description is not None:
            updates.append("description = ?")
            params.append(patch.description)
        if patch.area is not None:
            if patch.area not in CATEGORY_INFO:
                raise HTTPException(400, f"Unknown area: {patch.area}")
            updates.append("area = ?")
            params.append(patch.area)

        if not updates:
            raise HTTPException(400, "No fields to update")

        # If area changed, move file on disk FIRST (before DB commit)
        new_path = full_path
        if patch.area is not None and patch.area != existing["area"]:
            new_path = os.path.join(CPM_ROOT, patch.area, existing["filename"])
            os.makedirs(os.path.dirname(new_path), exist_ok=True)
            shutil.move(full_path, new_path)

        # Update DB (area + description + path if moved) in a single transaction
        if new_path != full_path:
            updates.append("path = ?")
            params.append(new_path)

        params.append(full_path)
        db.execute(
            f"UPDATE files SET {', '.join(updates)} WHERE path = ?",
            params,
        )
        db.commit()

    return {"status": "ok"}


@app.delete("/api/files/{path:path}")
def api_file_delete(path: str):
    full_path = os.path.join(CPM_ROOT, path)
    with _open_db() as db:
        existing = get_file_detail(db, full_path)
        if existing is None:
            raise HTTPException(404, "File not found")

        db.execute("DELETE FROM files WHERE path = ?", (full_path,))
        db.commit()

    # Remove from disk
    if os.path.isfile(full_path):
        os.remove(full_path)

    return {"status": "ok"}


# --- Upload ---

@app.post("/api/upload")
async def api_upload(file: UploadFile, area: str = Query(...)):
    if area not in CATEGORY_INFO:
        raise HTTPException(400, f"Unknown area: {area}")

    dest_dir = os.path.join(CPM_ROOT, area)
    os.makedirs(dest_dir, exist_ok=True)

    filename = file.filename or "UNKNOWN"
    dest_path = os.path.join(dest_dir, filename)

    content = await file.read()
    with open(dest_path, "wb") as f:
        f.write(content)

    # Register in DB
    stat = os.stat(dest_path)
    with _open_db() as db:
        db.execute(
            """INSERT OR REPLACE INTO files (path, area, filename, size, mtime, description, described)
               VALUES (?, ?, ?, ?, ?, '', 0)""",
            (dest_path, area, filename, stat.st_size, stat.st_mtime),
        )
        db.commit()

    return {"status": "ok", "path": dest_path, "size": stat.st_size}


# --- Extract (ZIP/DSK) ---

STAGING_DIR = "/data/staging"
MAX_EXTRACT_SIZE = 50 * 1024 * 1024  # 50 MB limit per extracted file


@app.post("/api/extract")
async def api_extract(file: UploadFile):
    staging_id = str(uuid.uuid4())
    staging_path = os.path.join(STAGING_DIR, staging_id)
    os.makedirs(staging_path, exist_ok=True)

    filename = file.filename or "archive"
    archive_path = os.path.join(staging_path, filename)

    content = await file.read()
    with open(archive_path, "wb") as f:
        f.write(content)

    # Try to extract
    extracted_files: list[dict] = []
    lower = filename.lower()

    if lower.endswith(".zip"):
        import zipfile
        try:
            with zipfile.ZipFile(archive_path, "r") as zf:
                for info in zf.infolist():
                    if info.is_dir():
                        continue
                    # Validate: no path traversal, size cap
                    member_name = os.path.basename(info.filename)
                    if not member_name or ".." in info.filename:
                        continue
                    if info.file_size > MAX_EXTRACT_SIZE:
                        continue
                    safe_path = os.path.join(staging_path, member_name)
                    with zf.open(info) as src, open(safe_path, "wb") as dst:
                        dst.write(src.read())
                    extracted_files.append({
                        "name": member_name,
                        "size": info.file_size,
                    })
        except zipfile.BadZipFile:
            raise HTTPException(400, "Invalid ZIP file")
    elif lower.endswith(".dsk"):
        # Use cpmtools to extract all files at once
        try:
            result = await asyncio.create_subprocess_exec(
                "cpmls", "-f", "ibm-3740", archive_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await result.communicate()
            file_names = []
            for line in stdout.decode(errors="replace").strip().splitlines():
                parts = line.split()
                if parts:
                    file_names.append(parts[-1])

            # Extract all files in one cpmcp call
            if file_names:
                proc = await asyncio.create_subprocess_exec(
                    "cpmcp", "-f", "ibm-3740", archive_path, "0:*.*", staging_path,
                    stderr=asyncio.subprocess.PIPE,
                )
                await proc.communicate()

                for fname in file_names:
                    fpath = os.path.join(staging_path, fname)
                    if os.path.isfile(fpath):
                        extracted_files.append({
                            "name": fname,
                            "size": os.path.getsize(fpath),
                        })
        except FileNotFoundError:
            raise HTTPException(500, "cpmtools not installed")
    else:
        # Not extractable — just list the file itself
        extracted_files.append({"name": filename, "size": len(content)})

    return {
        "staging_id": staging_id,
        "files": extracted_files,
    }


@app.post("/api/extract/commit")
def api_extract_commit(commit: ExtractCommit):
    if commit.area not in CATEGORY_INFO:
        raise HTTPException(400, f"Unknown area: {commit.area}")

    staging_path = os.path.join(STAGING_DIR, commit.staging_id)
    if not os.path.isdir(staging_path):
        raise HTTPException(404, "Staging directory not found")

    dest_dir = os.path.join(CPM_ROOT, commit.area)
    os.makedirs(dest_dir, exist_ok=True)

    committed: list[str] = []
    with _open_db() as db:
        for fname in commit.files:
            src = os.path.join(staging_path, fname)
            if not os.path.isfile(src):
                continue
            dest = os.path.join(dest_dir, fname)
            shutil.move(src, dest)
            stat = os.stat(dest)
            db.execute(
                """INSERT OR REPLACE INTO files (path, area, filename, size, mtime, description, described)
                   VALUES (?, ?, ?, ?, ?, '', 0)""",
                (dest, commit.area, fname, stat.st_size, stat.st_mtime),
            )
            committed.append(fname)
        db.commit()

    # Cleanup staging
    shutil.rmtree(staging_path, ignore_errors=True)

    return {"status": "ok", "committed": committed}


# --- Monitor ---

@app.get("/api/sessions")
def api_sessions():
    return [
        {
            "session_id": s.session_id,
            "peer_ip": s.peer_ip,
            "peer_port": s.peer_port,
            "connected_at": s.connected_at.isoformat(),
            "current_state": s.current_state,
        }
        for s in active_sessions.values()
    ]


@app.get("/api/connections")
def api_connections():
    return list(connection_history)


@app.websocket("/api/logs")
async def ws_logs(websocket: WebSocket):
    await _ws_broadcast(websocket, _log_subscribers)


# --- Indexer ---

@app.get("/api/indexer/status")
def api_indexer_status():
    return {
        "running": indexer_status.running,
        "last_run": indexer_status.last_run,
        "last_result": indexer_status.last_result,
        "file_count": indexer_status.file_count,
        "category_count": indexer_status.category_count,
    }


@app.post("/api/indexer/run")
async def api_indexer_run():
    if indexer_status.running:
        raise HTTPException(409, "Indexer is already running")

    indexer_status.running = True

    async def _run_indexer():
        try:
            await _stream_subprocess(
                ["python3", "/app/indexer/scan.py", CPM_ROOT, DB_PATH],
                _indexer_subscribers,
            )
            await _stream_subprocess(
                ["python3", "/app/indexer/describe.py", DB_PATH],
                _indexer_subscribers,
            )

            # Update stats
            with _open_db() as db:
                indexer_status.file_count = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
                indexer_status.category_count = db.execute("SELECT COUNT(DISTINCT area) FROM files").fetchone()[0]

            indexer_status.last_result = "success"
        except Exception as e:
            indexer_status.last_result = f"error: {e}"
            log.exception("Indexer run failed")
        finally:
            indexer_status.running = False
            indexer_status.last_run = datetime.datetime.now(datetime.timezone.utc).isoformat()

    asyncio.create_task(_run_indexer())
    return {"status": "started"}


@app.websocket("/api/indexer/output")
async def ws_indexer_output(websocket: WebSocket):
    await _ws_broadcast(websocket, _indexer_subscribers)


# --- Static files (SPA fallback) ---

def mount_static(static_dir: str) -> None:
    """Mount the React build directory as static files with SPA fallback."""
    if os.path.isdir(static_dir):
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
        log.info("Mounted admin UI from %s", static_dir)
    else:
        log.warning("Admin UI directory not found: %s — API-only mode", static_dir)
