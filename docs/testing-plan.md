# True End-to-End CP/M Testing System

## Context

The CP/M Software Depot BBS is running (299 files, 12 categories, telnet :2323). We need a test suite that proves files work the way a real CP/M user would experience it: boot CP/M → launch terminal program → connect to BBS → navigate menus → download via protocol → run the software. No shortcuts, no sideloading.

**Critical constraint discovered in research**: ZMODEM requires 8-bit binary I/O via direct hardware IN/OUT instructions. CP/M's BDOS strips the high bit. Terminal programs like ZMP need hardware-specific overlays for each machine's serial chip. This makes ZMODEM-inside-emulator extremely fragile. The portable alternatives that work through standard BIOS/BDOS calls (and thus in any emulator) are **XMODEM** and **Kermit**. We must add both to the BBS.

## Architecture

```
┌────────────────────────────────────────────┐     ┌─────────────────────┐
│  Test Container                            │     │  BBS Container      │
│                                            │     │                     │
│  pexpect orchestrator (Python)             │     │  Telnet Server      │
│    │                                       │     │  (:2323)            │
│    ▼                                       │     │                     │
│  z80pack (cpmsim) or RunCPM               │     │  Download protocols:│
│    │                                       │     │  [Z] ZMODEM (sz)   │
│    ├── CON: → pexpect stdin/stdout         │     │  [X] XMODEM (new)  │
│    │   (automation sees CP/M console       │     │  [K] Kermit (new)  │
│    │    + terminal program's screen)       │     │  [R] Raw            │
│    │                                       │ TCP │                     │
│    └── AUX: → socat PTY ─────────────────╌╌╌╌╌→│                     │
│         (serial bridge to BBS)             │     │                     │
│                                            │     │                     │
│  CP/M programs on A: drive:               │     │  /data/cpm/ (files) │
│  - KERMIT.COM (Columbia Kermit-80)         │     │                     │
│  - XMODEM.COM (BIOS-based receiver)       │     │                     │
│  - downloaded files land here too          │     │                     │
└────────────────────────────────────────────┘     └─────────────────────┘
```

### How the two-channel approach works

**Channel 1 — Console (CON:)**: z80pack's console I/O goes to its stdin/stdout. pexpect captures this. When CP/M Kermit enters "CONNECT" mode, BBS screens appear on the console (Kermit's terminal emulation renders them). pexpect sees the menus and sends keystrokes that Kermit forwards to the BBS.

**Channel 2 — Serial (AUX:)**: z80pack's auxiliary port is configured to a TCP socket. socat bridges it to the BBS at :2323. The terminal program (Kermit/XMODEM) does file transfers over this channel.

### Real user journey being tested

1. CP/M boots (emulator starts) → A> prompt
2. User types `KERMIT` → Kermit-80 launches
3. `SET PORT AUX` → Kermit uses the serial/AUX device
4. `CONNECT` → Kermit enters terminal mode, BBS welcome screen appears
5. User presses Enter → category list appears
6. User selects category, browses files, selects one
7. User chooses [K]ermit download → BBS starts Kermit send
8. User escapes to Kermit command mode → `RECEIVE` → file transfers
9. User `EXIT`s Kermit → back at A> prompt
10. User types the downloaded .COM filename → program runs
11. Verify: program produced output, no BDOS error

**All of this happens inside the CP/M emulator, through the serial bridge, with no host-side intervention except pexpect driving keystrokes.**

## Scope: BBS Server Changes

### Add XMODEM protocol to `server/download.py`

- `async def xmodem_send(filepath, writer, reader)` — implement XMODEM-CRC sender
- Use the `xmodem` PyPI package (tehmaze/xmodem) or implement directly (protocol is simple: SOH + block# + ~block# + 128 bytes + CRC)
- XMODEM is half-duplex: send block → wait for ACK/NAK → send next
- The reader/writer are the telnet connection (need `getc`/`putc` callbacks)
- Add `xmodem` to pip install in Dockerfile

### Add Kermit protocol to `server/download.py`

- `async def kermit_send(filepath, writer, reader)` — implement Kermit file sender
- Kermit encodes all data as printable ASCII (7-bit safe), making it work through any path
- Use a Python Kermit library or implement the basic send protocol:
  - Send-Init → File-Header → Data packets → EOF → Break
  - Each packet: MARK + LEN + SEQ + TYPE + DATA + CHECK
- Kermit is more complex than XMODEM but extremely well-documented

### Update `server/main.py` download screen

- Add `[X] XMODEM` and `[K] Kermit` options to download prompt
- Wire up the new protocol handlers in `_handle_download`
- Pass both reader and writer (XMODEM/Kermit need bidirectional I/O for handshaking)

### Files modified

| File | Change |
|------|--------|
| `server/download.py` | Add `xmodem_send()` and `kermit_send()` functions |
| `server/main.py` | Add [X] and [K] to download screen + handlers |
| `server/tui.py` | Update download prompt rendering |
| `Dockerfile` | Add `xmodem` to pip install |
| `requirements.txt` | Create: telnetlib3, xmodem |

## Scope: Test Infrastructure

### `Dockerfile.test`

```dockerfile
FROM python:3.11-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        lrzsz socat git build-essential libncurses-dev && \
    rm -rf /var/lib/apt/lists/*

# Build z80pack from source (best serial I/O, supports CP/M 2.2 + 3.0)
RUN git clone --depth 1 https://github.com/udo-munk/z80pack.git /opt/z80pack && \
    cd /opt/z80pack/cpmsim/srcsim && \
    make -f Makefile.linux && \
    cd /opt/z80pack/cpmsim/srctools && \
    make

# Build RunCPM from source (CP/M 2.2, simpler, second emulator)
RUN git clone --depth 1 https://github.com/MockbaTheBorg/RunCPM.git /opt/RunCPM && \
    cd /opt/RunCPM/RunCPM && \
    make -f Makefile.posix && \
    cp RunCPM /usr/local/bin/runcpm

# Python test dependencies
RUN pip install --no-cache-dir pytest pytest-asyncio pexpect telnetlib3 httpx xmodem

# CP/M terminal programs (pre-staged for emulator A: drives)
COPY tests/cpm_programs/ /app/cpm_programs/

COPY tests/ /app/tests/
COPY server/ /app/server/

WORKDIR /app
ENTRYPOINT ["pytest", "tests/", "-v", "--tb=short"]
```

### `docker-compose.test.yml`

```yaml
services:
  bbs:
    build: .
    container_name: cpmdepot-test
    volumes:
      - ./cpm:/data/cpm:ro
      - index_data:/data
    healthcheck:
      test: ["CMD", "python3", "-c",
        "import socket; s=socket.create_connection(('localhost',2323),2); s.close()"]
      interval: 3s
      timeout: 5s
      retries: 10
    networks:
      - testnet

  test-runner:
    build:
      context: .
      dockerfile: Dockerfile.test
    depends_on:
      bbs:
        condition: service_healthy
    volumes:
      - ./cpm:/data/cpm:ro
      - test_downloads:/tmp/downloads
    environment:
      - BBS_HOST=bbs
      - BBS_TELNET_PORT=2323
      - BBS_HTTP_PORT=8080
      - CPM_ROOT=/data/cpm
    networks:
      - testnet

volumes:
  index_data:
  test_downloads:

networks:
  testnet:
```

## File Structure

```
tests/
  conftest.py                        # Shared fixtures, env config, markers
  cpm_programs/                      # Pre-built CP/M binaries for testing
    KERMIT.COM                       # Columbia Kermit-80 (generic version)
    XRECV.COM                        # BIOS-based XMODEM receiver
  helpers/
    __init__.py
    telnet_client.py                 # Async BBS client (telnetlib3)
    ansi_parser.py                   # Strip ANSI codes from screen output
    file_integrity.py                # CRC32/SHA256 verification
    cpm_harness.py                   # Emulator wrapper (z80pack + RunCPM)
    socat_bridge.py                  # socat PTY↔TCP bridge manager
  tier1_protocol/
    __init__.py
    test_welcome.py
    test_categories.py
    test_file_list.py
    test_file_detail.py
    test_search.py
    test_navigation.py
  tier2_transfer/
    __init__.py
    test_xmodem_transfer.py          # XMODEM download integrity
    test_kermit_transfer.py          # Kermit download integrity
    test_zmodem_transfer.py          # ZMODEM handshake verification
    test_raw_transfer.py             # Raw binary download
  tier3_cpm_execution/
    __init__.py
    test_kermit_e2e.py               # Full journey: Kermit → BBS → download → run
    test_xmodem_e2e.py               # Full journey: XMODEM → BBS → download → run
    test_multi_platform.py           # Same tests across CP/M versions + hardware
  docs/
    testing-plan.md                  # This document
Dockerfile.test
docker-compose.test.yml
.github/workflows/e2e-tests.yml
```

## Test Tiers

### Tier 1: BBS Protocol Tests (Python telnet client, no emulator)

Verify the BBS itself works correctly. ~20 test cases covering welcome screen, categories, file listing, pagination, search, navigation, quit.

Uses `telnet_client.py` (telnetlib3 async wrapper) + `ansi_parser.py` (strip ANSI codes).

### Tier 2: File Transfer Protocol Tests (host-side, verify each protocol works)

Tests that each download protocol works correctly by connecting from the host side.

**`test_xmodem_transfer.py`**:
- Connect via telnet, navigate to a file, select [X]MODEM download
- Use Python `xmodem` library as receiver on the host side
- Verify received file matches source (SHA-256)
- Test with small file (<1K), medium file (~50K), and large file (~100K+)

**`test_kermit_transfer.py`**:
- Connect via telnet, navigate to a file, select [K]ermit download
- Use Python Kermit receiver on host side
- Verify received file matches source

**`test_zmodem_transfer.py`**:
- Verify ZMODEM handshake initiates (sz offer header appears)

**`test_raw_transfer.py`**:
- Raw binary download, un-escape IAC bytes, verify integrity

### Tier 3: CP/M End-to-End Tests (the real thing)

**This is where the CP/M emulator runs the full user journey.**

#### Helper: `tests/helpers/cpm_harness.py`

```python
class CPMHarness:
    """Manages a CP/M emulator instance with serial bridge to BBS."""

    def __init__(self, emulator: str, cpm_version: str, work_dir: str):
        """
        emulator: "z80pack" or "runcpm"
        cpm_version: "2.2" or "3.0"
        """

    def install_program(self, host_path: str, cpm_name: str):
        """Copy a .COM file into the emulator's A: drive."""

    def start(self, bbs_host: str, bbs_port: int) -> pexpect.spawn:
        """
        Start the emulator + socat bridge.
        Returns a pexpect child process for console automation.

        For z80pack: configures AUX: port → TCP, starts socat bridge,
                     launches cpmsim
        For RunCPM: starts runcpm with serial I/O configured
        """

    def wait_for_prompt(self, child: pexpect.spawn, timeout: float = 10.0):
        """Wait for CP/M 'A>' prompt."""

    def list_files(self, child: pexpect.spawn) -> list[str]:
        """Run DIR command, parse output, return filenames."""

    def run_program(self, child: pexpect.spawn, name: str,
                    timeout: float = 10.0) -> tuple[int, str]:
        """Execute a .COM file, return (exit_indicator, console_output)."""

    def stop(self):
        """Kill emulator and socat processes, cleanup."""
```

#### Helper: `tests/helpers/socat_bridge.py`

```python
class SocatBridge:
    """Manages socat PTY↔TCP bridge for connecting emulator serial to BBS."""

    def __init__(self, bbs_host: str, bbs_port: int):
        self.process = None
        self.pty_path = None

    def start(self) -> str:
        """
        Start socat: TCP:bbs_host:bbs_port PTY,link=/tmp/cpm_serial,rawer
        Returns the PTY device path.
        """

    def stop(self):
        """Kill socat process."""
```

#### `test_kermit_e2e.py` — Full Kermit journey

```
Test flow (driven by pexpect):
1. harness.start() → emulator boots, socat bridges AUX: to BBS
2. child.expect("A>")
3. child.sendline("KERMIT")           → launch Kermit-80
4. child.expect("Kermit-80>")
5. child.sendline("SET PORT AUX")     → use serial port
6. child.sendline("CONNECT")          → enter terminal mode
7. child.expect("Press.*ENTER")       → BBS welcome screen (via Kermit)
8. child.send("\r")                    → advance to categories
9. child.expect("Select category")    → BBS category list
10. child.send("A")                    → select Archivers
11. child.expect("View file")          → file listing
12. child.send("3\r")                  → select file #3
13. child.expect("ownload")            → file detail
14. child.send("K")                    → select Kermit download
    (BBS starts Kermit file send)
15. child.send("\x1c")                 → Kermit escape character (Ctrl-\)
16. child.expect("Kermit-80>")         → back in Kermit command mode
17. child.sendline("RECEIVE")          → Kermit receives the file
18. child.expect("OK")                 → transfer complete
19. child.sendline("EXIT")             → exit Kermit
20. child.expect("A>")                 → back at CP/M prompt
21. child.sendline("DIR")              → verify file appears
22. child.expect("CRCK44   COM")       → file is there
23. child.sendline("CRCK44")           → run the downloaded program
24. child.expect("CRC")               → program runs, shows output
    (no "BDOS ERR" in output = pass)
```

Assertions:
- File appears in DIR listing after download
- File executes without BDOS error
- Program produces expected output (banner/usage text)

#### `test_xmodem_e2e.py` — Full XMODEM journey

Similar flow but using an XMODEM receive program inside CP/M:
1. Boot CP/M, install XRECV.COM on A: drive
2. Use a simpler terminal program or PIP to connect to BBS via AUX:
3. Navigate menus, select file, choose [X]MODEM
4. Launch XRECV to receive the file
5. Verify file, run it

**Note**: XMODEM requires a terminal program that can switch between "terminal mode" (for BBS navigation) and "transfer mode" (XMODEM receive). If no suitable BIOS-based program exists, we can use a **two-stage approach**:
- Stage 1: A custom tiny CP/M program (`BBSNAV.COM`) that reads/writes AUX: for terminal interaction
- Stage 2: When ready to download, exit BBSNAV, launch XRECV which takes over AUX: for XMODEM

#### `test_multi_platform.py` — Cross-platform matrix

Run the same Kermit E2E test across multiple configurations:

| Config | Emulator | CP/M Version | Hardware |
|--------|----------|-------------|----------|
| `cpm22_generic` | z80pack | 2.2 | Generic Z80 |
| `cpm30_generic` | z80pack | 3.0 | Generic Z80 |
| `cpm22_runcpm` | RunCPM | 2.2 | RunCPM default |
| `cpm22_kaypro` | z80pack | 2.2 | Kaypro-style BIOS (if available) |

Uses pytest parametrize:
```python
@pytest.mark.parametrize("platform", [
    CPMPlatform("z80pack", "2.2", "generic"),
    CPMPlatform("z80pack", "3.0", "generic"),
    CPMPlatform("runcpm", "2.2", "default"),
])
def test_kermit_download_and_execute(platform):
    ...
```

## CP/M Programs Needed

### `tests/cpm_programs/KERMIT.COM`

- **Source**: Columbia University Kermit-80 (generic version)
- **URL**: http://www.columbia.edu/kermit/ftp/cpm80/
- **Which binary**: The "generic" CP/M 2.2 version that uses BIOS/IOBYTE
- **Pre-built**: Download and commit the .COM binary

### `tests/cpm_programs/XRECV.COM`

- **Source**: Need a BIOS-based XMODEM receiver
- **Options**:
  - Ward Christensen's original MODEM.COM (uses BDOS)
  - Or write a minimal one in Z80 assembly (~200 bytes)
  - Or find a portable CP/M XMODEM receiver that uses BIOS calls
- **Fallback**: If no portable XMODEM receiver exists, use Kermit as the primary protocol and document XMODEM as "hardware-dependent"

### Verification .COM files (already in cpm/ archive)

| File | What it does | Why it's a good test |
|------|-------------|---------------------|
| `crck44.com` | CRC checker | Prints usage, exits cleanly |
| `sq111.com` | Squeeze utility | Prints usage, exits cleanly |
| `usq120.com` | Unsqueeze | Prints usage, exits cleanly |
| `lu310.com` | Library utility | Prints help text |
| `uuencode.com` | UU encoder | Prints usage |

## Implementation Phases

### Phase 1: Add XMODEM + Kermit to BBS server
1. Add `xmodem_send()` to `server/download.py` using the `xmodem` PyPI package
2. Add `kermit_send()` to `server/download.py` (implement basic Kermit send protocol)
3. Update download screen in `server/main.py` — add [X] and [K] options
4. Update `Dockerfile` pip install line
5. Test manually: connect with telnet, verify new options appear

### Phase 2: Test infrastructure
6. Create `Dockerfile.test` with z80pack + RunCPM + pexpect
7. Create `docker-compose.test.yml`
8. Create `tests/helpers/cpm_harness.py` — emulator wrapper
9. Create `tests/helpers/socat_bridge.py` — serial bridge manager
10. Create `tests/helpers/telnet_client.py` + `ansi_parser.py` + `file_integrity.py`
11. Create `tests/conftest.py`
12. Acquire CP/M Kermit binary, stage in `tests/cpm_programs/`

### Phase 3: Tier 1 — BBS protocol tests
13. Implement `test_welcome.py`, `test_categories.py`, `test_navigation.py`
14. Implement `test_file_list.py`, `test_file_detail.py`, `test_search.py`

### Phase 4: Tier 2 — Transfer protocol tests
15. Implement `test_xmodem_transfer.py` (host-side XMODEM receive)
16. Implement `test_kermit_transfer.py` (host-side Kermit receive)
17. Implement `test_zmodem_transfer.py`, `test_raw_transfer.py`

### Phase 5: Tier 3 — CP/M end-to-end tests
18. Implement `test_kermit_e2e.py` — full journey through CP/M Kermit
19. Implement `test_xmodem_e2e.py` — full journey through XMODEM
20. Implement `test_multi_platform.py` — parametrized across CP/M versions + hardware

### Phase 6: CI/CD + documentation
21. Create `.github/workflows/e2e-tests.yml`

## CI/CD

```yaml
name: E2E Tests

on:
  push:
    branches: [main]
  pull_request:
  schedule:
    - cron: '0 6 * * *'  # Daily at 6am UTC
  workflow_dispatch:

jobs:
  tier1-tier2:
    name: Protocol & Transfer Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run Tier 1 + 2 tests
        run: |
          docker compose -f docker-compose.test.yml run --rm test-runner \
            pytest tests/tier1_protocol tests/tier2_transfer -v

  tier3:
    name: CP/M End-to-End Tests
    runs-on: ubuntu-latest
    if: github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'
    steps:
      - uses: actions/checkout@v4
      - name: Run Tier 3 tests
        run: |
          docker compose -f docker-compose.test.yml run --rm test-runner \
            pytest tests/tier3_cpm_execution -v
```

## Risks and Mitigations

| Risk | Mitigation |
|------|-----------|
| CP/M Kermit-80 generic binary doesn't work in z80pack | Try multiple Kermit-80 versions; z80pack is widely used with Kermit |
| z80pack AUX: port TCP config is undocumented | z80pack source is open; configure via simctl or conf files; fallback to named pipes |
| No portable XMODEM receiver for CP/M | Kermit is primary; XMODEM is secondary; can write minimal Z80 ASM receiver |
| pexpect timing issues with emulator output | Use generous timeouts, expect patterns not exact strings |
| RunCPM lacks serial I/O for two-channel | Use RunCPM only for Tier 3 "run downloaded file" verification, z80pack for full E2E |

## Verification

1. `docker compose -f docker-compose.test.yml up --build` — both containers start
2. Telnet to BBS → download screen shows [Z]MODEM [X]MODEM [K]ermit [R]aw [C]ancel
3. Tier 1: `pytest tests/tier1_protocol -v` — all BBS navigation tests pass
4. Tier 2: `pytest tests/tier2_transfer -v` — XMODEM + Kermit transfers verified
5. Tier 3: `pytest tests/tier3_cpm_execution -v` — CP/M Kermit downloads and runs a .COM file inside the emulator
6. `pytest tests/tier3_cpm_execution/test_multi_platform.py -v` — same test passes on CP/M 2.2 and 3.0
