"""Console configuration introspection and editing endpoints.

Introspection is read-only (parses committed YAML; never runs a build or touches
Neo4j). Editing endpoints validate before saving and back up the original file.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.console import config_introspect as ci
from backend.core.console import config_editor as ce

router = APIRouter(prefix="/api/console", tags=["Console"])


class ConfigEditRequest(BaseModel):
    path: str = Field(..., description="Repo-relative path of the config file")
    content: str = Field(..., description="Full new YAML content")


@router.get("/species")
def get_species():
    """List species and their datasets, with config-file existence flags."""
    try:
        return {"species": ci.list_species_and_datasets()}
    except ci.ConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.get("/species/{species}/datasets/{dataset}/adapters")
def get_adapters(species: str, dataset: str):
    """List adapters declared for a species/dataset."""
    try:
        return ci.list_adapters(species, dataset)
    except ci.ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/species/{species}/datasets/{dataset}/schema")
def get_schema(species: str, dataset: str):
    """Shallow schema view (node/edge type names + per-source schema files)."""
    try:
        return ci.list_schema(species, dataset)
    except ci.ConfigError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/writers")
def get_writers():
    return {"writers": ci.list_writers()}


@router.get("/flags")
def get_flags():
    return {"flags": ci.list_flags()}


# ---------------------------------------------------------------------------
# Inline configuration editing (Milestone 3)
# ---------------------------------------------------------------------------
@router.get("/config/files")
def list_config_files():
    """List the YAML config files editable from the Console."""
    return ce.list_editable_files()


@router.get("/config/file")
def get_config_file(path: str):
    """Read the raw content of an editable config file."""
    try:
        return ce.read_file(path)
    except ce.ConfigEditError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc


@router.post("/config/file/validate")
def validate_config_file(req: ConfigEditRequest):
    """Validate proposed config content without saving it."""
    try:
        return ce.validate_file(req.path, req.content)
    except ce.ConfigEditError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc


@router.post("/config/file/save")
def save_config_file(req: ConfigEditRequest):
    """Validate, back up, and save config content (atomic write)."""
    # Pre-validate so the UI can render inline validation errors on failure.
    try:
        validation = ce.validate_file(req.path, req.content)
    except ce.ConfigEditError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc
    if not validation["valid"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "Config is not valid; nothing was saved.",
                    "validation": validation},
        ) from None
    try:
        return ce.save_file(req.path, req.content)
    except ce.ConfigEditError as exc:
        raise HTTPException(status_code=exc.code, detail=str(exc)) from exc
