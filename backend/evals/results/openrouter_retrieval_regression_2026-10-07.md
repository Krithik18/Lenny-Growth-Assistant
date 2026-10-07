# OpenRouter retrieval regression — 7 October 2026

Six questions were run through the original and revised OpenRouter retrieval pipelines against the live archive, using real BGE-M3 embeddings and Voyage reranking. All 12 runs completed. No answers were generated, no OpenAI calls were made, and no database content was changed.

## Changes

- Resolve full guest names and unambiguous surnames against active archive metadata. Recognize episode variants such as April Dunford 2.0. Unknown or ambiguous names do not acquire an invented identity filter.
- For a recognized person, constrain semantic, keyword, and neighboring-chunk queries to their episodes or passages explicitly mentioning their full name. This preserves useful compilation excerpts and third-party references. An empty scoped result does not silently broaden to unrelated people.
- Keep short keywords and numbers. Remove conversational filler and recognized names from topic keywords. Reward all-topic matches and explicitly quoted phrases, while retaining broader keyword and semantic candidates.
- Use reciprocal-rank fusion for candidate ordering, including the fallback if reranking fails.
- Send episode title and guest metadata with unchanged transcript text to the reranker.
- For comparisons naming two to four known people, retrieve candidates for each. Preserve one best-ranked direct-guest passage per recognized person near the beginning of the final context order.

The shared retrieval improvements are opt-in through `query_aware`; only the OpenRouter entry point enables them. The OpenAI service and its default retrieval policy are unchanged.

## Observed retrieval results

The table counts passages in the actual 4,000-token answer context that were neither from a requested guest's episode nor explicitly mentioned a requested person's full name. This is an identity-scope check, not a claim-support or overall answer-accuracy score.

| Question | Outside person scope before | After | Evidence observed |
| --- | ---: | ---: | --- |
| April Dunford: competitive alternatives | 2 / 12 | 0 / 13 | Removed Krithika Shankarraman and Varun Parmar passages; retained April's explanation in a compilation and her own episodes. |
| Rahul Vohra: 40 percent survey threshold | 9 / 12 | 0 / 12 | First passage now contains Rahul's survey responses and explanation of the 40 percent observation. |
| Sean Ellis versus Rahul Vohra | 1 / 12 | 0 / 12 | First two passages now cover Rahul and Sean; previously the top five lacked Sean's own episode. |
| Brian Chesky: false premise about PMs | 2 / 12 | 0 / 13 | Context remains focused on Brian and explicit references to him. |
| Ronny Kohavi: misleading experiment results | 0 / 11 | 0 / 11 | Retained Ronny's own passages. |
| General onboarding activation plan | Not person-scoped | Not person-scoped | Preserved multiple relevant guests, including Sean Ellis and Lauryn Isford. |

The revised runs took 10–39 seconds in this sample. Timing is descriptive only: this small paired run does not control database warmth or upstream API variability.

## Limits

Person scope is useful evidence filtering, not proof of speaker attribution. A passage mentioning someone can contain another speaker's interpretation, and a single episode can have multiple speakers. Broad questions, unknown names, ambiguous first names, and semantic nuances still depend on retrieval and reranking quality. The current keyword configuration uses English stemming. A quoted phrase receives a ranking boost, not an exact-match-only restriction. The independent answer-grounding problem remains to be evaluated separately.

Raw passages and selected answer contexts are saved in `openrouter_retrieval_regression_2026-10-07.json`. Run new paid evaluations with a fresh output path; the script refuses to overwrite this evidence.
