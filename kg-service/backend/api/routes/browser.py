"""Console: consolidated metadata for the interactive graph browser.

Much of this data already exists across the Observatory endpoints (``/api/summary``,
``/api/graph-info``, ``/api/databases/.../versions``) and the Console schema
introspection. This router aggregates it into a single, browser-friendly payload
and degrades gracefully when a given backend is unreachable, so the visual
browser always has something to render.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.core.config import settings
from backend.core.neo4j_client import neo4j_client
from backend.core.console import config_introspect as ci

try:
    from backend.core.mork_client import MORKClient
except ImportError:  # pragma: no cover
    MORKClient = None

router = APIRouter(prefix="/api/console", tags=["Console"])

METADATA_LABELS = {"DatasetHash", "DatasetVersion", "KGVersion", "DatasetMapping"}


def _safe(fn, default=None):
    try:
        return fn()
    except Exception:  # noqa: BLE001 - metadata endpoints must not hard-fail
        return default


def _neo4j_schema() -> dict | None:
    """Detailed schema (node properties + edge connections) from Neo4j."""
    try:
        return neo4j_client.get_detailed_schema()
    except Exception:  # noqa: BLE001
        return None


@router.get("/browser/overview")
def browser_overview():
    """Aggregate graph metadata: counts, distributions, schema, dataset versions."""
    live = _safe(lambda: bool(neo4j_client.verify_connection()), False)

    counts = _safe(neo4j_client.get_total_counts, {})
    node_dist = _safe(neo4j_client.get_node_type_distribution, []) or []
    edge_dist = _safe(neo4j_client.get_edge_type_distribution, []) or []
    last_updated = _safe(neo4j_client.get_last_updated, None)
    datasets_md = _safe(neo4j_client.get_datasets_with_metadata, []) or []
    db_size = _safe(neo4j_client.get_database_size, {}) or {}
    labels = _safe(neo4j_client.get_labels, []) or []
    rel_types = _safe(neo4j_client.get_relationship_types, []) or []
    det_schema = _safe(_neo4j_schema, None)

    # Dataset versions (Neo4j KGVersion rows, when reachable).
    versions: list = []
    if live:
        try:
            from backend.api.routes.versions import list_versions
            result = _safe(lambda: list_versions("neo4j"), None)
            if result:
                versions = result.get("versions", [])
        except Exception:  # noqa: BLE001
            versions = []

    mork_versions: list = []
    mork_live = False
    if MORKClient is not None:
        try:
            mc = MORKClient()
            mork_live = mc.get_latest_version() is not None
            mork_versions = mc.get_all_versions()
        except Exception:  # noqa: BLE001
            mork_versions = []

    return {
        "neo4j_connected": live,
        "mork_connected": mork_live,
        "overview": {
            "node_count": counts.get("node_count"),
            "edge_count": counts.get("edge_count"),
            "dataset_count": len(datasets_md),
            "last_updated_at": last_updated,
            "database_size_gb": (db_size or {}).get("size_gb"),
        },
        "distributions": {
            "node_types": node_dist,
            "edge_types": edge_dist,
        },
        "schema": {
            "node_types": labels,
            "relationship_types": rel_types,
        },
        "detailed_schema": det_schema
        or {"nodes": [], "edges": []},
        "datasets": datasets_md,
        "versions": {
            "neo4j": versions,
            "mork": mork_versions,
        },
        "browser_conf": {
            "metadata_labels": sorted(METADATA_LABELS),
        },
    }


@router.get("/browser/datasets")
def browser_datasets():
    """List datasets with their node/edge type inventory (for the browser's table)."""
    datasets_md = _safe(neo4j_client.get_datasets_with_metadata, []) or []
    return {"datasets": datasets_md}


@router.get("/browser/schema/{species}")
def browser_species_schema(species: str):
    """Declared schema (node/edge types) as known to the pipeline for a species."""
    try:
        species_meta = {
            "species": species,
            "datasets": [],
        }
        cfg = ci.load_species_config()
        for ds_name, _ in (cfg.get(species) or {}).items():
            try:
                view = ci.list_schema(species, ds_name)
                species_meta["datasets"].append({
                    "name": ds_name,
                    "node_types": view["node_types"],
                    "edge_types": view["edge_types"],
                    "schema_config": view["schema_config"],
                    "data_source_schemas": view["data_source_schemas"],
                })
            except ci.ConfigError:
                continue
        return species_meta
    except ci.ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
