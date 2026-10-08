# Llama full RAG: patch 2, 20-question report

Test date: 8 October 2026, 16:03–16:21 IST. This report covers patch 2. Patch 3 was applied after this run finished and is excluded.

**16/20 requests returned HTTP 200; four returned HTTP 502.** Of the **13 published substantive answers**, source review found **five complete passes and eight useful but flawed answers**. Two unsupported controls correctly stopped. One additional request, the ambiguous first name “Naomi,” returned no answer and failed to explain the ambiguity. HTTP success measures availability, not source support or completeness.

| Source-review outcome | Count |
|---|---:|
| Complete substantive pass | 5 |
| Useful partial answer | 8 |
| Unanswered identity ambiguity | 1 |
| Correct unsupported control | 2 |
| Request error | 4 |

The application's labels were **11 complete, two partial, and three unsupported**. These differ from the source-review grades because a complete label and valid citation IDs do not show that every claim is supported or every required detail is present.

| Case | Source-review result | Main finding |
|---|---|---|
| rag-01: Bob Moesta, switching | **Complete pass** | Correctly connects changed circumstances and struggle to the push away and pull toward a new outcome. |
| rag-02: Kim Scott, care and challenge | **Useful partial** | Preserves the actors and feedback principles, but incorrectly calls an available mindset explanation missing. |
| rag-03: Melissa Perri, outcomes | **Useful partial** | Explains business value and goals but omits checking whether customer/business metrics actually move. |
| rag-04: Patrick Campbell, failed cards | **Error** | Relevant recovery evidence is available; incomplete speaker recovery and inconsistent review prevent publication. |
| rag-05: Teresa Torres, interview questions | **Error** | Story/timeline evidence is available, but drafting and review do not resolve the user's leading-question wording faithfully. |
| rag-06: interviews excluding Teresa | **Useful partial** | Removes patch 1's podcast-context contamination and false guest gaps; still omits qualifications and promised practical detail. |
| rag-07: April Dunford, alternatives | **Complete pass** | Correctly explains the customer's alternative, including status quo and short-listed competitors. |
| rag-08: Rumelt, strategy versus goals | **Useful partial** | Says goals are not strategy but omits the available explanation of diagnosis and coherent concrete actions. |
| rag-09: “Naomi,” pricing | **Fail: needs clarification** | Safely avoids choosing between Naomi Ionita and Naomi Gleit, but gives no ambiguity explanation or full-name clarification request. |
| rag-10: Knapp/Zeratsky, design sprint | **Complete pass** | Supports the prototype/testing loop and collective attribution; particular experiment details could be labeled as an example. |
| rag-11: Bill Carr, working backwards | **Useful partial** | Gives PR/FAQ drafting and review, but omits customer/problem/solution substance and the condition on CEO review. |
| rag-12: Ellis/Vohra comparison | **Error** | Both guests' evidence is present; draft conflation, answer-count retries, and some inaccurate review feedback end in timeout. |
| rag-13: 84 out of 200 | **Error** | Correct benchmark is available, but the plan and repairs fail to preserve 42% and the two-percentage-point comparison. |
| rag-14: exact Brian Chesky quote | **Complete pass** | Quote is verbatim in Brian's cited speech. |
| rag-15: useful dashboard metrics | **Complete pass** | Supported advice connects context, diagnosis, instrumentation, and trusted metrics with improvement decisions. |
| rag-16: first customers, in French | **Useful partial** | French advice is useful, but invents company-values matching and a design-partner selection criterion. |
| rag-17: Brian firing every PM | **Useful partial** | Correctly rejects the premise and explains changes; still states Brian's speculative designers' motive as fact. |
| rag-18: survey plus weather | **Useful partial** | Now includes the survey, choices, and 40% context; still reverses/confuses the user groups whose objections should be addressed. Weather is correctly unavailable. |
| rag-19: unknown named person | **Unsupported pass** | One permitted catalog identity check; no transcript retrieval, embeddings, reranking, or writer calls. |
| rag-20: disguised calculus | **Unsupported pass** | Only scope classification; zero database queries or retrieval/generation stages. |

The four errors are **rag-04, rag-05, rag-12, and rag-13**. All had relevant evidence available. They therefore identify delivery, planning, attribution, and review problems rather than an absence of archive evidence. Brief upstream rate limits increased attempts, but the traces for rag-12/13 show successful same-model fallbacks; the rate limits alone do not explain their failures. The longest request was rag-02, which ultimately returned a partial answer.

The live run used the actual workspace chat route and database, empty history, and no supplied-source injection, mocks, or answer cache. All **19 recorded hybrid retrievals** ran semantic and keyword searches in parallel with the OpenRouter/BGE-M3 filters. The pipeline used BGE-M3 embeddings, Voyage reranking, Llama 3.1 8B writing, and Qwen scope/planning/review. There were **zero OpenAI calls and zero reranking fallbacks**.

Runtime: **175 provider calls**, **21 upstream HTTP 429 responses**, **$0.3183506 in reported usage cost**, **36.517 seconds median request time**, and **224.573 seconds maximum**. These are observations from this run; they do not establish general speed or reliability.

The archive, database episode revisions, and text of **188 used chunks** stayed unchanged. Index coverage remained **303 episodes and 22,086 chunks**. The raw `code_unchanged` flag is **false**: `openrouter_provider.py` changed from LF to CRLF newline formatting. Follow-up verification found its content hash unchanged after newline normalization, and the other 17 monitored file hashes matched. Thus source content was preserved, but byte-for-byte code equality must not be claimed. Patch 3 was applied after the completed postflight.

There are also unresolved source-card metadata problems: Kim Scott passages display a Scott Wu episode title, and some Melissa Perri passages display a Melissa Tan title. The content audits use the actual transcript speakers; the misleading displayed titles remain a separate reference-quality issue.

Patch 2 shows targeted gains: rag-06 removes the earlier context-transfer error, and rag-18 includes the missing 40% benchmark. It also returns four errors, including rag-04/05, which returned answers under patch 1. The remaining partial answers and review inconsistencies mean this run does not demonstrate a general grounding improvement. These reused regression questions and AI-assisted reviews are not an independent human benchmark or an overall accuracy estimate. Frontend behavior, automatic skill selection, essays, and artifacts were outside this test.

Evidence: [raw live run](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix2_final20_2026-10-08.json), [review of rag-01 to rag-07](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix2_review_01_07.json), [review of rag-08 to rag-14](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix2_review_08_14.json), and [review of rag-15 to rag-20](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix2_review_15_20.json).
