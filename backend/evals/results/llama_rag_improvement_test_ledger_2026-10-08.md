# Llama RAG improvement: test ledger

Date: 8 October 2026. Work was limited to the OpenRouter answer provider and its regression tests. No OpenAI service or frontend implementation was changed by this patch.

## Automated checks

| Run | Result | Interpretation/action |
|---|---|---|
| Initial focused check in the restricted environment | Interrupted; no completed test results | Python/test startup stalled. Repeated with the approved runtime. |
| Patch 1 focused provider/service/evidence checks | 137 passed, 1 failed | New explicit-host test exposed a guard that skipped filtering when Lenny was the requested speaker. Corrected the guard. |
| Patch 1 focused rerun | 138 passed | The provider, service, and new evidence-focus cases passed. |
| Patch 1 full backend suite | 556 passed, 1 failed, 5 setup errors | Five temporary-folder permission errors; the failure was an existing essay test expecting the removed 1,250-word rule. |
| Patch 1 full suite with nested workspace temporary path | 556 passed, 1 failed, 5 setup errors | The temporary path's parent did not exist. No new application failures. |
| The five setup-affected tests with a fresh temporary folder directly in the backend workspace | 5 passed | Temporary-folder setup resolved. |
| Patch 2 full backend suite | 583 passed, 1 failed, no setup errors | Includes 21 overlap-speaker cases and a task-preservation case. The sole failure is the same unrelated essay-length assertion in `test_skill_routing.py`. It was not suppressed or changed. |
| Patch 3 full backend suite | 595 passed, 1 failed, no setup errors | Includes overlap-chain propagation, ambiguous/cyclic paths, explicit-turn resets, and generic-topic speaker filtering. The sole failure remains the unrelated essay-length assertion. |

Changed tracked provider/test files passed whitespace validation. A repository-wide whitespace check also reported concurrent README whitespace; this patch did not edit that file.

## Live RAG checks

All live batches use the existing 20-question regression fixture, the real workspace chat route, empty history, the stored database sources, and real provider calls. These are integration/regression measurements with AI-assisted passage reviews, not an independently annotated accuracy benchmark. Cost figures are reported API usage, not a billing guarantee.

1. **Full 20 baseline:** 18 HTTP 200 responses and two answer-generation errors. Runtime labels: 13 complete, two partial, three unsupported. The unsupported group includes two correct controls and one unresolved ambiguous first name. See [baseline report](llama_full_rag_baseline_20_2026-10-08_report.md).
2. **Patch 1 selected six:** all six HTTP 200; passage review found one complete substantive pass, two useful but flawed answers, two failures, and one correct scope block. Improvements in availability did not resolve all grounding errors. See [selected-six report](llama_full_rag_fix1_selected6_2026-10-08_report.md).
3. **Patch 2 full 20:** 16 HTTP 200 and four generation errors. Thirteen substantive answers, two correct controls, and one unresolved ambiguous name. Passage review: five complete substantive passes, eight useful/flawed partials, four errors, one unanswered ambiguous-name request, and two correct controls. This batch did not improve overall reliability over the baseline. See [full-20 report](llama_full_rag_fix2_final20_2026-10-08_report.md). The raw code fingerprint changed solely because the provider file's LF newlines became CRLF; reconstructing both variants exactly matched the before/after hashes. All other code hashes and used source text remained unchanged.
4. **Patch 3 selected eight:** completed: five HTTP 200 responses and three errors. Four substantive answers and one correct scope block. Patrick's source attribution passes; comparison/calculation return again but retain precision/completeness limits; survey/weather now targets the correct user group. Teresa remains a semantic-review failure, broad interviews hit a planning timeout, and the false-premise case fails writer-format validation. Median 28.438 seconds, maximum 82.617 seconds, 54 recorded API calls, five upstream 429 responses, $0.08264596 reported cost. All seven hybrid rounds were parallel and filtered correctly; no OpenAI calls or reranking fallback; source text and code hashes stayed unchanged. This is a separate targeted test of the latest patch, not a new full-20 result. See [current status report](llama_rag_status_2026-10-08.md).

## Focused changes

- Preserve the user's requested tasks, rather than creating gaps for every retrieved guest.
- Filter explicitly different speakers from a single-person answer task while preserving comparisons and actual host requests.
- Recover an opening speaker only from exact matching overlapping text with matching episode and revision IDs, valid character spans, and an unambiguous explicit label. Preserve unknown attribution when those conditions fail.
- Carry proven opening labels through continuous overlap chains; conflicting labels and unseeded cycles stay unknown. Filter explicit wrong-speaker evidence even when the planner uses a generic heading for a named-person request.
- Keep useful episode-level advice when a multi-guest passage does not identify an individual; preserve the requested topic and do not guess a voice.
- Repair rejected answers using specifically identified evidence instead of adding whole mixed-topic chunks.
- Reinforce faithful paraphrases, source qualifications, actual framework criteria, subgroup distinctions, and the setting where advice applies.
- Keep requested count calculations and benchmark comparisons in the plan, and distinguish a source's actual rationale from a causal explanation implied by the question.

Qwen still handles scope, planning, and grounding review; Llama 3.1 8B writes the answer. No stronger writer was substituted. Semantic and keyword retrieval, BGE-M3 provider filtering, and Voyage reranking remain the existing OpenRouter path.
