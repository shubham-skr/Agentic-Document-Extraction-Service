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
- Extraction: paired fields for lease abstractions and groups of four for other schemas, evidence-focused retrieval, provider JSON mode with standard-library recovery for malformed or truncated responses, and source citations. All provider calls use `LLM_BASE_URL` and `LLM_API_KEY`.
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

