# Design decisions — Outcome Document Extraction Service

## Summary

I chose an evidence-first hybrid pipeline rather than sending whole documents to one large model. The system preserves source structure, uses deterministic parsers for tabular data, and reserves LLM reasoning for semantic interpretation. LangGraph provides explicit workflow stages while bounded asynchronous tasks provide page and model-call parallelism.

## Pipeline

1. **Schema normalization.** Field types and scope are inferred deterministically from the supplied keys and descriptions. This avoids an unnecessary LLM call and guarantees that arbitrary client field keys are preserved.
2. **Document parsing.** PDFs are parsed page-wise with PyMuPDF; pages without a useful text layer are rendered at 150 DPI and OCR'd locally with Tesseract PSM 6, preserving blank page slots so citation page numbers do not shift. Page boundaries and positioned text blocks are retained. DOCX paragraphs and tables are traversed in original body order; spreadsheet cells retain source locators.
3. **Profiling and retrieval.** A lightweight profile identifies document format/type and likely sections. IDF-weighted lexical retrieval selects evidence using field keys, labels, descriptions and less-common terms.
4. **Extraction.** Lease abstraction fields are grouped in pairs to limit long legal-text responses and truncated JSON; other schemas are grouped in batches of four. The system prompt treats document text as untrusted evidence, prohibits unsupported inference and requires a verbatim citation for every non-null value. Only the allowed OpenRouter model IDs are accepted.
5. **Structured tabular handling.** Rent-roll unit blocks and T12 GL rows are parsed deterministically. Selectable-text budget PDFs use coordinate bands to recover all GL detail rows and variance columns; offering memoranda use labeled sections, the unit-mix table and the subject-property comparable row. These paths do not spend model calls. Calculations use source values and Python rather than asking an LLM to do arithmetic.
6. **Validation.** Values are normalized to the requested type, citation excerpts are checked against extracted source text, missing fields are serialized as null, and each row carries every schema key.

## Model routing and cost

The default inexpensive model handles ordinary text extraction; schema normalization is deterministic and consumes no model tokens. A stronger allowed model verifies a small set of consequential or low-confidence fields and is also available for fallback table extraction. The configured vision model is used selectively for high-risk or uncertain values on scanned pages (for example, security-deposit amendments); it is not called for every page. Local OCR remains the first pass to avoid per-page multimodal spend. All model calls use the environment-provided base URL and key. The service records token counts and per-model call counts. `cost_usd` is reported as 0 until an authoritative per-model pricing table is configured; the evaluator independently measures actual spend.

## Reliability and concurrency

PDF pages are processed concurrently in a bounded thread pool. LLM calls use a global semaphore, 60-second request timeout, one bounded retry for transient throttling/server errors, and JSON-mode structured responses. Each job has a 1,700-second hard timeout, below the 1,800-second contract limit. FastAPI returns job IDs immediately and stores job state in SQLite. Request hashes support idempotency; organization IDs scope reads. Terminal statuses are immutable. A single container worker process avoids concurrent SQLite writer contention; multiple document jobs can still be in flight asynchronously.

## Tradeoffs and limitations

- OCR is local and inexpensive but handwriting and dense tables may require visual escalation. OCR quality is not guaranteed for every scan.
- Lexical retrieval is deliberately simple and dependency-light; a larger deployment could add a local embedding index after measuring recall.
- Document layouts vary. The budget and offering parsers are geometry/label-driven and may need new column or label hints for unseen layouts. Specialized rent-roll/T12 parsers cover the supplied formats; generic fallback is header-driven and may need tuning for unseen layouts.
- The model's self-reported confidence is not calibrated. It is treated as a heuristic, not a probability guarantee.
- Citation verification is a conservative text-level check; it cannot independently prove semantic entailment.
- Durable job persistence is provided, but a multi-replica production deployment would move job dispatch to a transactional queue and add leases/heartbeats.

## What I would do with another week

Build a labelled evaluation harness with per-field precision/recall and citation entailment; add OCR confidence and targeted vision fallback for handwriting/low-quality regions; improve table reconstruction with coordinate-aware column detection; add robust job leases and restart recovery; calibrate confidence thresholds; and run cost/latency experiments across the allowed models.
