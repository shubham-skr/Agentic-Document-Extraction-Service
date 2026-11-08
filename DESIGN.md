# Design decisions — Outcome Document Extraction Service

## Summary

I use a general, schema-driven, evidence-first pipeline. Deterministic parsing handles predictable structures; model reasoning is reserved for ambiguous semantics. The service does not assume a fixed field list or hardcode sample values. It personalizes the extraction strategy for each document by planning from the actual input schema and a structural outline of that document.

## Pipeline

1. **Parse and preserve structure.** PDFs are read page by page with PyMuPDF; pages without a useful text layer are OCR'd locally with Tesseract. Page boundaries, layout and source locators are preserved. DOCX paragraphs and tables are traversed in body order. Spreadsheet cells retain sheet/cell coordinates.
2. **Profile the document.** Format, page/OCR characteristics and likely section headings are summarized.
3. **Plan around the supplied schema.** A fast allowed model receives the complete field descriptions and compact document outline. It determines field meaning, semantic equivalents/alternate terminology, likely headings, table/calculation strategy, dependencies and logical groups. It does not return values. A sanitizer rejects unknown keys, de-duplicates fields, caps groups at eight fields, and assigns every requested field exactly once. If planning fails, deterministic type inference and schema-derived groups provide a safe fallback.
4. **Retrieve hybrid evidence.** The planner's document-specific aliases, queries and section hints supplement lexical/phrase scoring. Retrieval keeps neighbouring lines and locators. This avoids relying on the exact schema keyword and improves recall where contracts use alternative terminology.
5. **Route and extract in groups.** High-complexity or OCR-heavy documents use the configured strong model for grouped extraction. Simpler documents use the fast model. Medium-complexity groups are routed by semantic strategy. A failed fast group may escalate once to the strong model. There is no per-field retry loop; the intended model-call pattern is one planner call, one call per coherent group, and one batched review.
6. **Use deterministic parsing where appropriate.** Existing CSV/XLSX, financial budget-PDF and offering-memorandum parsers are retained. Rent schedules are reconstructed from date-bounded source rows with schema-discovered output roles. Python computes schedule totals and annual rent per RSF from source values. Variable escalation descriptions are interpreted by the model, not inferred from rent differences alone.
7. **Validate evidence and meaning separately.** Citation authenticity checks whether the excerpt exists in source text at the stated locator; it does not require a field keyword to appear. A separate batched semantic review checks entailment, preserves distinctions between similar contractual concepts, and can correct or null a candidate. Unsupported or unverifiable non-null values are cleared.
8. **Serve jobs asynchronously.** FastAPI returns a job ID quickly, SQLite stores job state, organization IDs scope reads, request hashes support idempotency, and terminal statuses are immutable. Bounded concurrency and a 1,700-second deadline fit within the assignment's 1,800-second per-document gate.

## Model strategy and cost

The planner uses the fast model because it only interprets the schema and document outline. Complex extraction and its single batched semantic review use the configured strong model. Structured inputs that are reliably parsed deterministically bypass the LLM. A failed fast-model group is allowed one strong-model escalation; failed groups are not retried field by field. The service records calls, tokens and provider-reported cost by model. I do not claim a dollar spend without a valid new key and a measured provider usage report.

## Accuracy evidence

The applicant's last live Docker/OpenRouter run on the previous code completed eight jobs with an overall official score of 0.861. Five non-lease documents were approximately 1.000; the leases scored 0.600, 0.675 and 0.618. The field-level comparison showed that rent schedule arrays and totals were missing, and that several legal clauses used terminology different from schema labels.

The new deterministic schedule reconstruction was run offline against OCR text extracted from the three supplied lease documents and checked with the official validator. When its schedule arrays, total base rent and annual rent per RSF were applied to the applicant's existing predictions, the lease scores became 0.725, 0.700 and 0.700 and the eight-document mean became 0.890. This is a measured improvement attributable to schedule reconstruction only. The new planner, strong-model routing and batched semantic review still require a live OpenRouter run; no improved live result is claimed.

## Reliability and tradeoffs

- Local OCR avoids a paid OCR service and keeps the allowed-provider restriction, but noisy scans can still impair extraction.
- A planner adds one inexpensive model call, but reduces repeated generic prompts and improves retrieval/query personalization.
- Strong-model routing improves reasoning where ambiguity is high, at a higher per-token cost; deterministic parsing offsets that cost for structured documents.
- Hybrid lexical/phrase retrieval is light and transparent, but it is not a full embedding/vector retrieval system.
- Authenticity checks verify text presence, not meaning. The semantic reviewer handles entailment separately; neither is a mathematical guarantee.
- The current job store uses SQLite and a single container worker process. A larger deployment would use a durable transactional queue and worker leases/heartbeats.

## Further work

Run controlled same-evidence model comparisons and per-field precision/recall; calibrate the strong-model threshold against accuracy and cost; add embedding retrieval only if its recall gain justifies it; add OCR confidence and targeted vision fallback for low-quality regions; and load-test ten simultaneous LLM-heavy jobs with provider rate limits.
