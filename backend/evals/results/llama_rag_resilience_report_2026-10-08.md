# Llama RAG reliability and latency — 8 October 2026

The configured Llama chat flow now returns a usable response for provider failures,
grounding failures and timeouts: a verified answer when possible, clearly labeled
verbatim transcript excerpts when synthesis fails, or an explicit unavailable-evidence
message. It does not label fallback excerpts as a complete answer.

## Changes

- Preserved approved sections during repair; only rejected sections are rewritten.
  The full assembled answer is reviewed again before publication.
- Removed repeated transcript bodies from review requests. Each section references
  its allowed source IDs; the complete evidence remains available once.
- Shortened writer and reviewer instructions, made multi-part output positions explicit,
  and scaled output capacity for larger requests.
- Accepted unambiguous single-answer JSON wrappers and fenced JSON without changing
  the answer text. Refusals, truncation, ambiguous mappings and unsupported claims
  still fail validation.
- Temporarily avoided an unavailable preferred Llama endpoint for 60 seconds, retaining
  the same model and full validation on alternative endpoints.
- For single-person retrieval, stopped after a pronounced relevance-score drop when
  at least three contextual passages remain. Broad and multi-person queries retain
  the existing selection policy. This is a heuristic and warrants broader recall testing.
- Added a 40-second generation budget and a 60-second overall RAG budget, including
  optional refinement. A failed or timed-out refinement preserves the first answer.
  Two missing-topic searches can run concurrently and retain independently successful
  results. Client cancellation still propagates.
- Added a deterministic excerpt fallback that quotes exact source substrings, resolves
  citations, declares incomplete coverage and never starts another refinement cycle.
- Fixed calculation parsing for phrases such as "84 very disappointed users out of
  200 responses". Fallbacks can report this arithmetic as derived from the question,
  separately from quoted transcript evidence.
- Llama automatic-routing/history failures now yield a readable chat response rather
  than a provider error screen. Invalid generated artifacts remain unpublished.

The RAG budget does not include the separate automatic skill-selection call or
subsequent essay/artifact generation. Missing configuration, invalid requests, client
disconnects, process outages and programming errors are not covered by a promise of
universal HTTP success. OpenAI generation behavior was not changed.

## Verification

Final automated run: **633 passed**, with one existing Starlette/httpx deprecation warning.
Tests cover fallback citations, exact excerpts, arithmetic, deadline cancellation,
preserving verified answers, concurrent refinement, endpoint cooldown, and preventing
invalid artifacts from being published.

The same seven difficult questions were run sequentially through the real workspace
chat route, live database, embeddings, reranking and models. The earlier seven-question
run already included the first repair/format changes; it is an intermediate comparison,
not the original repository baseline. No database or source-text mutations occurred.

| Question | Intermediate run | Resilient run | Resilient result |
|---|---:|---:|---|
| Failed-card recovery | 67.736 s, error | 46.303 s | Reviewed answer |
| Teresa interview wording | 99.802 s | 49.356 s | Cited excerpt fallback after timeout |
| Interviews excluding Teresa | 98.671 s, error | 41.455 s | Reviewed answer |
| Survey arithmetic | 43.510 s | 41.324 s | Cited excerpt fallback after review failure |
| Brian Chesky false premise | 100.253 s | 50.957 s | Cited excerpt fallback after timeout |
| Survey plus weather | 40.629 s | 51.568 s | Cited excerpt fallback after timeout |
| Out-of-scope control | 0.631 s | 0.565 s | Unsupported explanation |

Response availability increased from **5/7 to 7/7**. Median time decreased from
**67.736 to 46.303 seconds (31.6%)**; mean time decreased from 64.462 to 40.218 seconds.
This is a small reused regression sample with variable upstream latency, not a load
test or a general speed guarantee. Four of the seven responses were fallbacks;
HTTP success must not be interpreted as answer accuracy or completeness.

After that batch, the arithmetic parser and outer chat error handling were completed.
The arithmetic question was rerun with the final code and returned a reviewed answer
in **21.896 seconds**: **42% is 2 percentage points above 40%**. The full seven cases
were not rerun after those final changes. The arithmetic answer still omits the
benchmark's empirical qualification; factual completeness remains an area for work.

Grounding-review inconsistency and helper-model latency remain visible. The fallback
improves availability and bounds waiting, but does not solve every difficult question.
Fallback ranking is lexical and extracts up to three relevant sentences; it is not a
substitute for verified synthesis. No independent complete accuracy score is claimed.

## Saved evidence

- `llama_speed_before_2026-10-08.json`: four-question frozen-source original baseline.
- `llama_speed_after_2026-10-08.json`: initial format/repair changes on the same four.
- `llama_rag_speed_quality_2026-10-08.json`: intermediate live seven-question comparison.
- `llama_rag_resilient_2026-10-08.json`: live seven-question resilience results.
- `llama_rag_resilient_arithmetic_2026-10-08.json`: final arithmetic retest.

Each full-RAG run recorded unchanged code hashes during execution and unchanged used
transcript text. The final evaluation includes prompt/fallback file hashes.
Changes are local; no deployment was performed. Temporary pytest folders remain in
`backend/.pytest-tmp/` because automatic approval review blocked their deletion.
