# Outcome — Document Extraction Service

**Submission role: AI/ML Developer**

Evidence-grounded document extraction for PDF, DOCX, XLSX and CSV using a LangGraph workflow, layout-preserving parsers, local OCR, schema normalization, OpenRouter model routing, deterministic spreadsheet extraction and a persistent asynchronous API.

## Quick start (Docker)

1. Copy `.env.example` to `.env`.
2. Set `LLM_BASE_URL` and `LLM_API_KEY` in `.env`. Never commit `.env`.
3. Run `docker compose up --build -d`.
4. Check `curl http://localhost:8080/health`.

The API listens on port 8080. `POST /jobs` accepts multipart fields `file` and `schema` (JSON string); optional `webhook_url`. Poll `GET /jobs/{job_id}`. Supply `X-Organization-Id` consistently to enable tenant isolation.

## Local development

Python 3.11 is recommended. Install Tesseract OCR (English language pack), then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# edit .env and provide your OpenRouter key
uvicorn app.main:app --reload --port 8080
```

## Architecture

- LangGraph StateGraph: parse → profile → normalize schema → extract.
- PDF: PyMuPDF native text and positioned blocks; scanned pages use parallel Tesseract OCR.
- DOCX: paragraphs and Word tables with source locators.
- XLSX/CSV: native cell/row parsing; rent-roll charge blocks and T12 line items are handled deterministically.
- Schema normalization: inexpensive allowed model rewrites descriptions into extraction guidance without changing field keys.
- Extraction: grouped field calls, evidence-focused retrieval, strict JSON and citations. All provider calls use `LLM_BASE_URL` and `LLM_API_KEY`.
- Verification: citation support checks, type normalization, deterministic arithmetic for tabular totals, schema-complete serialization.
- Service: FastAPI async jobs, SQLite persistence, tenant-scoped reads, idempotency, bounded concurrency, retry/backoff for provider throttling, terminal-state protection.

## Configuration

See `.env.example`. Allowed model IDs are restricted in `app/llm.py` to those listed in the assignment. No key or endpoint is hardcoded. The default models are configurable via environment variables.

## Tests and validator

```bash
pytest -q
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
```

Sample documents and ground-truth answers are deliberately excluded from the submission archive per the assignment rules. To run all eight samples locally, extract only those folders from the original assignment ZIP into this repository (do not add them to your submission ZIP):

```bash
unzip -q /path/to/Outcome_Take_Home_Assignment.zip 'sample/sample-data-documents/*' 'sample/sample-data-output-validated/*' -d .
```

Then run `scripts/generate_samples.sh`. The script runs the official validator and compares against truth when that folder is present. The three deterministic outputs currently included in `outputs/` score 1.000 each (box score, rent roll and T12); the remaining five require the configured LLM key. Run the CLI against a supplied document individually with:

```bash
python -m app.cli --file sample/sample-data-documents/lease_002.docx \
  --schema sample/schemas/lease_abstraction.json --output outputs/lease_002.json
```

## Evaluation status

The repository includes the official validator and output contract. Populate `outputs/` with results from your final local run and record the validator score here before submission. Do not claim scores that have not been measured.

## Sample evaluation note

The deterministic CSV/XLSX parsers are locally regression-tested against the supplied sample truth (box score, rent roll and T12). Narrative PDF/DOCX extraction requires a configured OpenRouter key; generate those outputs with `scripts/generate_samples.sh` and retain only generated result JSON in `outputs/`. The final measured eight-document score must be added here after running the official validator; no unmeasured score is claimed.


## Verified locally

- `python -m compileall -q app tests`: passed.
- `python -m pytest -q`: 3 passed.
- Official validator against the supplied truth: box score 1.000, rent roll 1.000, T12 1.000.
- FastAPI health, asynchronous job completion for the rent-roll workbook, and tenant-isolated 404 were exercised with the local test client.
- Docker was not available in the build environment, so the actual `docker compose up` image build must be verified on the submission machine.
