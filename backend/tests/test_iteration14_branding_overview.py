# Iteration 14: public client branding (slug link, logo icons, manifest), slug validation, tenant isolation for overview, dynsec no-op
import io
import os
import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
KOW_ID = "6ad7dcc3261e5ba3c23315b7"
MP_ID = "6ad7dcb08b38a7c48f3db7d2"


@pytest.fixture(scope="module")
def sa():
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip(f"login failed {r.status_code}")
    return s


# --- public branding (no auth) ---
class TestPublic:
    def test_branding_known(self):
        r = requests.get(f"{API}/public/branding/kowalski")
        assert r.status_code == 200
        d = r.json()
        assert d["app_name"] == "Kowalski Wentylacja" and d["theme"] == "amber" and d["logo_version"] == "985bf926"
        assert d["slug"] == "kowalski"

    @pytest.mark.parametrize("slug", ["nieistnieje", "A", "x", "..%2F..", "UPPER"])
    def test_branding_unknown_404(self, slug):
        assert requests.get(f"{API}/public/branding/{slug}").status_code == 404

    def test_empty_slug_client_not_reachable(self):
        # Marco Polo has slug "" -> must not be found by any route
        assert requests.get(f"{API}/public/branding/").status_code in (404, 405)

    @pytest.mark.parametrize("size", [180, 192, 512])
    def test_logo_square_sizes(self, size):
        r = requests.get(f"{API}/public/logo/kowalski?size={size}")
        assert r.status_code == 200 and r.headers["content-type"].startswith("image/png")
        assert Image.open(io.BytesIO(r.content)).size == (size, size)

    def test_logo_original(self):
        r = requests.get(f"{API}/public/logo/kowalski")
        assert r.status_code == 200
        img = Image.open(io.BytesIO(r.content))
        assert img.format == "PNG" and max(img.size) <= 256

    def test_logo_unknown_404(self):
        assert requests.get(f"{API}/public/logo/nieistnieje?size=192").status_code == 404

    def test_manifest(self):
        r = requests.get(f"{API}/public/manifest/kowalski")
        assert r.status_code == 200
        assert "manifest+json" in r.headers["content-type"]
        m = r.json()
        assert m["start_url"] == "/?klient=kowalski" and m["name"] == "Kowalski Wentylacja"
        assert m["display"] == "standalone" and m["scope"] == "/"
        srcs = [i["src"] for i in m["icons"]]
        assert any("/api/public/logo/kowalski?size=192" in s for s in srcs)
        assert any("/api/public/logo/kowalski?size=512" in s for s in srcs)
        # icon URLs resolve
        for s in srcs:
            assert requests.get(f"{BASE_URL}{s}").status_code == 200

    def test_manifest_unknown_404(self):
        assert requests.get(f"{API}/public/manifest/nieistnieje").status_code == 404


# --- slug management (superadmin) ---
class TestSlug:
    def test_invalid_slug_422(self, sa):
        for bad in ["Kowal", "a", "-abc", "ab cd", "a" * 41, "ąę"]:
            assert sa.patch(f"{API}/clients/{MP_ID}", json={"slug": bad}).status_code == 422, bad

    def test_duplicate_slug_409(self, sa):
        r = sa.patch(f"{API}/clients/{MP_ID}", json={"slug": "kowalski"})
        assert r.status_code == 409

    def test_set_and_clear_slug(self, sa):
        r = sa.patch(f"{API}/clients/{MP_ID}", json={"slug": "test-mp"})
        assert r.status_code == 200
        b = requests.get(f"{API}/public/branding/test-mp")
        assert b.status_code == 200 and b.json()["app_name"] is None and b.json()["logo_version"] is None
        m = requests.get(f"{API}/public/manifest/test-mp").json()
        assert m["name"] == "Marco Polo Wentylacja" and m["icons"][0]["src"] == "/icon-192.png"
        assert requests.get(f"{API}/public/logo/test-mp").status_code == 404
        r = sa.patch(f"{API}/clients/{MP_ID}", json={"slug": ""})
        assert r.status_code == 200
        assert requests.get(f"{API}/public/branding/test-mp").status_code == 404
        c = [c for c in sa.get(f"{API}/clients").json()["clients"] if c["id"] == MP_ID][0]
        assert c["slug"] == ""

    def test_non_superadmin_cannot_patch(self):
        assert requests.patch(f"{API}/clients/{MP_ID}", json={"slug": "zzz"}).status_code == 401


# --- tenant isolation + offline device for overview; dynsec is no-op in preview ---
class TestTenantAndDevices:
    def test_client_user_sees_only_own_device(self, sa):
        email = "test_it14_viewer@example.com"
        r = sa.post(f"{API}/users", json={"email": email, "password": "TestPass!2026x", "role": "viewer", "client_id": MP_ID})
        assert r.status_code in (200, 201), r.text
        uid = r.json().get("id")
        try:
            u = requests.Session()
            assert u.post(f"{API}/auth/login", json={"email": email, "password": "TestPass!2026x"}).status_code == 200
            devs = u.get(f"{API}/devices").json()["devices"]
            assert [d["device_id"] for d in devs] == ["chlodnia-01"]
            assert u.get(f"{API}/devices/kowalski-a/thresholds").status_code in (403, 404)
            br = u.get(f"{API}/branding").json()
            assert br["client_id"] == MP_ID
        finally:
            if uid:
                sa.delete(f"{API}/users/{uid}")

    def test_create_offline_device_and_delete(self, sa):
        r = sa.post(f"{API}/devices", json={"client_id": KOW_ID, "name": "TEST_off", "device_id": "test-it14-off", "chambers": 2, "simulated": False})
        assert r.status_code == 200, r.text
        try:
            assert r.json()["mqtt_password"]
            d = [d for d in sa.get(f"{API}/devices").json()["devices"] if d["device_id"] == "test-it14-off"][0]
            assert d["online"] is False and d["simulated"] is False
        finally:
            assert sa.delete(f"{API}/devices/test-it14-off").status_code == 200
        assert all(d["device_id"] != "test-it14-off" for d in sa.get(f"{API}/devices").json()["devices"])
