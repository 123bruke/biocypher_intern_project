"""Safe, read-only ad-hoc query execution against deployed graph backends.

Two backends are supported:

* ``neo4j`` — Cypher, executed through the Neo4j driver's *read transaction*
  (server-enforced read access mode) plus a client-side mutation-keyword guard
  and a statement timeout.
* ``mork``  — MeTTa queries against a MORK AtomSpace. Queries are executed via
  MORK's read path only; the small set of known-mutating operations are rejected
  up front.

Nothing here ever writes to a backend. Every endpoint is ``POST`` and executes
against the *deployed* database (the same one the Console reflects), so users
can explore live data without touching it.
"""
from __future__ import annotations

import re
import time
from typing import Any, Optional

from backend.core.config import settings
from backend.core.neo4j_client import neo4j_client

try:
    from backend.core.mork_client import MORKClient
except ImportError:  # pragma: no cover - fallback if the MORK wrapper breaks
    MORKClient = None

# Default safety caps (overridable per request, clamped server-side).
DEFAULT_TIMEOUT_MS = 10_000
MAX_TIMEOUT_MS = 60_000
DEFAULT_LIMIT = 200
MAX_LIMIT = 2_000

# --------------------------------------------------------------------------
# Cypher mutation-keyword guard (defense in depth).
#
# The authoritative read-only enforcement for Neo4j is the read transaction's
# access mode (server rejects writes). This guard runs first so we can fail fast
# and return a friendly message without waiting on the server, and it also
# protects against writes hidden behind Cypher sugar / procedure calls.
# --------------------------------------------------------------------------

# Mutation keywords that can never appear in a read-only Cypher query.
_CYPHER_MUTATION_RE = re.compile(
    r"\b(?:CREATE|MERGE|SET|DELETE|DETACH|REMOVE|DROP)\b",
    re.IGNORECASE,
)

# Procedure-call / admin writes (LOAD CSV, periodic commit, index/constraint ops,
# and known write procedures in the apoc / gds / db namespaces).
_CYPHER_WRITE_RE = re.compile(
    r"\b(?:LOAD\s+CSV|PERIODIC\s+COMMIT|CREATE\s+INDEX|CREATE\s+CONSTRAINT"
    r"|ALTER|RENAME-SEQUENCE)\b"
    r"|\bCALL\s+(?:apoc\.(?:create|merge|atomic|load|refresh|trigger|periodic)"
    r"|gds\.graph\.(?:project|write)|db\.create)"
    r"|\bCALL\s+[a-zA-Z0-9_.]+\.write\b",
    re.IGNORECASE,
)

# MeTTa operations that would mutate the AtomSpace.
_METTA_WRITE_RE = re.compile(
    r"^\s*\((?:insert|merge|swap|delete|load-as-cset|load)\b",
    re.IGNORECASE,
)


def _has_cypher_writes(query: str) -> bool:
    """Return True if ``query`` looks like it would mutate a Neo4j graph."""
    return bool(_CYPHER_MUTATION_RE.search(query) or _CYPHER_WRITE_RE.search(query))


def _cap_query(query: str, limit: int) -> str:
    """Return ``query`` with a hard LIMIT appended server-side (best effort).

    Client-side slicing remains the authoritative cap; this just keeps the driver
    from streaming an unbounded result set when the query has no LIMIT of its own.
    """
    q = query.rstrip()
    if not q.endswith(";"):
        # Don't override an explicit LIMIT the user wrote.
        if re.search(r"\bLIMIT\s+\d+", q, re.IGNORECASE):
            return q
        return f"{q}\nLIMIT {int(limit)}"
    return f"{q[:-1]}\nLIMIT {int(limit)};"


def _nullable(value: Any) -> Any:
    """Recursively convert driver-specific types to JSON-safe primitives."""
    from neo4j import Node, Relationship, Path as Neo4jPath
    from neo4j.exceptions import Neo4jError

    if value is None:
        return None
    if isinstance(value, (Node,)):
        return {"id": value.element_id if hasattr(value, "element_id") else value.id,
                "labels": list(value.labels),
                "properties": {k: _nullable(v) for k, v in value.items()}}
    if isinstance(value, Relationship):
        return {"id": value.element_id if hasattr(value, "element_id") else value.id,
                "type": value.type,
                "properties": {k: _nullable(v) for k, v in value.items()}}
    if isinstance(value, Neo4jPath):
        return [(_nullable(node), _nullable(rel), _nullable(node2))
                for node, rel, node2 in _zip_path(value)]
    if isinstance(value, list):
        return [_nullable(v) for v in value]
    if isinstance(value, dict):
        return {k: _nullable(v) for k, v in value.items()}
    if isinstance(value, Neo4jError):
        return str(value)
    return value


def _zip_path(path: "Neo4jPath"):
    nodes = list(path.nodes)
    rels = list(path.relationships)
    # Normalize cardinality mismatch (nodes = rels + 1).
    out = []
    for i in range(len(rels)):
        out.append((nodes[i], rels[i], nodes[i + 1]))
    return out


class QueryError(Exception):
    """Raised with a user-facing message when a query cannot run safely."""

    def __init__(self, message: str, write_blocked: bool = False, code: int = 400):
        super().__init__(message)
        self.write_blocked = write_blocked
        self.code = code


class QueryBackends:
    """Read-only query execution for deployed graph backends."""

    # ------------------------------------------------------------------
    # Discovery
    # ------------------------------------------------------------------
    def list_backends(self) -> list[dict]:
        """Return the known backends plus their current reachability."""
        return [
            {
                "name": "neo4j",
                "display_name": "Neo4j",
                "type": "graph",
                "query_language": "Cypher",
                "available": self._neo4j_available(),
            },
            {
                "name": "mork",
                "display_name": "MORK (AtomSpace)",
                "type": "atomspace",
                "query_language": "MeTTa",
                "available": self._mork_available(),
            },
        ]

    def _neo4j_available(self) -> bool:
        try:
            return bool(neo4j_client.verify_connection())
        except Exception:  # noqa: BLE001 - connectivity checks shouldn't throw
            return False

    def _mork_available(self) -> bool:
        if MORKClient is None:
            return False
        try:
            client = MORKClient()
            return client.verify_connection()
        except Exception:  # noqa: BLE001
            return False

    # ------------------------------------------------------------------
    # Neo4j (Cypher)
    # ------------------------------------------------------------------
    def run_neo4j(self, query: str, limit: int, timeout_ms: int) -> dict:
        query = (query or "").strip()
        if not query:
            raise QueryError("Query is empty.", code=422)
        if _has_cypher_writes(query):
            raise QueryError(
                "This query was blocked: writes to the live graph are disabled. "
                "Only read-only Cypher (MATCH / RETURN / WHERE / CALL … ) is allowed.",
                write_blocked=True,
            )

        from neo4j import Query as Neo4jQuery

        limit = max(1, min(int(limit), MAX_LIMIT))
        timeout_ms = max(1, min(int(timeout_ms), MAX_TIMEOUT_MS))

        if not self._neo4j_available():
            raise QueryError(
                "Neo4j is not reachable (check the NEO4J_URI/NEO4J_DATABASE settings).",
                code=503,
            )

        started = time.time()
        try:
            with neo4j_client.driver.session(
                database=settings.NEO4J_DATABASE
            ) as session:
                def _read(tx):
                    result = tx.run(
                        _cap_query(query, limit + 1),
                        timeout=timeout_ms,
                    )
                    return result.keys(), list(result)

                keys, records = session.read_transaction(_read)
        except QueryError:
            raise
        except Exception as exc:  # noqa: BLE001 - surface driver errors cleanly
            raise QueryError(f"Neo4j query failed: {exc}", code=500) from exc

        all_rows = [_nullable(list(record)) for record in records]
        truncated = len(all_rows) > limit
        rows = all_rows[:limit]
        return {
            "backend": "neo4j",
            "ok": True,
            "fields": list(keys),
            "rows": rows,
            "row_count": len(all_rows),
            "returned": len(rows),
            "truncated": truncated,
            "elapsed_ms": round((time.time() - started) * 1000, 2),
            "write_blocked": False,
        }

    # ------------------------------------------------------------------
    # MORK (MeTTa / Atomese)
    # ------------------------------------------------------------------
    def run_mork(self, query: str, limit: int, timeout_ms: int) -> dict:
        query = (query or "").strip()
        if not query:
            raise QueryError("Query is empty.", code=422)
        if _METTA_WRITE_RE.match(query):
            raise QueryError(
                "This MeTTa expression was blocked: mutating the live AtomSpace is "
                "disabled. Only read-only queries are allowed.",
                write_blocked=True,
            )
        if MORKClient is None:
            raise QueryError("MORK backend is not available on this host.", code=503)

        limit = max(1, min(int(limit), MAX_LIMIT))
        timeout_ms = max(1, min(int(timeout_ms), MAX_TIMEOUT_MS))
        started = time.time()

        try:
            client = MORKClient()
            with client.server.work_at("annotation") as scope:
                # MORK's query/collect path is read-only; run it and block for results.
                data = scope.query_(query, max_results=limit)
                data.block()
                raw: str = getattr(data, "data", "") or ""

            lines = [
                line for line in str(raw).splitlines()
                if line.strip() and not line.strip().startswith(";")
            ]
            truncated = len(lines) > limit
            rows = [[line] for line in lines[:limit]]
            return {
                "backend": "mork",
                "ok": True,
                "fields": ["result"],
                "rows": rows,
                "row_count": len(lines),
                "returned": len(rows),
                "truncated": truncated,
                "elapsed_ms": round((time.time() - started) * 1000, 2),
                "write_blocked": False,
            }
        except QueryError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise QueryError(f"MORK query failed: {exc}", code=500) from exc


query_backends = QueryBackends()
