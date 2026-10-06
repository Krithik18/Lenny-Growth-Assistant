# Full transcript evaluation

## Indexed knowledge

- Approved ZIP: `5915e40e36e0511a3befc5aa22c3ed37ba4f4e0d9971367332810da71a817bf6`.
- Transcript files fully indexed: **303 / 303**.
- Chunks: **22,086**; compatible OpenAI embeddings: **22,086**.
- Distinct transcript bodies: 291 (exact duplicates remain traceable to their ZIP members).
- Embeddings: text-embedding-3-small, 1,536 dimensions. Answers and automated evaluation: gpt-6-luna only.
- Archive filenames and source metadata are preserved, including existing inconsistencies.

## Retrieval only

One source-derived question per transcript file. Labels were generated from deterministic transcript excerpts;
evidence anchors were verified against the source. These are synthetic evaluation labels, not independent human gold.
An exact anchor in a duplicate source counts as a hit. A miss may still retrieve other valid evidence.
This stage tests initial semantic retrieval separately from generation and missing-topic refinement.

Completed: 303 / 303; errors: 0.

| Metric | Result |
|---|---:|
| Expected evidence in top 5 | 60.4% |
| Expected evidence in top 20 | 81.5% |
| Expected evidence in 2,000-token initial context | 62.7% |
| MRR within top 20 | 0.448 |
| Median embedding + database retrieval time | 3.51 seconds |

| Requested question type | Cases | Hit at 5 | Hit at 20 |
|---|---:|---:|---:|
| definition | 37 | 83.8% | 97.3% |
| example | 38 | 55.3% | 81.6% |
| explanation | 38 | 57.9% | 78.9% |
| fact | 38 | 55.3% | 76.3% |
| mistake | 38 | 60.5% | 78.9% |
| practical_advice | 38 | 52.6% | 76.3% |
| process | 38 | 50.0% | 73.7% |
| tradeoff | 38 | 68.4% | 89.5% |

## Answer checks

Forty questions, selected deterministically across the eight requested categories before examining retrieval results.
Each is run twice: with a fixed reference excerpt, and through the real retrieval-and-answer service.
The scores below are advisory GPT-6 Luna judgments. Using the same model as judge can introduce bias;
they must not be presented as human-certified accuracy. Check individual answers and evidence in the JSON reports.

Selected source checks and interpretation: [source_review.md](source_review.md). Some judge flags conflate
reference-detail omissions with unsupported claims; preserve raw judgments rather than treating them as factual verdicts.

| Stage | Completed | Grounded | Addresses question | Expected points | Appropriate evidence limits |
|---|---:|---:|---:|---:|---:|
| fixed_evidence | 40/40 | 100.0% | 100.0% | 95.0% | 100.0% |
| end_to_end | 40/40 | 87.5% | 95.0% | 60.0% | 82.5% |

## Broader user scenarios

Thirty authored prompts cover comparisons, multipart questions, practical advice, definitions, frameworks,
examples, numerical facts/calculations, false premises, out-of-domain questions, instruction overrides,
ambiguity, partial evidence, Spanish, typos, code requests, essay requests, exhaustive lists, current facts,
quotes, summaries, and step-by-step processes.

Completed: 30/30. Advisory rubric passes: 25/30.
Advisory grounded judgments: 29/30.

| Scenario | Coverage | Rubric | Grounded |
|---|---|---|---|
| activation-plan | complete | review | pass |
| ambiguous | partial | review | pass |
| career-advice | complete | pass | pass |
| chesky | complete | pass | pass |
| code | complete | review | pass |
| comparison-design | complete | pass | pass |
| comparison-pmf | partial | pass | pass |
| current-status | partial | pass | pass |
| discovery-definition | complete | pass | pass |
| discovery-experiments | complete | pass | pass |
| essay | complete | pass | pass |
| example-growth | complete | review | pass |
| exhaustive | partial | pass | pass |
| experimentation-risk | complete | pass | pass |
| false-premise | complete | pass | pass |
| invent-fact | unsupported | pass | pass |
| partial-weather | partial | pass | review |
| pmf-number | partial | pass | pass |
| positioning | complete | pass | pass |
| practical-metrics | complete | pass | pass |
| pricing-advice | complete | pass | pass |
| quote | complete | pass | pass |
| short-summary | complete | pass | pass |
| spanish | partial | review | pass |
| step-by-step | partial | pass | pass |
| strategy-framework | complete | pass | pass |
| typos | complete | pass | pass |
| unknown-forecast | unsupported | pass | pass |
| unrelated-private-data | unsupported | pass | pass |
| weather | unsupported | pass | pass |

## Cases requiring review

- jessica-livingston (end_to_end): The answer accurately captures Livingston’s advice to notice subtle cues, including whether founders get along, and to investigate red flags rather than treat them as automatic disqualifiers. But it omits the specific suggested questions about how co-founders met and whether they had worked together before, as well as checking whether founders understand their product and become defensive.
- david-singleton (end_to_end): The answer is supported by the cited sources: Singleton describes co-creating with early users, showing them the product regularly, gathering feedback, and waiting to broaden access until the alpha group was happy. It also accurately reflects his comments about engineers bringing technical skill and user insight. However, it does not clearly state the key recommendation to get something into users’ hands quickly and repeatedly run their feedback through a product-development loop. Regular sharing and gathering feedback partially conveys that idea, but omits the emphasis on speed and an ongoing loop.
- chris-hutchins (fixed_evidence): The answer accurately explains that a podcast gives Chris a reason to invite knowledgeable people and ask them questions, and that it offers a platform to explore his curiosities. These points are supported by Chris’s statements in the cited excerpt. However, it omits his additional point that focusing on a vertical or niche helps listeners understand what the show is about and helps it stand out, so it does not cover all reference points.
- chris-hutchins (end_to_end): The answer accurately explains that a podcast gives Chris a natural reason to invite knowledgeable people and ask them questions to learn about a subject. It does not mention his additional point that focusing on a niche helps listeners understand what the show is about and helps it stand out, so it misses one expected point.
- garrett-lord (end_to_end): The answer is supported by the cited evidence on data quality, volume in advanced domains, and the value of expert reasoning and trajectory data. It does not cover a key reference point: builders need fast turnaround so researchers can test hypotheses and quickly scale pipelines that show gains.
- nir-eyal (end_to_end): The answer correctly explains that procrastination and distraction are tied to discomfort and emotional regulation, and it usefully recommends identifying the internal trigger and having coping tools ready. However, the supplied excerpt names specific tools—the ten-minute rule, surfing the urge, and reimagining the task—and says to put the intended work on the calendar. The answer omits these and incorrectly says the evidence does not specify a particular tool, so it abstains from details that are present in the evidence.
- ebi-atawodi (end_to_end): The answer usefully describes a shared problem document and gathering stakeholder perspectives. However, it incorrectly says the evidence gives no update schedule: Atawodi says to revise the document every quarter. It also misses the specific cross-functional review described in the excerpt, where UX, research, data, product, and engineering partners examine, discuss, revise, and vote on problems. So it does not cover both expected points.
- graham-weaver (end_to_end): The answer is supported by S1 and S4 and usefully advises intentionality, looking toward a longer-term direction, and not waiting for fear or perfect timing to disappear. However, it omits Weaver’s specific five-years-from-now question and his point that the first steps toward a desired change will often feel worse, so the expected points are not fully covered.
- kim-scott (end_to_end): The answer accurately covers regular feedback-seeking, giving praise as well as criticism, starting neutrally, becoming more direct if the boss brushes the feedback off, and showing more care if the boss seems sad or angry. However, it leaves out the important qualification that the employee should remain clear about the issue rather than retracting or softening the criticism. The claims it does make are supported by the supplied evidence.
- jen-abel-20 (end_to_end): The answer offers relevant advice—that design partners should guide product understanding and should not be counted on as major rollout pipeline—but it wrongly says the evidence lacks a fuller process. The supplied excerpt also says to seek startup-friendly, often technology-focused organizations and people aligned with the founder’s vision; be candid about the product’s limitations and roadmap; and set pricing expectations with a defined early-partner discount. Because it omits those points and abstains despite their presence in the evidence, it does not cover the expected points and the abstention is not correct.
- carole-robin (end_to_end): The supplied excerpt directly gives the missed-deadline example: the leader realized his anger masked fear that nobody was as worried as he was, told the team he was deeply worried and afraid about the deadline’s impact on customers, and said the team rallied to fix it faster than ever. The answer instead describes Robin’s separate off-site story and incorrectly says the evidence does not connect an example to a missed deadline. It therefore fails to answer the question and abstains despite the relevant evidence being present.
- gustaf-alstromer (end_to_end): The answer accurately conveys Gustaf’s advice not to interpret non-use as personal rejection: people may be busy, forget, or simply be indifferent. That is supported by S5 and addresses the question, but it omits the further advice to reach out again later, particularly after improving the product. It makes no unsupported claims or inappropriate abstentions.
- tamar-yehoshua (end_to_end): The advice about choosing a place where recruits can build careers and where you can learn, rather than focusing on a top brand, is supported by S1 and S5. The additional advice about evaluating an engineering partner and agreeing on roles is supported by S2. However, the answer omits Yehoshua’s warning that financial returns are difficult to predict and the point that learned skills remain valuable even if a company fails, so it does not cover all the expected points.
- gergely (end_to_end): The answer gives practical focus advice supported by S1: use deadlines, start a 20-minute distraction-free work block, and block distracting sites. It does not mention the key advice in the reference points—telling others when to expect your work to create an external commitment. The cited source also does not include that detail.
- gustav-söderström (fixed_evidence): The answer gives evidence-supported cautions about mistaking disrupted habits or incomplete execution for proof that a rewrite is bad. But it misses Söderström’s direct warning: don’t become precious about a rewrite after investing heavily in it; follow the data and change your mind when it disproves the hypothesis.
- gustav-söderström (end_to_end): The answer is supported by the cited evidence: Söderström discusses negative reactions to change and the risk of a false negative when a rewrite is not fully implemented. But it misses the central mistake he explicitly warned against: getting precious about a rewrite after investing heavily in it, rather than changing course when data disproves the hypothesis.
- bob-moesta-20 (end_to_end): The answer correctly identifies the Pixar-inspired, concise sequence and broadly describes its structure. But the supplied excerpt does explain what the story should help a listener understand: it should intrigue them, let them see and feel the speaker’s journey, and convey where they want to go. The answer incorrectly says this explanation is absent and that the excerpt cuts off before the full sequence, even though both appear in the supplied reference excerpt. It therefore abstains from information that is present and misses a key part of the question.
- shreyas-doshi-live (end_to_end): The answer incorrectly says the evidence does not define a “one-way door.” The reference excerpt explains that a decision may look reversible but be effectively irreversible for a PM leader because it commits the team to more work and adds to its workload. The answer’s discussion of customer motivation, differentiation, and distribution is supported by S1, but it does not answer the question and its abstention is not warranted.
- rahul-vohra (end_to_end): The answer accurately explains both key points: the calendar reflects intended work, while the Switch log records actual work, and Rahul logs each task change with “TS:” plus a few words. The weekly review and charting details are also supported. However, it unnecessarily labels the evidence insufficient and the coverage partial: the excerpt directly answers the question, so that caveat is not needed.
- activation-plan: The three steps are useful and supported by the cited transcript: investigate why users drop off (S2), map the onboarding and activation opportunity (S4), and test a more relevant, self-serve route to value (S6, S3). However, the answer does not explicitly clarify that this three-step structure is its synthesis of the podcast’s advice rather than a verbatim framework, as the rubric requests.
- example-growth: The cited transcript supports that Ellis changed the sequence and focus of onboarding to highlight what users were excited about, rather than trying to remove features. But the answer omits the rubric’s key specifics: that onboarding led with antivirus and what users valued about it. The citation supports the general change, not those omitted details.
- ambiguous: The answer correctly says the context does not identify which person “he” refers to, and its descriptions are supported by the cited transcripts. But the rubric calls for asking for clarification or stating that context is insufficient without guessing a guest or topic. Listing several guests and their recommendations goes beyond that; it should have asked which person the user meant.
- partial-weather: The response correctly explains the survey question and its three answer options, cites the relevant transcript, marks the answer partial, and lists Mumbai weather as missing. However, it says Vohra advised not acting on feedback from “every” early user; the cited transcript says not to act on feedback from “many” early users. That overstates the source, so the response is not fully grounded and the citation does not support that wording.
- spanish: La respuesta está bien calibrada: el fragmento citado menciona a personas «extremadamente decepcionadas» y «algo decepcionadas», pero no contiene una tercera opción ni atribuye la encuesta a Rahul Vohra. La cita respalda esa limitación; aun así, la respuesta no ofrece las tres opciones que pide la rúbrica.
- code: The answer accurately presents the podcast’s 40% benchmark and labels the code as its own implementation. However, the function only handles a zero total; it does not reject other invalid counts, such as negative values or more very-disappointed responses than total responses.

## Operational checks

- Local backend suite: 54 passed.
- Original ten retrieval regressions against the full archive: 7/10 exact-anchor hits at five (the earlier five-file pilot scored 9/10). Corpus expansion changes competing results.
- Embedding-table RLS enabled: True.
- Running API: health ready; retrieval HTTP 200; answer HTTP 200; invalid request HTTP 422.
- Chesky multipart API answer: complete, using gpt-6-luna.
- Migration 0004 applied. Alembic reports no new upgrade operations; query-plan check confirms use of the HNSW index.
- The saved EXPLAIN was taken during concurrent evaluation and is a diagnostic snapshot, not an isolated latency benchmark.

## Limits

- Testing covers every transcript with one question, not every passage or possible question.
- Full ingestion broadens source coverage; it does not guarantee perfect retrieval or factual answers.
- Citation validation checks source IDs; the semantic judgments above are fallible model evaluations.
- Source metadata errors cannot be corrected reliably without additional source verification.
- Initial context remains bounded; exhaustive corpus questions and multi-turn references need additional product work.
- HNSW approximate vector and GIN keyword indexes are used; recall and performance need monitoring under production traffic.
- Reports are snapshots; model output can vary between runs.
