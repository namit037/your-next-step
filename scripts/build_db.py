"""Build data/occupations.db from the public datasets in data/source/.

Run from the project root:   python scripts/build_db.py

Sources
  US  BLS Employment Projections 2025-35 (pay, growth, entry education)
  UK  ONS ASHE Table 14.7a (median annual pay, full-time employees, April 2026 provisional)
      + DfE Skills Imperative 2035 (jobs by year -> projected growth)
  The two UK files are joined on the 4-digit SOC 2020 occupation code.
"""

import csv
import re
import sys
from pathlib import Path

import openpyxl

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))  # lets `python scripts/build_db.py` import `app`

from app import db  # noqa: E402

SOURCE_DIR = ROOT / "data" / "source"
US_FILE = SOURCE_DIR / "us_bls_occupation_projections_2025-35.xlsx"
UK_PAY_FILE = SOURCE_DIR / "uk_ons_ashe_table14.7a_annual_pay_gross_2026.xlsx"
UK_GROWTH_FILE = SOURCE_DIR / "uk_dfe_skills_imperative_2035_by_occupation.csv"

# Growth is measured over the same 10 years as the US data (2025 -> 2035).
UK_BASE_YEAR, UK_END_YEAR = "2025", "2035"


# --- small helpers -------------------------------------------------------------
def to_number(value) -> float | None:
    """Turn a spreadsheet cell into a number, or None if it isn't one.

    Handles values like '$239,200', '>=239200' and the markers statistics
    offices use for hidden figures ('x', '..', '—').
    """
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.\-]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def clean_text(value) -> str | None:
    text = str(value).strip() if value is not None else ""
    return None if text in ("", "—", "-", "..") else text


def column_index(header: list, name: str) -> int:
    """Find a column by its heading, so a reordered file fails loudly, not silently."""
    for i, heading in enumerate(header):
        if heading is not None and str(heading).strip() == name:
            return i
    raise ValueError(f"Column '{name}' not found. Has the source file changed?")


# --- US ------------------------------------------------------------------------
def load_us(path: Path) -> list[dict]:
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    rows = wb["Table 1.2"].iter_rows(values_only=True)
    next(rows)  # table title
    header = list(next(rows))
    c_title = column_index(header, "2025 National Employment Matrix title")
    c_code = column_index(header, "2025 National Employment Matrix code")
    c_type = column_index(header, "Occupation type")
    c_jobs = column_index(header, "Employment, 2025")
    c_growth = column_index(header, "Employment change, percent, 2025–35")
    c_pay = column_index(header, "Median annual wage, dollars, 2025")
    c_edu = column_index(header, "Typical education needed for entry")

    records = []
    for row in rows:
        if row[c_type] != "Line item":  # skip group totals, keep real occupations
            continue
        jobs = to_number(row[c_jobs])  # BLS reports employment in thousands
        records.append(
            {
                "country": "US",
                "code": str(row[c_code]).strip(),
                "title": str(row[c_title]).strip(),
                "median_pay": to_number(row[c_pay]),
                "currency": "USD",
                "growth_pct": to_number(row[c_growth]),
                "education": clean_text(row[c_edu]),
                "employment": round(jobs * 1000) if jobs is not None else None,
                "source": "US Bureau of Labor Statistics, Employment Projections 2025-35",
            }
        )
    return records


# --- UK ------------------------------------------------------------------------
def load_uk_growth(path: Path) -> dict[str, dict]:
    """Return {soc_code: {title, jobs_start, jobs_end}} from the DfE projections."""
    pattern = re.compile(r"^(\d{4}) - (.+?)(?: SOC2020)?$")
    jobs: dict[str, dict] = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            match = pattern.match(row["occupation_name"].strip())
            if not match or row["time_period"] not in (UK_BASE_YEAR, UK_END_YEAR):
                continue
            code, title = match.groups()
            entry = jobs.setdefault(code, {"title": title})
            key = "jobs_start" if row["time_period"] == UK_BASE_YEAR else "jobs_end"
            entry[key] = to_number(row["jobs"])
    return jobs


def load_uk_pay(path: Path) -> dict[str, float | None]:
    """Return {soc_code: median annual pay, full-time} for 4-digit occupations."""
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    # Full-time jobs only: the 'All' sheet mixes in part-time jobs, whose annual
    # pay is far lower and not comparable with the US full-time-equivalent wages.
    rows = wb["Full-Time"].iter_rows(values_only=True)
    for row in rows:  # skip the title lines until the heading row
        if row[0] == "Description":
            header = list(row)
            break
    else:
        raise ValueError("Heading row not found in ASHE file.")
    c_code = column_index(header, "Code")
    c_median = column_index(header, "Median")

    pay = {}
    for row in rows:
        code = str(row[c_code] or "").lstrip("'").strip()
        if re.fullmatch(r"\d{4}", code):  # 4-digit = individual occupations
            pay[code] = to_number(row[c_median])
    return pay


def load_uk(pay_path: Path, growth_path: Path) -> list[dict]:
    growth = load_uk_growth(growth_path)
    pay = load_uk_pay(pay_path)
    records = []
    for code, entry in sorted(growth.items()):
        start, end = entry.get("jobs_start"), entry.get("jobs_end")
        growth_pct = (end / start - 1) * 100 if start and end is not None else None
        records.append(
            {
                "country": "UK",
                "code": code,
                "title": entry["title"],
                "median_pay": pay.get(code),
                "currency": "GBP",
                "growth_pct": round(growth_pct, 1) if growth_pct is not None else None,
                "education": None,  # not in the UK sources
                "employment": round(start) if start else None,
                "source": "ONS ASHE 2026 (provisional) + DfE Skills Imperative 2035",
            }
        )
    return records


# --- build ---------------------------------------------------------------------
def build(db_path: Path) -> dict[str, int]:
    """Create a fresh database file and return how many rows each country got."""
    records = load_us(US_FILE) + load_uk(UK_PAY_FILE, UK_GROWTH_FILE)

    db_path.parent.mkdir(parents=True, exist_ok=True)
    db_path.unlink(missing_ok=True)  # always rebuild from scratch
    conn = db.connect(db_path)
    db.init_schema(conn)
    conn.executemany(
        "INSERT INTO occupations (country, code, title, median_pay, currency,"
        " growth_pct, education, employment, source)"
        " VALUES (:country, :code, :title, :median_pay, :currency,"
        " :growth_pct, :education, :employment, :source)",
        records,
    )
    conn.commit()
    counts = {
        r["country"]: r["n"]
        for r in conn.execute("SELECT country, COUNT(*) AS n FROM occupations GROUP BY country")
    }
    conn.close()
    return counts


if __name__ == "__main__":
    target = db.get_db_path()
    result = build(target)
    print(f"Built {target}: {result}")
