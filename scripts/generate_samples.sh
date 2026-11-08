#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Local CLI defaults must not inherit Docker-only /data paths from .env.
mkdir -p data/uploads outputs
export DATABASE_PATH="$ROOT/data/jobs.sqlite3"
export UPLOAD_DIR="$ROOT/data/uploads"
export OUTPUT_DIR="$ROOT/outputs"

for f in \
  sample/sample-data-documents/boxscore_001.csv \
  sample/sample-data-documents/budget_001.pdf \
  sample/sample-data-documents/lease_001.pdf \
  sample/sample-data-documents/lease_002.docx \
  sample/sample-data-documents/lease_003.pdf \
  sample/sample-data-documents/om_001.pdf \
  sample/sample-data-documents/rentroll_001.xlsx \
  sample/sample-data-documents/t12_001.xlsx; do
  if [[ ! -f "$f" ]]; then
    echo "Missing sample document: $f" >&2
    echo "Extract sample/sample-data-documents/* from the original assignment ZIP first." >&2
    exit 2
  fi
done

run() { python -m app.cli --file "sample/sample-data-documents/$1" --schema "sample/schemas/$2" --output "outputs/${1%.*}.json"; }
run boxscore_001.csv boxscore.json
run budget_001.pdf budget_variance.json
run lease_001.pdf lease_abstraction.json
run lease_002.docx lease_abstraction.json
run lease_003.pdf lease_abstraction.json
run om_001.pdf offering_memorandum.json
run rentroll_001.xlsx rent_roll_units.json
run t12_001.xlsx operating_statement_lines.json
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
