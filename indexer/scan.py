"""scan.py — Walk file areas, catalog archives, track in SQLite for incremental updates."""

import os
import sqlite3
import sys


def init_db(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS files (
            path TEXT PRIMARY KEY,
            area TEXT NOT NULL,
            filename TEXT NOT NULL,
            size INTEGER NOT NULL,
            mtime REAL NOT NULL,
            description TEXT DEFAULT '',
            described INTEGER DEFAULT 0
        )
    """)
    conn.commit()
    return conn


def scan_tree(root: str, conn: sqlite3.Connection) -> tuple[int, int]:
    """Walk root, upsert files into DB. Returns (new_count, skipped_count)."""
    new_count = 0
    skipped = 0

    for dirpath, _, filenames in os.walk(root):
        # Determine area from first directory level under root
        reldir = os.path.relpath(dirpath, root)
        area = reldir.split(os.sep)[0] if reldir != "." else "unsorted"

        for fname in filenames:
            filepath = os.path.join(dirpath, fname)
            try:
                stat = os.stat(filepath)
            except OSError:
                continue

            size = stat.st_size
            mtime = stat.st_mtime

            # Check if already indexed with same mtime/size
            row = conn.execute(
                "SELECT mtime, size FROM files WHERE path = ?", (filepath,)
            ).fetchone()

            if row and row[0] == mtime and row[1] == size:
                skipped += 1
                continue

            conn.execute(
                """INSERT OR REPLACE INTO files (path, area, filename, size, mtime, described)
                   VALUES (?, ?, ?, ?, ?, 0)""",
                (filepath, area, fname, size, mtime),
            )
            new_count += 1

    conn.commit()
    return new_count, skipped


def main():
    if len(sys.argv) < 3:
        print(f"Usage: {sys.argv[0]} <file_root> <db_path>")
        sys.exit(1)

    root = sys.argv[1]
    db_path = sys.argv[2]

    if not os.path.isdir(root):
        print(f"Error: {root} is not a directory")
        sys.exit(1)

    conn = init_db(db_path)
    new, skipped = scan_tree(root, conn)
    print(f"Scan complete: {new} new/updated, {skipped} unchanged")
    conn.close()


if __name__ == "__main__":
    main()
