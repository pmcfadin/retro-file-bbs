# Browser-Based CP/M Emulation

## Idea

Run CP/M disk images directly in the browser — click a .dsk file and get a live CP/M session with the disk contents mounted.

## Existing Emulators to Build On

- **RunCPM** — C-based CP/M 2.2 emulator, compilable to WebAssembly
- **cpm.js / z80pack-js** — JavaScript Z80 + CP/M BIOS implementations
- **JSSpeccy-style Z80 cores** — many JS Z80 emulators available

## Architecture

1. Embed a Z80+CP/M emulator (JS or WASM) in the browser
2. Mount files from a `.dsk` image as the virtual disk
3. Render output to a terminal widget (xterm.js fits the CRT aesthetic)
4. Wire keyboard input to the emulator's console input

## Hard Parts

- **Disk I/O mapping** — CP/M does raw sector reads, need BIOS-level disk emulation matching the disk format (detect_format() already identifies these)
- **Terminal emulation** — CP/M apps use ADM-3A or VT52 escape codes, not ANSI/VT100
- **Program compatibility** — some programs expect specific hardware (e.g., Kaypro screen memory)

## Easy Parts

- Z80 CPU emulation is well-solved in JS
- Disk images and format detection already exist in our stack
- xterm.js provides terminal widget for free

## Effort Estimate

- Basic "boot CP/M, run DIR, launch a .COM file" — a few days of integration work using an existing emulator
- Full compatibility across all disk formats — significantly longer
