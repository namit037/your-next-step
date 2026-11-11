"""All SQL lives here, so the API routes stay short and easy to read.

Every value from the user goes in as a query parameter (the `?` marks), never
pasted into the SQL text. That is what prevents SQL injection.
"""

import sqlite3

# Users pick a sort name; we map it to a real column from this fixed list.
SORT_COLUMNS = {"title": "title", "pay": "median_pay", "growth": "growth_pct"}


def _escape_like(text: str) -> str:
    """Make % and _ in a search term match literally instead of as wildcards."""
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def search_occupations(
    conn: sqlite3.Connection,
    *,
    country: str,
    q: str | None = None,
    min_pay: float | None = None,
    education: str | None = None,
    sort: str = "title",
    order: str = "asc",
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[sqlite3.Row], int]:
    """Return one page of matching occupations and the total match count."""
    where = ["country = ?"]
    params: list = [country]
    if q:
        where.append("title LIKE ? ESCAPE '\\'")
        params.append(f"%{_escape_like(q)}%")
    if min_pay is not None:
        where.append("median_pay >= ?")
        params.append(min_pay)
    if education:
        where.append("education = ?")
        params.append(education)
    where_sql = " AND ".join(where)

    total = conn.execute(
        f"SELECT COUNT(*) FROM occupations WHERE {where_sql}", params
    ).fetchone()[0]

    column = SORT_COLUMNS[sort]  # safe: sort was validated against this dict
    direction = "DESC" if order == "desc" else "ASC"
    rows = conn.execute(
        f"SELECT * FROM occupations WHERE {where_sql} "
        f"ORDER BY {column} IS NULL, {column} {direction}, title "  # NULLs last
        "LIMIT ? OFFSET ?",
        [*params, page_size, (page - 1) * page_size],
    ).fetchall()
    return rows, total


def get_occupation(conn: sqlite3.Connection, occupation_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM occupations WHERE id = ?", (occupation_id,)
    ).fetchone()


def get_occupations(conn: sqlite3.Connection, ids: list[int]) -> list[sqlite3.Row]:
    """Fetch several occupations by id (order not guaranteed)."""
    marks = ",".join("?" for _ in ids)
    return conn.execute(
        f"SELECT * FROM occupations WHERE id IN ({marks})", ids
    ).fetchall()
