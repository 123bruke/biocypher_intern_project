"""Inline editing of the pipeline's YAML configuration with validation feedback.

Supports editing three kinds of committed config from the Console:

* **Adapters config** (per species/dataset) — validate each declared adapter's
  ``adapter.module``/``adapter.cls`` and ``nodes``/``edges`` flags.
* **Schema config** (per species/dataset, also the primer) — validate each type
  entry's ``represented_as``.
* **``species_config.yaml``** — validate the species→dataset→config references.

Every write is confined to the repo's ``config/`` and ``data_source_schemas/``
directories, is re-validated before being saved, and backs up the original file
first. Saving is atomic (temp file + rename), so a bad write can never corrupt a
live config.
"""
from __future__ import annotations

import datetime
import os
import tempfile
from pathlib import Path
from typing import Any, Optional

import yaml

from backend.core.config import settings
from backend.core.console import config_introspect as ci

# Top-level directories under the repo that we allow editing.
_ALLOWED_ROOTS = ("config", "data_source_schemas")

# Build flags whose values may be edited inline (mirrors ci.BUILD_FLAGS).
# (kept for parity/extension; not required for file editing below)


class ConfigEditError(Exception):
    """Raised when a config file cannot be read/saved (user-facing)."""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


def resolve_editable_path(rel: str) -> Path:
    """Resolve a repo-relative config path and confine it under the allowed roots.

    Raises ``ConfigEditError`` when the path escapes the allowed directories.
    """
    if not rel:
        raise ConfigEditError("No config path provided.", code=422)
    rel = rel.replace("\\", "/")
    target = (settings.repo_root_path / rel).resolve()
    root = settings.repo_root_path.resolve()
    # Must be inside the repo.
    if target != root and root not in target.parents:
        raise ConfigEditError("Config path escapes the repository.", code=400)
    # Must be under an allowed top-level dir.
    try:
        rel_to_root = target.relative_to(root)
    except ValueError as exc:
        raise ConfigEditError("Config path is outside the repository.", code=400) from exc
    first = rel_to_root.parts[0] if rel_to_root.parts else ""
    if first not in _ALLOWED_ROOTS:
        raise ConfigEditError(
            f"Editing is restricted to these directories: {', '.join(_ALLOWED_ROOTS)}. "
            f"'{first}' is not editable from the Console.",
            code=400,
        )
    return target


# --------------------------------------------------------------------------
# Validation helpers
# --------------------------------------------------------------------------
def parse_yaml(text: str, file_path: Path) -> Any:
    """Parse YAML content *exactly as the build would* (handles !include).

    Writes the content to a temp file beside the real file so relative ``!include``
    directives resolve against the same directory, then runs the repo's loader.
    """
    load = ci._load_yaml_with_includes()
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", suffix=".yaml", dir=str(file_path.parent), delete=False, encoding="utf-8"
        ) as fh:
            fh.write(text)
            tmp_path = Path(fh.name)
        return load(str(tmp_path)) or {}
    finally:
        if tmp_path is not None:
            try:
                os.remove(tmp_path)
            except OSError:
                pass


def _adapter_errors(name: str, entry: Any) -> list[str]:
    errs: list[str] = []
    if not isinstance(entry, dict):
        return [f"[{name}] adapter entry must be a mapping, got {type(entry).__name__}."]
    adapter = entry.get("adapter")
    if not isinstance(adapter, dict):
        errs.append(f"[{name}] missing 'adapter' mapping.")
        return errs
    if not isinstance(adapter.get("module"), str) or not adapter["module"].strip():
        errs.append(f"[{name}] 'adapter.module' is required and must be a string.")
    if not isinstance(adapter.get("cls"), str) or not adapter["cls"].strip():
        errs.append(f"[{name}] 'adapter.cls' is required and must be a string.")
    for flag in ("nodes", "edges"):
        if flag in adapter:
            if not isinstance(adapter[flag], bool):
                errs.append(f"[{name}] 'adapter.{flag}' should be a boolean.")
    return errs


def validate_adapters_config(text: str, file_path: Path) -> dict:
    errs: list[str] = []
    warns: list[str] = []
    try:
        data = parse_yaml(text, file_path)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"YAML parse error: {exc}"], "warnings": []}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["Adapters config must be a mapping."], "warnings": []}
    for name, entry in data.items():
        if name == "input_dir":
            if not isinstance(entry, str):
                warns.append("'input_dir' should be a string path.")
            continue
        errs.extend(_adapter_errors(str(name), entry))
    return {
        "valid": not errs,
        "errors": errs,
        "warnings": warns,
        "summary": {"adapters": sum(
            1 for k, v in data.items() if k != "input_dir" and isinstance(v, dict)
        )},
    }


_SCHEMA_REPRESENTED = {"node", "edge", "relationship_type", "relationship"}


def validate_schema_config(text: str, file_path: Path) -> dict:
    errs: list[str] = []
    warns: list[str] = []
    try:
        data = parse_yaml(text, file_path)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"YAML parse error: {exc}"], "warnings": []}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["Schema config must be a mapping."], "warnings": []}
    node_types, edge_types = [], []
    for key, val in data.items():
        if key == "Title":
            continue
        if not isinstance(val, dict):
            warns.append(f"Type '{key}' should be a mapping; skipping.")
            continue
        represented = str(val.get("represented_as", "")).lower()
        if not represented:
            errs.append(f"Type '{key}' is missing 'represented_as'.")
        elif represented not in _SCHEMA_REPRESENTED:
            warns.append(
                f"Type '{key}' has unusual 'represented_as' '{represented}' "
                f"(expected one of {sorted(_SCHEMA_REPRESENTED)})."
            )
        else:
            if represented == "edge" or represented in ("relationship_type", "relationship"):
                edge_types.append(str(key))
            else:
                node_types.append(str(key))
    return {
        "valid": not errs,
        "errors": errs,
        "warnings": warns,
        "summary": {"node_types": node_types, "edge_types": edge_types},
    }


def validate_species_config(text: str, file_path: Path) -> dict:
    errs: list[str] = []
    warns: list[str] = []
    try:
        data = parse_yaml(text, file_path)
    except Exception as exc:  # noqa: BLE001
        return {"valid": False, "errors": [f"YAML parse error: {exc}"], "warnings": []}
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return {"valid": False, "errors": ["species_config must be a mapping."], "warnings": []}
    for species, datasets in data.items():
        if not isinstance(datasets, dict):
            errs.append(f"Species '{species}' should map to a set of datasets.")
            continue
        for ds_name, entry in datasets.items():
            if not isinstance(entry, dict):
                errs.append(f"{species}/{ds_name} should be a mapping.")
                continue
            for cfg_key in ("adapters_config", "schema_config"):
                rel = entry.get(cfg_key)
                if not rel:
                    warns.append(f"{species}/{ds_name}: '{cfg_key}' is not set.")
                    continue
                p = ci._resolve(rel)
                if not p.exists():
                    warns.append(f"{species}/{ds_name}: '{cfg_key}' -> {rel} does not exist.")
    return {
        "valid": not errs,
        "errors": errs,
        "warnings": warns,
        "species_count": len(data) if isinstance(data, dict) else 0,
    }


def validate_file(rel: str, content: str) -> dict:
    """Validate config content for a given repo-relative path (no save)."""
    path = resolve_editable_path(rel)
    if not path.exists():
        # Allow validating a brand-new proposal but warn it isn't live yet.
        existing = False
    else:
        existing = True
    name = path.name
    if "adapters_config" in name or name.endswith("_adapters_config.yaml"):
        result = validate_adapters_config(content, path)
    elif name == "species_config.yaml":
        result = validate_species_config(content, path)
    else:
        result = validate_schema_config(content, path)
    result["path"] = str(path)
    result["existing"] = existing
    return result


# --------------------------------------------------------------------------
# Read / write
# --------------------------------------------------------------------------
def read_file(rel: str) -> dict:
    path = resolve_editable_path(rel)
    if not path.is_file():
        raise ConfigEditError(f"Config file not found: {path}", code=404)
    return {
        "path": str(path),
        "relative_path": str(path.relative_to(settings.repo_root_path)),
        "exists": True,
        "name": path.name,
        "size": path.stat().st_size,
        "content": path.read_text(encoding="utf-8"),
    }


def save_file(rel: str, content: str) -> dict:
    """Validate then atomically save a config file, backing up the original."""
    path = resolve_editable_path(rel)
    validation = validate_file(rel, content)
    if not validation["valid"]:
        raise ConfigEditError(
            "Refusing to save: the config is not valid. Fix the validation errors first.",
            code=422,
        )
    path.parent.mkdir(parents=True, exist_ok=True)

    # Back up the existing file (if any) before overwriting.
    backup = None
    if path.exists():
        backup = path.with_name(
            f"{path.name}.bak-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
        )
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")

    # Atomic write via temp file + rename.
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass

    return {
        "path": str(path),
        "relative_path": str(path.relative_to(settings.repo_root_path)),
        "saved": True,
        "validation": validation,
        "backup": str(backup) if backup else None,
    }


def list_editable_files() -> dict:
    """Enumerate the config files editable from the Console."""
    root = settings.repo_root_path
    files: list[dict] = []
    for base in _ALLOWED_ROOTS:
        base_dir = root / base
        if not base_dir.is_dir():
            continue
        for p in sorted(base_dir.rglob("*.yaml")):
            rel = str(p.relative_to(root))
            kind = _kind_for(p)
            files.append({
                "path": rel,
                "name": p.name,
                "kind": kind,
            })
    return {"files": files}


def _kind_for(p: Path) -> str:
    name = p.name
    if "adapters_config" in name:
        return "adapters"
    if "schema_config" in name or name.startswith("primer_schema"):
        return "schema"
    if name == "species_config.yaml":
        return "species"
    return "other"
