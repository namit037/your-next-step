"""Shared test setup: a small throwaway database for every test.

The rows below are MADE-UP TEST DATA (not real statistics). They only exist so
the tests have something predictable to search.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.main import app, get_db

# (country, code, title, median_pay, currency, growth_pct, education, employment)
SAMPLE_ROWS = [
    ("US", "T-1", "Registered nurses", 90000, "USD", 5.0, "Bachelor's degree", 3000),
    ("US", "T-2", "Software developers", 130000, "USD", 15.0, "Bachelor's degree", 1500),
    ("US", "T-3", "Electricians", 62000, "USD", 9.0, "High school diploma", 800),
    ("UK", "T-4", "Nurses", 40000, "GBP", 6.0, None, 700),
    ("UK", "T-5", "Software development professionals", 55000, "GBP", 12.0, None, 600),
    ("UK", "T-6", "Electricians and electrical fitters", 42000, "GBP", 3.0, None, 500),
]


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "test.db"
    conn = db.connect(path)
    db.init_schema(conn)
    conn.executemany(
        "INSERT INTO occupations (country, code, title, median_pay, currency,"
        " growth_pct, education, employment, source) VALUES (?,?,?,?,?,?,?,?, 'test')",
        SAMPLE_ROWS,
    )
    conn.commit()
    conn.close()

    def override_get_db():
        conn = db.connect(path)
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
