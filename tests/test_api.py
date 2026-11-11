from fastapi.testclient import TestClient

from app.main import app


def titles(response):
    return [item["title"] for item in response.json()["items"]]


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


# --- search -----------------------------------------------------------------
def test_search_only_returns_the_chosen_country(client):
    assert titles(client.get("/occupations?country=US&q=nurse")) == ["Registered nurses"]
    assert titles(client.get("/occupations?country=UK&q=nurse")) == ["Nurses"]


def test_search_is_case_insensitive(client):
    assert client.get("/occupations?country=US&q=NURSE").json()["total"] == 1


def test_percent_sign_is_not_a_wildcard(client):
    assert client.get("/occupations?country=US&q=%25").json()["total"] == 0


def test_country_is_required_and_validated(client):
    assert client.get("/occupations").status_code == 422
    assert client.get("/occupations?country=FR").status_code == 422


def test_min_pay_filter(client):
    r = client.get("/occupations?country=US&min_pay=100000")
    assert titles(r) == ["Software developers"]


def test_sort_by_pay_descending(client):
    r = client.get("/occupations?country=US&sort=pay&order=desc")
    assert titles(r) == ["Software developers", "Registered nurses", "Electricians"]


def test_pagination(client):
    first = client.get("/occupations?country=US&page_size=2&page=1").json()
    second = client.get("/occupations?country=US&page_size=2&page=2").json()
    assert first["total"] == 3
    assert len(first["items"]) == 2
    assert len(second["items"]) == 1


def test_page_size_is_capped(client):
    assert client.get("/occupations?country=US&page_size=500").status_code == 422


def test_education_filter_us_only(client):
    ok = client.get("/occupations?country=US&education=Bachelor's degree")
    assert ok.json()["total"] == 2
    assert client.get("/occupations?country=UK&education=x").status_code == 400


def test_education_levels(client):
    assert client.get("/education-levels").json() == [
        "Bachelor's degree",
        "High school diploma",
    ]


# --- single occupation --------------------------------------------------------
def test_get_one_occupation(client):
    r = client.get("/occupations/1")
    assert r.status_code == 200
    assert r.json()["title"] == "Registered nurses"


def test_unknown_occupation_is_404(client):
    assert client.get("/occupations/999").status_code == 404


# --- compare ------------------------------------------------------------------
def test_compare_two_from_same_country(client):
    r = client.get("/compare?ids=1,2")
    assert r.status_code == 200
    assert [o["id"] for o in r.json()] == [1, 2]


def test_compare_rejects_mixed_countries(client):
    assert client.get("/compare?ids=1,4").status_code == 400


def test_compare_needs_two_to_three_ids(client):
    assert client.get("/compare?ids=1").status_code == 422
    assert client.get("/compare?ids=1,2,3,4").status_code == 422


def test_compare_unknown_id_is_404(client):
    assert client.get("/compare?ids=1,999").status_code == 404


def test_compare_bad_ids_are_422(client):
    assert client.get("/compare?ids=abc,2").status_code == 422


# --- database missing ---------------------------------------------------------
def test_missing_database_gives_clear_503(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "nope.db"))
    r = TestClient(app).get("/occupations?country=US")
    assert r.status_code == 503


# --- the website ----------------------------------------------------------------
def test_home_page_and_static_files_are_served():
    web = TestClient(app)
    home = web.get("/")
    assert home.status_code == 200
    assert "Your Next Step" in home.text
    assert web.get("/static/app.js").status_code == 200
    assert web.get("/static/style.css").status_code == 200
