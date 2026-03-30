![Retro File BBS](docs/readme_banner.png)

# Retro File BBS

A containerized telnet BBS serving a curated CP/M software archive, with a web admin UI for file management, uploads, monitoring, and settings.

## Getting Started

### Option A: Pull and run

No git clone needed — just Docker:

```bash
docker pull ghcr.io/pmcfadin/retro-file-bbs:latest
docker run -p 2323:2323 -p 8080:8080 -v /path/to/your/cpm:/data/cpm:ro ghcr.io/pmcfadin/retro-file-bbs:latest
```

### Option B: Clone and build

```bash
git clone https://github.com/pmcfadin/retro-file-bbs.git
cd retro-file-bbs
docker compose up --build
```

### Option C: Production deploy (NAS / Portainer)

```bash
cp .env.example .env
# edit .env with your paths and ports
docker compose -f docker-compose.prod.yml up -d
```

Then connect: **telnet on :2323**, **admin UI at http://localhost:8080**.

Use [SyncTERM](https://syncterm.bbsdev.net/) for the full ANSI + ZMODEM experience.

## Services

| Port | Service |
|------|---------|
| 2323 | Telnet BBS — ANSI menus, file browsing, ZMODEM downloads |
| 8080 | Admin Web UI — file management, uploads, monitoring, settings |

## What's Inside

268 public domain CP/M programs across 12 categories:

| Category | Files | Highlights |
|----------|------:|------------|
| Archivers | 32 | ARC, LBR, Squeeze/Unsqueeze, Crunch, UNARC, UNZIP |
| Comm | 78 | IMP, MEX, QTERM, MODEM7, ZMP, XMODEM, ZMODEM |
| Editors | 24 | WordStar 3.3 & 4.0, VDE, Micro Emacs, SpellBinder |
| FAQ | 3 | CP/M guides and references |
| Games | 30 | Zork I/II/III, 18 Infocom titles, Colossal Cave, Sargon Chess |
| Printer | 4 | Printer utilities |
| Prod | 17 | dBASE II, SuperCalc, Multiplan, Turbo Pascal 3.0, GSX |
| Programming | 36 | BDS C, MBASIC 5.21, FORTRAN-80, COBOL-80, Forth, HiTech C |
| Sys | 21 | SWEEP, debuggers, Unix-like utils, boot disk with DR tools |
| Texts | 9 | CP/M primers, documentation |
| Transfer | 7 | Disk transfer and encoding utilities |
| Zutils | 7 | Z-System utilities |

Software sourced from [retroarchive.org](http://www.retroarchive.org/cpm/), the [Walnut Creek CP/M CD-ROM](https://archive.org/details/cdrom-1994-11-walnutcreek-cpm), [IF Archive](https://ifarchive.org/indexes/if-archive/games/cpm/), [cpm.z80.de](http://www.cpm.z80.de/), and [zimmers.net](https://www.zimmers.net/anonftp/pub/cpm/).

## Admin Web UI

The web UI at port 8080 is a single-operator tool for managing the BBS file archive:

| Page | What it does |
|------|--------------|
| **Files** | Browse, search, edit descriptions, move categories, delete files |
| **Upload** | Add files or extract archives (ZIP/DSK/IMG) into the catalog |
| **Monitor** | Live sessions, connection history, server logs |
| **Indexer** | Run the scan/describe pipeline, view output |
| **Settings** | Server config and display preferences |

See [docs/Web_user_flows.md](docs/Web_user_flows.md) for detailed user flows.

## How It Works

A Python **indexer** runs on each container start:

1. `scan.py` — walks `cpm/`, catalogs files in SQLite (incremental via mtime/size)
2. `describe.py` — extracts descriptions from ZIP/LBR/ARC archives, READMEs, or filename heuristics

Then a **telnetlib3 server** serves the archive with an ANSI TUI: welcome screen, category browser, paginated file listings, search, and file detail views with download options.

## CP/M Emulator Mode

Boot a z80pack CP/M 2.2 guest with Kermit and connect to the BBS the retro way:

```bash
docker compose run --rm cpm
```

Once at the `A>` prompt:

```
B:
KERMIT
CONNECT
```

You'll be on the BBS via Kermit's terminal mode. `Ctrl-\ C` returns to the Kermit prompt.

This boots a Z80 emulator, patches Kermit-80 for direct AUX port I/O, and bridges the serial connection to the BBS over telnet — the full 1980s experience.

## Adding Software

Drop files into the appropriate `cpm/` subdirectory and restart:

```bash
docker compose restart cpmdepot
```

The indexer picks up new files automatically. Supported archive formats for description extraction: `.ZIP`, `.LBR`, `.ARC`.

You can also upload files directly through the **Upload** page in the admin web UI.

## Architecture

```
[Telnet Client]  --> :2323 --> Python telnet server --> SQLite --> cpm/ (read-only)
[Web Browser]    --> :8080 --> FastAPI + React SPA  --> SQLite --> cpm/ (read/write)
[CP/M Emulator]  --> z80pack + Kermit --> AUX bridge --> :2323
```

## Development

```bash
# Run the test suite (requires Docker)
docker build -f Dockerfile.test . -t retro-bbs:test-runtime
docker run --rm retro-bbs:test-runtime tests/ -v

# Lint
ruff check indexer/ server/ emulation/

# Test indexer locally
python3 indexer/scan.py ./cpm /tmp/test.db
python3 indexer/describe.py /tmp/test.db

# Admin UI development
cd admin-ui
npm install
npm run dev    # Vite dev server on :5173, proxies API to :8080
```

## CI/CD

GitHub Actions auto-builds and pushes `ghcr.io/pmcfadin/retro-file-bbs:latest` on every push to `main`.

## Recommended Clients

- [SyncTERM](https://syncterm.bbsdev.net/) — best experience, native ZMODEM
- [netrunner](https://www.mysticbbs.com/netrunner/) — modern BBS terminal
- Any telnet client (Terminal + `telnet`, PuTTY, xterm)
