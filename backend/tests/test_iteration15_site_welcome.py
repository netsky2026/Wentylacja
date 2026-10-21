# Iteration 15: platform site settings (phone/email/logo), site manifest, client manifest fallback, auth guards, alarm-settings regression
import io
import os

import pytest
import requests
from PIL import Image

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
ADMIN = {"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"}
MARCO_POLO_ID = "6ad7dcb08b38a7c48f3db7d2"
KOWALSKI_ID = "6ad7dcc3261e5ba3c23315b7"
TMP_SLUG = "test-it15-mp"


def png_bytes(color=(0, 160, 60, 255), size=(300, 200)):
    buf = io.BytesIO()
    Image.new("RGBA", size, color).save(buf, "PNG")
    return buf.getvalue()


def session():
    s = requests.Session()
    s.headers.update({"Origin": BASE_URL})
    return s


@pytest.fixture(scope="module")
def admin():
    s = session()
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN)
    if r.status_code != 200:
        pytest.skip(f"admin login failed {r.status_code} {r.text}")
    return s


@pytest.fixture(scope="module")
def viewer(admin):
    # temp client-level user (admin role of Kowalski) for 403 checks
    email = "test_it15_admin@example.com"
    r = admin.post(f"{BASE_URL}/api/users", json={"email": email, "password": "TestPass!2026x", "role": "admin", "client_id": KOWALSKI_ID})
    assert r.status_code in (200, 201), r.text
    uid = r.json().get("id")
    s = session()
    lr = s.post(f"{BASE_URL}/api/auth/login", json={"email": email, "password": "TestPass!2026x"})
    assert lr.status_code == 200, lr.text
    yield s
    if uid:
        admin.delete(f"{BASE_URL}/api/users/{uid}")


class TestSitePublic:
    def test_public_site_shape(self):
        r = requests.get(f"{BASE_URL}/api/public/site")
        assert r.status_code == 200
        d = r.json()
        assert set(d) >= {"phone", "email", "logo_version"}
        assert isinstance(d["phone"], str) and isinstance(d["email"], str)

    def test_unauth_mutations_401(self):
        s = session()
        assert s.put(f"{BASE_URL}/api/site", json={"phone": "", "email": ""}).status_code == 401
        assert s.post(f"{BASE_URL}/api/site/logo", files={"file": ("a.png", png_bytes(), "image/png")}).status_code == 401
        assert s.delete(f"{BASE_URL}/api/site/logo").status_code == 401

    def test_no_origin_forbidden(self, admin):
        s = requests.Session()
        s.cookies.update(admin.cookies)
        r = s.put(f"{BASE_URL}/api/site", json={"phone": "", "email": ""}, headers={"Origin": "https://evil.example.com"})
        assert r.status_code == 403

    def test_client_admin_403(self, viewer):
        assert viewer.put(f"{BASE_URL}/api/site", json={"phone": "1", "email": ""}).status_code == 403
        assert viewer.post(f"{BASE_URL}/api/site/logo", files={"file": ("a.png", png_bytes(), "image/png")}).status_code == 403
        assert viewer.delete(f"{BASE_URL}/api/site/logo").status_code == 403


class TestSiteContact:
    def test_put_and_get(self, admin):
        r = admin.put(f"{BASE_URL}/api/site", json={"phone": " +48 600 100 200 ", "email": "biuro@marcopolo.pl"})
        assert r.status_code == 200, r.text
        assert r.json()["phone"] == "+48 600 100 200"
        g = requests.get(f"{BASE_URL}/api/public/site").json()
        assert g["phone"] == "+48 600 100 200" and g["email"] == "biuro@marcopolo.pl"

    @pytest.mark.parametrize("body", [{"phone": "abc", "email": ""}, {"phone": "", "email": "nope"},
                                      {"phone": "", "email": "a@b.pl;c@d.pl"}, {"phone": "1" * 41, "email": ""}])
    def test_invalid_422(self, admin, body):
        assert admin.put(f"{BASE_URL}/api/site", json=body).status_code == 422

    def test_clear(self, admin):
        r = admin.put(f"{BASE_URL}/api/site", json={"phone": "", "email": ""})
        assert r.status_code == 200
        g = requests.get(f"{BASE_URL}/api/public/site").json()
        assert g["phone"] == "" and g["email"] == ""


class TestSiteLogo:
    def test_upload_and_icons(self, admin):
        r = admin.post(f"{BASE_URL}/api/site/logo", files={"file": ("l.png", png_bytes(), "image/png")})
        assert r.status_code == 200, r.text
        v = r.json()["logo_version"]
        assert requests.get(f"{BASE_URL}/api/public/site").json()["logo_version"] == v
        orig = requests.get(f"{BASE_URL}/api/public/site/logo")
        assert orig.status_code == 200 and orig.headers["content-type"] == "image/png"
        assert max(Image.open(io.BytesIO(orig.content)).size) <= 256
        for size in (32, 180, 192, 512):
            ic = requests.get(f"{BASE_URL}/api/public/site/logo?size={size}")
            assert ic.status_code == 200
            assert Image.open(io.BytesIO(ic.content)).size == (size, size)

    def test_site_manifest_uses_logo(self):
        m = requests.get(f"{BASE_URL}/api/public/manifest")
        assert m.status_code == 200
        d = m.json()
        assert d["start_url"] == "/" and d["name"] == "Marco Polo Wentylacja"
        assert all("/api/public/site/logo?size=" in i["src"] for i in d["icons"])

    def test_client_without_logo_falls_back(self, admin):
        r = admin.patch(f"{BASE_URL}/api/clients/{MARCO_POLO_ID}", json={"slug": TMP_SLUG})
        assert r.status_code == 200, r.text
        try:
            d = requests.get(f"{BASE_URL}/api/public/manifest/{TMP_SLUG}").json()
            assert d["start_url"] == f"/?klient={TMP_SLUG}"
            assert all("/api/public/site/logo?size=" in i["src"] for i in d["icons"])
        finally:
            admin.patch(f"{BASE_URL}/api/clients/{MARCO_POLO_ID}", json={"slug": ""})

    def test_client_with_logo_keeps_own(self):
        d = requests.get(f"{BASE_URL}/api/public/manifest/kowalski").json()
        assert all("/api/public/logo/kowalski" in i["src"] for i in d["icons"])

    def test_invalid_upload(self, admin):
        r = admin.post(f"{BASE_URL}/api/site/logo", files={"file": ("x.png", b"not an image", "image/png")})
        assert r.status_code == 422
        big = admin.post(f"{BASE_URL}/api/site/logo", files={"file": ("x.png", b"0" * 1_000_500, "image/png")})
        assert big.status_code == 413

    def test_delete_restores_default(self, admin):
        assert admin.delete(f"{BASE_URL}/api/site/logo").status_code == 200
        assert requests.get(f"{BASE_URL}/api/public/site").json()["logo_version"] is None
        assert requests.get(f"{BASE_URL}/api/public/site/logo").status_code == 404
        icons = requests.get(f"{BASE_URL}/api/public/manifest").json()["icons"]
        assert icons[0]["src"] == "/icon-192.png"


class TestRegression:
    def test_alarm_settings_not_configured(self, admin):
        r = admin.get(f"{BASE_URL}/api/alarm-settings?client_id={KOWALSKI_ID}")
        assert r.status_code == 200
        d = r.json()
        assert d["email_configured"] is False and d["sms_configured"] is False

    def test_devices_and_me(self, admin):
        assert admin.get(f"{BASE_URL}/api/auth/me").json()["role"] == "superadmin"
        assert len(admin.get(f"{BASE_URL}/api/devices").json()["devices"]) >= 2
