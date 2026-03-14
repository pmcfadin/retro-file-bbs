# retro_bbs Development Guidelines

## Project Overview
CP/M Software Depot BBS — a containerized telnet BBS serving CP/M software archives via Synchronet BBS.
See `sped.md` for the full technical spec.

## Active Technologies
- Synchronet BBS (Docker: `bbsio/synchronet:3.19c`) — handles telnet, ANSI menus, file areas, ZMODEM, HTTP/FTP
- Python 3.11+ — thin indexer scripts (scan, describe, sync)
- SQLite — file metadata cache for incremental indexing

## Project Structure
```
docker-compose.yml           # Synchronet container orchestration
Dockerfile                   # Extends bbsio/synchronet:3.19c, adds Python indexer
entrypoint.sh                # Run indexer pipeline, then start Synchronet
indexer/
  scan.py                    # Walk file areas, catalog in SQLite
  describe.py                # Extract FILE_ID.DIZ / README / heuristic descriptions
  sync_synchronet.py         # Write FILES.BBS, register via addfiles.js
sbbs/
  ctrl/
    file.ini                 # Synchronet file area config (pre-seeded)
cpm/                         # CP/M software archive (not in git, bind-mounted read-only)
sped.md                      # Technical spec v2
```

## Commands
- Build & run: `docker compose up --build`
- Test indexer locally: `python3 indexer/scan.py ./cpm /tmp/test.db && python3 indexer/describe.py /tmp/test.db`
- Lint: `ruff check indexer/`
- Synchronet config: `docker exec -it cpmbbs scfg`

## Code Style
- Python: standard conventions, type hints, stdlib only (no external deps)
