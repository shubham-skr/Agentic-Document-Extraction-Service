# Outcome — Document Extraction Service

**Submission role: AI/ML Developer**

An evidence-grounded extraction service for PDF, DOCX, XLSX and CSV. The pipeline combines structure-preserving parsing, local OCR, deterministic table extraction, per-document schema planning, hybrid evidence retrieval, model-tier routing and independent semantic verification. The input schema remains dynamic: output keys are preserved exactly, and extraction guidance is generated from the current document and schema rather than from sample-specific values.

## Quick start (Docker)

1. Copy `.env.example` to `.env`.
2. Set `LLM_BASE_URL` and a valid `LLM_API_KEY` in `.env`. Never commit `.env`.
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

1. **Ingestion and structure preservation.** PDFs use PyMuPDF native text/positioned blocks and local Tesseract OCR for scanned pages, with page locators preserved. DOCX paragraphs and tables are read in body order. XLSX/CSV cells and rows retain source locations.
2. **Document profiling.** A lightweight profile records format, OCR/page characteristics and candidate section headings.
3. **Per-document schema planner.** For semantic documents, the fast allowed model receives the current schema and a compact document outline. It creates field meanings independent of field labels, document-relevant synonyms/alternate terminology, search queries, section hints, calculation dependencies, strategies and bounded logical groups. It returns no extracted values. The plan is sanitized: only caller-supplied keys are accepted, every field is assigned once, and a group is capped at eight fields. A schema-derived fallback is used if planning fails. Predictable CSV/XLSX and the supported structured budget/OM paths bypass planning to avoid unnecessary model calls.
4. **Hybrid evidence retrieval.** Retrieval combines schema wording, planner-generated semantic queries/aliases, phrase matches, section hints and IDF-weighted lexical evidence. It returns surrounding lines and source locators rather than isolated keyword hits. The planner personalizes retrieval for each document; no lease answer, property name or sample-specific alias is hardcoded.
5. **Adaptive extraction.** Coherent field groups are extracted in one call each. High-complexity/OCR-heavy documents route to the configured strong model; simple documents use the fast model, and medium documents route semantically dense groups to the strong model. A failed fast-model group gets at most one bounded strong-model escalation. There are no field-by-field retries. One batched semantic review checks all fields after extraction.
6. **Deterministic extraction and calculations.** CSV/XLSX, supported budget PDFs and offering memoranda retain their tested structured parsers. Date-bounded rent schedules are reconstructed from source rows using schema-discovered start/end/monthly-rent fields and planner section hints. Total base rent and annual rent per RSF are calculated in Python from the extracted schedule and rentable area. Variable escalation wording is left to semantic extraction rather than guessed from the fact that scheduled rents differ.
7. **Evidence validation.** Citation authenticity is checked separately from semantic relevance. The authenticity check verifies quoted source text and locator but does not require the schema keyword to appear in the citation. The independent semantic reviewer assesses whether the evidence entails the requested concept and value. Values without an authentic citation are cleared. Type inference respects narrative clause descriptions such as “short phrase” even when a field key contains words such as `rent` or `fee`.
8. **Service reliability.** FastAPI provides asynchronous jobs, SQLite persistence, organization-scoped reads, idempotency, terminal-state protection, bounded concurrency and a 1,700-second job deadline. All model requests use `LLM_BASE_URL` and `LLM_API_KEY`; `app/llm.py` restricts model IDs to the assignment allowlist.

## Model routing and cost

The planner uses the configured fast model. Complex documents are routed to the configured strong model for grouped extraction and batched semantic review. Deterministic routes use no LLM calls. Token and per-model usage are recorded in job metadata; actual OpenRouter spend should be read from provider usage/billing and the returned usage metadata. No unverified dollar-spend estimate is claimed here.

## Configuration

See `.env.example`. The allowed model IDs are restricted in `app/llm.py` to the assignment's list. No key or endpoint is hardcoded. The fast, strong and vision models are configurable by environment variables.

## Tests and sample evaluation

Run:

```bash
python -m compileall -q app tests tools
python -m pytest -q
python tools/validate.py outputs/ --schema-dir sample/schemas --truth-dir sample/sample-data-output-validated
```

The test suite covers planner group sanitization, fast/strong model routing, bounded calls (planner + group + one batch review in the mocked single-group flow), semantic-alias retrieval, citation authenticity independent of schema wording, rent-schedule reconstruction/calculations, parser regressions, JSON recovery, SQLite persistence and API job lifecycle.

Sample documents and ground-truth answers are excluded from the submission archive. To run all eight supplied samples locally, activate `.venv`, ensure `.env` contains a newly issued OpenRouter key, and execute:

```bash
source .venv/bin/activate
bash scripts/run_local_samples.sh "$HOME/Downloads/OUTCOME LABS/Outcome_Take_Home_Assignment.zip"
```

The runner restores sample inputs/truth locally, rebuilds Docker, submits all eight documents through `POST /jobs`, waits for terminal states, writes `outputs/*.json` and runs the official validator. Inputs and answer files remain excluded from the packaged submission.

## Verified status and limitations

- `python -m compileall -q app tests tools`: passed.
- `python -m pytest -q`: **18 passed** in the current offline environment.
- The most recent live Docker/OpenRouter baseline reported by the applicant completed all eight jobs in terminal states. Submission POSTs were 0.02–1.78 seconds; the slowest extraction took 484.4 seconds, below the 1,800-second limit. That run's official mean was 0.861; lease scores were 0.600, 0.675 and 0.618. It used the previous implementation, not the new planner/strong-model route.
- An offline evaluation applied the new deterministic schedule reconstruction and derived annual-rent-per-RSF values to those existing lease predictions. The official validator improved the three lease scores to 0.725, 0.700 and 0.700 and the overall eight-document mean to **0.890**. This measures the deterministic schedule improvement only; it is not a live evaluation of the new planner or Gemini Pro extraction.
- The new live planner/model-routing implementation has not been run against OpenRouter in this environment because no valid rotated API key is available here. It has not been Docker-built here because Docker is unavailable in this environment. Do not claim a new live accuracy, cost or concurrency score until the local runner completes against a newly issued key.

## Packaging

After generating all eight final outputs and confirming the official validator, run `scripts/package_submission.sh`. It includes `.git` history and excludes `.env`, virtual environments, uploaded sample documents and ground-truth answers.
