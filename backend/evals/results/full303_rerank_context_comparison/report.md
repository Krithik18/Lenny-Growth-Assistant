# Full 303-transcript audit and context-budget comparison

Started: 2026-10-07T13:31:30.582523+05:30 (India time).

## Main findings

- Completed all 303 questions at all three budgets: 909 evaluated answers, with reranking enabled.
- Comparable answer completeness: 2,000 tokens = 78.8%; 4,000 tokens = 81.8%; 6,000 tokens = 81.1%.
- Complete, grounded, and addresses the question: 2,000 tokens = 75.8%; 4,000 tokens = 78.5%; 6,000 tokens = 78.1%.
- The highest observed completeness was at 4,000 tokens, 3.0 percentage points above 2,000. Automated judgments are advisory.
- Exact source evidence reached the returned top 20 for 87.1% of questions. More context cannot restore evidence absent from these results.
- Reranking fell back in 49/303 cases; missing details also occurred when evidence was already in context.
- Application defaults remain unchanged. Review evidence selection, ranking failures, and generation omissions before choosing a new default.

## Scope and configuration

- One source-derived question for each of all 303 transcript files; 909 initial answers across three budgets.
- Live index checked: 303 episodes, 22,086 chunks, and 22,086 compatible embeddings.
- All reference anchors and excerpts verified against the approved ZIP before testing.
- Reranking enabled; semantic and keyword SQL searches execute concurrently on separate connections.
- GPT-6 Luna generates, reranks, and judges; text-embedding-3-small uses 1,536 dimensions.
- Retrieve/rerank once per question, then reuse the same returned top 20 for 2,000/4,000/6,000-token contexts.
- Initial answers only: missing-topic refinement is disabled for this controlled comparison. The application default is not changed by this audit.
- Four question jobs run concurrently; three budgets per question run concurrently. Timings are under this development workload.

[All 303 test questions](questions.md) · [Original source-derived reference labels and excerpts](reference_cases.json)

## What is working

The complete approved collection is searchable, and every test question's reference anchor exists in its source. Search and reranking preserve source IDs and original text; the answering provider validates citation IDs. That citation validation checks identity, not whether every claim is semantically supported.

Expected exact evidence appeared in the first five results for **83.8%** of questions and in the first 20 for **87.1%**. Alternative valid passages can still answer a question when the exact anchor is absent.

## Context-budget results

| Metric | 2,000 tokens | 4,000 tokens | 6,000 tokens |
|---|---:|---:|---:|
| Completed questions | 303/303 | 303/303 | 303/303 |
| Exact evidence in supplied context | 84.2% | 86.8% | 87.1% |
| All expected points covered (per-budget judge) | 78.8% | 81.8% | 81.1% |
| Claims grounded in cited evidence | 95.0% | 95.4% | 95.7% |
| Addresses the question | 93.1% | 93.1% | 93.7% |
| Appropriate evidence limits | 96.7% | 95.4% | 97.0% |
| Median answer generation | 5.11 s | 5.12 s | 5.31 s |
| Median retrieval + initial answer | 20.95 s | 20.56 s | 21.11 s |
| Silent reference-point omissions | 53 | 45 | 50 |
| Completeness using the same valid reference points | 78.8% | 81.8% | 81.1% |
| Complete, grounded, and addresses the question | 75.8% | 78.5% | 78.1% |

Completeness measures all source-supported reference points; it is stricter than the model's own coverage flag. The comparable completeness row uses 302 questions with at least one reference point supported by the judges at every budget, applying that same point set to all budgets. Silent omissions mean the answer marked itself complete while the judge identified missing reference details; not every such detail necessarily represents a separate requested subquestion.

### Paired improvements and regressions

| Larger budget versus 2,000 | Became complete | Became incomplete | Complete at both | Incomplete at both |
|---|---:|---:|---:|---:|
| 4,000 | 15 | 6 | 232 | 49 |
| 6,000 | 12 | 5 | 233 | 52 |

### Completeness by reranking outcome

| Ranking outcome | Comparable questions | 2,000 tokens | 4,000 tokens | 6,000 tokens |
|---|---:|---:|---:|---:|
| successful reranking | 253 | 81.8% | 84.2% | 82.2% |
| reranking fallback | 49 | 63.3% | 69.4% | 75.5% |

These are different sets of questions, so their rates are diagnostic; they do not establish the causal benefit of reranking.

The paired results show individual changes, not just averages. Model output and judging can vary; a larger budget is not guaranteed to improve every answer.

A reviewed example is [Asha Sharma's planning question](asha-sharma.json): the 2,000-token context excluded the passage describing quarterly OKRs and four-to-six-week squad goals, and the answer flagged those details as unavailable. The 4,000-token context included that passage and the answer covered them. This is a context-selection improvement; the underlying retrieval was identical. Its reranking response was invalid and the service used candidate order, so it also illustrates the need to repair evidence ordering before relying on larger contexts to compensate.

## What went wrong

Each omitted expected point is assigned to the earliest observed failure stage. Counts below are points, not unique questions, and the same question can have several failure types.

| Failure stage | 2,000 tokens | 4,000 tokens | 6,000 tokens |
|---|---:|---:|---:|
| Supported in source, absent from returned top 20 | 63 | 57 | 59 |
| In top 20, excluded from supplied context | 18 | 11 | 4 |
| Available in context, omitted from answer | 21 | 19 | 23 |
| Synthetic reference point not supported by reference excerpt | 2 | 2 | 2 |

Reranking fell back to candidate order in **49 / 303 cases**. Timeouts and invalid ranking responses are preserved in the per-case trace. Keeping reranking enabled does not mean every call succeeded.

Failed stages were retried in **10 cases**, reusing successful answers and retrieval. Incomplete evaluator responses were retried with a 4,000-token evaluator output limit; the application answer output limit stayed at 1,800 tokens. These operational failures are not counted as evidence gaps.

Recorded budget-stage errors before the final retry pass: ProviderError: 9, RuntimeError: 4. ProviderError can indicate a provider request failure or an answer validation failure; the request traces identify the affected stage. RuntimeError generally records an incomplete evaluation response. Earlier interrupted attempts remain in their original result directories; provider traces are retained in the recovered cases.

### Evidence gaps and response wording

These source-derived questions deliberately have evidence in the approved archive. A retrieval or context gap must not be described as proof that the information is absent from all transcripts. Appropriate response wording is 'I could not find support for this detail in the retrieved evidence,' while answering the supported parts. Existing partial/unsupported flags and missing_topics are checked, but the current assistant can miss a gap and incorrectly label an incomplete answer complete. This audit measures that behavior before remediation.

Genuine corpus-wide absence is not established by these tests. Verifying that would require separate questions and a broader source investigation; no absence claim is inferred from a search miss.

### Representative cases to inspect

**Supported in source, absent from returned top 20:**

- [alexander-embiricos](alexander-embiricos.json): The reference explicitly says that, if he could choose one core competency, Embiricos would choose a meaningful understanding of the problems a certain customer has. The retrieved passages discuss identifying a problem or understanding workflows, but do not establish the specific-customer understanding in this point. The provided context likewise does not support that specific advice, and the answer does not state it. The reference says that a strong understanding and network of customers currently underserved by AI tools would set a new company up well. No retrieved passage or passage in the provided context supports this combined point, and the answer does not state it.
- [andrew-wilkinson](andrew-wilkinson.json): The reference supports that building agents was limited to people like Wilkinson with the time and skill to build them. The returned Wilkinson passages show him building workflows himself, but do not establish the time-and-technical-skill limitation; the passages that mention coding skills concern another guest. The provided context likewise lacks this point, and the answer omits it. The reference describes Wilkinson’s envisioned ChatGPT interface asking a business user questions and setting up an agent. No returned passage or provided-context passage supports that future accessible interface, and the answer does not state it.
- [anneka-gupta](anneka-gupta.json): The reference supports being direct, giving examples, and tailoring feedback to the person’s goals. The retrieved Anneka passages and provided context support directness and examples, but do not include her advice to ask about the person’s career goals and tailor the feedback accordingly. The answer covers directness and examples but omits that goal-tailoring element.
- [austin-hay](austin-hay.json): The reference supports the example: spending $2,000 and two days on SSO to prevent a security problem such as someone downloading user data. No top-20 passage or provided-context passage gives that SSO example or its details. The answer instead discusses reviewing SaaS costs and terms as usage scales; it omits the requested example and therefore does not cover the point.

**In top 20, excluded from supplied context:**

- [adam-grenier](adam-grenier.json): The reference and a retrieved passage support looking for established channels that are newly becoming scalable. That passage is not in provided_context, and the answer does not state this criterion. The reference and a retrieved passage support considering existing channels that introduce something brand new. This detail is absent from provided_context and the answer. The reference and a retrieved passage say brand-new channels rarely work or are worth the hoped-for effort early on. This is not present in provided_context and the answer omits it.
- [asha-sharma](asha-sharma.json): The reference and a retrieved passage support aligning around the current AI season, customer problems, what winning means, and a north-star metric. The provided context only mentions the sequence of seasons, not the other alignment elements, and the answer does not state the full point. The reference and a retrieved passage describe loose quarterly OKRs and squad goals set in four-to-six-week increments. Neither the provided context nor the answer includes this cadence. The reference and a retrieved passage say they leave slack in the system and stay open to changes. That detail is absent from the provided context and answer.
- [benjamin-lauzier](benjamin-lauzier.json): The reference and a retrieved passage say Lyft used driver ETAs, with an ETA of two minutes or less associated with riders being likely to book. That detail is absent from the provided context and the answer. The reference and a retrieved passage explain that teams can check whether added supply is reducing ETAs. The provided context and answer do not include this operational use.
- [bob-moesta](bob-moesta.json): The reference and retrieved passage S4 support the warning not to use a discussion guide or ask everyone the same questions, because that can prevent following the most meaningful details in each person’s story. The provided context does not include that warning, and the answer instead discusses unreliable explanations of habitual behavior and how to probe. Those claims are supported by the cited context, but they do not answer the specific question.

**Available in context, omitted from answer:**

- [alex-hardimen](alex-hardimen.json): The reference, retrieved passages, and context support building end-to-end systems and tooling to create and reshape storytelling formats over time. The answer mentions reusable storytelling systems, but does not clearly include the tooling or the end-to-end support for storytelling formats required by this point.
- [brendan-foody](brendan-foody.json): The reference and retrieved/context passage S2 connect the quality of experts to the quality of model decisions and recommendations. The answer says qualified professionals and expert-built work help improve models, but does not clearly state that higher-caliber experts improve the quality of the post-training work.
- [camille-ricketts](camille-ricketts.json): The reference and retrieved passage S2 support caution about investing heavily in community for sales-led products, often pricier or requiring longer contracts. But the answer only says these products may call for a different approach; it does not clearly state Camille’s specific uncertainty that community should be the top investment.
- [chris-hutchins](chris-hutchins.json): The reference, retrieved passage, and context S2 support the point that focusing on a vertical or niche helps people understand what the show is about and helps it stand out among many podcasts. The answer omits this advice.

**Synthetic reference point not supported by reference excerpt:**

- [manik-gupta](manik-gupta.json): The reference excerpt does not discuss company-product fit. Retrieved passages and provided context S1 support checking whether a successful product belongs in the portfolio and plays to the company’s strengths; the answer also includes creating distinctive customer value better than competitors. The reference excerpt does not support this point. Retrieved passage S2 and provided context explain that resolving company-product fit first makes the path to product-market fit easier by reducing distractions and establishing strategic effort and sponsorship. The answer clearly states these reasons.

## Latency and token usage

Median retrieval (including reranking): **15.28 seconds**.

| Component | Median observed duration |
|---|---:|
| embedding | 0.36 s |
| evidence_order | 7.20 s |
| semantic | 2.20 s |
| keyword | 6.11 s |
| neighbors | 0.40 s |

Component medians do not add to the overall median. Semantic and keyword searches overlap; SQL timings include database round-trip time. Context-budget response timings exclude the judge but were measured while other evaluations were active. They are not isolated production latency benchmarks.

| Budget | Median actual transcript tokens supplied | Answer input tokens total | Answer output tokens total |
|---|---:|---:|---:|
| 2,000 | 1917 | 865,021 | 120,316 |
| 4,000 | 3896 | 1,543,172 | 118,536 |
| 6,000 | 5882 | 2,249,342 | 122,790 |

Usage totals above cover answer-generation calls only; reranking and automated evaluation also consume tokens. No monetary cost is inferred from unverified model pricing. Answer output limit remains 1,800 tokens.

## Interpretation limits

- One question per transcript is coverage of files, not every passage or possible user question.
- Synthetic reference labels and same-model judging are advisory; the point classifications are not independent human findings.
- Judges disagreed across budgets about reference support in 0 cases and about support in the unchanged top-20 retrieval in 14 cases. These require source review.
- Source anchors are deterministically verified, but exact-anchor misses can have valid alternative evidence.
- HNSW retrieval is approximate. Duplicate source files remain traceable; identical text consumes one selection slot.
- No assertion that missing information is absent from the entire corpus is made.
- App defaults and response behavior were not changed by this experiment; remediation follows review of these results.

Two attempts stopped on Windows checkpoint filesystem errors in the OneDrive folder. Completed stages were preserved and resumed in a working directory outside OneDrive after improving task cleanup. Interruptions/client-closed errors are operational failures, not transcript retrieval misses. Completed-stage timing data is retained; retry calls remain visible in the traces.

## All 303 cases

Every link contains the question, reference points, ranked passages, each budget's actual evidence/answer/judgment, and request timing/usage traces.

| Transcript/test case | 2,000: completeness / issues | 4,000: completeness / issues | 6,000: completeness / issues |
|---|---|---|---|
| [ada-chen-rekhi](ada-chen-rekhi.json) | complete | complete | complete |
| [adam-fishman](adam-fishman.json) | complete | complete; grounding | complete |
| [adam-grenier](adam-grenier.json) | incomplete; context_selection_gap | incomplete; generation_omission | incomplete; generation_omission |
| [adriel-frederick](adriel-frederick.json) | complete | complete | complete |
| [aishwarya-naresh-reganti-kiriti-badam](aishwarya-naresh-reganti-kiriti-badam.json) | complete | complete | complete |
| [albert-cheng](albert-cheng.json) | complete | complete | complete |
| [alex-hardimen](alex-hardimen.json) | incomplete; generation_omission | complete | incomplete; generation_omission |
| [alex-komoroske](alex-komoroske.json) | complete | complete | complete |
| [alexander-embiricos](alexander-embiricos.json) | incomplete; retrieval_gap | incomplete; context_selection_gap, retrieval_gap | incomplete; retrieval_gap |
| [alisa-cohn](alisa-cohn.json) | complete | complete | complete |
| [ami-vora](ami-vora.json) | complete | complete | complete |
| [amjad-masad](amjad-masad.json) | complete | complete | complete |
| [andrew-wilkinson](andrew-wilkinson.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap, grounding |
| [andy-johns](andy-johns.json) | complete | complete | complete |
| [andy-raskin](andy-raskin.json) | complete | complete | complete |
| [andy-raskin_](andy-raskin_.json) | complete | complete; grounding | complete |
| [anneka-gupta](anneka-gupta.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [annie-duke](annie-duke.json) | complete | complete | complete |
| [annie-pearl](annie-pearl.json) | complete | complete | complete |
| [anton-osika](anton-osika.json) | complete | complete | complete |
| [anuj-rathi](anuj-rathi.json) | complete | complete | complete |
| [aparna-chennapragada](aparna-chennapragada.json) | complete | complete | complete |
| [april-dunford](april-dunford.json) | complete | complete | complete |
| [april-dunford-20](april-dunford-20.json) | complete | complete | complete |
| [archie-abrams](archie-abrams.json) | complete | complete | complete |
| [arielle-jackson](arielle-jackson.json) | complete | complete | complete |
| [asha-sharma](asha-sharma.json) | incomplete; context_selection_gap | complete | complete |
| [austin-hay](austin-hay.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [ayo-omojola](ayo-omojola.json) | complete | complete | complete |
| [bangaly-kaba](bangaly-kaba.json) | incomplete; retrieval_gap | incomplete; retrieval_gap, grounding | incomplete; generation_omission |
| [barbra-gago](barbra-gago.json) | complete | complete | complete |
| [ben-horowitz](ben-horowitz.json) | complete | complete | complete |
| [ben-williams](ben-williams.json) | complete | complete | complete |
| [benjamin-lauzier](benjamin-lauzier.json) | incomplete; context_selection_gap | complete | complete |
| [benjamin-mann](benjamin-mann.json) | complete | complete | complete |
| [bill-carr](bill-carr.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [bob-baxley](bob-baxley.json) | complete | complete | complete |
| [bob-moesta](bob-moesta.json) | incomplete; context_selection_gap | incomplete; generation_omission | incomplete; generation_omission |
| [bob-moesta-20](bob-moesta-20.json) | complete | complete | complete |
| [boz](boz.json) | complete | complete | complete |
| [brandon-chu](brandon-chu.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; generation_omission |
| [brendan-foody](brendan-foody.json) | incomplete; generation_omission, grounding | complete; grounding | complete |
| [bret-taylor](bret-taylor.json) | complete; grounding | complete | complete |
| [brian-balfour](brian-balfour.json) | complete | complete | complete |
| [brian-chesky](brian-chesky.json) | complete | complete | complete |
| [brian-tolkin](brian-tolkin.json) | complete | complete | complete |
| [cam-adams](cam-adams.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [camille-fournier](camille-fournier.json) | complete | complete | complete |
| [camille-hearst](camille-hearst.json) | complete | complete | complete |
| [camille-ricketts](camille-ricketts.json) | incomplete; generation_omission, retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [carilu-dietrich](carilu-dietrich.json) | complete | complete | complete |
| [carole-robin](carole-robin.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [casey-winters](casey-winters.json) | complete | complete | complete |
| [casey-winters_](casey-winters_.json) | complete; grounding | complete | complete; grounding |
| [chandra-janakiraman](chandra-janakiraman.json) | complete | complete | complete |
| [chip-conley](chip-conley.json) | complete | complete | complete |
| [chip-huyen](chip-huyen.json) | complete | complete | complete |
| [chris-hutchins](chris-hutchins.json) | incomplete; generation_omission | incomplete; generation_omission | incomplete; generation_omission |
| [christian-idiodi](christian-idiodi.json) | incomplete; context_selection_gap | complete | complete |
| [christina-wodtke](christina-wodtke.json) | incomplete; context_selection_gap, grounding | complete | complete |
| [christine-itwaru](christine-itwaru.json) | complete | complete; grounding | complete |
| [christopher-lochhead](christopher-lochhead.json) | incomplete; retrieval_gap | incomplete; generation_omission, retrieval_gap | incomplete; generation_omission, retrieval_gap |
| [christopher-miller](christopher-miller.json) | complete | complete | complete |
| [claire-butler](claire-butler.json) | complete | complete | complete |
| [claire-hughes-johnson](claire-hughes-johnson.json) | incomplete; retrieval_gap | incomplete; retrieval_gap, grounding | incomplete; retrieval_gap, grounding |
| [claire-vo](claire-vo.json) | complete | complete | complete |
| [crystal-w](crystal-w.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [dalton-caldwell](dalton-caldwell.json) | incomplete; generation_omission | incomplete; context_selection_gap | incomplete; generation_omission |
| [dan-hockenmaier](dan-hockenmaier.json) | complete | complete | complete |
| [dan-shipper](dan-shipper.json) | complete | complete | complete |
| [daniel-lereya](daniel-lereya.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap, grounding |
| [david-placek](david-placek.json) | complete | complete | complete |
| [david-singleton](david-singleton.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [deb-liu](deb-liu.json) | complete | complete | complete |
| [dhanji-r-prasanna](dhanji-r-prasanna.json) | complete | complete | complete |
| [dharmesh-shah](dharmesh-shah.json) | incomplete; generation_omission | complete | complete |
| [dmitry-zlokazov](dmitry-zlokazov.json) | complete | complete | complete |
| [donna-lichaw](donna-lichaw.json) | complete | complete | complete; grounding |
| [dr-fei-fei-li](dr-fei-fei-li.json) | complete | incomplete; generation_omission | incomplete; generation_omission |
| [drew-houston](drew-houston.json) | incomplete; generation_omission, grounding | incomplete; generation_omission | incomplete; generation_omission |
| [dylan-field](dylan-field.json) | complete | complete | complete |
| [dylan-field-20](dylan-field-20.json) | complete | complete | complete |
| [ebi-atawodi](ebi-atawodi.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; context_selection_gap |
| [edwin-chen](edwin-chen.json) | complete | incomplete; generation_omission | complete |
| [eeke-de-milliano](eeke-de-milliano.json) | complete | complete | complete |
| [elena-verna](elena-verna.json) | complete | complete | incomplete; retrieval_gap |
| [elena-verna-20](elena-verna-20.json) | incomplete; retrieval_gap | incomplete; retrieval_gap, grounding | incomplete; retrieval_gap |
| [elena-verna-30](elena-verna-30.json) | complete | complete | complete |
| [elena-verna-40](elena-verna-40.json) | complete | complete | complete |
| [eli-schwartz](eli-schwartz.json) | complete | complete | complete |
| [elizabeth-stone](elizabeth-stone.json) | complete | complete | complete |
| [emilie-gerber](emilie-gerber.json) | complete | complete | complete |
| [emily-kramer](emily-kramer.json) | complete | complete | complete |
| [eoghan-mccabe](eoghan-mccabe.json) | complete | complete | complete |
| [eoy-review](eoy-review.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [eric-ries](eric-ries.json) | complete | complete | complete |
| [eric-simons](eric-simons.json) | complete | complete | complete |
| [ethan-evans](ethan-evans.json) | incomplete; generation_omission | complete | incomplete; generation_omission |
| [ethan-evans-20](ethan-evans-20.json) | incomplete; generation_omission | complete | complete |
| [ethan-smith](ethan-smith.json) | complete | complete | complete |
| [evan-lapointe](evan-lapointe.json) | complete | complete | complete |
| [failure](failure.json) | complete | complete | complete |
| [fareed-mosavat](fareed-mosavat.json) | complete | complete | complete |
| [farhan-thawar](farhan-thawar.json) | complete; grounding | complete; grounding | complete |
| [fei-fei](fei-fei.json) | complete | complete | complete; grounding |
| [garrett-lord](garrett-lord.json) | complete | complete | complete |
| [gaurav-misra](gaurav-misra.json) | complete | complete | complete |
| [geoff-charles](geoff-charles.json) | complete | complete | complete |
| [geoffrey-moore](geoffrey-moore.json) | complete; grounding | complete | complete; grounding |
| [gergely](gergely.json) | complete | incomplete; generation_omission | incomplete; generation_omission |
| [gia-laudi](gia-laudi.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [gibson-biddle](gibson-biddle.json) | incomplete; generation_omission | complete | incomplete; generation_omission |
| [gina-gotthilf](gina-gotthilf.json) | complete | complete | complete |
| [gokul-rajaram](gokul-rajaram.json) | complete | complete | complete |
| [graham-weaver](graham-weaver.json) | complete | complete | complete |
| [grant-lee](grant-lee.json) | complete | incomplete; generation_omission | complete |
| [guillermo-rauch](guillermo-rauch.json) | complete | complete | complete |
| [gustaf-alstromer](gustaf-alstromer.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [gustav-söderström](gustav-söderström.json) | incomplete; retrieval_gap | incomplete; context_selection_gap, generation_omission | incomplete; retrieval_gap |
| [hamel-husain-shreya-shankar](hamel-husain-shreya-shankar.json) | complete | complete | complete |
| [hamelshreya](hamelshreya.json) | complete | complete | complete |
| [hamilton-helmer](hamilton-helmer.json) | complete | complete | complete |
| [hari-srinivasan](hari-srinivasan.json) | complete | complete | complete |
| [heidi-helfand](heidi-helfand.json) | complete | complete | complete; grounding |
| [hila-qu](hila-qu.json) | complete | complete | complete |
| [hilary-gridley](hilary-gridley.json) | complete | complete | complete |
| [howie-liu](howie-liu.json) | complete | complete | complete |
| [ian-mcallister](ian-mcallister.json) | complete | complete | complete |
| [inbal-s](inbal-s.json) | complete | complete | complete |
| [interview-q-compilation](interview-q-compilation.json) | complete | complete | complete |
| [itamar-gilad](itamar-gilad.json) | complete | complete | complete |
| [ivan-zhao](ivan-zhao.json) | complete | complete | complete |
| [jackie-bavaro](jackie-bavaro.json) | complete | complete | complete |
| [jackson-shuttleworth](jackson-shuttleworth.json) | complete | complete | complete |
| [jag-duggal](jag-duggal.json) | complete | complete | complete |
| [jake-knapp-john-zeratsky](jake-knapp-john-zeratsky.json) | complete | complete | complete |
| [jake-knapp-john-zeratsky-20](jake-knapp-john-zeratsky-20.json) | complete | complete | complete |
| [janna-bastow](janna-bastow.json) | complete | complete | complete |
| [jason-droege](jason-droege.json) | complete | complete | complete |
| [jason-feifer](jason-feifer.json) | complete | complete | complete |
| [jason-fried](jason-fried.json) | incomplete; generation_omission | incomplete; generation_omission | complete |
| [jason-m-lemkin](jason-m-lemkin.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; context_selection_gap |
| [jason-shah](jason-shah.json) | complete | complete | complete |
| [jeanne-grosser](jeanne-grosser.json) | complete | complete | complete |
| [jeff-weinstein](jeff-weinstein.json) | complete; grounding | complete | complete |
| [jeffrey-pfeffer](jeffrey-pfeffer.json) | complete | complete | complete |
| [jen-abel](jen-abel.json) | complete | complete | complete; grounding |
| [jen-abel-20](jen-abel-20.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [jeremy-henrickson](jeremy-henrickson.json) | complete | complete | complete |
| [jerry-colonna](jerry-colonna.json) | complete | complete | complete |
| [jess-lachs](jess-lachs.json) | complete | complete | complete |
| [jessica-hische](jessica-hische.json) | complete | complete | complete |
| [jessica-livingston](jessica-livingston.json) | complete | complete | complete |
| [jiaona-zhang](jiaona-zhang.json) | complete | complete | complete |
| [joe-hudson](joe-hudson.json) | complete | complete | complete |
| [john-cutler](john-cutler.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [john-mark-nickels](john-mark-nickels.json) | complete | complete | complete |
| [jonathan-becker](jonathan-becker.json) | complete | complete | complete |
| [jonathan-lowenhar](jonathan-lowenhar.json) | complete | complete | complete |
| [jonny-miller](jonny-miller.json) | complete | complete | complete |
| [josh-miller](josh-miller.json) | complete | complete | complete |
| [judd-antin](judd-antin.json) | complete | complete | complete |
| [jules-walter](jules-walter.json) | complete | complete | complete |
| [julia-schottenstein](julia-schottenstein.json) | complete | complete | complete |
| [julian-shapiro](julian-shapiro.json) | complete | complete | complete |
| [julie-zhuo](julie-zhuo.json) | incomplete; context_selection_gap | incomplete; context_selection_gap | complete |
| [julie-zhuo-20](julie-zhuo-20.json) | complete | complete | complete |
| [karina-nguyen](karina-nguyen.json) | complete | complete | complete |
| [karri-saarinen](karri-saarinen.json) | complete | complete | complete |
| [katie-dill](katie-dill.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [kayvon-beykpour](kayvon-beykpour.json) | complete | complete | complete |
| [keith-coleman-jay-baxter](keith-coleman-jay-baxter.json) | complete | complete | complete |
| [keith-yandell](keith-yandell.json) | complete | complete | complete |
| [ken-norton](ken-norton.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [kenneth-berger](kenneth-berger.json) | complete | complete | complete |
| [kevin-aluwi](kevin-aluwi.json) | complete | complete | complete |
| [kevin-weil](kevin-weil.json) | complete | complete | complete |
| [kevin-yien](kevin-yien.json) | complete | complete | complete |
| [kim-scott](kim-scott.json) | incomplete; generation_omission | complete | complete |
| [kristen-berman](kristen-berman.json) | complete | complete | complete |
| [krithika-shankarraman](krithika-shankarraman.json) | complete | complete | complete |
| [kunal-shah](kunal-shah.json) | complete | complete | complete |
| [lane-shackleton](lane-shackleton.json) | complete | complete | complete |
| [laura-modi](laura-modi.json) | complete | complete | complete |
| [laura-schaffer](laura-schaffer.json) | complete | complete | complete |
| [lauren-ipsen](lauren-ipsen.json) | complete | complete | complete |
| [lauryn-isford](lauryn-isford.json) | complete | complete | complete |
| [logan-kilpatrick](logan-kilpatrick.json) | complete | complete | complete |
| [luc-levesque](luc-levesque.json) | complete | complete | complete |
| [lulu-cheng-meservey](lulu-cheng-meservey.json) | complete | complete | complete |
| [madhavan-ramanujam](madhavan-ramanujam.json) | complete | complete | complete |
| [madhavan-ramanujam-20](madhavan-ramanujam-20.json) | complete | complete | complete |
| [maggie-crowley](maggie-crowley.json) | complete | complete | complete |
| [manik-gupta](manik-gupta.json) | incomplete; reference_label_needs_review | incomplete; reference_label_needs_review | incomplete; reference_label_needs_review |
| [marc-benioff](marc-benioff.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [marily-nika](marily-nika.json) | complete | complete | complete |
| [marty-cagan](marty-cagan.json) | complete | complete | complete |
| [marty-cagan-20](marty-cagan-20.json) | complete | complete; grounding | complete; grounding |
| [matt-abrahams](matt-abrahams.json) | complete | incomplete; generation_omission | incomplete; generation_omission |
| [matt-dixon](matt-dixon.json) | complete | complete | complete |
| [matt-lemay](matt-lemay.json) | complete | complete | complete |
| [matt-macinnis](matt-macinnis.json) | incomplete; generation_omission | complete | incomplete; generation_omission |
| [matt-mochary](matt-mochary.json) | complete | complete | complete |
| [matt-mullenweg](matt-mullenweg.json) | complete | complete | complete |
| [matthew-dicks](matthew-dicks.json) | complete | complete | complete |
| [maya-prohovnik](maya-prohovnik.json) | incomplete; context_selection_gap, grounding | incomplete; context_selection_gap, grounding | incomplete; generation_omission |
| [mayur-kamat](mayur-kamat.json) | complete; grounding | complete | complete |
| [megan-cook](megan-cook.json) | complete | complete | complete |
| [melanie-perkins](melanie-perkins.json) | incomplete; generation_omission | incomplete; generation_omission | complete |
| [melissa](melissa.json) | complete | complete | complete |
| [melissa-perri](melissa-perri.json) | complete | complete; grounding | complete |
| [melissa-perri-denise-tilles](melissa-perri-denise-tilles.json) | complete | complete | complete |
| [melissa-tan](melissa-tan.json) | complete | complete | complete |
| [meltem-kuran](meltem-kuran.json) | complete | complete | complete |
| [merci-grace](merci-grace.json) | complete | complete | complete |
| [michael-truell](michael-truell.json) | complete | complete | complete |
| [mihika-kapoor](mihika-kapoor.json) | complete | complete | complete |
| [mike-krieger](mike-krieger.json) | complete | complete | complete |
| [mike-maples-jr](mike-maples-jr.json) | incomplete; retrieval_gap | incomplete; generation_omission, retrieval_gap | incomplete; context_selection_gap, retrieval_gap |
| [molly-graham](molly-graham.json) | complete | complete | complete |
| [nabeel-s-qureshi](nabeel-s-qureshi.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [nan-yu](nan-yu.json) | incomplete; generation_omission | complete | complete |
| [nancy-duarte](nancy-duarte.json) | incomplete; retrieval_gap, grounding | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [naomi-gleit](naomi-gleit.json) | complete | complete | complete |
| [naomi-ionita](naomi-ionita.json) | complete | complete | complete |
| [nick-turley](nick-turley.json) | complete | complete | complete |
| [nickey-skarstad](nickey-skarstad.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [nicole-forsgren](nicole-forsgren.json) | complete | complete | complete |
| [nicole-forsgren-20](nicole-forsgren-20.json) | complete | complete | complete |
| [nikhyl-singhal](nikhyl-singhal.json) | incomplete; generation_omission | incomplete; retrieval_gap | incomplete; generation_omission |
| [nikita-bier](nikita-bier.json) | complete | complete | complete |
| [nikita-miller](nikita-miller.json) | complete | complete | complete |
| [nilan-peiris](nilan-peiris.json) | complete | complete | complete |
| [nir-eyal](nir-eyal.json) | incomplete; context_selection_gap | complete | incomplete; generation_omission |
| [noah-weiss](noah-weiss.json) | complete | complete | complete |
| [noam-lovinsky](noam-lovinsky.json) | complete | complete | complete |
| [oji-udezue](oji-udezue.json) | complete | complete | complete |
| [paige-costello](paige-costello.json) | complete | complete | complete |
| [patrick-campbell](patrick-campbell.json) | complete | complete | complete |
| [paul-adams](paul-adams.json) | complete | complete | complete |
| [paul-millerd](paul-millerd.json) | complete | complete | complete |
| [pete-kazanjy](pete-kazanjy.json) | complete | complete | complete |
| [peter-deng](peter-deng.json) | complete; grounding | complete | complete |
| [petra-wille](petra-wille.json) | complete | complete | complete |
| [phyl-terry](phyl-terry.json) | complete | complete | complete |
| [raaz-herzberg](raaz-herzberg.json) | complete | complete | complete |
| [rachel-lockett](rachel-lockett.json) | incomplete; generation_omission | incomplete; context_selection_gap | incomplete; retrieval_gap |
| [rahul-vohra](rahul-vohra.json) | complete | complete | complete |
| [ramesh-johari](ramesh-johari.json) | complete | complete | complete |
| [ravi-mehta](ravi-mehta.json) | complete | complete | complete |
| [ray-cao](ray-cao.json) | complete | complete | complete |
| [richard-rumelt](richard-rumelt.json) | complete | complete | complete |
| [robby-stein](robby-stein.json) | complete | complete | complete |
| [roger-martin](roger-martin.json) | complete | complete | complete |
| [ronny-kohavi](ronny-kohavi.json) | complete | complete | complete |
| [ryan-hoover](ryan-hoover.json) | complete | complete | complete |
| [ryan-j-salva](ryan-j-salva.json) | complete | complete | complete |
| [ryan-singer](ryan-singer.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [sachin-monga](sachin-monga.json) | complete | complete | complete |
| [sahil-mansuri](sahil-mansuri.json) | complete | complete | complete |
| [sam-schillace](sam-schillace.json) | complete | complete | complete |
| [sanchan-saxena](sanchan-saxena.json) | incomplete; retrieval_gap | complete; grounding | incomplete; retrieval_gap |
| [sander-schulhoff](sander-schulhoff.json) | complete | complete | complete |
| [sander-schulhoff-20](sander-schulhoff-20.json) | complete | complete | complete |
| [sarah-tavel](sarah-tavel.json) | complete | complete | complete |
| [scott-belsky](scott-belsky.json) | complete | complete | complete |
| [scott-wu](scott-wu.json) | complete | complete | complete |
| [sean-ellis](sean-ellis.json) | complete | complete | complete |
| [seth-godin](seth-godin.json) | complete | complete | complete |
| [shaun-clowes](shaun-clowes.json) | complete | complete | complete |
| [shishir-mehrotra](shishir-mehrotra.json) | complete | complete | complete |
| [shreyas-doshi](shreyas-doshi.json) | complete | complete | complete |
| [shreyas-doshi-live](shreyas-doshi-live.json) | complete | complete | complete |
| [shweta-shriva](shweta-shriva.json) | complete | complete | complete |
| [sri-batchu](sri-batchu.json) | incomplete; generation_omission, retrieval_gap, grounding | incomplete; generation_omission, retrieval_gap | incomplete; retrieval_gap, grounding |
| [sriram-and-aarthi](sriram-and-aarthi.json) | complete | complete | complete |
| [stewart-butterfield](stewart-butterfield.json) | complete | complete | complete |
| [tamar-yehoshua](tamar-yehoshua.json) | complete | complete | complete |
| [tanguy-crusson](tanguy-crusson.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [teaser_2021](teaser_2021.json) | complete | complete | complete |
| [teresa-torres](teresa-torres.json) | complete | complete | complete |
| [tim-holley](tim-holley.json) | complete | complete | complete |
| [timothy-davis](timothy-davis.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [tobi-lutke](tobi-lutke.json) | incomplete; retrieval_gap | incomplete; context_selection_gap, retrieval_gap | incomplete; context_selection_gap, retrieval_gap |
| [todd-jackson](todd-jackson.json) | complete | incomplete; generation_omission | complete |
| [tom-conrad](tom-conrad.json) | complete | complete | complete |
| [tomer-cohen](tomer-cohen.json) | complete | complete | complete |
| [tomer-cohen-20](tomer-cohen-20.json) | complete | complete | complete |
| [tristan-de-montebello](tristan-de-montebello.json) | complete | complete | complete |
| [upasna-gautam](upasna-gautam.json) | complete | complete | incomplete; generation_omission |
| [uri-levine](uri-levine.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [uri-levine-20](uri-levine-20.json) | complete; grounding | complete; grounding | complete; grounding |
| [varun-mohan](varun-mohan.json) | complete | complete | complete |
| [varun-parmar](varun-parmar.json) | complete | complete | complete |
| [vijay](vijay.json) | incomplete; retrieval_gap | incomplete; retrieval_gap | incomplete; retrieval_gap |
| [vikrama-dhiman](vikrama-dhiman.json) | complete | complete | complete |
| [wes-kao](wes-kao.json) | complete | complete | complete |
| [wes-kao-20](wes-kao-20.json) | complete | complete | complete |
| [will-larson](will-larson.json) | complete | complete | complete |
| [yamashata](yamashata.json) | complete | complete; grounding | complete; grounding |
| [yuhki-yamashata](yuhki-yamashata.json) | complete | complete | complete |
| [yuriy-timen](yuriy-timen.json) | complete; grounding | complete | complete |
| [zoelle-egner](zoelle-egner.json) | complete | complete | complete |

## Reproduce or resume

```powershell
.\.venv\Scripts\python.exe -m evals.transcript_audit --run full303_rerank_context_comparison --workers 4 --budgets 2000 4000 6000
.\.venv\Scripts\python.exe -m evals.report_transcript_audit --run full303_rerank_context_comparison
```

Run from backend. Completed stages are reused; failed stages resume. Code/configuration hashes prevent silently mixing different implementations in the same run. Raw failures and retries remain in traces.
