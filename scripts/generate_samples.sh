#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
run() { python -m app.cli --file "sample/sample-data-documents/$1" --schema "sample/schemas/$2" --output "outputs/${1%.*}.json"; }
run boxscore_001.csv boxscore.json
run budget_001.pdf budget_variance.json
run lease_001.pdf lease_abstraction.json
run lease_002.docx lease_abstraction.json
run lease_003.pdf lease_abstraction.json
run om_001.pdf offering_memorandum.json
run rentroll_001.xlsx rent_roll_units.json
run t12_001.xlsx operating_statement_lines.json
python tools/validate.py outputs/ --schema-dir sample/schemas
