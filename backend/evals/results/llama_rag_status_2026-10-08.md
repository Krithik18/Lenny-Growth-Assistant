# Llama RAG status and performance

Status as of 8 October 2026, after the latest eight-case follow-up. This is a report of completed work; no additional model tests were run to produce it.

The OpenRouter pipeline is connected and demonstrably uses the intended APIs. Retrieval, reranking, and source handling work in these tests. Answer generation is still inconsistent, so the complete flow cannot yet be described as seamless or production-ready.

## What is working

- **Index coverage:** 303 episodes and 22,086 chunks have OpenRouter embeddings. OpenAI embeddings remain separately available with the same coverage.
- **Hybrid retrieval:** semantic and keyword searches overlap in time. All 19 hybrid rounds in the latest full-20 run and all seven in the subsequent eight-case run verified this. Chunk queries filter to OpenRouter/BGE-M3 embeddings.
- **Reranking:** the real Voyage `voyageai/rerank-2.5-lite` endpoint was used, with no reranking fallback in those runs. This verifies execution, not perfect ordering or complete recall.
- **Answer provider:** successful writer calls return `meta-llama/llama-3.1-8b-instruct`. Qwen handles scope, evidence planning, and grounding review. No OpenAI model calls occurred in these OpenRouter test batches.
- **Citation structure:** every returned citation ID resolves to a supplied source. The existing grounded-answer response format works. This is not proof that every cited passage supports every generated claim.
- **Speaker continuity:** the latest Patrick Campbell answer passed source review. Same-episode, same-revision, exactly matching overlaps carry the proven speaker through a chunk chain; Lenny's examples remain separate. Conflicting or unproven labels remain unknown.
- **Mixed requests:** the latest survey/weather response explains the supported survey portion and marks exact weather unavailable. Direct review confirms the survey question/options, 40% benchmark, and correct main-benefit-resonant user group are now represented.
- **Scope controls:** the tested calculus question stops before database retrieval, embeddings, reranking, or writing. The full-20 unknown-person control stops before substantive chunk retrieval; it may read the identity catalog.

## What is not reliably working

- **Teresa interview question:** relevant passages are retrieved, but Llama repeatedly frames story/timeline techniques as an explicitly supported remedy for leading questions. Grounding review rejects that association; some reviewer objections are also overly strict. Latest result: error, 66.897 seconds.
- **Broad customer-interview question:** earlier runs produced useful advice and removed podcast contamination, but the latest attempt timed out twice during Qwen planning, before Llama writing. Latest result: error, 82.617 seconds. Its earlier omissions cannot be counted as fixed by this failed run.
- **False-premise question:** earlier runs correctly rejected the mass-firing premise but sometimes stated Brian's speculation as fact. The latest attempt failed the required writer-output format checks instead of returning an answer. Latest result: error, 29.977 seconds.
- **Completeness and precision:** the latest comparison and arithmetic responses return useful answers. The arithmetic correctly gives 84/200 = 42% and says it exceeds 40%, but omits the explicit two-percentage-point margin and empirical qualification. Preliminary comparison review identifies lost qualifications and a citation-placement concern. These are not complete quality passes.
- **Name ambiguity:** a first-name-only Naomi request cannot distinguish Naomi Gleit from Naomi Ionita. It safely avoids guessing but returns a generic insufficient-evidence response instead of a helpful clarification.
- **Source metadata:** some episode titles/guest metadata do not match the actual transcript speaker. Explicit labels help attribution, but the underlying metadata problems remain.
- **Availability and latency:** upstream rate limits, helper timeouts, JSON-format failures, and repeated review/repair cycles remain visible. Fallback uses the same Llama model, but does not ensure a correct final response.

## Measured performance

| Completed batch | Successful HTTP responses | Median request time | Slowest request | Recorded API calls | Reported usage cost |
|---|---:|---:|---:|---:|---:|
| Initial full 20 | 18/20 (90%) | 35.974 s | 138.145 s | 180 | $0.3588 |
| First focused six | 6/6 (100%) | 27.218 s | 108.345 s | 43 | $0.0796 |
| Later full 20, before the latest fix | 16/20 (80%) | 36.517 s | 224.573 s | 175 | $0.3184 |
| Latest focused eight | 5/8 (62.5%) | 28.438 s | 82.617 s | 54 | $0.0826 |

These are response-availability rates, not accuracy rates. The six/eight-case batches deliberately select difficult regression questions and cannot be compared directly with the full-20 rates. All requests were sequential; this was not a load, throughput, or concurrent-user test.

Latest eight-case mean request time was **38.249 seconds**. Mean reported cost was **$0.01033 per test request**, including failed requests and the scope control. The later full-20 mean cost was **$0.01592 per request**. The four batches total **54 test requests over reused questions**, 452 recorded provider calls, and approximately **$0.8394 reported usage cost**. This is not 54 unique questions, and reported costs may omit unreported usage on timed-out calls.

The later full-20 run recorded **21 upstream HTTP 429 responses**; the latest eight recorded **five**. These recovered endpoint attempts should not be confused with final application errors. The broad interview failure was a planning timeout; the Teresa failure was semantic rejection; the latest false-premise failure was output-format validation.

Latest per-question results:

| Case | Result | Time | Calls | Quality/evidence status |
|---|---|---:|---:|---|
| Patrick / failed cards | HTTP 200 | 16.903 s | 6 | Source-supported pass; speaker chain verified |
| Teresa / leading questions | HTTP 502 | 66.897 s | 12 | Semantic review exhausted; no published answer |
| Customer interviews excluding Teresa | HTTP 502 | 82.617 s | 5 | Planning timed out; no published answer |
| Sean Ellis versus Rahul Vohra | HTTP 200 | 53.774 s | 6 | Useful; preliminary review finds precision/citation concerns |
| 84 of 200 versus 40% | HTTP 200 | 26.748 s | 10 | Correct 42% and above-40 direction; margin/caveat omitted |
| Brian / false firing premise | HTTP 502 | 29.977 s | 7 | Writer output failed format checks |
| Survey plus exact weather | HTTP 200, partial | 26.900 s | 7 | Supported survey portion, correct user group; weather unavailable |
| Calculus with growth wording | HTTP 200, unsupported | 2.179 s | 1 | Correct scope block; no retrieval/writer calls |

## Quality and test interpretation

The completed passage audit of the later full-20 run found **five complete substantive passes, eight useful but flawed answers, four errors, one unanswered ambiguous-name request, and two correct controls**. The latest eight-case run has four substantive answers, one correct scope block, and three errors. Its detailed comparison audit was interrupted before being finalized; the saved Patrick/Teresa/interview audit is complete, and survey content was checked directly for this report. Do not present a complete independent accuracy score for the latest batch.

Backend automated verification: **595 passed, one failed**. The remaining failure is the existing essay skill test expecting the removed 1,250-word rule. It was neither suppressed nor changed as part of the Llama work. Temporary-directory setup errors were resolved. Automated unit checks verify behavior/contracts; they do not measure generated-answer accuracy.

Database revisions and all used source text stayed unchanged in the live runs. The later full-20 raw code hash changed only through LF-to-CRLF newlines; reconstructing those variants exactly reproduced the recorded hashes. The latest eight-case code hashes matched before/after. OpenAI service and frontend implementations were not changed by this work.

These reused regression sets and AI-assisted passage reviews show concrete fixes, but do not demonstrate a steady overall improvement or production accuracy. The pipeline is suitable for further supervised testing; consistent answer delivery and factual completeness remain unfinished.

## Detailed evidence

- [Baseline full-20 report](llama_full_rag_baseline_20_2026-10-08_report.md)
- [First focused-six report](llama_full_rag_fix1_selected6_2026-10-08_report.md)
- [Later full-20 report](llama_full_rag_fix2_final20_2026-10-08_report.md)
- [Latest eight-case raw results](llama_full_rag_fix3_selected8_2026-10-08.json)
- [Latest speaker/interview source audit](llama_full_rag_fix3_review_04_06.json)
- [Automated and live test ledger](llama_rag_improvement_test_ledger_2026-10-08.md)
