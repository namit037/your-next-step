"""Tests for the data-building script (uses the real files in data/source/)."""

import pytest

from scripts import build_db
from scripts.build_db import clean_text, column_index, to_number


# --- helpers ----------------------------------------------------------------
@pytest.mark.parametrize(
    "raw, expected",
    [
        (5, 5.0),
        ("$239,200", 239200.0),
        (">=239200", 239200.0),
        ("12.5", 12.5),
        ("x", None),
        ("..", None),
        ("—", None),
        ("", None),
        (None, None),
    ],
)
def test_to_number(raw, expected):
    assert to_number(raw) == expected


def test_clean_text():
    assert clean_text("  Bachelor's degree ") == "Bachelor's degree"
    assert clean_text("—") is None
    assert clean_text(None) is None


def test_column_index_finds_and_fails_loudly():
    assert column_index(["a", " b "], "b") == 1
    with pytest.raises(ValueError):
        column_index(["a"], "missing")


# --- the built database -------------------------------------------------------
@pytest.fixture(scope="module")
def built(tmp_path_factory):
    path = tmp_path_factory.mktemp("db") / "occupations.db"
    counts = build_db.build(path)
    from app import db

    conn = db.connect(path)
    yield counts, conn
    conn.close()


def test_both_countries_are_loaded(built):
    counts, _ = built
    assert counts["US"] > 800
    assert counts["UK"] > 400


def test_us_known_row(built):
    _, conn = built
    row = conn.execute(
        "SELECT * FROM occupations WHERE country='US' AND code='29-1141'"
    ).fetchone()
    assert row["title"] == "Registered nurses"
    assert row["median_pay"] == 97550
    assert row["education"] == "Bachelor's degree"
    assert row["currency"] == "USD"


def test_uk_join_attaches_pay_to_growth(built):
    _, conn = built
    row = conn.execute(
        "SELECT * FROM occupations WHERE country='UK' AND code='2134'"
    ).fetchone()
    assert row["title"].startswith("Programmers")
    assert 30_000 < row["median_pay"] < 120_000
    assert row["currency"] == "GBP"
    assert row["education"] is None  # not available in the UK sources


def test_most_uk_rows_have_pay(built):
    _, conn = built
    total, with_pay = conn.execute(
        "SELECT COUNT(*), SUM(median_pay IS NOT NULL) FROM occupations WHERE country='UK'"
    ).fetchone()
    assert with_pay / total > 0.8


def test_values_are_sane(built):
    _, conn = built
    bad = conn.execute(
        "SELECT COUNT(*) FROM occupations WHERE median_pay <= 0"
        " OR growth_pct < -100 OR growth_pct > 500"
    ).fetchone()[0]
    assert bad == 0


def test_rebuilding_does_not_duplicate(tmp_path):
    path = tmp_path / "again.db"
    first = build_db.build(path)
    second = build_db.build(path)
    assert first == second
