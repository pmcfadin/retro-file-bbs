# CP/M Software Depot

A telnet BBS serving a curated CP/M software archive. Browse categories, search files, and download via ZMODEM — all from an ANSI terminal.

```
telnet localhost 2323
```

## Quickstart

```bash
docker compose up --build
```

Connect with any telnet client. Use [SyncTERM](https://syncterm.bbsdev.net/) for the full ANSI + ZMODEM experience.

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

## Services

| Port | Service |
|------|---------|
| 2323 | Telnet BBS — ANSI menus, file browsing, ZMODEM downloads |
| 8080 | HTTP mirror — browse and download files from a web browser |

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

## Architecture

```
[Telnet Client]  --> :2323 --> Python telnet server --> SQLite --> cpm/ (read-only)
[Web Browser]    --> :8080 --> Python http.server   ------------> cpm/ (read-only)
[CP/M Emulator]  --> z80pack + Kermit --> AUX bridge --> :2323 --> (same telnet server)
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
```

## Recommended Clients

- [SyncTERM](https://syncterm.bbsdev.net/) — best experience, native ZMODEM
- [netrunner](https://www.mysticbbs.com/netrunner/) — modern BBS terminal
- Any telnet client (Terminal + `telnet`, PuTTY, xterm)
