import os, sys, re
sys.setrecursionlimit(10000)
sys.path.insert(0, os.path.abspath(".."))
from backend.core.query_backends import _cap_query
print(_cap_query("MATCH (n) RETURN n", 201))
print(_cap_query("MATCH (n) RETURN n;", 201))
print(_cap_query("MATCH (n) RETURN n LIMIT 5", 201))
print(_cap_query("MATCH (n) RETURN n LIMIT 5;", 201))

from fastapi.testclient import TestClient
from backend.api.main import app
client = TestClient(app)
r = client.post("/api/console/query", json={"backend": "neo4j", "query": "MATCH (n) RETURN n LIMIT 5"})
print("read query now:", r.status_code, r.json())
