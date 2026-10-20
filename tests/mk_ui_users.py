# create Kowalski UI test users (admin, viewer)
import os, requests
API = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
s = requests.Session(); s.post(f"{API}/auth/login", json={"email": "admin@chlewnia.pl", "password": "Wentylacja!2026"})
fk = next(c["id"] for c in s.get(f"{API}/clients").json()["clients"] if c["name"] == "Ferma Kowalski")
for r in ("admin", "viewer"):
    print(s.post(f"{API}/users", json={"email": f"test_ui_{r}@kowalski.pl", "password": "Haslo1234!", "role": r, "client_id": fk}).status_code)
