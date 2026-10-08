# Ten fresh OpenRouter retrieval questions

Ran the unchanged current Qwen scope router, BGE-M3 hybrid retrieval with concurrent semantic/keyword search, Voyage reranker, and 4,000-token context selection. Questions and rubrics were saved before the run; none exactly overlap the prior 68. No answer-generation calls or archive writes were made.

## Outcome

- Eight acceptable results: six with useful evidence and two appropriate out-of-domain rejections.
- One partial comparison: Teresa Torres evidence was retrieved, but Rob Fitzpatrick's side was missing.
- One failure: a local identity-preservation check rejected two otherwise valid Qwen routing responses.
- There were zero failed HTTP/API attempts and no reranker fallbacks. The runtime failure was a local ProviderError.
- The derivative and antibiotic-dose questions both made zero database, embedding, or reranking calls despite relevant-looking terms.
- Stored passage text and offsets were preserved; archive coverage remained 303 episodes and 22,086 chunks.

## Failure and partial result

The Julie Zhuo delegation-and-football question was correctly split by Qwen: it retained delegation advice and removed the sports score. The local capitalized-name regex matched Explain Julie Zhuo as a name. Since the rewrite began What is Julie Zhuo's advice, the validator decided that this supposed name was missing and rejected it twice. It never opened the archive. This is a reproducible validator bug, not evidence that Qwen misunderstood the scope.

A separate read-only metadata audit found no active approved guest name containing Fitzpatrick. The comparison therefore has direct Teresa Torres evidence only. This confirms a guest-coverage limit; it does not prove that no other transcript ever mentions Rob or his book. The missing side must be disclosed rather than synthesizing Rob's advice without a source.

No production fix or successful retry was substituted into this test. The original failed trace is preserved. The immediate follow-up is to fix identity extraction so instruction verbs are not treated as names, with tests that still reject genuine guest changes.

## Per-question evidence assessment

| ID | Question | Outcome | Reviewed context sources | Finding |
|---|---|---|---|---|
| fresh-01 | How does Bob Moesta use a customer's struggling moment to understand why they switch products? | pass | S1, S2 | Bob Moesta describes interviewing churned customers to understand changed context and the struggling moment that makes them switch. Relevant content is available beyond biography or promotion. |
| fresh-02 | How does Kim Scott combine caring personally with challenging directly when giving difficult feedback? | pass | S1, S2 | Kim Scott explicitly defines Radical Candor as caring personally and challenging directly, with a leadership example and the contrast with obnoxious aggression. |
| fresh-03 | What does Melissa Perri recommend measuring to tell whether a product team is delivering outcomes rather than just shipping features? | pass | S1, S3, S4 | Melissa Perri connects product work to business value, company goals, whether metrics move, and feedback mechanisms rather than shipping volume. These are measurement principles, not a complete list of numerical KPIs; adjacent resume and process material also ranks highly. |
| fresh-04 | What does Patrick Campbel recommend doing when customers churn because their payment cards fail? | pass | S1, S2 | Patrick Campbel resolves to Patrick Campbell. Payment-card failure funnels, upcoming-expiry reminders, and replacement-card prompts are selected. Some practical reminders are spoken by host Lenny and must not all be attributed to Patrick. |
| fresh-05 | Comment une jeune entreprise peut-elle choisir les premiers clients auxquels vendre son produit ? | pass | S1, S2 | French request translated faithfully. Seth Godin discusses choosing a smallest viable audience using needs, ability to pay, technical fit, and willingness to stay; Christian Idiodi discusses reference customers. |
| fresh-06 | Our dashboard is full of numbers, but nobody changes what they do after looking at it. How can we make those numbers useful? | pass | S1, S2 | Crystal Widjaja distinguishes observed dashboard facts from contextual actionable insights; segmentation and hypothesis testing connect metrics to changed marketing decisions. |
| fresh-07 | Compare Rob Fitzpatrick and Teresa Torres on asking customers about things they actually did rather than what they might do in the future. | partial | S1, S2 | Teresa Torres gives direct evidence favoring past behavior over hypothetical future behavior. Rob Fitzpatrick's side is absent from the selected context and he was not resolved as a catalog identity. This cannot be scored as a fully supported two-person comparison. |
| fresh-08 | In a growth experiment, find the derivative of f(x) = x cubed minus 4x. | pass | None | Pure symbolic differentiation rejected despite growth/experiment wording. Zero database, embedding, or reranking calls. |
| fresh-09 | For our product team's strategy meeting, what dose of antibiotics should I take for a sore throat? | pass | None | Medical dosage request rejected despite product-team/strategy wording. Zero database, embedding, or reranking calls. |
| fresh-10 | Explain Julie Zhuo's advice on delegating decisions to a team and tell me the score of last night's football match. | fail | None | Qwen twice returned schema-valid supported Julie Zhuo delegation questions with the sports request removed. The local capitalized-name regex matched 'Explain Julie Zhuo' and falsely treated the missing verb 'Explain' as a changed identity. Both decisions were rejected; ProviderError occurred before archive access. This is a local validation bug, not an HTTP/API failure or Qwen scope rejection. |

Pass means selected evidence addresses the requested topic, or an appropriate rejection occurred. It does not mean exhaustive episode coverage or that a generated answer would attribute every claim correctly. In particular, some payment-recovery advice is spoken by host Lenny, not Patrick Campbell. This qualitative coding-agent review is not independent blind annotation.

The companion raw JSON retains original questions, scope outputs, API traces, candidate passages, ranking scores, selected context, and query counts. Source IDs refer to each question's own context. The review and analysis JSON files retain the assessments and reproduced validator failure.
