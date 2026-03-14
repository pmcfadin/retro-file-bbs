# CP/M Software Depot BBS

A containerized telnet BBS serving a CP/M software archive, powered by [Synchronet BBS](https://www.synchro.net/).

## Quickstart

1. Place your CP/M file archive under `./cpm/` (organized by category subdirectories).

2. Start the BBS:
   ```bash
   docker compose up --build
   ```

3. Connect:
   - **Telnet**: `telnet localhost 2323` (or use SyncTERM for full ANSI + ZMODEM)
   - **Web**: http://localhost:8080
   - **FTP**: `ftp localhost 2121`

## How It Works

**Synchronet BBS** handles all client-facing functionality: telnet, ANSI menus, file browsing, ZMODEM downloads, and the HTTP/FTP file mirror.

A thin Python **indexer** runs on each container start:
1. `scan.py` — walks the CP/M archive, catalogs files in SQLite (incremental via mtime/size tracking)
2. `describe.py` — extracts descriptions: FILE_ID.DIZ from .ZIP/.LBR/.ARC archives, then README/DOC/TXT fallback, then filename heuristic
3. `sync_synchronet.py` — writes FILES.BBS per area and registers files into Synchronet via `addfiles.js`

## File Areas

File area definitions live in `sbbs/ctrl/file.ini` (Synchronet's native config format). Each area maps a subdirectory of `./cpm/` to a BBS library entry. Edit this file to add or rename areas.

## Recommended Clients

- [SyncTERM](https://syncterm.bbsdev.net/) — best experience, native ZMODEM
- [netrunner](https://www.mysticbbs.com/netrunner/) — modern BBS terminal
- Any telnet client (xterm + telnet, PuTTY)

## Architecture

```
[Telnet Client] → :2323 → Synchronet BBS → file areas → ./cpm/ (read-only)
[Web Browser]   → :8080 → Synchronet HTTP → file areas → ./cpm/ (read-only)
[FTP Client]    → :2121 → Synchronet FTP  → file areas → ./cpm/ (read-only)
```

## Admin

- Run SCFG (interactive config): `docker exec -it cpmbbs scfg`
- Shell into container: `docker exec -it cpmbbs bash`
- Re-run indexer: `docker exec -it cpmbbs python3 /indexer/scan.py /sbbs/xfer/cpm /sbbs/data/indexer_cache.db && docker exec -it cpmbbs python3 /indexer/describe.py /sbbs/data/indexer_cache.db && docker exec -it cpmbbs python3 /indexer/sync_synchronet.py /sbbs/data/indexer_cache.db`
