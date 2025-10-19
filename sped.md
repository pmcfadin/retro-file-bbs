Telnet CP/M Software Depot BBS — Technical Spec v2 (Containerized, No Serial)

Owner: Patrick (Scout Dog AI Studios)
Goal: Run a telnet-only BBS inside a container that serves a very large CP/M software library (e.g., SIMTEL20 mirror). Users connect via telnet clients (SyncTERM, netrunner, xterm+telnet) and navigate ANSI/ASCII menus to browse a file-tree with descriptions and download files. No local serial cabling or CP/M-side TUI required.

⸻

1) Objectives & Scope
	•	Provide a LAN/WAN telnet BBS that exposes CP/M software with proper descriptions, browsing, and searching.
	•	Handle very large catalogs gracefully (SIMTEL20 scale) with pre-indexing and paging.
	•	Offer reliable, simple downloads over telnet (raw transfers or ZMODEM) and optionally HTTP/FTP mirrors for convenience.

Out of scope (v2): Dial-up/POTS, FidoNet-style echo networks, message networks. Focus is on Files BBS use-case.

⸻

2) High-Level Architecture

[Client: SyncTERM/any telnet]  ==(TCP/23 or 2323)==>  [Docker Host]
                                                   └─ BBS Container
                                                      ├─ BBS daemon (Mystic or Synchronet)
                                                      ├─ Importer/Indexer (SIMTEL20 → areas, metadata)
                                                      ├─ Optional: HTTP static server for file mirror
                                                      └─ Persistent volumes: /bbs/data, /bbs/files

	•	BBS Engine (choice):
	•	Synchronet (sbbs): battle-tested, containers available, rich file areas, built-in protocols incl. ZMODEM.
	•	Mystic BBS: modern, great theming, simple file areas, also Dockerized by community.
	•	File Areas: Mapped to directory tree under /bbs/files (bind-mount of SIMTEL20 mirror or curated subsets).
	•	Importer/Indexer: Scans mirror, creates per-file metadata (desc, size, dates), generates FILE_ID.DIZ when missing, and updates BBS area databases for fast browsing.
	•	Optional Mirrors: HTTP (read-only) served from the same files to allow direct downloads outside telnet.

⸻

3) BBS Choice & Rationale

Default recommendation: Synchronet for large file depots.
	•	Mature file area model (nested libraries/dirs).
	•	Upload/Download protocols, including ZMODEM autodetect for telnet clients (SyncTERM, iTerm w/ rz/sz bridges).
	•	Good tooling (SCFG, JS scripting). Docker images maintained by community.

Alternative: Mystic if you prefer its editor and menu system; supports FTP/HTTP add-ons and good file area UX.

⸻

4) Docker Compose (Synchronet-focused)

services:
  sbbs:
    image: ghcr.io/synchronetbbs/sbbs:latest
    container_name: cpmbbs
    environment:
      - TZ=America/Los_Angeles
    ports:
      - "2323:23"      # telnet (non-privileged host port)
      - "8080:80"      # optional web interface
      - "2121:21"      # optional FTP (passive ports handled by iptables or docker)
    volumes:
      - ./sbbs:/sbbs            # Synchronet config/data
      - /path/to/simtel:/sbbs/xfer/simtel:ro   # your mirror
      - ./importer:/importer    # indexer scripts
    restart: unless-stopped

Adjust /path/to/simtel to your library root. You can add more mounts for curated areas (e.g., /sbbs/xfer/editors, /sbbs/xfer/comm).

⸻

5) File Areas & Catalog Strategy

5.1 Area Layout
	•	Map top-level Libraries to big categories (e.g., SIMTEL20, UTILS, COMM, DEV, GAMES).
	•	Under each, map directories to Sub-areas mirroring the filesystem.
	•	Use Synchronet SCFG to define:
	•	Libraries → Xfer Libraries
	•	Dirs per library → Xfer Directories (path: /sbbs/xfer/simtel/<subdir>)

5.2 Descriptions (FILE_ID.DIZ preferred)
	•	Many archives contain FILE_ID.DIZ. Importer should:
	1.	If FILE_ID.DIZ exists in archive (.LBR, .ARC, .ZIP), extract first ~10 lines as description.
	2.	Else, derive from nearby README, *.DOC, *.TXT (first 4–10 non-empty lines).
	3.	Else, generate heuristic one-liner from filename tokens.
	•	Save results back into the BBS area databases so dir listings are instant.

5.3 Scale & Performance
	•	Incremental import: track file mtime/size hash to avoid reprocessing.
	•	Pagination: ensure BBS shows pages of ~20–40 entries with next/prev.
	•	Index DB: maintain a small SQLite (or JS DB for Synchronet) as the importer’s cache.

⸻

6) Importer/Indexer (Container Task)

Language: Python or Node.js (your choice; below assumes Python)

Responsibilities:
	•	Walk /sbbs/xfer/simtel (read-only).
	•	For archives (.LBR, .ZIP, .ARC): try to read FILE_ID.DIZ. For .LBR, use lbrutil or a pure-Python reader; as fallback, skip extraction but keep filename and size.
	•	For loose files (.COM, .HEX, .DOC): search sibling text for description.
	•	Normalize line endings, strip control chars, wrap 72 cols.
	•	Write Synchronet dir metadata via:
	•	Option A: Synchronet jsexec sbbslist.js-friendly JSON files for fast import.
	•	Option B: Script Synchronet scfg CLI (or exec/sbbsctrl addfile) to insert/update entries.

Run mode:
	•	On container start, full import if no cache; otherwise incremental.
	•	Optional cron (/etc/cron.d) to refresh nightly.

⸻

7) Telnet UX (Client-Facing)
	•	ANSI/ASCII menu (auto-detect terminal; gracefully degrade to plain ASCII for minimal clients).
	•	Hierarchical browsing: Libraries → Directories → Files.
	•	Search: title/description keyword search (maps to index/cache).
	•	Preview: press V to view description/READ.ME (paged).
	•	Download: press D (BBS prompts protocol). Recommend offering:
	•	Raw (no protocol) for simple terminals.
	•	ZMODEM if client supports (SyncTERM/MLTERM); fastest and robust.
	•	Optional: display a copyable HTTP URL mirroring the file (http://host:8080/xfer/...) for out-of-band download from a modern browser.

⸻

8) HTTP/FTP Mirrors (Optional but Recommended)
	•	Run the Synchronet built-in web server (port 80 mapped to host 8080) to expose /xfer read-only.
	•	Optionally enable FTP (passive ports require NAT config) for classic tooling.
	•	Benefits: easy mass download/browsing by modern machines; telnet users can still get files via BBS UI.

⸻

9) Security, Users & Access
	•	LAN-only by default (bind to 0.0.0.0:2323 but firewall to your LAN). Expose to WAN only if desired.
	•	Create a single guest user with file download permissions; disable uploads.
	•	Read‑only bind mounts for file areas.
	•	Container runs as non-root; set proper UID/GID on mounted volumes.

⸻

10) Acceptance Criteria (v2 Telnet)
	1.	Container starts; BBS listens on host :2323 (telnet).
	2.	From SyncTERM: connect, authenticate as guest, navigate Libraries → Dirs → Files.
	3.	Large directories (>1,000 files) page quickly (≤ 500 ms per page after import).
	4.	Search returns relevant matches with preview and quick navigation.
	5.	Download a .COM and a .LBR via ZMODEM successfully.
	6.	Optional: same file accessible via HTTP at http://host:8080/xfer/....

⸻

11) Deliverables
	•	docker-compose.yml (as above)
	•	BBS engine config directory (./sbbs pre-seeded with minimal SCFG)
	•	importer/ scripts:
	•	scan.py (walk & cache)
	•	describe.py (derive FILE_ID.DIZ/desc)
	•	sync_synchronet.py (apply to BBS areas)
	•	README with quickstart, client list (SyncTERM, netrunner), and admin tips.

⸻

12) Roadmap
	•	v2.1: Add Mystic variant with theme + menu art.
	•	v2.2: Auto-build nightly indexes; sitemaps for HTTP mirror.
	•	v2.3: Optional login + per-user favorites; download stats.
	•	v3.0: Multi-node (Docker Swarm/K8s) for WAN exposure; GeoIP-based mirrors.

⸻

13) Notes for Codex
	•	Prefer Synchronet unless you have a strong Mystic preference; focus on file areas and speed.
	•	Descriptions are king: always try FILE_ID.DIZ; fall back to DOC/README lines; last resort heuristics.
	•	Keep imports idempotent; don’t duplicate entries.
	•	Expose telnet on 2323 by default to avoid privileged port binding.

End of Spec v2 (Telnet‑only)
