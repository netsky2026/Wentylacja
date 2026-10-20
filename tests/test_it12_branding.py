# Iteration 12: client branding (display_name/theme/logo), /api/branding, user theme preferences
import io
import os
import uuid
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = ("admin@chlewnia.pl", "Wentylacja!2026")
PW = "TestPass!2026"


def login(email, pw):
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    return s


def png(size=(600, 300), color=(255, 120, 0, 255), fmt="PNG"):
    b = io.BytesIO()
    Image.new("RGBA" if fmt != "JPEG" else "RGB", size, color if fmt != "JPEG" else color[:3]).save(b, fmt)
    return b.getvalue()


@pytest.fixture(scope="module")
def sa():
    return login(*ADMIN)


@pytest.fixture(scope="module")
def clients(sa):
    cs = sa.get(f"{API}/clients").json()["clients"]
    return {c["name"]: c for c in cs}


@pytest.fixture(scope="module")
def env(sa, clients):
    """TEST client + viewer users in TEST client and Kowalski client"""
    tag = uuid.uuid4().hex[:6]
    cid = sa.post(f"{API}/clients", json={"name": f"TEST_brand_{tag}"}).json()["id"]
    kid = clients["Ferma Kowalski"]["id"]
    mid = clients["Marco Polo"]["id"]
    users = {}
    for key, client_id, role in (("tv", cid, "viewer"), ("kv", kid, "viewer"), ("mv", mid, "viewer"), ("ka", kid, "admin")):
        email = f"test_{key}_{tag}@example.com"
        r = sa.post(f"{API}/users", json={"email": email, "password": PW, "role": role, "client_id": client_id, "name": key})
        assert r.status_code in (200, 201), r.text
        users[key] = (r.json().get("id"), email)
    yield {"cid": cid, "kid": kid, "mid": mid, "users": users}
    for uid, _ in users.values():
        sa.delete(f"{API}/users/{uid}")
    sa.delete(f"{API}/clients/{cid}")
    sa.put(f"{API}/auth/preferences", json={"theme": None})


class TestPatchClient:
    def test_patch_display_name_theme(self, sa, env):
        r = sa.patch(f"{API}/clients/{env['cid']}", json={"display_name": "  TEST Brand  ", "theme": "blue"})
        assert r.status_code == 200
        c = [c for c in sa.get(f"{API}/clients").json()["clients"] if c["id"] == env["cid"]][0]
        assert c["display_name"] == "TEST Brand" and c["theme"] == "blue" and c["logo_version"] is None

    def test_invalid_theme_422(self, sa, env):
        assert sa.patch(f"{API}/clients/{env['cid']}", json={"theme": "pink"}).status_code == 422

    def test_patch_unknown_client_404(self, sa):
        assert sa.patch(f"{API}/clients/000000000000000000000000", json={"theme": "blue"}).status_code == 404

    def test_non_superadmin_403(self, env):
        s = login(env["users"]["ka"][1], PW)
        assert s.patch(f"{API}/clients/{env['kid']}", json={"theme": "light"}).status_code == 403
        assert s.post(f"{API}/clients/{env['kid']}/logo", files={"file": ("a.png", png(), "image/png")}).status_code == 403
        assert s.delete(f"{API}/clients/{env['kid']}/logo").status_code == 403

    def test_display_name_too_long(self, sa, env):
        r = sa.patch(f"{API}/clients/{env['cid']}", json={"display_name": "x" * 200})
        print("long display_name status", r.status_code)
        assert r.status_code in (200, 422)


class TestLogo:
    def test_upload_resize_and_get(self, sa, env):
        r = sa.post(f"{API}/clients/{env['cid']}/logo", files={"file": ("l.png", png(), "image/png")})
        assert r.status_code == 200, r.text
        assert r.json()["logo_version"]
        g = sa.get(f"{API}/clients/{env['cid']}/logo")
        assert g.status_code == 200 and g.headers["content-type"].startswith("image/png")
        im = Image.open(io.BytesIO(g.content))
        assert im.format == "PNG" and max(im.size) == 256 and im.size == (256, 128)

    def test_own_viewer_200_other_404_unauth_401(self, env):
        tv = login(env["users"]["tv"][1], PW)
        assert tv.get(f"{API}/clients/{env['cid']}/logo").status_code == 200
        kv = login(env["users"]["kv"][1], PW)
        assert kv.get(f"{API}/clients/{env['cid']}/logo").status_code == 404
        assert requests.get(f"{API}/clients/{env['cid']}/logo").status_code == 401

    def test_jpeg_webp_accepted(self, sa, env):
        for fmt, mt in (("JPEG", "image/jpeg"), ("WEBP", "image/webp")):
            r = sa.post(f"{API}/clients/{env['cid']}/logo", files={"file": (f"l.{fmt.lower()}", png(fmt=fmt), mt)})
            assert r.status_code == 200, (fmt, r.text)

    def test_invalid_file_422(self, sa, env):
        r = sa.post(f"{API}/clients/{env['cid']}/logo", files={"file": ("x.png", b"not an image", "image/png")})
        assert r.status_code == 422
        gif = io.BytesIO(); Image.new("RGB", (10, 10)).save(gif, "GIF")
        assert sa.post(f"{API}/clients/{env['cid']}/logo", files={"file": ("x.gif", gif.getvalue(), "image/gif")}).status_code == 422

    def test_too_large_413(self, sa, env):
        big = os.urandom(1_100_000)
        assert sa.post(f"{API}/clients/{env['cid']}/logo", files={"file": ("b.png", big, "image/png")}).status_code == 413

    def test_delete_logo(self, sa, env):
        assert sa.delete(f"{API}/clients/{env['cid']}/logo").status_code == 200
        assert sa.get(f"{API}/clients/{env['cid']}/logo").status_code == 404
        b = sa.get(f"{API}/branding?client_id={env['cid']}").json()
        assert b["logo_version"] is None


class TestBranding:
    def test_superadmin_branding(self, sa, env, clients):
        b = sa.get(f"{API}/branding?client_id={env['kid']}").json()
        assert b["client_id"] == env["kid"] and b["app_name"] == "Kowalski Wentylacja" and b["theme"] == "amber"
        assert b["logo_version"]
        b2 = sa.get(f"{API}/branding?client_id={env['mid']}").json()
        assert b2["theme"] == "green" and b2["logo_version"] is None
        b3 = sa.get(f"{API}/branding").json()
        assert b3 == {"client_id": None, "app_name": None, "theme": "green", "logo_version": None}

    def test_client_user_ignores_client_id_param(self, env):
        kv = login(env["users"]["kv"][1], PW)
        b = kv.get(f"{API}/branding?client_id={env['mid']}").json()
        assert b["client_id"] == env["kid"] and b["theme"] == "amber"
        assert kv.get(f"{API}/clients/{env['kid']}/logo").status_code == 200
        mv = login(env["users"]["mv"][1], PW)
        assert mv.get(f"{API}/clients/{env['kid']}/logo").status_code == 404

    def test_branding_unauth_401(self):
        assert requests.get(f"{API}/branding").status_code == 401


class TestPreferences:
    def test_set_theme_and_me(self, env):
        s = login(env["users"]["kv"][1], PW)
        assert s.get(f"{API}/auth/me").json().get("theme") is None
        r = s.put(f"{API}/auth/preferences", json={"theme": "light"})
        assert r.status_code == 200 and r.json()["theme"] == "light"
        assert s.get(f"{API}/auth/me").json()["theme"] == "light"
        s2 = login(env["users"]["kv"][1], PW)
        assert s2.get(f"{API}/auth/me").json()["theme"] == "light"
        assert s.put(f"{API}/auth/preferences", json={"theme": None}).json()["theme"] is None

    def test_invalid_theme_422(self, sa):
        assert sa.put(f"{API}/auth/preferences", json={"theme": "red"}).status_code == 422

    def test_unauth_401(self):
        assert requests.put(f"{API}/auth/preferences", json={"theme": "blue"}).status_code == 401
