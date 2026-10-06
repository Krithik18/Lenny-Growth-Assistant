# Evidence selection at a fixed 2,000-token answer context

## Changes

- Search semantic and keyword candidates on the first retrieval, preserving the semantic top 20.
- Include immediate neighbors around a bounded set of strong hits to recover continuations.
- Ask GPT-6 Luna to rank up to 50 original passages against the question before context packing.
- Validate the returned ID permutation; preserve original candidate order on failure or timeout.
- Require answer coverage of concrete steps, examples, numbers, and qualifications, and recheck evidence before claiming a gap.
- Rank keyword candidate IDs before loading their vectors; no database migration or reindexing required.

## Same-question retrieval comparison

40 deterministically selected questions, five per category, identical to the earlier answer subset. The baseline is historical, not a concurrent control. This is not a rerun of all 303 questions.

| Metric | Historical semantic search | New selection |
|---|---:|---:|
| Expected evidence in top 5 | 60.0% | 77.5% |
| Expected evidence in top 20 | 77.5% | 82.5% |
| Expected evidence in 2,000-token context | 65.0% | 80.0% |
| Median retrieval time | 6.60 s | 17.03 s |

Median initial retrieval + answer time: **22.83 seconds** (excludes evaluation judging). Runs used two concurrent cases; these are development timings, not isolated production benchmarks. Reranking adds a model call and reads up to 50 candidate chunks, separate from the answering model's 2,000-token evidence budget.

## Initial-answer checks

| Advisory automated judgment | Pass rate |
|---|---:|
| Claims grounded in cited evidence | 97.5% |
| Addresses question | 97.5% |
| All expected reference points covered | 70.0% |
| Appropriate evidence limits | 100.0% |

These checks use the initial answer only, with no second-round evidence expansion. The existing service may still add up to 2,000 tokens through its optional missing-topic refinement. The original end-to-end answer report used that service and a different judge rubric, so its percentages are not a direct before/after answer-quality comparison.

The revised rubric separately checks reference completeness and justified abstention. A reference detail missing from retrieved context still counts against completeness, but an honest statement that it is missing is not an incorrect abstention. GPT-6 Luna is also the judge; these judgments are advisory, not human-certified accuracy.

## Remaining cases for review

- **bob-moesta**: The answer’s claims about asking concrete questions and following up on a person’s answers are supported by the cited excerpts. But it answers a different warning: the question asks about avoiding a fixed discussion guide and identical questions so the interviewer can follow the most meaningful details in each story. The answer does not clearly state that mistake.
- **carole-robin**: The answer accurately describes the market-share example in S1 and S2 and correctly notes that the provided context does not include the missed-deadline anecdote, so its abstention is appropriate. It does not cover the reference points about the leader recognizing his fear, telling the team he was deeply worried and afraid, or the team rallying to fix the problem faster than ever.
- **chris-hutchins**: The answer accurately explains that a podcast gives Chris a reason to invite knowledgeable people and ask them questions. However, it does not explicitly include his point that it is a platform for exploring personal curiosities, or that focusing on a niche helps listeners understand the show and helps it stand out. The cited context supports the claims it does make, and no unwarranted abstention occurs.
- **david-singleton**: The answer accurately describes involving suitable early users, showing them the product regularly, gathering feedback, and using user-focused reviews. However, it does not clearly include the recommendation to get something into users’ hands quickly, so it misses one required reference point.
- **ebi-atawodi**: The answer accurately describes maintaining a living top-10 list and incorporating stakeholder perspectives. However, it does not cover the reference’s specific point that product, design, data, and engineering partners should meet to review, discuss, and prioritize the problems together. The claims it does make are supported by the provided context, and it does not improperly claim that any detail is missing.
- **gergely**: The answer gives relevant, evidence-supported advice about using deadlines and focus techniques. However, it does not clearly state the key recommendation to tell others when they can expect the work, creating an external commitment and accountability. Referring generally to readers’ expectations and a publication schedule falls short of explicitly covering that point.
- **gustaf-alstromer**: The answer accurately conveys that people who don’t use a product are often busy or indifferent, rather than rejecting the founders. However, it omits Alströmer’s advice that founders can reach out again later, especially after making improvements.
- **gustav-söderström**: The answer is supported by the cited context: Söderström warns teams to distinguish resistance to change from genuine problems and to avoid judging a rewrite before its necessary pieces can be evaluated. But it omits the central mistake in the expected answer: becoming precious about a rewrite after investing heavily in it, rather than changing course when data disproves the hypothesis. It does not claim that this information is unavailable, so abstention is not at issue.
- **jen-abel-20**: The answer accurately covers partner fit, honest product expectations, and using partners for feedback and guidance, with claims supported by the cited context. However, it omits the reference point about setting pricing expectations and defining a clear early-partner discount to avoid anchoring future expansion. It does not make an unsupported claim that pricing guidance was absent.
- **jessica-livingston**: The answer accurately reports Livingston’s advice to pay attention to subtle cues, especially whether founders get along, and its cited sources support treating flags as prompts to investigate rather than automatic reasons to reject. It omits her suggestions to notice whether founders understand their product and seem defensive, and to ask how co-founders met or whether they have worked together before.
- **nir-eyal**: The answer accurately explains that procrastination is an emotion-regulation problem and gives grounded advice to notice the internal trigger and use the 10-minute rule. However, it omits the recommendation to put the intended work on the calendar, and it does not mention the other suggested tools, such as surfing the urge or reimagining the task. It does not make an inappropriate claim that any information is unavailable.
- **shreyas-doshi-live**: The answer accurately explains that a decision that looks reversible may be hard to undo in practice, and supports this with the feature-build commitment and QBR context. However, it does not explicitly cover that the decision can leave the team committed to further ongoing work and add to the PM leader’s workload—the second expected point.
- **teaser_2021**: The answer covers the difficult stretch between starting and finishing, repeated setbacks, getting back up, persevering, and seeking feedback. However, it incorrectly attributes the claim that the messy middle is “99%” of the process to Sahil Bloom; that point is stated by Greg Isenberg in the cited context. Bloom does describe the stretch as running between where you start and finish and emphasizes pushing through setbacks. No relevant detail is claimed to be missing.

## Validation and next experiment

- Local backend suite: 69 passed. Git whitespace check passed.
- Original evaluation reports are preserved; intermediate runs and raw judgments are separate.
- The default initial answer context remains 2,000 tokens; no larger-budget answer experiment has been run.
- This development subset has been inspected during implementation; use held-out questions and a full-corpus rerun before generalizing.
- Larger contexts cannot recover evidence absent from the candidate pool, and do not guarantee the model will use every detail.

For later controlled budget comparisons, reuse the saved ranked evidence:

```powershell
.\.venv\Scripts\python.exe -m evals.evidence_selection --answers --budget 4000 --reuse-ranked-from evidence_v4_2000
.\.venv\Scripts\python.exe -m evals.evidence_selection --answers --budget 6000 --reuse-ranked-from evidence_v4_2000
```

Run from `backend`. These commands are documented for later use; they have not been executed.
