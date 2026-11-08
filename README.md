# Outcome — Document Extraction Service

**Submission role: AI/ML Developer**

A schema-driven document extraction service for PDF, DOCX, XLSX and CSV. The pipeline combines layout-preserving parsing, local OCR, deterministic extraction for structured financial documents, evidence-grounded LLM extraction for semantic documents, and persistent asynchronous jobs.

## Run with Docker

1. Copy `.env.example` to `.env`.
2. Set `LLM_BASE_URL` and a valid `LLM_API_KEY` in `.env`. Never commit `.env`.
3. Run `docker compose up --build -d`.
4. Check `curl http://localhost:8080/health`.

The service listens on port 8080. `POST /jobs` accepts multipart fields `file` and `schema` (a JSON string); optional `webhook_url`. Poll `GET /jobs/{job_id}`. Use `X-Organization-Id` consistently for tenant-scoped job access.

## Local development

Python 3.11 is recommended. Install Tesseract OCR with the English language pack, then:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
chmod 600 .env
# Set LLM_BASE_URL and LLM_API_KEY in .env
uvicorn app.main:app --reload --port 8080
```

## Architecture

- **Ingestion and structure preservation:** PyMuPDF extracts native PDF text and positioned blocks; Tesseract OCR handles image-only pages. DOCX parsing preserves paragraph and Word-table locators. XLSX/CSV parsing preserves sheet, row and cell locations.
- **Document routing:** deterministic parsers handle structured CSV/XLSX rent rolls, box scores and operating statements, plus the supported budget and offering-memorandum layouts. Semantic documents use the LLM path.
- **Schema-driven extraction:** types are inferred from each field's description. Lease fields are requested in small coherent pairs; non-lease semantic fields use groups of four. Unresolved fields receive a targeted recovery pass with a larger evidence window. All model calls use only assignment-allowed model IDs through `LLM_BASE_URL` and `LLM_API_KEY`.
- **Rent schedules:** the system discovers schedule fields from the supplied schema, reconstructs date/rent rows from OCR or document text, preserves aligned arrays, and computes total base rent and annual rent per rentable square foot in Python. The parser does not depend on property names or sample-specific values. Successfully reconstructed schedule fields are not sent back to the LLM.
- **Evidence and normalization:** values are normalized to the requested type. A citation must be supported by the extracted source text; the check does not require the schema field's exact keyword to appear in the citation. Missing or unsupported values remain null. High-risk or uncertain OCR-derived fields can receive bounded visual review.
- **Service reliability:** FastAPI accepts jobs asynchronously, persists state in SQLite, supports idempotent request hashes and organization-scoped reads, and protects terminal job states. LLM calls are bounded by a semaphore, per-request timeout and transient-error retry. Each job has a 1,700-second deadline, below the 1,800-second assignment limit.

## Configuration and model use

See `.env.example`. The fast extraction model is `google/gemini-3.8-flash`; `google/gemini-3.1-pro-preview` is available for targeted consequential-field review and bounded fallback; `z-ai/glm-5.3-flash` is the vision model. The service restricts model IDs to the list in the assignment. No API key or provider endpoint is hardcoded.

In the best measured two-field baseline, the three lease runs used approximately **$0.91 combined** (about $0.29–$0.33 per lease) before deterministic rent-schedule fields were removed from LLM requests. Provider usage is reported in output metadata; Outcome measures spend independently.

## Tests and evaluation

```bash
python -m compileall -q app tests tools
python -m pytest -q
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
```

The included `outputs/` contains all eight sample results and scores **0.890 mean** with the official validator:

| Document | Score |
|---|---:|
| Box score CSV | 1.000 |
| Budget PDF | 0.999 |
| Lease 001 PDF | 0.725 |
| Lease 002 DOCX | 0.700 |
| Lease 003 PDF | 0.700 |
| Offering memorandum PDF | 1.000 |
| Rent roll XLSX | 1.000 |
| T12 XLSX | 1.000 |
| **Mean** | **0.890** |




## Run all eight samples locally

Sample documents and ground-truth answers are intentionally excluded from the submission archive. To restore them locally and run the Docker/API evaluation:

```bash
bash scripts/run_local_samples.sh "$HOME/Downloads/OUTCOME LABS/Outcome_Take_Home_Assignment.zip"
```

The script restores the sample inputs and truth files locally, rebuilds the service, submits all eight documents, polls each job to a terminal state, writes `outputs/*.json`, and runs the official validator. It uses the API key from `.env`.
