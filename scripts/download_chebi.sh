#!/usr/bin/env bash
cd /home/fsc_core_i5fscuser/projects/biocypher-kg-console || exit 1
LOG=ontology_dataset_cache/chebi_download.log
URL=http://ftp.ebi.ac.uk/pub/databases/chebi/ontology/chebi.owl
OUT=ontology_dataset_cache/chebi.owl.part
echo "START $(date)" >"$LOG"
for i in $(seq 1 300); do
  wget -c --timeout=60 --tries=1 -O "$OUT" "$URL" >>"$LOG" 2>&1
  SIZE=$(stat -c%s "$OUT" 2>/dev/null || echo 0)
  if [ "$SIZE" -ge 865000000 ]; then
    mv "$OUT" ontology_dataset_cache/chebi.owl
    echo "COMPLETE size=$SIZE $(date)" >>"$LOG"
    exit 0
  fi
  echo "RETRY $i size=$SIZE" >>"$LOG"
  sleep 5
done
echo "GAVE_UP $(date)" >>"$LOG"
