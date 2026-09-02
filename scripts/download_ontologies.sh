#!/usr/bin/env bash
# Pre-download all ontology .owl files used by the adapters into ontology_dataset_cache/
# Usage:
#   bash scripts/download_ontologies.sh              # all missing ones
#   bash scripts/download_ontologies.sh do hsapdv    # only specific ones
cd "$(dirname "$0")/.." || exit 1
CACHE=ontology_dataset_cache
mkdir -p "$CACHE"

download() {
  local name="$1" url="$2"
  local out="$CACHE/$name.owl"
  if [ -s "$out" ]; then
    echo "== $name already cached ($(du -h "$out" | cut -f1)) - skipping"
    return 0
  fi
  if [ -e "$out.part" ]; then
    echo "== $name has an unfinished $out.part - another job may be running; remove the .part to force re-download"
    return 0
  fi
  echo "== Downloading $name from $url"
  wget -c --tries=50 --timeout=60 --waitretry=10 -O "$out.part" "$url" || { echo "== FAILED: $name"; return 1; }
  mv "$out.part" "$out"
  printf '{\n  "date": "%s",\n  "url": "%s",\n  "hash": null,\n  "version": "unknown"\n}\n' \
    "$(date +%Y-%m-%dT00:00:00)" "$url" > "$CACHE/${name}_meta.json"
  echo "== $name done ($(du -h "$out" | cut -f1))"
}

declare -A ONTS=(
  [chebi]="http://ftp.ebi.ac.uk/pub/databases/chebi/ontology/chebi.owl"
  [go]="http://purl.obolibrary.org/obo/go.owl"
  [uberon]="http://purl.obolibrary.org/obo/uberon.owl"
  [cl]="http://purl.obolibrary.org/obo/cl.owl"
  [clo]="http://purl.obolibrary.org/obo/clo.owl"
  [bto]="http://purl.obolibrary.org/obo/bto.owl"
  [hpo]="http://purl.obolibrary.org/obo/hp.owl"
  [efo]="http://www.ebi.ac.uk/efo/efo.owl"
  [do]="https://purl.obolibrary.org/obo/doid.owl"
  [hsapdv]="http://purl.obolibrary.org/obo/hsapdv.owl"
  [omim]="http://purl.obolibrary.org/obo/mondo/sources/omim.owl"
)

if [ $# -gt 0 ]; then
  for n in "$@"; do download "$n" "${ONTS[$n]}"; done
else
  for n in "${!ONTS[@]}"; do download "$n" "${ONTS[$n]}"; done
fi
echo "ALL_DONE"
