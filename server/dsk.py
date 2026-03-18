"""dsk.py — CP/M disk image format detection and metadata extraction.

CP/M disks store no format metadata on-disk, so detection works by
brute-force: try each candidate diskdef with cpmls and score the results
by whether the directory listing looks valid (printable 8.3 filenames).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re

log = logging.getLogger(__name__)

# Common CP/M disk formats to try, ordered by likelihood.
# Each entry: (format_name, display_name, system_origin)
FORMATS = [
    ("ibm-3740",    "IBM 3740 8\" SSSD",         "IBM / generic CP/M"),
    ("ibm-3740-2",  "IBM 3740 8\" SSSD (alt)",   "IBM / generic CP/M"),
    ("kpii",        "Kaypro II SSDD",            "Kaypro II"),
    ("kpiv",        "Kaypro IV DSDD",            "Kaypro IV"),
    ("osborne1",    "Osborne 1 SSSD",            "Osborne 1"),
    ("apple-do",    "Apple II (DOS order)",       "Apple II"),
    ("apple-po",    "Apple II (ProDOS order)",    "Apple II"),
    ("pcw",         "Amstrad PCW",               "Amstrad PCW"),
    ("cpcsys",      "Amstrad CPC System",        "Amstrad CPC"),
    ("cpcdata",     "Amstrad CPC Data",          "Amstrad CPC"),
    ("myz80",       "MyZ80 emulator",            "MyZ80"),
    ("z80pack-hd",  "z80pack hard disk",         "z80pack"),
    ("ampro400d",   "Ampro Little Board 400K",   "Ampro Little Board"),
    ("ampro800",    "Ampro Little Board 800K",   "Ampro Little Board"),
    ("p112",        "DX Designs P112",           "P112"),
    ("screen12",    "Screenwriter II",           "Screenwriter"),
    ("electroglas", "Electroglas",               "Electroglas"),
]

# Valid CP/M filename pattern: 1-8 chars, dot, 1-3 chars (all printable ASCII)
_VALID_FILENAME = re.compile(
    r"^[A-Za-z0-9!#$%&'()\-@^_`{}~ ]{1,8}\.[A-Za-z0-9!#$%&'()\-@^_`{}~ ]{1,3}$"
)


def _score_filenames(lines: list[str]) -> tuple[int, int]:
    """Score cpmls output lines by how many look like valid CP/M filenames.

    Returns (valid_count, total_count).
    """
    valid = 0
    total = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        # cpmls output varies; filename is typically the last field
        parts = line.split()
        if not parts:
            continue
        fname = parts[-1]
        # Strip user number prefix like "0:"
        if ":" in fname:
            fname = fname.split(":", 1)[1]
        total += 1
        if _VALID_FILENAME.match(fname):
            valid += 1
    return valid, total


async def detect_format(image_path: str) -> dict | None:
    """Try to detect the CP/M disk format of an image file.

    Returns a dict with keys: format, display_name, system, files, file_list
    or None if no format matched.
    """
    image_size = os.path.getsize(image_path)
    best: dict | None = None
    best_score = 0

    for fmt, display_name, system in FORMATS:
        try:
            proc = await asyncio.create_subprocess_exec(
                "cpmls", "-f", fmt, image_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                continue

            output = stdout.decode(errors="replace").strip()
            if not output:
                continue

            lines = output.splitlines()
            valid, total = _score_filenames(lines)

            if total == 0:
                continue

            score = valid
            # Bonus for high valid ratio
            if total > 0 and valid / total > 0.8:
                score += total

            if score > best_score:
                best_score = score
                # Parse file list
                file_list = []
                for line in lines:
                    parts = line.split()
                    if parts:
                        fname = parts[-1]
                        if ":" in fname:
                            fname = fname.split(":", 1)[1]
                        file_list.append(fname)

                best = {
                    "format": fmt,
                    "display_name": display_name,
                    "system": system,
                    "file_count": total,
                    "valid_names": valid,
                    "image_size": image_size,
                    "file_list": file_list,
                }

        except FileNotFoundError:
            log.warning("cpmtools not installed — cannot detect DSK format")
            return None
        except Exception as e:
            log.debug("Format %s failed for %s: %s", fmt, image_path, e)
            continue

    return best


async def extract_with_format(
    image_path: str, dest_dir: str, fmt: str
) -> list[dict]:
    """Extract all files from a CP/M disk image using the given format.

    Returns list of {name, size} dicts for extracted files.
    """
    proc = await asyncio.create_subprocess_exec(
        "cpmcp", "-f", fmt, image_path, "0:*.*", dest_dir,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await proc.communicate()

    if proc.returncode != 0:
        log.warning("cpmcp failed for %s with format %s: %s",
                     image_path, fmt, stderr.decode(errors="replace"))

    extracted: list[dict] = []
    for fname in os.listdir(dest_dir):
        fpath = os.path.join(dest_dir, fname)
        if os.path.isfile(fpath) and fname != os.path.basename(image_path):
            extracted.append({
                "name": fname,
                "size": os.path.getsize(fpath),
            })

    return extracted
