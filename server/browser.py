"""browser.py — SQLite query functions for browsing the CP/M file archive."""

import sqlite3

CATEGORY_INFO: dict[str, tuple[str, str]] = {
    "archivers": ("Archivers", "Archive & compression tools (ARC, LBR, etc.)"),
    "comm": ("Comm", "Communications & modem programs"),
    "editors": ("Editors", "Text editors & word processors"),
    "faq": ("FAQ", "Frequently asked questions & guides"),
    "printer": ("Printer", "Printer utilities & drivers"),
    "prod": ("Prod", "Productivity & office tools"),
    "programming": ("Programming", "Compilers, assemblers, & dev tools"),
    "sys": ("Sys", "System utilities & OS patches"),
    "texts": ("Texts", "Documentation & reference material"),
    "transfer": ("Transfer", "File transfer protocols & tools"),
    "unsorted": ("Unsorted", "Uncategorized files"),
    "zutils": ("Zutils", "Z-System utilities"),
}


def get_categories(db: sqlite3.Connection) -> list[tuple[str, int, str]]:
    """Return list of (area, count, description) sorted alphabetically by area name."""
    rows = db.execute(
        "SELECT area, COUNT(*) as count FROM files GROUP BY area ORDER BY area"
    ).fetchall()

    result: list[tuple[str, int, str]] = []
    for area, count in rows:
        _, description = CATEGORY_INFO.get(area, (area, ""))
        result.append((area, count, description))

    return result


def get_files(
    db: sqlite3.Connection, area: str | None, page: int, per_page: int
) -> tuple[list[dict], int]:
    """Return paginated file list and the total count.

    If area is None, returns files across all areas.
    Returns (files, total) where files is a list of dicts with keys:
    path, area, filename, size, mtime, description.
    """
    if area is not None:
        total: int = db.execute(
            "SELECT COUNT(*) FROM files WHERE area = ?", (area,)
        ).fetchone()[0]
        offset = (page - 1) * per_page
        rows = db.execute(
            """SELECT path, area, filename, size, mtime, description
               FROM files WHERE area = ? ORDER BY filename LIMIT ? OFFSET ?""",
            (area, per_page, offset),
        ).fetchall()
    else:
        total = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
        offset = (page - 1) * per_page
        rows = db.execute(
            """SELECT path, area, filename, size, mtime, description
               FROM files ORDER BY filename LIMIT ? OFFSET ?""",
            (per_page, offset),
        ).fetchall()

    files: list[dict] = [
        {
            "path": row[0],
            "area": row[1],
            "filename": row[2],
            "size": row[3],
            "mtime": row[4],
            "description": row[5],
        }
        for row in rows
    ]

    return files, total


def get_file_detail(db: sqlite3.Connection, path: str) -> dict | None:
    """Return a dict with all columns for the given path, or None if not found."""
    row = db.execute(
        "SELECT path, area, filename, size, mtime, description, described FROM files WHERE path = ?",
        (path,),
    ).fetchone()

    if row is None:
        return None

    return {
        "path": row[0],
        "area": row[1],
        "filename": row[2],
        "size": row[3],
        "mtime": row[4],
        "description": row[5],
        "described": row[6],
    }


def get_total_stats(db: sqlite3.Connection) -> tuple[int, int]:
    """Return (total_files, total_categories) counts from the database."""
    total_files: int = db.execute("SELECT COUNT(*) FROM files").fetchone()[0]
    total_categories: int = db.execute(
        "SELECT COUNT(DISTINCT area) FROM files"
    ).fetchone()[0]

    return total_files, total_categories
