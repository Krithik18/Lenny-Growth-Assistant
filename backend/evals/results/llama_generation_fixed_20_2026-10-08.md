# Llama answer-generation evaluation: 20 questions

Run date: 2026-10-08. Model: `meta-llama/llama-3.1-8b-instruct` through the production OpenRouter answer provider.

## Method

Twenty unique questions used fixed transcript snapshots selected before the live run. Nineteen cases supplied evidence; one tested empty-evidence behavior. Scope routing, database search, query embeddings, retrieval, reranking, and RAG refinement were bypassed. The production prompt, output budget, JSON validation, and one validation-repair retry were retained. Production code was unchanged.

Review compared the final answer with the exact supplied passages and the predefined rubric: answer the requested question, support claims with the cited passages, preserve speaker attribution, distinguish missing evidence from available evidence, and follow requested format/language. Partial is useful content with a material omission or correctness problem; it is not a full pass. These are manual judgments by the coding assistant, not independently annotated benchmark scores.

## Results

- Full manual passes: **6/20** (five model answers plus the local empty-evidence control).
- Useful answers with material problems: **8/20**.
- Returned answers that failed substantive review: **4/20**.
- No returned answer after validation retries: **2/20** (`ProviderError`).
- Final schema/citation-ID-valid application responses: **18/20**. This is not a grounding score.
- 19 questions reached OpenRouter; 24 calls including retries. All returned the requested Llama model. No HTTP/API transport failures.
- Five questions required a retry; three recovered a valid response. Seven of 24 API responses were structurally rejected.
- Expected coverage labels matched in 9/20 cases; this metric does not establish claim support.
- OpenRouter-reported aggregate cost: $0.00122053.

## Main findings

1. Coverage logic remains unreliable. Marty and Julie answers state the requested facts, then say those same facts are missing. Crystal and Seth answers introduce missing topics the user never requested.
2. Mixed requests can erase supported information. The survey-plus-weather case discards the survey; the Rob-plus-Teresa case discards the supported Teresa half.
3. Valid citation IDs do not ensure correct citation support. Crystal cites the wrong passage for instrumentation; Bill cites the wrong passage for iterative review; April/Jake cites only April while including a Jake claim in the summary.
4. Speaker and topic distinctions can fail. Kim Scott recounts her leader treating Kim with care; the answer attributes this to Kim leading her own team. Patrick cancellation-flow advice is presented as failed-card recovery.
5. Instructions are inconsistently followed. The exact-quote case returns a paraphrase; the arithmetic case never computes 42%; the design-sprint and host-attribution cases fail JSON validation after retries.
6. There are clear successes: Bob churn reasoning, Melissa outcomes, Teresa actual behavior, Brian false-premise correction, and refusal to invent a weather forecast. The empty-evidence control also behaves correctly.

## Per-question review

| ID | Question | Final coverage | Review | Finding |
|---|---|---|---|---|
| gen-01 | According to Bob Moesta, why should a team interview people who stopped using its product? | complete | pass | Explains changed context, struggling moments, and reasons for switching. Some redundant context sections, but the central answer is supported. |
| gen-02 | Explain the two dimensions of Kim Scott's Radical Candor and how they work together. | complete | fail | Core framework is correct, but the final section attributes the caring/challenging leadership story to Kim Scott herself. S1 describes her leader caring for Kim and challenging Kim, not Kim treating her own team this way. |
| gen-03 | What does Crystal Widjaja mean by an actionable insight, and how is it different from an observed dashboard fact? | partial | partial | Useful distinction and example, but labels unrequested and already answered topics as missing. Instrumentation/hypothesis testing is in S2 but cited as S1. Also treats Lenny's dashboard question as a diagnostic sign rather than a question. |
| gen-04 | Summarize Melissa Perri's advice for judging outcomes instead of how many features a team ships. | complete | pass | Supported summary of business value, incentives, company goals, and stagnant metrics. Actual transcript speaker Melissa Perri is followed despite misleading episode metadata. |
| gen-05 | What practical approach does Patrick Campbell suggest for churn caused by failed credit cards? | partial | fail | Conflates voluntary cancellation questions with recovery from failed credit cards. Omits the supplied recommendation to build a payment-failure marketing funnel and instead presents nostalgia/offboarding questions as the failed-card solution. |
| gen-06 | According to Teresa Torres, why ask customers about what they actually did instead of what they might do? | complete | pass | Correctly explains why actual behavior is more reliable than hypothetical opinions. Story-collection claim cites S2, where it is explicitly stated; overlapping S1 supports the customer enjoyment point. |
| gen-07 | How does Marty Cagan distinguish a feature team from an empowered product team? | partial | partial | Correctly states roadmap/output versus problems to solve, but then lists the very same requested definitions and differences as missing. Recovered valid JSON after a retry. |
| gen-08 | A survey has 84 very disappointed respondents out of 200. How does that compare with the threshold Rahul Vohra discusses? | partial | partial | Recognizes the survey is above the 40% benchmark, but never computes 84/200 = 42% or the two-percentage-point difference. Invents a missing comparison involving the number of companies, which the question did not request. |
| gen-09 | Give one short exact quote from Brian Chesky distinguishing micromanagement from being in the details. | complete | partial | Grounded paraphrase of micromanagement versus detail awareness, but supplies no exact quote despite the explicit request for one. |
| gen-10 | Which three tactics does Julie Zhuo describe for making difficult feedback easier to receive? | partial | partial | Lists all three supported tactics, then incorrectly says the third is missing. Summary cites only S1 despite summarizing three source passages. Verbose quotations rather than a focused three-tactic answer. |
| gen-11 | What are the five stages of the design sprint described by Jake Knapp and John Zeratsky? | ProviderError | error | Both attempts rejected: first has empty summary citations for a partial answer; second uses invalid coverage value 'unsupport'. First attempt names all five stages but claims the stages are missing. ProviderError returned. |
| gen-12 | How does Bill Carr describe writing and improving a PR/FAQ before choosing what to build? | complete | partial | Useful iterative concentric-circle review and problem quantification. Omits the explicit who-is-the-customer / what-is-the-problem / what-is-the-solution writing structure. Summary cites S2 for iterative review, which is supported by S1. Valid JSON recovered on retry. |
| gen-13 | Réponds en français : comment Seth Godin conseille-t-il de choisir ses premiers clients ? | partial | partial | Responds in French with supported customer-selection criteria, but omits the smallest viable audience principle and marks unrequested examples/consequences as missing even though an example and consequence are present in S1. |
| gen-14 | Why did Brian Chesky fire all product managers at Airbnb? | complete | pass | Rejects the fired-all-PMs premise and describes reassignment, product marketing, and review changes. S2 supports reassignment; the clearest explicit denial is additionally in supplied S1 but was not cited. |
| gen-15 | Explain Rahul Vohra's product-market-fit survey and give tomorrow's exact weather in Pune. | unsupported | fail | Rejects the entire survey-and-weather question. The survey is explicitly explained in S1 and should have been preserved as a partial answer, with only the weather marked missing. |
| gen-16 | Compare Rob Fitzpatrick and Teresa Torres on interviewing customers about past actions. | unsupported | fail | Correctly avoids inventing Rob Fitzpatrick evidence, but discards supplied Teresa Torres advice instead of returning a partial answer and identifying the unavailable comparison side. |
| gen-17 | Compare April Dunford's competitive-alternative advice with Jake Knapp's advice about a differentiated customer promise. | partial | partial | Summary mentions both April and Jake, but sections cover only April. Labels Jake's supplied differentiated-promise passage as missing. Summary cites only S1, which does not support the Jake claim; S2 is unused. No April/Jake claim transfer observed in the final sections. |
| gen-18 | What payment-recovery approach does Patrick Campbell recommend, and what specific customer prompts does Lenny describe? | ProviderError | error | First attempt exceeds 1800 output tokens with repetitive explanations and malformed JSON. Retry uses a string instead of boolean false. ProviderError returned. Rejected content also confuses failed-card recovery with cancellation tactics and transfers Patrick's salvage/pause advice to Lenny. |
| gen-19 | What will tomorrow's exact temperature be in Pune? | unsupported | pass | Correctly returns unsupported for a weather question despite supplied business/feedback passages; no forecast invented. |
| gen-20 | What advice does an unavailable guest give about acquisition costs? | unsupported | pass | Correct empty-evidence response generated locally, with zero API calls. This validates application behavior rather than model quality. |

## Evidence and reproducibility

- [Raw API responses, final answers, and supplied sources](llama_generation_fixed_20_2026-10-08.json)
- [Structured manual review and counts](llama_generation_fixed_20_2026-10-08_review.json)
- [Frozen questions and transcript snapshots](../answer_generation_fixed_sources_20.json)
- [Live generation-only runner](../answer_generation_live_20.py)

Fixture SHA-256: `b61c1baad38de2265aa7a2ff8a7bb6d91c0b0d51b478b89dd859aaa2114a2e1a`.

Verified: 20 unique completed cases, unchanged fixture hash, all model IDs and API success flags, and replay of validation reproducing every API-backed final answer. A rerun must use a fresh output path so these results remain preserved.

This is one generation-only run on reused archive topics with newly framed questions and finite fixed evidence. It does not measure end-to-end retrieval quality, production RAG refinement, repeat-run stability, or independently rated model accuracy. Some snapshot metadata is inconsistent with the transcript speaker, and some passages begin mid-turn; judgments use the actual text where available. The failures here occurred even when the needed passages were supplied.
