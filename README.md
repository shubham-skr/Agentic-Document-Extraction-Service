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
- PDF: PyMuPDF native text and positioned blocks; scanned pages use parallel Tesseract OCR.
- DOCX: paragraphs and Word tables with source locators.
- XLSX/CSV: native cell/row parsing; rent-roll charge blocks and T12 line items are handled deterministically.
- Schema normalization: deterministic typing from the supplied field names and descriptions; it makes no extra API call and preserves the original field semantics.
- Extraction: groups of four fields, evidence-focused retrieval, provider JSON mode with standard-library recovery for malformed or truncated responses, and source citations. All provider calls use `LLM_BASE_URL` and `LLM_API_KEY`.
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

The official validator is included. The three deterministic spreadsheet/CSV outputs currently present in `outputs/` score 1.000 each against the supplied truth. The five semantic PDF/DOCX outputs must be generated with a valid OpenRouter key using `scripts/run_local_samples.sh`; do not claim a final eight-document score until that validator run completes.

## Sample evaluation note

The deterministic CSV/XLSX parsers are regression-tested against the supplied sample truth (box score, rent roll and T12). Narrative PDF/DOCX extraction requires a configured OpenRouter key; generate those outputs with `scripts/run_local_samples.sh` and retain only generated result JSON in `outputs/`. The final measured eight-document score must be added here after running the official validator; no unmeasured score is claimed.


## Verified locally

- `python -m compileall -q app tests`: passed.
- `python -m pytest -q`: 10 passed (JSON recovery, confidence coercion, SQLite commit persistence, mocked DOCX extraction path, and API job lifecycle).
- Official validator against the supplied truth: box score 1.000, rent roll 1.000, T12 1.000.
- FastAPI API test: POST returned in under 2 seconds and a deterministic CSV job reached SUCCESS. A separate 10-job concurrent CSV test accepted all 10 and all reached SUCCESS; maximum POST latency was 0.046 seconds. These API tests did not exercise live LLM throughput.
- Docker was not available in this build environment. The sample runner rebuilds and tests the Docker service on the submission machine before evaluating all eight samples.


## Rebuild the submission ZIP

After generating all eight outputs and confirming the validator, run `scripts/package_submission.sh`. It includes the `.git` history and excludes `.env`, virtual environments, uploaded sample documents, and ground-truth answers.
