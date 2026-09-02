import os, sys
sys.setrecursionlimit(10000)
sys.path.insert(0, os.path.abspath(".."))
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)

checks = [
    ("GET", "/api/console/species", None),
    ("GET", "/api/console/writers", None),
    ("GET", "/api/console/flags", None),
    ("GET", "/api/console/query/backends", None),
    ("GET", "/api/console/browser/overview", None),
    ("GET", "/api/console/config/files", None),
    ("GET", "/api/console/browser/schema/hsa", None),
    ("GET", "/health", None),
    ("GET", "/", None),
]
for method, path, body in checks:
    try:
        r = client.request(method, path, json=body)
        ok = r.status_code in (200, 503)
        print(("PASS" if ok else "FAIL"), method, path, "->", r.status_code)
    except Exception as e:
        print("ERR", method, path, e)

# species/adapters (existing, may 404 if config missing - expected to work here)
r = client.get("/api/console/species/hsa/datasets/sample/adapters")
print("adapters:", r.status_code, "count=", r.json().get("count") if r.status_code == 200 else r.text[:120])
