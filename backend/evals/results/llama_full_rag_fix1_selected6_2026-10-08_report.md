# Llama full RAG: patch 1 selected-six report

Test date: 8 October 2026. This report covers the first focused patch, before patch 2.

All **6/6 requests returned HTTP 200**, including the two questions that previously ended in errors. That is an availability result. Source review found **one fully passing substantive answer, two useful but flawed answers, two failed answers, and one correct scope block**. Returning an answer and resolving its citation IDs do not establish that its claims are supported.

| Case | Source-review result | What the test showed |
|---|---|---|
| rag-04: Patrick Campbell, failed payment cards | **Fail**; baseline: error | An answer now returns and stays on payment failures, but attributes Lenny's card-notification examples to Patrick. Relevant Patrick evidence was retrieved; speaker attribution remains wrong. |
| rag-05: Teresa Torres, leading interview questions | **Complete pass**; baseline: error | Gives grounded techniques: natural conversation, actual stories, “What happened next?”, and actual behavior instead of hypotheticals. The earlier overly literal evidence rejection is resolved in this case. |
| rag-06: customer interviews excluding Teresa | **Fail**; baseline: useful partial | Several recommendations are useful and Teresa is excluded, but podcast publication-review advice is presented as customer-research advice. It also invents an unrequested missing topic, loses Dalton's time-allocation qualification, and overstates a survey recommendation. |
| rag-17: Brian Chesky firing every PM | **Useful partial**; baseline: useful partial | Correctly rejects the firing premise and explains the role changes. The invented “opportunity to break free” phrase is removed, but Brian's qualified speculation about designers' motives is still stated as fact. |
| rag-18: Rahul Vohra's survey plus Mumbai weather | **Useful partial**; baseline: useful partial | Gives the survey question and three choices and correctly marks weather unavailable. Still omits the available 40% benchmark. New wording confuses the two user groups and contradicts the source about whose objections to address. |
| rag-20: calculus disguised as a growth experiment | **Unsupported pass**; baseline: unsupported pass | Correctly blocks the request after scope classification. No database retrieval, embedding, reranking, or answer-generation calls follow. |

The live test used the real workspace chat route and database, empty conversation history, and no supplied-source injection, mocks, or answer cache. The five answerable questions used parallel semantic and keyword searches, with the recorded OpenRouter/BGE-M3 filters applied in **5/5 cases**. BGE-M3 supplied embeddings, Voyage supplied reranking, Llama 3.1 8B supplied the substantive answers, and Qwen handled scope, evidence planning, and review. There were **no OpenAI calls** and **no reranking fallbacks**.

The batch recorded **43 provider calls**, **three upstream HTTP 429 responses**, and **$0.07959449 in reported usage cost**. All six requests ultimately completed. Median request time was **27.218 seconds**; the longest was **108.345 seconds**, for rag-06. These are measurements from this small selected batch, not a general speed or reliability estimate.

The source archive, used source text, episode revisions, index coverage, and tested code snapshot stayed unchanged during the run. Coverage remained **303 episodes and 22,086 chunks**. The test itself made no production changes. Patch 2 and any later tests are excluded from these findings.

Patch 1 improves completion of the previously failing requests, with a real quality improvement for rag-05. It does not establish a general grounding improvement: rag-04 publishes a misattribution, rag-06 introduces a context-transfer error, and rag-17/18 retain material flaws. These six reused regression questions and AI-assisted source reviews cannot establish an overall accuracy rate. Frontend behavior, automatic skill selection, essays, and artifacts were outside this test.

Evidence: [raw live run](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix1_selected6_2026-10-08.json), [source review of rag-04 to rag-06](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix1_review_04_06.json), and [source review of rag-17, rag-18, and rag-20](C:/Users/91990/OneDrive/Desktop/Lenny-Growth-Assistant/backend/evals/results/llama_full_rag_fix1_review_17_20.json).
