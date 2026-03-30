# Retro File BBS — Web Admin UI User Flows

**Last updated:** 2026-03-18

The admin web UI runs on port 8080 alongside the telnet server. It is a single-operator tool for managing the BBS file archive, not a public-facing site.

---

## Navigation

Sidebar links to all five pages:

| Route | Page | Purpose |
|-------|------|---------|
| `/` | Files | Browse, search, edit, and delete files |
| `/upload` | Upload | Add files or extract archives (ZIP/DSK/IMG) |
| `/monitor` | Monitor | Live sessions, connection history, server logs |
| `/indexer` | Indexer | Run the scan/describe pipeline, view output |
| `/settings` | Settings | Server config, display preferences |

---

## 1. Files Page (`/`)

The main catalog view. Browse, search, filter, and manage individual files.

### Browse & Filter
1. Page loads → fetches categories and first page of files.
2. Filter by category using the dropdown (shows file count per category).
3. Type a search query and press Enter or click **[SEARCH]** to filter by filename and description.
4. Click **[CLEAR]** to reset search.
5. Change per-page count (10 / 25 / 50 / 100).
6. Paginate with **[PREV]** / **[NEXT]**.

### Edit a File
1. Click any row → editor panel opens on the right.
2. If the file is a `.dsk` or `.img` disk image, a "Disk Image Contents" preview loads showing format, system, and file listing.
3. Edit the description textarea.
4. Change the category via dropdown (moves the file on disk).
5. Click **[SAVE]** → patches the file record, shows toast confirmation.

### Delete a File
1. With the editor panel open, click **[DELETE]**.
2. Confirmation modal appears with the filename.
3. Click **[CONFIRM]** → deletes file from DB and disk, closes editor.
4. Click **[CANCEL]** → dismisses modal.

**API calls:** `getCategories`, `getFiles`, `getDskPreview`, `patchFile`, `deleteFile`

---

## 2. Upload Page (`/upload`)

Two upload modes depending on file type.

### Single File Upload
1. Select a target category from the dropdown.
2. Drop a file on the drop zone (or click to browse).
3. If the file is not a ZIP/DSK/IMG, it uploads directly to the selected category.
4. Toast confirms "Uploaded {filename}".

### Archive Extraction (ZIP / DSK / IMG)
1. Select a target category.
2. Drop a `.zip`, `.dsk`, or `.img` file → "Analyzing..." appears.
3. Extract review panel opens:
   - Disk image metadata banner (format, system, image size, file count) if applicable.
   - Table of extracted files with checkboxes (all pre-selected).
   - Toggle individual files by clicking rows.
4. Click **[COMMIT]** → selected files are written to the target category.
5. Success panel shows committed files with two options:
   - **[VIEW FILES]** → navigates to Files page.
   - **[UPLOAD MORE]** → returns to the drop zone.
6. Click **[CANCEL]** at any point to abort and return to the drop zone.

**API calls:** `getCategories`, `uploadFile`, `extractArchive`, `commitExtract`

---

## 3. Monitor Page (`/monitor`)

Real-time view of telnet activity and server logs. Everything auto-refreshes — no manual action needed.

### Active Sessions
- Table showing session ID, IP, port, connection time, and current state.
- Polls every 5 seconds.

### Connection History
- Last 20 connection events (connect/disconnect), most recent first.
- Polls every 5 seconds.

### Live Logs
- Streams server log lines via WebSocket in real time.
- Auto-scrolls to the bottom; click **[PAUSE]** to freeze scrolling for reading.
- Click **[RESUME]** to re-enable auto-scroll.
- Retains the last 500 lines in memory.

**API calls:** `getSessions` (polled), `getConnections` (polled), WebSocket `/api/logs`

---

## 4. Indexer Page (`/indexer`)

Run the scan + describe pipeline and watch its output.

### Status Panel
- Shows running/idle status (color-coded badge), last run timestamp, last result, file count, and category count.
- Polls every 5 seconds.

### Run Indexer
1. Click **[RUN NOW]** → starts the indexer pipeline (scan.py then describe.py).
2. Button changes to **[RUNNING...]** and disables.
3. Output streams live in the log viewer via WebSocket.
4. When finished, status updates to show new file/category counts and result.

**API calls:** `getIndexerStatus` (polled), `runIndexer`, WebSocket `/api/indexer/output`

---

## 5. Settings Page (`/settings`)

View and edit server configuration, toggle display preferences.

### View Config
- Displays version, telnet port, web port, file archive path, database path, file count, and category count.
- Values fetched live from the running server.

### Edit Config
1. Click **[EDIT]** → fields become editable text/number inputs.
2. Modify version, ports, file archive path, or database path.
3. Click **[SAVE]** → sends only changed fields to the server.
   - Confirmation message: "Saved. Port changes take effect on restart."
4. Click **[CANCEL]** → reverts edits, returns to read-only view.

### Display
- **[SCANLINES: ON/OFF]** — toggles the CRT scanline overlay effect. Preference persists in localStorage.

**API calls:** `getConfig`, `patchConfig`, `getIndexerStatus`

---

## API Reference

All endpoints use base path `/api`.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/config` | Server configuration |
| PATCH | `/api/config` | Update configuration |
| GET | `/api/categories` | List file categories with counts |
| GET | `/api/files` | Paginated file listing (supports `area`, `search`, `page`, `per_page`) |
| GET | `/api/files/{path}` | Single file detail |
| PATCH | `/api/files/{path}` | Update description or category |
| DELETE | `/api/files/{path}` | Delete file from DB and disk |
| POST | `/api/upload?area=` | Upload a single file (multipart) |
| POST | `/api/extract` | Upload and extract archive (multipart) |
| POST | `/api/extract/commit` | Commit selected extracted files to a category |
| GET | `/api/preview/{path}` | Disk image preview (format, file list) |
| GET | `/api/sessions` | Active telnet sessions |
| GET | `/api/connections` | Recent connection events |
| WS | `/api/logs` | Live server log stream |
| GET | `/api/indexer/status` | Indexer run status and stats |
| POST | `/api/indexer/run` | Trigger indexer pipeline |
| WS | `/api/indexer/output` | Live indexer output stream |
