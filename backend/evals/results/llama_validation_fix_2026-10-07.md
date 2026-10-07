# Llama validation fix regression — 7 October 2026

The OpenRouter answer provider now supplies explicit coverage/citation rules, a JSON example, guest metadata, and one regeneration attempt with sanitized validation feedback. It retains strict types and all existing citation and coverage checks. Refusals and transport errors do not trigger regeneration. OpenAI code is unchanged.

## Verification

127 selected unit and integration tests passed, including both workspace providers and the OpenAI provider. The patch also passes the whitespace check.

Live tests used the real workspace route through ASGI transport, the live database, OpenRouter BGE-M3 embeddings, Voyage reranking, and `meta-llama/llama-3.1-8b-instruct`. Both indexes covered the same 22,086 chunks across 303 episodes. These are small regression samples, not a new full evaluation or a controlled quality benchmark.

| Question | Original evaluation | First fix | Final prompt revision |
| --- | --- | --- | --- |
| Activation plan | HTTP 502 | HTTP 200, partial | Not rerun |
| April Dunford positioning | HTTP 502 | HTTP 502 | HTTP 200, complete |
| Brian Chesky false premise | HTTP 502 | HTTP 200, partial | HTTP 200, partial |
| Rahul Vohra survey + Mumbai weather | HTTP 200, unsupported | HTTP 200, partial | HTTP 200, partial |

All three final-revision responses passed the structural checks, their citations resolved, and their retrieval traces used provider `openrouter`. Positioning succeeded without regeneration. The false-premise case used the regeneration attempt; a later optional refinement failed validation, and the existing service correctly preserved the valid initial answer. The weather case also exercised existing reranker error handling during refinement.

## Remaining quality limits

Passing these checks proves JSON consistency and citation-ID validity, not that a cited passage supports every claim. The final positioning answer still attributes statements from Krithika Shankarraman and Varun Parmar passages to April Dunford. The first-fix survey answer also added an unrelated switch-lock section. Guest metadata and attribution instructions did not reliably prevent those errors.

The false-premise answer now explicitly rejects the claim that Brian Chesky fired every product manager and cites his explanation of the changed function. Partial coverage preserves an evidence-based answer while identifying the unanswered aspect. The survey/weather case no longer discards the supported portion merely because weather is unavailable.

This patch improves validation reliability; it does not establish production-level grounding quality for Llama 3.1 8B. A stronger-model comparison or an independently evaluated claim-support verification stage is the next step before calling its answer quality equivalent to OpenAI.

Raw traces: `llama_repair_regression_2026-10-07.json` and `llama_repair_regression_v2_2026-10-07.json`. The original ten-question-per-provider evaluation is preserved.
