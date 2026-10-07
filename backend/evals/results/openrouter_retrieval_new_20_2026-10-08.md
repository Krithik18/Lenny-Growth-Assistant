# OpenRouter retrieval: 20 new questions

Tested the existing revised pipeline without tuning it during the run: OpenRouter BGE-M3 embeddings, archive semantic/keyword candidate selection, Voyage reranking, and the initial 4,000-token context. No Llama answers were generated. No archive data was written. All 20 questions differ from the old 40 regression questions.

The question set and rubrics were saved before the run. This is a new diagnostic set constructed and qualitatively reviewed by the coding agent, not an independently authored, blindly annotated benchmark. A pass requires evidence addressing the topic, or an appropriate clarification/rejection; nonempty results, identity membership, and scores alone are not passes.

## Results

- 20/20 runs completed without runtime errors.
- 16 acceptable outcomes: 12 questions with useful supporting evidence and four appropriate ambiguity/unknown-person/domain blocks.
- One partial evidence result: the Spanish positioning-versus-tagline question retrieved related positioning and sales-pitch material but no explicit distinction.
- Three failures: two false domain rejections and one false domain acceptance.
- Live API traces show 14 BGE-M3 embedding calls and 14 Voyage reranking calls. No failed API attempts, reranker fallbacks, or score-floor rejections.
- All selected text and source offsets were preserved; archive coverage stayed at 303 episodes and 22,086 chunks.

## Failures and limitations

1. “¿Cómo puedo reducir la pérdida de clientes después de que se registran?” is a valid retention question, but the English vocabulary gate rejected it before search.
2. “How do I separate a wise bet from a lucky win?” is a valid decision-quality question, but unfamiliar wording was also rejected before search.
3. “What is the product of 137 and 29?” was falsely accepted because of the word product. It made three transcript queries and embedding/reranking calls; subscription, sponsor, and naming chunks entered context. Conservative score floors did not reject this unrelated set.

The Spanish question naming April Dunford resolved her identity but did not retrieve an explicit positioning-versus-tagline distinction. An additional active-April-episode text search found zero chunks containing tagline or slogan. This shows insufficient answer evidence; it does not establish that the reranker discarded a known exact answer.

Naomi was initially expected by the test author to resolve to Naomi Ionita, but the catalog audit found Naomi Gleit too. Its metadata-only clarification is therefore appropriate. The frozen question and original expectation remain in the dataset. Brian similarly matches Chesky, Tolkin, and Balfour; the system correctly did not guess.

Useful evidence was found for feedback, pre-mortems, empowered teams, growth motions, strategy versus goals, multi-person decisions, design sprints, misspelled Teresa Torres, interviews excluding Teresa, retention diagnosis, sample ratio mismatch, and the supported PR/FAQ part of a mixed weather request.

Mixed sponsor text and peripheral passages still enter context. For example, Bill Carr's context includes a Wix sponsor segment, and the Rumelt result includes Jag Duggal paraphrasing Rumelt. These passages must retain their actual speaker attribution. Text preservation does not mean every chunk has complete sentence boundaries or that the context exhausts the episode.

The three failed questions were not used to modify the pipeline in this evaluation. Next priorities are semantic/multilingual domain detection and an evidence-sufficiency rejection stage. The 20-case outcome is a diagnostic result, not an accuracy probability or a guarantee about generated answers.

## Per-question evidence review

| ID | Question | Outcome | Context sources used in review | Finding |
|---|---|---|---|---|
| new-01 | How does Julie Zhuo suggest a new manager give useful feedback to a struggling teammate? | pass | S1, S2, S3 | Concrete feedback tactics: establish mutual feedback expectations, check helpful intent, and express vulnerability. Mixed sponsorship and peripheral management passages also enter context. |
| new-02 | What does Shreyas Doshi recommend doing in a pre-mortem before launching a product? | pass | S1, S2, S3 | Pre-mortem prompt, hypothetical failed launch, engineering/go-to-market participation, and quiet individual risk collection are present. |
| new-03 | Why does Marty Cagan distinguish empowered product teams from feature teams? | pass | S1, S3 | Feature teams receive output roadmaps; empowered teams receive problems and own outcomes. Peripheral sales discussion remains. |
| new-04 | What does Elena Verna say about when a company should use product-led growth versus sales-led growth? | pass | S1, S2, S3 | Self-serve versus sales motions, segment economics, and moving upmarket/downmarket are supported. |
| new-05 | How does Rumelt distinguish a strategy from a list of ambitious goals? | pass | S1, S3, S4 | Rumelt explicitly says ambitions and goal lists are not strategy and calls for diagnosis and concrete actions. A Jag Duggal paraphrase also ranks highly; attribution must remain distinct. |
| new-06 | Compare Annie Duke and Shreyas Doshi on assessing decisions before the outcome is known. | pass | S1, S2, S3 | Shreyas's pre-mortem and Annie's uncertainty/pre-commitment advice support a comparison. Presence of both guests alone was not the pass criterion. |
| new-07 | How do Jake Knapp and John Zeratsky use a design sprint to test an idea before building the full product? | pass | S1, S2, S3 | The five-day map/sketch/decide/prototype/test sequence and risk-focused prototype example are present, with statements from both guests. |
| new-08 | How does Teressa Tores recommend avoiding leading questions during customer interviews? | pass | S1, S2, S3 | Teressa Tores resolves to Teresa Torres; story-based, past-behavior interviews and neutral timeline prompts support the requested interview technique. |
| new-09 | What does Naomi recommend about choosing a value metric for SaaS pricing? | pass | None | Appropriate clarification: catalog contains Naomi Gleit and Naomi Ionita. Original test expectation incorrectly assumed a unique Naomi; that assumption is disclosed rather than changing the frozen question or claiming a false rejection. |
| new-10 | Find advice about running customer interviews from guests other than Teresa Torres. | pass | S1, S2 | Jag Duggal's direct customer calls and Zoelle Egner's recurring interview invitations provide actionable advice excluding Teresa Torres. |
| new-11 | People sign up for our app but never return after the first week. Which podcast ideas could help us understand why? | pass | S1, S3 | Gia Laudi's value moments/re-engagement and Bangaly Kaba's account-access churn diagnosis address return behavior; some international expansion discussion is less direct. |
| new-12 | What is sample ratio mismatch in an A/B experiment, and why does Ronny Kohavi treat it as a warning sign? | pass | S1, S3 | Sample ratio mismatch definition, observed versus planned allocation, and data-pipeline/bot causes are present. |
| new-13 | Según April Dunford, ¿cómo se diferencia el posicionamiento de un eslogan de marketing? | partial | S1, S7, S8 | Correct person but mostly sales-pitch and broad positioning passages; no explicit positioning-versus-tagline distinction found in the context. A follow-up active-episode text search found zero April chunks containing tagline or slogan, so this is not proven to be a reranker exclusion of available exact evidence. |
| new-14 | ¿Cómo puedo reducir la pérdida de clientes después de que se registran? | fail | None | Valid Spanish retention question falsely blocked as out_of_domain before database or API calls. English-topic vocabulary cannot recognize it without an English identity/topic. |
| new-15 | How do I separate a wise bet from a lucky win? | fail | None | Valid decision-quality-versus-luck question falsely blocked as out_of_domain. Unfamiliar but meaningful wording lacks a recognized domain token. |
| new-16 | What does Marissa Exampleworth recommend for reducing churn in a subscription product? | pass | None | Unknown explicit person was not guessed. One guest-metadata query, no transcript or API calls. |
| new-17 | What does Brian recommend about hiring? | pass | None | Brian is ambiguous: catalog contains Brian Chesky, Brian Tolkin, and Brian Balfour. Metadata-only clarification is appropriate. |
| new-18 | Calculate the escape velocity of a spacecraft from Mars. | pass | None | Mars escape-velocity question blocked without database or API calls. |
| new-19 | What is the product of 137 and 29? | fail | S1, S2, S3 | Arithmetic meaning of product passed the domain gate. Three transcript queries and both embedding/rerank calls returned irrelevant subscription, sponsorship, and naming material; no candidate rejected by score floor. |
| new-20 | Explain Bill Carr's approach to writing a PR/FAQ and give me the weather forecast for Delhi this weekend. | pass | S1, S2 | Weather clause removed; Bill Carr's customer/problem/solution definition and iterative PR/FAQ review process retrieved. Mixed Wix sponsorship remains in another selected chunk. |

Source IDs above refer to each question's saved context in the companion raw JSON. That file also retains candidate passages, API traces, scores, query plans, and database query counts. The review JSON stores the qualitative assessments and catalog audit separately.
