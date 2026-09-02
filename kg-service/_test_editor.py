import os, sys
sys.setrecursionlimit(10000)
sys.path.insert(0, os.path.abspath(".."))
from backend.core.console import config_editor as ce
from backend.core.config import settings

print("repo root:", settings.repo_root_path)

# Read an existing adapters config
r = ce.read_file("config/hsa/hsa_adapters_config_sample.yaml")
print("read:", r["name"], r["exists"], "size", r["size"])
v = ce.validate_file(r["relative_path"], r["content"])
print("validate valid:", v["valid"], "errs", len(v["errors"]), "warns", len(v["warnings"]), "summary", v.get("summary"))

# Invalid adapters content -> should be invalid
bad = "gencode_gene:\n  adapter:\n    module: ''\n    cls: ''\n  nodes: True\n"
bv = ce.validate_file("config/hsa/hsa_adapters_config_sample.yaml", bad)
print("bad validate valid:", bv["valid"], "errs", bv["errors"])

# YAML parse error
try:
    ce.validate_file("config/primer_schema_config.yaml", "{{{{ not yaml")
except Exception as e:
    print("parse err raised:", type(e).__name__, e)

# Species config
sv = ce.validate_file("config/species_config.yaml", open(settings.repo_root_path/"config/species_config.yaml", encoding="utf-8").read())
print("species validate valid:", sv["valid"], "errs", sv["errors"], "warns", len(sv["warnings"]))

# Path confinement
for badpath in ["../../etc/passwd", "/etc/passwd", "kg-service/backend/whatever.py"]:
    try:
        ce.resolve_editable_path(badpath)
        print("FAIL allowed:", badpath)
    except ce.ConfigEditError as e:
        print("confined OK:", badpath, "->", e)
