# Design — Outcome Document Extraction Service

**Role: AI/ML Developer**

## Approach

The service accepts PDF, DOCX, XLSX and CSV through one asynchronous API. Parsing preserves document structure and source locations: PDF page text and positioned blocks, OCR page boundaries, DOCX paragraph/table indices, and spreadsheet sheet/row/cell references. Native text is preferred; local Tesseract handles image-only PDF pages. Parsed text is treated as untrusted data, never as instructions.

Extraction is schema-driven. Field types are inferred from the provided descriptions, and output keys are preserved. Structured tabular documents use deterministic parsers where their layout is identifiable; this avoids spending model tokens on arithmetic and row alignment. Semantic documents use OpenRouter models from the assignment allow-list. The fast model performs ordinary extraction; the stronger model is reserved for selected consequential-field review or bounded fallback; the vision model is used selectively for uncertain OCR-derived pages.

## Key accuracy decision: source-grounded schedules

The lease runs showed that long rent schedules were a recurring source of missing rows and expensive model retries. The final implementation discovers the schedule's start-date, end-date, monthly-rent and derived fields from the schema, then reconstructs date-bounded monetary rows from the document's OCR/text. It keeps the three arrays aligned and computes total base rent and annual rent per rentable square foot in Python. Schedule fields recovered this way are excluded from LLM requests. This is generic with respect to property names and schedule values; it does not embed sample answers.

Other semantic fields remain LLM-extracted from retrieved source evidence. Lease fields are grouped in pairs to limit truncation; unresolved fields receive a targeted, larger-evidence retry. The pipeline validates citation authenticity against extracted source text without requiring an exact schema keyword in the citation. Unsupported values remain null. A separate review path can escalate selected high-risk or uncertain fields; it is bounded to control spend.

## Models, cost and evaluation

Only assignment-listed models are accepted in `app/llm.py`. All calls use runtime environment variables; keys and endpoints are not hardcoded. The best measured two-field Flash baseline spent approximately **$0.91 across the three lease samples** (roughly $0.29–$0.33 per lease). The stronger model and vision model are used sparingly. The evaluator measures actual cost independently; metadata is operational telemetry, not a substitute for that measurement.

The official validator scores the included eight sample outputs at **0.890 mean**: box score 1.000, budget 0.999, lease samples 0.725/0.700/0.700, offering memorandum 1.000, rent roll 1.000 and T12 1.000. The lease output results came from the measured Flash baseline with the generic schedule parser and deterministic calculations applied to its predictions. The final source also skips schedule fields from model calls, but has not yet been rerun against OpenRouter after this last call-saving change. Offline compilation and 17 tests pass; actual OCR schedule reconstruction was checked on the three source documents.

## Reliability and tradeoffs

FastAPI returns job IDs immediately and stores state in SQLite. Request hashes provide idempotency, organization IDs scope job reads, and terminal states are not rewritten. Ten jobs can be accepted in flight; LLM calls are bounded by a semaphore. Each request has a timeout and transient-provider retry; each job has a 1,700-second hard deadline, below the contract's 1,800-second limit.

The deterministic budget, offering, rent-roll, T12 and box-score parsers are accurate on the supplied formats but unseen layouts may require additional structural handling. OCR may still miss handwriting, stamps or low-quality scans; vision review is intentionally limited to avoid making every page expensive. The fast LLM path can still miss uncommon legal clauses, and confidence scores are heuristic rather than calibrated probabilities.

## What changed during development

The initial lease extractor made many individual calls and still missed fields. A newer planner/strong-model-heavy route reduced calls but did not improve the measured score and cost more, so it was not selected as the final baseline. The final choice keeps the higher-scoring Flash extraction strategy and adds deterministic, schema-discovered rent-schedule reconstruction; this improved the official sample mean from 0.861 to 0.890 without using the ground-truth answers as extraction inputs. Remaining lease clause omissions are documented by the output scores rather than hidden by hardcoded values.

With another week, I would build a larger held-out legal-document evaluation set, add a high-recall section index with semantic retrieval, evaluate entailment/contradiction detection for obligations and exceptions, and benchmark model tiers on identical evidence while measuring p50/p95 latency and cost under ten concurrent jobs.
