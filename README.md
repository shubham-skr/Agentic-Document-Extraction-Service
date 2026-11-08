# Outcome — Document Extraction Service

**Submission role: AI/ML Developer**

An evidence-grounded extraction service for PDF, DOCX, XLSX and CSV. It preserves the caller's schema keys and combines structure-preserving parsing, local OCR, deterministic table extraction, per-document schema planning, hybrid evidence retrieval, group-level model routing, bounded missing-field recovery and targeted visual review. It does not depend on a fixed field list or sample-specific answer values.

## Quick start (Docker)

1. Copy `.env.example` to `.env`.
2. Set `LLM_BASE_URL` and a valid, newly issued `LLM_API_KEY` in `.env`. Never commit `.env`.
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
# edit .env and provide a newly issued OpenRouter key
uvicorn app.main:app --reload --port 8080
```

## Architecture

1. **Ingestion and structure preservation.** PDFs use PyMuPDF native text/positioned blocks and local Tesseract OCR for scanned pages, with page boundaries preserved. DOCX paragraphs and tables are read in body order. XLSX/CSV cells and rows retain source locations.
2. **Document profiling.** A lightweight profile records format, OCR/page characteristics and candidate section headings.
3. **Per-document schema planner.** For semantic documents, the fast allowed model receives the current schema and a compact document outline. It creates concise field meanings, alternative terminology, retrieval queries, section hints, calculation dependencies, strategies and coherent groups. It returns no extracted answers. The planner response is compact and sanitized: only caller-supplied keys are accepted, every field is assigned once, and a group is capped at eight fields. A schema-derived fallback is used if planning fails. Predictable CSV/XLSX and supported structured budget/OM paths bypass planning.
4. **Hybrid evidence retrieval.** Retrieval combines schema wording, planner-generated aliases/queries, phrase matches, section hints and IDF-weighted lexical evidence. It returns neighbouring lines and source locators. This is lightweight query expansion plus lexical retrieval, not a vector-embedding system.
5. **Adaptive grouped extraction.** The model tier is selected per group using planner strategy and field semantics, rather than sending every group from a long document to the strong model. Direct names, dates and labeled facts prefer the fast model; groups requiring interpretation, options, calculations or narrative clauses use the strong model. A failed fast group can escalate once. No field-by-field retry loop is used.
6. **Review and bounded recovery.** One batched semantic review checks populated candidates only. Unresolved fields are then recovered in batches of up to ten, with larger evidence windows; this avoids dozens of individual retries. For OCR PDFs, high-risk or uncertain fields (such as amended security deposits and guarantors) can be checked against original page images using the configured vision model, limited to two pages per document.
7. **Deterministic extraction and calculations.** CSV/XLSX, supported budget PDFs and offering memoranda retain their structured parsers. Date-bounded rent schedules are reconstructed from source rows using schema-discovered start/end/monthly-rent roles. Python calculates total base rent and annual rent per RSF after model review/recovery so a model null decision cannot erase deterministic calculations. Variable escalation wording is not guessed merely because rent values differ.
8. **Evidence validation.** Citation authenticity is checked separately from semantic relevance. Authenticity verifies that quoted source text appears in the document and does not require the schema keyword to appear. A semantic reviewer assesses whether evidence supports the value. Missing page locators can be inferred from authentic PDF excerpts to enable targeted visual review.
9. **Service reliability.** FastAPI provides asynchronous jobs, SQLite persistence, organization-scoped reads, idempotency, terminal-state protection, bounded concurrency and a 1,700-second job deadline. All model requests use `LLM_BASE_URL` and `LLM_API_KEY`; `app/llm.py` restricts model IDs to the assignment allowlist.

## Model and cost strategy

The fast model plans the document/schema strategy. Extraction uses the fast model for direct evidence and the strong model for semantically difficult groups; unresolved fields receive bounded batched recovery. The vision model is used only for selected OCR pages and high-risk/uncertain fields. Deterministic routes use no model calls. Per-model calls, tokens and provider-reported cost are recorded in job metadata. Actual spend should be checked against the provider's usage dashboard; no unmeasured cost estimate is claimed.

## Configuration

See `.env.example`. Model IDs are restricted in `app/llm.py` to the assignment's allowlist. No key or endpoint is hardcoded.

## Tests and sample evaluation

Run:

```bash
python -m compileall -q app tests tools
python -m pytest -q
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
```

The offline suite covers planner sanitization, per-group routing, bounded unresolved-field batches, page inference, targeted visual review, citation authenticity independent of schema wording, semantic-alias retrieval, rent-schedule reconstruction/calculations, parser regressions, JSON recovery, SQLite persistence and API job lifecycle.

To run all eight supplied samples locally, activate `.venv`, ensure `.env` contains a newly issued OpenRouter key, and execute:

```bash
source .venv/bin/activate
bash scripts/run_local_samples.sh "$HOME/Downloads/OUTCOME LABS/Outcome_Take_Home_Assignment.zip"
```

The runner restores sample inputs/truth locally, rebuilds Docker, submits all eight documents through `POST /jobs`, waits for terminal states, writes `outputs/*.json` and runs the official validator. Sample inputs and answers remain excluded from the packaged submission.

## Verified status and limitations

- `python -m compileall -q app tests tools`: passed.
- `python -m pytest -q`: **24 passed** in the current offline environment.
- The applicant's most recent live run of the prior schema-aware implementation completed all eight jobs with terminal `SUCCESS` states. POST times were 0.02–1.91 seconds; lease extraction times were 220.0–228.6 seconds. That run's official mean was **0.847** (leases: 0.675, 0.675 and 0.425). Each lease made 8–9 model calls and reported $0.368–$0.371 model cost.
- Applying only the deterministic post-review schedule calculations to those same existing outputs changed the offline validator mean from 0.847 to **0.850**; the lease scores became 0.700, 0.675 and 0.425. This is not a live run of the current code.
- The current adaptive routing, batched unresolved-field recovery and vision-page review have passed mocked/offline tests but have **not** been run against live OpenRouter in this environment. They have not been built in Docker here. Do not claim a new live accuracy, cost, or 10-document concurrency result until the local runner completes against a newly issued key.

## Packaging

After generating all eight final outputs and confirming the official validator, run `scripts/package_submission.sh`. It includes `.git` history and excludes `.env`, virtual environments, uploaded sample documents and ground-truth answers.
