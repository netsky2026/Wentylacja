# Iteration 28: client-admin editable contact (/api/client-contact), public branding contact, superadmin PATCH contact,
# cycle cost-per-head data for the batches chart (chamber 2 of kowalski-a). Seed for UI kept when KEEP_SEED=1.
import json
import os
import uuid
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"
H = {"Origin": BASE_URL}
KOW = "kowalski-a"
CID = "6ad7dcc3261e5ba3c23315b7"
TAG = uuid.uuid4().hex[:6]
PW = "Haslo1234!x"
mongo = MongoClient("mongodb://localhost:27017")["test_database"]
ORIG = {"phone": "+48 501 222 444", "email": "biuro@kowalski-ferma.pl", "address": "Wola 12, 05-100 Nowe", "website": "kowalski-ferma.pl"}
SYN = {"2026-09-05": (40.0, 3000.0), "2026-09-20": (20.0, 1500.0), "2026-10-05": (30.0, 600.0)}
CH = 2


def login(email, pw):
    s = requests.Session()
    s.headers.update(H)
    r = s.post(f"{API}/auth/login", json={"email": email, "password": pw})
    assert r.status_code == 200, r.text
    s.headers["X-CSRF-Token"] = s.cookies.get("csrf") or ""
    return s


@pytest.fixture(scope="module")
def sa():
    s = login("admin@chlewnia.pl", "Wentylacja!2026")
    s.users, ids = {}, []
    for role in ("admin", "operator", "viewer"):
        email = f"test_{TAG}_{role}@kowalski.pl"
        r = s.post(f"{API}/users", json={"email": email, "password": PW, "role": role, "client_id": CID})
        assert r.status_code in (200, 201), r.text
        ids.append(r.json().get("id") or r.json().get("user", {}).get("id"))
        s.users[role] = email
    yield s
    s.put(f"{API}/client-contact?client_id={CID}", json=ORIG)
    for i in ids:
        if i:
            s.delete(f"{API}/users/{i}")


# --- client-contact RBAC
def test_contact_rbac(sa):
    for role, code in (("operator", 403), ("viewer", 403)):
        u = login(sa.users[role], PW)
        assert u.get(f"{API}/client-contact").status_code == code
        assert u.put(f"{API}/client-contact", json=ORIG).status_code == code


def test_superadmin_requires_client_id(sa):
    assert sa.get(f"{API}/client-contact").status_code == 422


def test_client_admin_get_own(sa):
    u = login(sa.users["admin"], PW)
    r = u.get(f"{API}/client-contact")
    assert r.status_code == 200
    assert set(r.json()) == {"phone", "email", "address", "website"}


def test_client_admin_put_and_public_branding(sa):
    u = login(sa.users["admin"], PW)
    body = {"phone": "+48 600 111 222", "email": "test_kow@ferma.pl", "website": "www.test-kow.pl", "address": "ul. Testowa 5, Wola"}
    r = u.put(f"{API}/client-contact", json=body)
    assert r.status_code == 200, r.text
    assert r.json() == body
    assert u.get(f"{API}/client-contact").json() == body
    pb = requests.get(f"{API}/public/branding/kowalski").json()
    assert pb["contact"] == body
    # superadmin sees same via ?client_id and /api/clients
    assert sa.get(f"{API}/client-contact?client_id={CID}").json() == body
    cl = [c for c in sa.get(f"{API}/clients").json()["clients"] if c.get("id") == CID or c.get("_id") == CID]
    assert cl and cl[0]["contact"] == body


def test_client_admin_cannot_target_other_client(sa):
    u = login(sa.users["admin"], PW)
    other = next(c for c in sa.get(f"{API}/clients").json()["clients"] if (c.get("id") or c.get("_id")) != CID)
    oid = other.get("id") or other.get("_id")
    before = sa.get(f"{API}/client-contact?client_id={oid}").json()
    r = u.put(f"{API}/client-contact?client_id={oid}", json={"phone": "999", "email": "", "website": "", "address": "HACK"})
    assert r.status_code == 200  # scope ignores client_id for client admin -> writes own client
    assert sa.get(f"{API}/client-contact?client_id={oid}").json() == before
    assert sa.get(f"{API}/client-contact?client_id={CID}").json()["address"] == "HACK"


@pytest.mark.parametrize("bad", [{"email": "not-an-email"}, {"phone": "abc"}, {"website": "javascript:<x>"},
                                 {"address": "x" * 201}])
def test_contact_validation(sa, bad):
    u = login(sa.users["admin"], PW)
    assert u.put(f"{API}/client-contact", json={**ORIG, **bad}).status_code == 422


def test_foreign_origin_rejected(sa):
    u = login(sa.users["admin"], PW)
    u.headers["Origin"] = "https://evil.example.com"
    assert u.put(f"{API}/client-contact", json=ORIG).status_code in (401, 403)


def test_superadmin_patch_client_contact(sa):
    body = {"phone": "+48 22 333 44 55", "email": "sa@kowalski.pl", "website": "kowalski.pl", "address": "SA addr"}
    r = sa.patch(f"{API}/clients/{CID}", json={"contact": body})
    assert r.status_code == 200, r.text
    assert sa.get(f"{API}/client-contact?client_id={CID}").json() == body
    assert requests.get(f"{API}/public/branding/kowalski").json()["contact"] == body
    assert sa.put(f"{API}/client-contact?client_id={CID}", json=ORIG).status_code == 200


# --- cycle cost per head for chart
def test_cycles_cost_per_head(sa):
    assert not mongo.cycles.find_one({"device_id": KOW, "chamber": CH}), "chamber 2 not empty"
    for d, (k, w) in SYN.items():
        mongo.meter_daily.update_one({"_id": f"{KOW}|{d}"}, {"$setOnInsert": {"device_id": KOW, "day": d, "kwh": k,
                                     "water": {str(CH): w}, "test_tag": "it28"}}, upsert=True)
    ids = []
    for start, end in (("2026-09-01", "2026-09-10"), ("2026-09-15", "2026-09-25"), ("2026-10-01", None)):
        r = sa.post(f"{API}/devices/{KOW}/chambers/{CH}/cycles", json={"start": start, "animals": 300})
        assert r.status_code == 200, r.text
        ids.append(r.json()["id"])
        if end:
            e = sa.post(f"{API}/devices/{KOW}/cycles/{ids[-1]}/end", json={"end": end})
            assert e.status_code == 200, e.text
    json.dump(ids, open("/tmp/it28_cycles.json", "w"))
    rows = {c["start"]: c for c in sa.get(f"{API}/devices/{KOW}/cycles?chamber={CH}").json()["cycles"]}
    a, b, c = rows["2026-09-01"], rows["2026-09-15"], rows["2026-10-01"]
    assert a["cost_per_head"] == pytest.approx((40 * 0.85 + 3 * 6.5) / 300, abs=1e-3)
    assert b["cost_per_head"] == pytest.approx((20 * 0.85 + 1.5 * 6.5) / 300, abs=1e-3)
    assert c["end"] is None and c["cost_per_head"] is not None
    assert b["cost_per_head"] < a["cost_per_head"]


def test_cleanup_cycles_unless_keep(sa):
    if os.environ.get("KEEP_SEED") == "1":
        pytest.skip("seed kept for UI")
    ids = json.load(open("/tmp/it28_cycles.json"))
    from bson import ObjectId
    mongo.cycles.delete_many({"_id": {"$in": [ObjectId(i) for i in ids]}})
    mongo.meter_daily.delete_many({"test_tag": "it28"})
