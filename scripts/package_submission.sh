#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
required_outputs=(
  boxscore_001.json budget_001.json lease_001.json lease_002.json
  lease_003.json om_001.json rentroll_001.json t12_001.json
)
missing=()
for name in "${required_outputs[@]}"; do
  if [ ! -s "outputs/$name" ]; then missing+=("outputs/$name"); fi
done
if [ "${#missing[@]}" -gt 0 ]; then
  echo "Refusing to package an incomplete submission. Missing outputs:" >&2
  printf '  %s\n' "${missing[@]}" >&2
  exit 1
fi
if [ -d sample/sample-data-output-validated ]; then
  python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
else
  python tools/validate.py outputs/ --schema-dir sample/schemas
fi
DEST="${1:-../251110069_shubham_kumar_aiml.zip}"
mkdir -p "$(dirname "$DEST")"
rm -f "$DEST"
zip -qr "$DEST" . \
  -x '.env' '.venv/*' 'venv/*' 'data/*' \
     'sample/sample-data-documents/*' 'sample/sample-data-output-validated/*' \
     '*/__pycache__/*' '*.pyc' '.pytest_cache/*'
echo "Created $DEST"
