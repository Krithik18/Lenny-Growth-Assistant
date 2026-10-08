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

Changed tracked provider/test files passed whitespace validation. A repository-wide whitespace check also reported concurrent README whitespace; this patch did not edit that file.

## Live RAG checks

All live batches use the existing 20-question regression fixture, the real workspace chat route, empty history, the stored database sources, and real provider calls. These are integration/regression measurements with AI-assisted passage reviews, not an independently annotated accuracy benchmark. Cost figures are reported API usage, not a billing guarantee.

1. **Full 20 baseline:** 18 HTTP 200 responses and two answer-generation errors. Runtime labels: 13 complete, two partial, three unsupported. The unsupported group includes two correct controls and one unresolved ambiguous first name. See [baseline report](llama_full_rag_baseline_20_2026-10-08_report.md).
2. **Patch 1 selected six:** all six HTTP 200; passage review found one complete substantive pass, two useful but flawed answers, two failures, and one correct scope block. Improvements in availability did not resolve all grounding errors. See [selected-six report](llama_full_rag_fix1_selected6_2026-10-08_report.md).
3. **Patch 2 final 20:** running at ledger creation. Results and source-review findings will be recorded in the final report, without treating successful JSON/citation validation as claim-support proof.

## Focused changes

- Preserve the user's requested tasks, rather than creating gaps for every retrieved guest.
- Filter explicitly different speakers from a single-person answer task while preserving comparisons and actual host requests.
- Recover an opening speaker only from exact matching overlapping text with matching episode and revision IDs, valid character spans, and an unambiguous explicit label. Preserve unknown attribution when those conditions fail.
- Keep useful episode-level advice when a multi-guest passage does not identify an individual; preserve the requested topic and do not guess a voice.
- Repair rejected answers using specifically identified evidence instead of adding whole mixed-topic chunks.
- Reinforce faithful paraphrases, source qualifications, actual framework criteria, subgroup distinctions, and the setting where advice applies.

Qwen still handles scope, planning, and grounding review; Llama 3.1 8B writes the answer. No stronger writer was substituted. Semantic and keyword retrieval, BGE-M3 provider filtering, and Voyage reranking remain the existing OpenRouter path.
