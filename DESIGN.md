# Design decisions — Outcome Document Extraction Service

## Summary

I chose an evidence-first hybrid pipeline rather than sending whole documents to one large model. The system preserves source structure, uses deterministic parsers for tabular data, and reserves LLM reasoning for semantic interpretation. LangGraph provides explicit workflow stages while bounded asynchronous tasks provide page and model-call parallelism.

## Pipeline

1. **Schema normalization.** A low-cost allowed model clarifies each client field's semantics, synonyms, type, scope and cardinality. Original keys and intent remain authoritative. A deterministic fallback exists if the normalizer fails.
2. **Document parsing.** PDFs are parsed page-wise with PyMuPDF; pages without a useful text layer are rendered and OCR'd locally with Tesseract. Page boundaries and positioned text blocks are retained. DOCX paragraphs/tables and spreadsheet cells retain source locators.
3. **Profiling and retrieval.** A lightweight profile identifies document format/type and likely sections. Lexical retrieval selects relevant source lines for field groups, reducing irrelevant prompt tokens.
4. **Extraction.** Related fields are grouped into calls. The system prompt treats document text as untrusted evidence, prohibits unsupported inference and requires a verbatim citation for every non-null value. Only the allowed OpenRouter model IDs are accepted.
5. **Structured tabular handling.** Rent-roll unit blocks and T12 GL rows are parsed deterministically. Calculations use source values and Python rather than asking an LLM to do arithmetic.
6. **Validation.** Values are normalized to the requested type, citation excerpts are checked against extracted source text, missing fields are serialized as null, and each row carries every schema key.

## Model routing and cost

The default inexpensive model handles schema normalization and ordinary text extraction. A stronger allowed model verifies a small set of consequential or low-confidence fields and is also available for fallback table extraction. The configured vision model is used selectively for high-risk or uncertain values on scanned pages (for example, security-deposit amendments); it is not called for every page. Local OCR remains the first pass to avoid per-page multimodal spend. All model calls use the environment-provided base URL and key. The service records token counts and per-model call counts. `cost_usd` is reported as 0 until an authoritative per-model pricing table is configured; the evaluator independently measures actual spend.

## Reliability and concurrency

PDF pages are processed concurrently in a bounded thread pool. LLM calls use a semaphore and retry transient throttling/server errors with exponential backoff and jitter. FastAPI returns job IDs immediately and stores job state in SQLite. Request hashes support idempotency; organization IDs scope reads. Terminal statuses are immutable. A single container worker process avoids concurrent SQLite writer contention; multiple document jobs can still be in flight asynchronously.

## Tradeoffs and limitations

- OCR is local and inexpensive but handwriting and dense tables may require visual escalation. OCR quality is not guaranteed for every scan.
- Lexical retrieval is deliberately simple and dependency-light; a larger deployment could add a local embedding index after measuring recall.
- Spreadsheet schemas vary. Specialized rent-roll/T12 parsers cover the supplied formats; generic fallback is header-driven and may need tuning for unseen layouts.
- The model's self-reported confidence is not calibrated. It is treated as a heuristic, not a probability guarantee.
- Citation verification is a conservative text-level check; it cannot independently prove semantic entailment.
- Durable job persistence is provided, but a multi-replica production deployment would move job dispatch to a transactional queue and add leases/heartbeats.

## What I would do with another week

Build a labelled evaluation harness with per-field precision/recall and citation entailment; add OCR confidence and targeted vision fallback for handwriting/low-quality regions; improve table reconstruction with coordinate-aware column detection; add robust job leases and restart recovery; calibrate confidence thresholds; and run cost/latency experiments across the allowed models.
