#!/usr/bin/env bash
# Rebuild the actual Docker service, submit all eight sample documents, and score outputs.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
ZIP_PATH="${1:-$(dirname "$ROOT")/Outcome_Take_Home_Assignment.zip}"

if [[ ! -f "$ZIP_PATH" ]]; then
  echo "Cannot find assignment ZIP: $ZIP_PATH" >&2
  echo "Usage: bash scripts/run_local_samples.sh \"/absolute/path/Outcome_Take_Home_Assignment.zip\"" >&2
  exit 2
fi
if [[ -z "${VIRTUAL_ENV:-}" ]]; then
  echo "Activate your project environment first: source .venv/bin/activate" >&2
  exit 2
fi
if [[ ! -f .env ]]; then
  echo "Missing .env. Copy .env.example to .env and add a newly issued OpenRouter key." >&2
  exit 2
fi
set -a
# shellcheck disable=SC1091
source .env
set +a
if [[ -z "${LLM_API_KEY:-}" ]]; then
  echo "LLM_API_KEY is empty in .env. Add a newly issued OpenRouter key; do not reuse the exposed key." >&2
  exit 2
fi

mkdir -p outputs
unzip -oq "$ZIP_PATH" 'sample/sample-data-documents/*' 'sample/sample-data-output-validated/*' -d .

# Build the exact container image used by the grader; Docker installs Tesseract and Python deps.
docker compose up --build -d
healthy=0
for _ in $(seq 1 90); do
  if curl -fsS http://127.0.0.1:8080/health >/dev/null 2>&1; then healthy=1; break; fi
  sleep 1
done
if [[ "$healthy" -ne 1 ]]; then
  echo "Service did not become healthy within 90 seconds. Recent container logs:" >&2
  docker compose logs --tail=100 >&2
  exit 1
fi

python tools/run_samples_via_api.py
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
