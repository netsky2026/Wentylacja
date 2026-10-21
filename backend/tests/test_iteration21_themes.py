# Iteration 21: new color themes (forest, grass, sun, orange) - user prefs, client theme, public branding/manifest
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
H = {"Origin": BASE_URL}
NEW = ["forest", "grass", "sun", "orange"]
BG = {"forest": "#050F07", "grass": "#2E9A3E", "sun": "#FFD000", "orange": "#FF8A1F"}


@pytest.fixture(scope="module")
def s():
    ss = requests.Session()
    ss.headers.update(H)
    r = ss.post(f"{BASE_URL}/api/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"})
    assert r.status_code == 200, r.text
    me = ss.get(f"{BASE_URL}/api/auth/me").json()
    orig_user_theme = me.get("theme")
    clients = ss.get(f"{BASE_URL}/api/clients").json()["clients"]
    kow = next(c for c in clients if c.get("slug") == "kowalski")
    ss.kow = kow
    ss.orig_client_theme = kow.get("theme")
    yield ss
    ss.put(f"{BASE_URL}/api/auth/preferences", json={"theme": orig_user_theme})
    ss.patch(f"{BASE_URL}/api/clients/{kow['id']}", json={"theme": ss.orig_client_theme or "green"})
    assert ss.get(f"{BASE_URL}/api/auth/me").json().get("theme") == orig_user_theme


# User preference theme
@pytest.mark.parametrize("theme", NEW)
def test_user_theme_new(s, theme):
    r = s.put(f"{BASE_URL}/api/auth/preferences", json={"theme": theme})
    assert r.status_code == 200, r.text
    assert r.json()["theme"] == theme
    assert s.get(f"{BASE_URL}/api/auth/me").json()["theme"] == theme


def test_user_theme_invalid(s):
    r = s.put(f"{BASE_URL}/api/auth/preferences", json={"theme": "pink"})
    assert r.status_code == 422


def test_user_theme_null(s):
    r = s.put(f"{BASE_URL}/api/auth/preferences", json={"theme": None})
    assert r.status_code == 200 and r.json()["theme"] is None


# Client theme + public branding / manifest
@pytest.mark.parametrize("theme", NEW)
def test_client_theme_branding(s, theme):
    r = s.patch(f"{BASE_URL}/api/clients/{s.kow['id']}", json={"theme": theme})
    assert r.status_code == 200, r.text
    b = requests.get(f"{BASE_URL}/api/public/branding/kowalski").json()
    assert b["theme"] == theme
    m = requests.get(f"{BASE_URL}/api/public/manifest/kowalski").json()
    assert m["background_color"].upper() == BG[theme].upper()
    assert m.get("theme_color", BG[theme]).upper() == BG[theme].upper()


def test_client_theme_invalid(s):
    r = s.patch(f"{BASE_URL}/api/clients/{s.kow['id']}", json={"theme": "pink"})
    assert r.status_code == 422
