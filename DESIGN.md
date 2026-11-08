# Design decisions — Outcome Document Extraction Service

## Summary

The service uses a general, schema-driven, evidence-first pipeline. Deterministic parsing handles predictable structures; model reasoning is used for ambiguous semantics. Output keys are preserved exactly. The extraction strategy is personalized at runtime from the supplied document and its schema, not from hardcoded sample answers or property names.

## Pipeline and decisions

1. **Parse and preserve structure.** PDFs use PyMuPDF; pages without useful text are OCR'd locally with Tesseract. Page boundaries are retained. DOCX paragraphs/tables are traversed in body order. Spreadsheet cells retain sheet/cell coordinates.
2. **Profile and plan.** A fast allowed model receives the schema and a compact structural outline. It generates concise per-field intent, semantic alternatives, search queries, likely sections, strategy, dependencies and coherent groups. The planner does not extract values. A sanitizer rejects unknown keys, de-duplicates groups, assigns every schema key exactly once and caps groups at eight fields. Predictable structured inputs bypass planning.
3. **Retrieve evidence.** Planner-generated alternatives and section hints supplement lexical, phrase and IDF-weighted retrieval. The system preserves neighbouring lines and source locators. This is lightweight hybrid lexical retrieval, not a vector database.
4. **Route by group semantics.** Direct names, dates and labeled values prefer the fast model. Groups involving legal options, conditions, calculations or narrative clauses use the strong model. A long document is not, by itself, a reason to send every group to the strong model. A failed fast-model group may escalate once.
5. **Review and recover.** One batched semantic review checks populated predictions. Missing fields are recovered in batches of up to ten with expanded evidence, rather than retrying each field separately. For scanned PDFs, high-risk/uncertain fields can be checked against up to two original page images using the configured vision model.
6. **Calculate from source.** Structured CSV/XLSX, supported budget PDFs and offering memoranda retain deterministic parsers. Date/rent rows are reconstructed from the document and schema-discovered field roles. Python computes total base rent and annual rent per RSF after LLM review/recovery so a later null decision cannot erase a deterministic result. Escalation wording is not guessed from changing rent values alone.
7. **Validate source and meaning separately.** Citation authenticity verifies that quoted text occurs in the source; it does not require the schema keyword to appear. Semantic review assesses whether evidence entails the requested concept and value. Page numbers can be inferred from authentic PDF citations when the model omits the locator.
8. **Serve jobs.** FastAPI returns job IDs quickly; SQLite persists job state; organization IDs scope reads; request hashes support idempotency; terminal states are immutable; bounded concurrency and a 1,700-second deadline fit within the assignment's 1,800-second gate.

## Model and cost tradeoffs

The fast model handles planning and straightforward evidence extraction. The strong model is reserved for semantically difficult groups and batched recovery. The vision model is invoked only for high-risk/uncertain fields on scanned pages. Deterministic routes bypass LLM calls. This should improve the balance between accuracy and cost compared with routing every field group in every complex document to the strong model. Calls, tokens and per-model cost are recorded; actual provider spend must be confirmed from live usage.

## Measured evidence and limitations

The applicant's most recent live Docker/OpenRouter run of the previous schema-aware version completed 8/8 jobs, but its official mean was **0.847**. The three lease scores were 0.675, 0.675 and 0.425. Each lease used 8–9 calls, reported costs between $0.368 and $0.371, and completed in 220–229 seconds. This established that the call-count reduction worked, but lease recall remained poor.

A separate offline operation applied deterministic rent-schedule calculations to those same outputs and raised the validator mean to **0.850**. That improvement is attributable only to deterministic schedule calculations. The current per-group model routing, bounded missing-field recovery and visual review are covered by **24 passing mocked/offline tests**, but have not yet been live-evaluated against OpenRouter or Docker in this environment. No improved live score, provider cost or 10-document concurrency result is claimed.

## Further work

Run same-evidence Flash/Pro comparisons; measure field-level precision/recall and planner output length; check visual page selection on the live scanned leases; tune recovery batch size against rate limits and cost; and load-test ten simultaneous LLM-heavy jobs.
