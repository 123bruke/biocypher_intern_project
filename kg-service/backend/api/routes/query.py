"""Console: safe, read-only ad-hoc query against deployed graph backends.

Provides:
  * GET  /api/console/query/backends  — list backends + reachability
  * POST /api/console/query           — run a read-only query (Cypher / MeTTa)

Writes are rejected before execution and, for Neo4j, again by the driver's read
transaction access mode. Query size, row count, and duration are all capped.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.query_backends import query_backends, QueryError

router = APIRouter(prefix="/api/console", tags=["Console"])


class QueryRequest(BaseModel):
    backend: str = Field(..., description="'neo4j' or 'mork'")
    query: str = Field(..., min_length=1, max_length=20_000)
    limit: int = Field(200, ge=1, le=2_000)
    timeout_ms: int = Field(10_000, ge=500, le=60_000)


@router.get("/query/backends")
def list_query_backends():
    """List deployable query backends and whether each is currently reachable."""
    return {"backends": query_backends.list_backends()}


@router.post("/query")
def run_query(req: QueryRequest):
    """Execute a read-only query against the chosen backend.

    The request is always treated as read-only: mutating statements are rejected
    up front (HTTP 400 with ``write_blocked``) and, for Neo4j, a read transaction
    enforces it server-side too. Results are truncated to ``limit`` rows and the
    query is bounded by ``timeout_ms``.
    """
    if req.backend not in ("neo4j", "mork"):
        raise HTTPException(
            status_code=400,
            detail=f"Unknown backend '{req.backend}'. Choose 'neo4j' or 'mork'.",
        )
    try:
        if req.backend == "neo4j":
            return query_backends.run_neo4j(req.query, req.limit, req.timeout_ms)
        return query_backends.run_mork(req.query, req.limit, req.timeout_ms)
    except QueryError as exc:
        raise HTTPException(
            status_code=exc.code,
            detail={"message": str(exc), "write_blocked": exc.write_blocked},
        ) from exc
