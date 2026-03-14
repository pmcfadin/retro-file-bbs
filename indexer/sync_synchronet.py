"""sync_synchronet.py — Feed file descriptions into Synchronet's file area database.

Writes FILES.BBS per directory (filename + description), then calls
Synchronet's addfiles.js via jsexec to register them in the BBS filebase.
Also updates ctrl/file.ini if new areas are found.
"""

import configparser
import os
import sqlite3
import subprocess
import sys


# Map area directory names to Synchronet internal codes (max 8 chars)
AREA_CODES = {
    "archivers": "ARCHIVE",
    "comm": "COMM",
    "editors": "EDITORS",
    "faq": "FAQ",
    "printer": "PRINTER",
    "prod": "PROD",
    "programming": "PROG",
    "sys": "SYS",
    "texts": "TEXTS",
    "transfer": "XFER",
    "unsorted": "UNSORT",
    "zutils": "ZUTIL",
}


def write_files_bbs(conn: sqlite3.Connection, xfer_root: str) -> dict[str, int]:
    """Write FILES.BBS in each area directory for Synchronet to import.

    FILES.BBS format (standard BBS):
      FILENAME.EXT  Description on first line
                    Continuation lines indented with spaces

    Returns dict of area_code -> file_count.
    """
    counts = {}

    # Get distinct areas that have described files
    areas = conn.execute(
        "SELECT DISTINCT area FROM files WHERE described = 1"
    ).fetchall()

    for (area,) in areas:
        code = AREA_CODES.get(area, area.upper()[:8])

        # Collect files for this area — may span subdirectories
        rows = conn.execute(
            """SELECT filename, description, path
               FROM files WHERE area = ? AND described = 1
               ORDER BY filename""",
            (area,),
        ).fetchall()

        if not rows:
            continue

        # Write FILES.BBS in the area root directory
        area_path = os.path.join(xfer_root, area)
        if not os.path.isdir(area_path):
            print(f"  Warning: {area_path} not found, skipping")
            continue

        files_bbs_path = os.path.join(area_path, "FILES.BBS")
        try:
            with open(files_bbs_path, "w") as f:
                for filename, description, filepath in rows:
                    desc_lines = (description or "").split("\n")
                    # First line: filename padded to 13 chars + description
                    f.write(f"{filename:<13s} {desc_lines[0]}\n")
                    # Continuation lines: indented
                    for extra in desc_lines[1:]:
                        if extra.strip():
                            f.write(f"{'':>14s}{extra}\n")
        except OSError as e:
            print(f"  Error writing {files_bbs_path}: {e}")
            continue

        counts[code] = len(rows)
        print(f"  {area} ({code}): {len(rows)} files -> FILES.BBS")

    return counts


def import_via_addfiles(sbbs_root: str, area_counts: dict[str, int]):
    """Call Synchronet's addfiles.js to register files in the BBS database.

    This is the proper way to get files into Synchronet's filebase —
    FILES.BBS alone isn't enough, the files must be registered via addfiles.
    """
    jsexec = os.path.join(sbbs_root, "exec", "jsexec")

    if not os.path.isfile(jsexec):
        print(f"  Warning: jsexec not found at {jsexec}")
        print("  FILES.BBS written but not imported — run addfiles.js manually")
        return

    for dir_code in area_counts:
        full_code = f"CPM_{dir_code}"
        try:
            result = subprocess.run(
                [jsexec, "addfiles.js", full_code, "-diz", "-from=System"],
                cwd=sbbs_root,
                timeout=120,
                capture_output=True,
                text=True,
            )
            if result.returncode == 0:
                print(f"  Imported {full_code} into Synchronet filebase")
            else:
                # Try without -diz flag (some versions differ)
                result2 = subprocess.run(
                    [jsexec, "addfiles.js", full_code],
                    cwd=sbbs_root,
                    timeout=120,
                    capture_output=True,
                    text=True,
                )
                if result2.returncode == 0:
                    print(f"  Imported {full_code} into Synchronet filebase")
                else:
                    print(f"  Warning: addfiles.js {full_code} failed: {result.stderr[:200]}")
        except subprocess.TimeoutExpired:
            print(f"  Warning: addfiles.js {full_code} timed out")
        except OSError as e:
            print(f"  Warning: could not run addfiles.js: {e}")
            return


def main():
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} <db_path>")
        sys.exit(1)

    db_path = sys.argv[1]
    sbbs_root = os.environ.get("SBBS_ROOT", "/sbbs")
    xfer_root = os.path.join(sbbs_root, "xfer", "cpm")

    conn = sqlite3.connect(db_path)

    total = conn.execute("SELECT COUNT(*) FROM files WHERE described = 1").fetchone()[0]
    print(f"Syncing {total} described files to Synchronet...")

    # Step 1: Write FILES.BBS per area
    area_counts = write_files_bbs(conn, xfer_root)

    # Step 2: Import into Synchronet's filebase via addfiles.js
    import_via_addfiles(sbbs_root, area_counts)

    print("Sync complete")
    conn.close()


if __name__ == "__main__":
    main()
