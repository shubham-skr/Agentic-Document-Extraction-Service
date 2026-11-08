#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
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
