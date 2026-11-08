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
chmod 600 .env
# edit .env and provide your OpenRouter key
uvicorn app.main:app --reload --port 8080
```

## Architecture

- LangGraph StateGraph: parse → profile → deterministic schema typing → extract.
- PDF: PyMuPDF native text and positioned blocks; scanned pages use parallel 150-DPI Tesseract OCR with page-preserving output.
- DOCX: paragraphs and Word tables with source locators.
- PDF tables: geometry-aware column parsing for financial budget reports; offering memoranda use labeled facts, unit-mix rows and financial-summary extraction. XLSX/CSV: native cell/row parsing; rent-roll charge blocks and T12 line items are handled deterministically.
- Schema normalization: deterministic typing from the supplied field names and descriptions; it makes no extra API call and preserves the original field semantics.
- Extraction: paired fields for lease abstractions and groups of four for other schemas, followed by a field-by-field recovery pass for unresolved lease fields using a larger evidence window. Provider JSON mode and standard-library recovery handle malformed or truncated responses; non-null values still require source citations. All provider calls use `LLM_BASE_URL` and `LLM_API_KEY`.
- Verification: citation support checks, robust numeric confidence coercion, type normalization, deterministic arithmetic for tabular totals, and schema-complete serialization.
- Service: FastAPI async jobs, SQLite persistence, tenant-scoped reads, idempotency, bounded concurrency, retry/backoff for provider throttling, terminal-state protection.

## Configuration

See `.env.example`. Allowed model IDs are restricted in `app/llm.py` to those listed in the assignment. No key or endpoint is hardcoded. The default models are configurable via environment variables.

## Tests and validator

```bash
pytest -q
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
```

Sample documents and ground-truth answers are deliberately excluded from the submission archive per the assignment rules. To run all eight supplied samples end-to-end, activate `.venv`, ensure `.env` contains a newly issued OpenRouter key, and execute:

```bash
source .venv/bin/activate
bash scripts/run_local_samples.sh "$HOME/Downloads/OUTCOME LABS/Outcome_Take_Home_Assignment.zip"
```

The runner restores the sample inputs and truth locally, rebuilds the Docker image, submits all eight documents concurrently through `POST /jobs`, polls each job to a terminal state, writes `outputs/*.json`, and runs the official validator against the truth files. Sample documents and truth files remain excluded from the packaged submission.

## Evaluation status

The most recent **live Docker/OpenRouter evaluation before the latest lease-recovery change** completed all eight sample jobs. Its official validator scores were:

| Document | Score | Rows |
|---|---:|---:|
| Box score CSV | 1.000 | 10/10 |
| Budget PDF | 0.999 | 55/55 |
| Lease 001 PDF | 0.525 | 1/1 |
| Lease 002 DOCX | 0.625 | 1/1 |
| Lease 003 PDF | 0.593 | 1/1 |
| Offering memorandum PDF | 1.000 | 1/1 |
| Rent roll XLSX | 1.000 | 325/325 |
| T12 XLSX | 1.000 | 119/119 |

The measured mean was **0.843**. One lease job reached `PARTIAL`; the other seven reached `SUCCESS`. The current source adds a targeted second pass for unresolved lease fields, but that change has **not yet been live-evaluated**. Do not represent a higher lease score or a higher overall mean until the official validator has been rerun.

The five non-lease results above are deterministic and use no model calls for the budget/OM/spreadsheet paths. The updated lease retry can increase model calls and cost. All job deadlines remain capped at 1,700 seconds, below the assignment's 1,800-second per-document limit.

## Verified locally

- `python -m compileall -q app tests`: passed.
- `python -m pytest -q`: 13 passed when sample fixtures are present (two sample-backed parser tests are skipped when sample inputs are excluded) (JSON recovery, confidence coercion, SQLite commit persistence, mocked DOCX extraction path, and API job lifecycle).
- Official validator: five documents VALID; no hallucinations, missed rows or extra rows. Budget explanation text has a small 0.98 field score due to formatting variation; the remaining budget fields and all offering-memorandum fields score 1.00.
- FastAPI API test: POST returned in under 2 seconds and a deterministic CSV job reached SUCCESS. A separate 10-job concurrent CSV test accepted all 10 and all reached SUCCESS; maximum POST latency was 0.046 seconds. These API tests did not exercise live LLM throughput.
- Your previous live run of the earlier version completed all eight jobs in 115.7–313.7 seconds each, with all POST requests under 2 seconds. Those measurements are a baseline, not a live benchmark of this updated OCR/retrieval version.
- Docker was not available in this build environment. The sample runner rebuilds and tests the Docker service on the submission machine before evaluating all eight samples.


## Rebuild the submission ZIP

After generating all eight outputs and confirming the validator, run `scripts/package_submission.sh`. It includes the `.git` history and excludes `.env`, virtual environments, uploaded sample documents, and ground-truth answers.
