"""describe.py — Extract descriptions from archives (FILE_ID.DIZ, README, heuristics)."""

from __future__ import annotations

import os
import re
import sqlite3
import struct
import sys
import textwrap
import zipfile


def normalize_text(text: str, max_cols: int = 72) -> str:
    """Strip control chars, normalize whitespace, wrap to max_cols."""
    # Strip control characters except newline/tab
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    # Normalize line endings
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse excessive blank lines
    text = re.sub(r"\n{3,}", "\n\n", text)
    # Wrap long lines
    lines = []
    for line in text.split("\n"):
        if len(line) > max_cols:
            lines.extend(textwrap.wrap(line, max_cols))
        else:
            lines.append(line)
    # Take first 10 meaningful lines
    result_lines = []
    for line in lines:
        if len(result_lines) >= 10:
            break
        result_lines.append(line)
    return "\n".join(result_lines).strip()


def try_zip_description(filepath: str) -> str | None:
    """Try to extract FILE_ID.DIZ or README from a ZIP archive."""
    try:
        with zipfile.ZipFile(filepath, "r") as zf:
            names = zf.namelist()
            # Priority 1: FILE_ID.DIZ
            for name in names:
                if os.path.basename(name).upper() == "FILE_ID.DIZ":
                    return normalize_text(zf.read(name).decode("ascii", errors="replace"))
            # Priority 2: README or .DOC/.TXT files
            for pattern in (r"README", r".*\.DOC$", r".*\.TXT$"):
                for name in names:
                    if re.match(pattern, os.path.basename(name), re.IGNORECASE):
                        data = zf.read(name).decode("ascii", errors="replace")
                        return normalize_text(data)
    except (zipfile.BadZipFile, OSError, KeyError):
        pass
    return None


def try_lbr_description(filepath: str) -> str | None:
    """Try to extract FILE_ID.DIZ or descriptive file from an LBR archive.

    LBR format: 32-byte directory entries starting at offset 0.
    Each entry: status(1) + name(8) + ext(3) + padding(4) + index(2) + length(2) + crc(2) + ...
    First entry is the directory itself. Status 0x00 = active, 0xFE = deleted, 0xFF = unused.
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read()

        if len(data) < 32:
            return None

        # Parse directory entries (each 32 bytes)
        # First entry is the directory itself — tells us directory size
        first_entry = data[0:32]
        if first_entry[0] != 0x00:
            return None

        dir_sectors = struct.unpack_from("<H", first_entry, 14)[0]
        dir_size = dir_sectors * 128
        num_entries = dir_size // 32

        entries = []
        for i in range(1, num_entries):
            offset = i * 32
            if offset + 32 > len(data):
                break
            status = data[offset]
            if status == 0xFF:  # unused
                break
            if status != 0x00:  # deleted or invalid
                continue
            name = data[offset + 1 : offset + 9].decode("ascii", errors="replace").strip()
            ext = data[offset + 9 : offset + 12].decode("ascii", errors="replace").strip()
            idx = struct.unpack_from("<H", data, offset + 12)[0]
            length = struct.unpack_from("<H", data, offset + 14)[0]

            full_name = f"{name}.{ext}" if ext else name
            file_offset = idx * 128
            file_size = length * 128
            entries.append((full_name, file_offset, file_size))

        # Search for description files
        desc_priorities = ["FILE_ID.DIZ", "README", "READ.ME"]
        doc_patterns = [r".*\.DOC$", r".*\.TXT$"]

        for target in desc_priorities:
            for name, offset, size in entries:
                if name.upper().replace(" ", "") == target:
                    text = data[offset : offset + size].decode("ascii", errors="replace")
                    return normalize_text(text)

        for pattern in doc_patterns:
            for name, offset, size in entries:
                if re.match(pattern, name, re.IGNORECASE):
                    text = data[offset : offset + size].decode("ascii", errors="replace")
                    return normalize_text(text)

    except (OSError, struct.error):
        pass
    return None


def try_arc_description(filepath: str) -> str | None:
    """Try to extract description from an ARC archive.

    ARC format: repeated blocks of [0x1A, method(1), filename(13-null-term), ...].
    Method 0 = end of archive.
    """
    try:
        with open(filepath, "rb") as f:
            data = f.read()

        entries = []
        pos = 0
        while pos < len(data) - 2:
            if data[pos] != 0x1A:
                break
            method = data[pos + 1]
            if method == 0:
                break

            # Filename: 13 bytes, null-terminated
            name_end = pos + 2 + 13
            if name_end > len(data):
                break
            name_bytes = data[pos + 2 : name_end]
            null_idx = name_bytes.find(0)
            if null_idx >= 0:
                name = name_bytes[:null_idx].decode("ascii", errors="replace")
            else:
                name = name_bytes.decode("ascii", errors="replace").strip()

            # Compressed size at offset +15 (4 bytes LE) for methods >= 2
            if pos + 29 > len(data):
                break
            compressed_size = struct.unpack_from("<I", data, pos + 15)[0]

            # Original size at offset +19 if method >= 2
            header_size = 29
            entry_data_start = pos + header_size
            entries.append((name, entry_data_start, compressed_size))

            pos = entry_data_start + compressed_size

        # Only look for uncompressed FILE_ID.DIZ (method would need to be 1/2)
        # For simplicity, just look for descriptive filenames
        for target in ["FILE_ID.DIZ", "README", "READ.ME"]:
            for name, offset, size in entries:
                if name.upper() == target:
                    text = data[offset : offset + min(size, 4096)].decode(
                        "ascii", errors="replace"
                    )
                    return normalize_text(text)

    except (OSError, struct.error):
        pass
    return None


def try_sibling_description(filepath: str) -> str | None:
    """Look for README/description files in the same directory."""
    directory = os.path.dirname(filepath)
    basename = os.path.splitext(os.path.basename(filepath))[0]

    # Check for companion description files
    candidates = [
        f"{basename}.DOC",
        f"{basename}.TXT",
        f"{basename}.doc",
        f"{basename}.txt",
        "README",
        "README.TXT",
        "READ.ME",
    ]

    for candidate in candidates:
        candidate_path = os.path.join(directory, candidate)
        if os.path.isfile(candidate_path):
            try:
                with open(candidate_path, "r", errors="replace") as f:
                    return normalize_text(f.read())
            except OSError:
                continue

    return None


def heuristic_description(filename: str) -> str:
    """Generate a one-liner from filename tokens."""
    name = os.path.splitext(filename)[0]
    # Split on common separators and camelCase boundaries
    tokens = re.split(r"[-_\s]+", name)
    # Expand common abbreviations
    expansions = {
        "cpm": "CP/M",
        "util": "utility",
        "utils": "utilities",
        "comm": "communications",
        "xfer": "file transfer",
        "asm": "assembler",
        "ed": "editor",
        "prt": "printer",
        "doc": "documentation",
        "hlp": "help",
        "sys": "system",
        "cfg": "configuration",
        "prn": "printer",
        "txt": "text",
    }
    expanded = []
    for t in tokens:
        lower = t.lower()
        if lower in expansions:
            expanded.append(expansions[lower])
        elif t:
            expanded.append(t)

    if expanded:
        desc = " ".join(expanded)
        return desc[0].upper() + desc[1:]
    return filename


def describe_file(filepath: str, filename: str) -> str:
    """Get the best available description for a file."""
    ext = os.path.splitext(filename)[1].upper()

    # Try archive-internal descriptions first
    if ext == ".ZIP":
        desc = try_zip_description(filepath)
        if desc:
            return desc
    elif ext == ".LBR":
        desc = try_lbr_description(filepath)
        if desc:
            return desc
    elif ext == ".ARC":
        desc = try_arc_description(filepath)
        if desc:
            return desc

    # Try sibling files
    desc = try_sibling_description(filepath)
    if desc:
        return desc

    # Fall back to heuristic
    return heuristic_description(filename)


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    conn = sqlite3.connect(db_path)

    rows = conn.execute(
        "SELECT path, filename FROM files WHERE described = 0"
    ).fetchall()

    if not rows:
        print("All files already have descriptions")
        return

    count = 0
    for path, filename in rows:
        desc = describe_file(path, filename)
        conn.execute(
            "UPDATE files SET description = ?, described = 1 WHERE path = ?",
            (desc, path),
        )
        count += 1
        if count % 50 == 0:
            conn.commit()
            print(f"  Described {count}/{len(rows)} files...")

    conn.commit()
    print(f"Descriptions complete: {count} files processed")
    conn.close()


if __name__ == "__main__":
    main()
