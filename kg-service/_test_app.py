import os, sys
sys.setrecursionlimit(10000)
sys.path.insert(0, os.path.abspath(".."))
from fastapi.testclient import TestClient
from backend.api.main import app

client = TestClient(app)

# Query backends list
r = client.get("/api/console/query/backends")
print("backends:", r.status_code, r.json())

# Write-blocked query -> 400 write_blocked
r = client.post("/api/console/query", json={"backend": "neo4j", "query": "CREATE (n:X) RETURN n"})
print("create blocked:", r.status_code, r.json()["detail"])

# Valid read query -> will fail 500 (no neo4j) but not 400 write_blocked
r = client.post("/api/console/query", json={"backend": "neo4j", "query": "MATCH (n) RETURN n LIMIT 5"})
print("read query:", r.status_code, r.json())

# Unknown backend
r = client.post("/api/console/query", json={"backend": "foo", "query": "x"})
print("unknown backend:", r.status_code)

# Browser overview
r = client.get("/api/console/browser/overview")
print("overview:", r.status_code, r.json().get("neo4j_connected"), r.json().get("overview"))

# Config files list
r = client.get("/api/console/config/files")
print("config files:", r.status_code, len(r.json()["files"]))

# Config file validate
r = client.post("/api/console/config/file/validate", json={
    "path": "config/hsa/hsa_adapters_config_sample.yaml",
    "content": open(os.path.join("..", "config", "hsa", "hsa_adapters_config_sample.yaml"), encoding="utf-8").read(),
})
print("validate:", r.status_code, r.json().get("valid"))
