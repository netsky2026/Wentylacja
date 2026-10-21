# Iteration 17: auto-generated unique client slug on POST /api/clients, public branding, regression for seeded clients
import os

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
CREATED = []


@pytest.fixture(scope="module")
def admin():
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    yield s
    for cid in CREATED:
        s.delete(f"{BASE_URL}/api/clients/{cid}")


def mk(s, name):
    r = s.post(f"{BASE_URL}/api/clients", json={"name": name})
    assert r.status_code == 200, r.text
    d = r.json()
    CREATED.append(d["id"])
    return d


# Slug generation
def test_polish_transliteration(admin):
    d = mk(admin, "Ferma Żółć Nowak")
    assert d["slug"] == "ferma-zolc-nowak"
    assert d["name"] == "Ferma Żółć Nowak"


def test_duplicate_suffix(admin):
    assert mk(admin, "Ferma Żółć Nowak")["slug"] == "ferma-zolc-nowak-2"
    assert mk(admin, "ferma zolc nowak")["slug"] == "ferma-zolc-nowak-3"


def test_symbols_fallback(admin):
    s = mk(admin, "!!")["slug"]
    assert s == "ferma" or s.startswith("ferma-")


def test_single_char_fallback(admin):
    s = mk(admin, "ą")["slug"]
    assert s == "ferma" or s.startswith("ferma-")


def test_long_name_slug_valid(admin):
    s = mk(admin, "Bardzo długa nazwa fermy " * 3)["slug"]
    assert len(s) <= 40 and not s.endswith("-")
    assert admin.get(f"{BASE_URL}/api/public/branding/{s}").status_code == 200


# Public branding + persistence in list
def test_public_branding_and_list(admin):
    r = requests.get(f"{BASE_URL}/api/public/branding/ferma-zolc-nowak")
    assert r.status_code == 200
    assert r.json()["slug"] == "ferma-zolc-nowak"
    lst = admin.get(f"{BASE_URL}/api/clients").json()["clients"]
    slugs = {c["slug"] for c in lst}
    assert {"ferma-zolc-nowak", "ferma-zolc-nowak-2", "ferma-zolc-nowak-3"} <= slugs
    assert all(c["slug"] for c in lst), "every client should have a slug"


def test_manifest_new_client(admin):
    r = requests.get(f"{BASE_URL}/api/public/manifest/ferma-zolc-nowak")
    assert r.status_code == 200
    assert r.json()["start_url"] == "/?klient=ferma-zolc-nowak"


# Regression: seeded client unchanged
def test_kowalski_unchanged(admin):
    lst = admin.get(f"{BASE_URL}/api/clients").json()["clients"]
    k = [c for c in lst if c["name"] == "Ferma Kowalski"]
    assert k and k[0]["slug"] == "kowalski"
    assert any(c["name"] == "Marco Polo" for c in lst)


def test_unauth_create_rejected():
    r = requests.post(f"{BASE_URL}/api/clients", json={"name": "x"}, headers={"Origin": BASE_URL})
    assert r.status_code in (401, 403)


def test_cleanup_deletes(admin):
    for cid in list(CREATED):
        r = admin.delete(f"{BASE_URL}/api/clients/{cid}")
        assert r.status_code == 200
        CREATED.remove(cid)
    assert requests.get(f"{BASE_URL}/api/public/branding/ferma-zolc-nowak").status_code == 404
