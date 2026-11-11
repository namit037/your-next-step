"""Your Next Step: the web API.

Run locally with:  uvicorn app.main:app --reload
"""

import sqlite3
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app import db, repository
from app.schemas import Country, Occupation, OccupationPage

MAX_COMPARE = 3
STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

app = FastAPI(
    title="Your Next Step",
    description="Search and compare careers using real public data (UK and US).",
)


def get_db() -> Iterator[sqlite3.Connection]:
    """Give each request its own database connection, closed afterwards."""
    path = db.get_db_path()
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail="Database not built yet. Run: python scripts/build_db.py",
        )
    conn = db.connect(path)
    try:
        yield conn
    finally:
        conn.close()


@app.get("/health")
def health() -> dict:
    """Tiny endpoint to check the server is running."""
    return {"status": "ok"}


@app.get("/education-levels", response_model=list[str])
def education_levels(conn: sqlite3.Connection = Depends(get_db)) -> list[str]:
    """Options for the education filter (US data only)."""
    return repository.education_levels(conn)


@app.get("/occupations", response_model=OccupationPage)
def list_occupations(
    country: Country,
    q: str | None = Query(None, max_length=100, description="Search in the title"),
    min_pay: float | None = Query(None, ge=0),
    education: str | None = Query(None, max_length=100, description="US only"),
    sort: Literal["title", "pay", "growth"] = "title",
    order: Literal["asc", "desc"] = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    conn: sqlite3.Connection = Depends(get_db),
) -> OccupationPage:
    """Search and filter occupations within one country."""
    if education and country != "US":
        raise HTTPException(400, "The education filter is only available for US.")
    rows, total = repository.search_occupations(
        conn,
        country=country,
        q=q,
        min_pay=min_pay,
        education=education,
        sort=sort,
        order=order,
        page=page,
        page_size=page_size,
    )
    return OccupationPage(
        items=[Occupation(**dict(r)) for r in rows],
        total=total,
        page=page,
        page_size=page_size,
    )


# Note: /compare is declared before /occupations/{id} so the paths never clash.
@app.get("/compare", response_model=list[Occupation])
def compare(
    ids: str = Query(..., description="2 or 3 ids, comma separated, e.g. 1,2,3"),
    conn: sqlite3.Connection = Depends(get_db),
) -> list[Occupation]:
    """Return 2-3 occupations from the same country, side by side."""
    try:
        wanted = list(dict.fromkeys(int(x) for x in ids.split(",")))  # dedupe
    except ValueError:
        raise HTTPException(422, "ids must be whole numbers separated by commas.")
    if not 2 <= len(wanted) <= MAX_COMPARE:
        raise HTTPException(422, f"Pick between 2 and {MAX_COMPARE} different ids.")

    found = {r["id"]: r for r in repository.get_occupations(conn, wanted)}
    missing = [i for i in wanted if i not in found]
    if missing:
        raise HTTPException(404, f"Occupation(s) not found: {missing}")

    rows = [found[i] for i in wanted]  # keep the order the user asked for
    if len({r["country"] for r in rows}) > 1:
        raise HTTPException(400, "Can only compare occupations from the same country.")
    return [Occupation(**dict(r)) for r in rows]


@app.get("/occupations/{occupation_id}", response_model=Occupation)
def read_occupation(
    occupation_id: int, conn: sqlite3.Connection = Depends(get_db)
) -> Occupation:
    row = repository.get_occupation(conn, occupation_id)
    if row is None:
        raise HTTPException(404, "Occupation not found.")
    return Occupation(**dict(row))


# --- the website itself -----------------------------------------------------------
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
def home() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")
