"""search.py — Full-text search over the CP/M file archive."""

import sqlite3


def search_files(
    db: sqlite3.Connection, query: str, page: int, per_page: int
) -> tuple[list[dict], int]:
    """Search files by filename and description using SQLite LIKE.

    Returns (results, total) where results is a list of dicts with keys:
    path, area, filename, size, description.
    """
    pattern = f"%{query}%"

    total: int = db.execute(
        "SELECT COUNT(*) FROM files WHERE filename LIKE ? OR description LIKE ?",
        (pattern, pattern),
    ).fetchone()[0]

    offset = (page - 1) * per_page
    rows = db.execute(
        """SELECT path, area, filename, size, description
           FROM files
           WHERE filename LIKE ? OR description LIKE ?
           ORDER BY filename
           LIMIT ? OFFSET ?""",
        (pattern, pattern, per_page, offset),
    ).fetchall()

    results: list[dict] = [
        {
            "path": row[0],
            "area": row[1],
            "filename": row[2],
            "size": row[3],
            "description": row[4],
        }
        for row in rows
    ]

    return results, total
