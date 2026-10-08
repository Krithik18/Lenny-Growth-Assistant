# Test 1: complete Llama RAG baseline

8 October 2026. Production code was unchanged throughout this test.

The real workspace chat route received 20 requests selecting OpenRouter. Each applicable request used scope checking, stored BGE-M3 query retrieval, concurrent semantic/keyword searches, Voyage reranking, Llama generation with Qwen planning/review, and the existing optional refinement flow. No frozen passages were injected. Frontend, automatic skill selection, essays and artifacts were outside this chat-RAG test.

## Results

| Application outcome | Questions |
| --- | ---: |
| Answer marked complete | 13 |
| Answer marked partial | 2 |
| Correct unsupported controls | 2 |
| Ambiguous first-name request declined | 1 |
| Generation error, HTTP 502 | 2 |

18/20 requests returned valid results. Fifteen returned substantive answers. These are availability and application coverage counts, not an independently measured accuracy rate. The Naomi request was declined because the archive contains both Naomi Gleit and Naomi Ionita; it was not an out-of-domain control.

Source audit covers all 20 cases: ten complete content passes, five useful but flawed or incomplete answers, two correct unsupported controls, two errors and one unanswered ambiguous-identity request. These totals were checked against all three source-review files. One useful answer included an unsupported motive, so the partial grades must not be interpreted as all claims being supported. The ambiguous Naomi request was safely blocked, but did not answer the intended relevant pricing question or explain that a full name was needed.

## Per-question record

| ID | Question topic | Outcome | Seconds |
| --- | --- | --- | ---: |
| 01 | Bob Moesta: struggling moments and switching | Complete; content pass | 24.6 |
| 02 | Kim Scott: care and direct challenge | Complete; content pass, wrong stored episode title | 104.1 |
| 03 | Melissa Perri: outcomes versus features | Complete; content pass | 16.9 |
| 04 | Patrick Campbel typo: failed cards | Error; relevant evidence was available | 37.0 |
| 05 | Teressa Tores typo: interview questions | Error; possible over-strict reviewer | 40.4 |
| 06 | Customer interviews excluding Teresa | Partial; useful advice plus unrequested gaps | 138.1 |
| 07 | Apryl Dunfrd typo: competitive alternatives | Complete; content pass, duplicate source provenance | 68.1 |
| 08 | Rumelt surname: strategy versus goals | Complete; content pass, diagnosis and actions supported | 58.1 |
| 09 | Naomi first name: value-metric pricing | Unsupported; safe ambiguous-name block, relevant question unanswered | 1.6 |
| 10 | Jake and John: design sprint | Complete; content pass, prototype/testing loop supported | 32.5 |
| 11 | Bill Carr: working backwards | Complete label; useful but omits customer/problem framing and FAQ substance | 23.6 |
| 12 | Sean Ellis versus Rahul Vohra: PMF | Complete; content pass, shared survey and benchmark supported; empirical qualifier softened | 38.4 |
| 13 | 84/200 versus the PMF benchmark | Complete label; 42% correct, two-percentage-point margin and benchmark caveat omitted | 34.9 |
| 14 | Exact Brian Chesky quote | Complete; verbatim quote from Brian's explicitly labeled speech | 45.5 |
| 15 | Making dashboard numbers useful | Complete; content pass | 58.9 |
| 16 | First customers, French question | Complete; content pass | 51.1 |
| 17 | Brian fired every PM: false premise | Complete label; useful answer with unsupported designers' motive | 34.5 |
| 18 | PMF survey plus weather | Partial; weather correctly unavailable, 40% benchmark omitted | 28.4 |
| 19 | Unknown Marissa Exampleworth | Correct unsupported control | 3.6 |
| 20 | Calculus disguised as growth experiment | Correct unsupported control | 2.2 |

## Stage checks

- All 22,086 active chunks across 303 episodes had compatible OpenRouter embeddings before and after testing.
- All 21 hybrid search rounds showed overlapping semantic/keyword query intervals on separate connections. Chunk queries consistently filtered OpenRouter BGE-M3 embeddings.
- All 21 Voyage reranking rounds returned usable rankings; no reranker fallback occurred. This does not prove perfect relevance ranking.
- Writer responses identified Llama 3.1 8B. Qwen handled scope, evidence planning and review. No OpenAI API calls occurred.
- All returned citation IDs resolved. All 20 outcomes received a separate source audit; citation resolution and application coverage labels did not establish complete claim support.
- Active revisions, 197 used chunk texts and relevant source-code hashes matched the end-of-run checks.

## Main problems identified

1. Patrick's drafts mixed the host's expiring-card messages and voluntary-cancellation tactics with the guest's failed-card advice. Relevant evidence was already present.
2. Teresa's drafts included supported story/timeline techniques but were rejected repeatedly because descriptive labels were not literal transcript words. Review strictness appears excessive in this case.
3. The customer-interview request acquired unrequested Jessica Livingston and Matt Abrahams gaps, which triggered irrelevant refinement searches and inflated latency.
4. Mixed sources and expanding whole cited chunks during repair can reintroduce peripheral material. Some stored episode titles/provenance remain misleading.
5. The Brian false-premise answer adds an unsupported designers' motive; the survey/weather answer omits the available benchmark.
6. The working-backwards answer gives the press-release and iterative review sequence but leaves out the available customer/problem/solution framing and FAQ substance. Its complete label overstates the process coverage.
7. The arithmetic answer calculates 42% correctly but omits the two-percentage-point comparison and the source's empirical qualification. The PMF comparison is supported, although its growth statement should preserve “almost always” and could explain the guests' different uses of feedback more fully.
8. The first-name Naomi request needs a full-name clarification because both Naomi Gleit and Naomi Ionita are indexed. Safe identity handling currently yields a generic no-evidence response rather than explaining the ambiguity.

Median request time was 36.0 seconds; the slowest was 138.1 seconds. There were 180 application API calls and 14 upstream HTTP 429 responses. Successful same-model fallback helped complete requests. Returned usage reported about $0.36; this is not a complete billing guarantee.

This is a reused regression/integration set and an AI-assisted audit, not an independent generalization benchmark. Focused improvements are being made only after recording this baseline.

## Evidence

- [Full live trace](llama_full_rag_baseline_20_2026-10-08.json)
- [Source audit 01–07](llama_full_rag_baseline_review_01_07.json)
- [Source audit 08–14](llama_full_rag_baseline_review_08_14.json)
- [Source audit 15–20](llama_full_rag_baseline_review_15_20.json)
