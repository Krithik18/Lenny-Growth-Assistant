# Llama answer generation: progress report

Date: 8 October 2026

The Llama answer pipeline is producing useful answers across several types of question. Most tests returned valid results, although not all have completed detailed source review. It still has failures on some questions with several requested parts or tricky speaker attribution.

## Latest completed live test

The test used 20 questions with frozen podcast passages, including two unsupported controls.

| Result returned by the application | Questions |
| --- | ---: |
| Answer marked complete | 14 |
| Useful answer with an explicit evidence gap | 2 |
| Correctly declined because evidence was unavailable | 2 |
| ProviderError; no final answer delivered | 2 |
| Total | 20 |

That is **18/20 valid results (90% availability)**: 16 substantive answers and two safe unsupported results. It is not a 90% answer-accuracy score. A result marked complete can still omit an important detail or attach an imperfect citation.

Detailed source review has been completed for **13 of the 20 cases**:

| Source-review result | Questions |
| --- | ---: |
| Complete, supported substantive answer | 7 |
| Useful answer with an omission or citation limitation | 2 |
| Correct unsupported control | 2 |
| No final answer delivered | 2 |
| Returned a valid result; detailed source review pending | 7 |

The two useful but incomplete answers were labelled complete by the application. That is why the output labels and the source-review grades are reported separately. Questions 11–17 have not completed this separate source audit and are not counted as confirmed quality passes. No materially fabricated final claim was found in the completed reviewed subset.

## What is working

- **Writing from the supplied passages:** successful examples include Kim Scott's care-and-challenge framework, Crystal's distinction between an observation and an actionable insight, Melissa's signs that busy teams are not making progress, and Patrick's distinction between failed payments and voluntary cancellation.
- **Quotes and ordered explanations:** Brian Chesky's short quotation and Julie's three feedback tactics were accurate in source review. The design-sprint answer gave the five activities in order.
- **Calculations:** 78 out of 200 became 39%, correctly described as one percentage point below the passage's 40% benchmark.
- **Correcting a false premise:** the answer rejected the claim that Brian Chesky eliminated all product managers and described the changed roles and workflow.
- **Keeping supported parts of a mixed question:** the survey answer was retained while tomorrow's Pune rainfall was explicitly left unanswered. The Teresa-versus-Rob answer supplied Teresa's advice while acknowledging missing Rob evidence.
- **Avoiding invented answers in the two controls:** unrelated business passages did not become a cricket prediction, and an empty source list produced an unsupported result without an API call.
- **Output and error handling:** returned results use the existing GroundedAnswer format. Invalid responses become ProviderError, rather than being delivered as accepted answers. Citation-ID validation and bounded retry/fallback handling are covered by automated tests.

The design-sprint, false-premise and mixed-question examples above describe observed returned behavior. Their detailed independent source audit is among the seven cases still pending.

## What still needs work

Two questions failed in this run:

1. **Feature teams versus empowered teams:** the writer combined two requested answers into one array entry. The draft contained the essential distinction, but the response did not satisfy the required structure, so no final answer was delivered.
2. **Who said what about failed-card recovery:** rejected drafts attributed Lenny's expiring-card prompts to Patrick Campbell and also combined the requested answers incorrectly. This is a real attribution weakness as well as a format failure.

Other limitations already found in source review include missing details in Bob's churn interview advice and Teresa's interview advice. Teresa's answer also has one section whose citation does not cover every statement in that section, although the other supplied passage supports those statements. Some answers repeat material or closely mirror transcript wording.

## What these results measure

The writer is **meta-llama/llama-3.1-8b-instruct**, called through OpenRouter. API traces confirm the returned writer model. **Qwen plans the evidence and reviews the drafts**, so this is a Llama-and-Qwen pipeline result.

This latest run tested answer generation with frozen sources. It did not call the database, embeddings, retrieval, scope classifier or reranker. Those stages must be evaluated together in a subsequent full RAG test. The questions and passages have been reused during fixes; the source review is AI-assisted, not an independent human-annotated accuracy benchmark.

The latest automated checks passed: **119 focused tests** and **536 tests across the full backend suite**, with one existing deprecation warning. The focused tests are a subset of the full suite. These tests establish software behavior; they do not establish universal factual accuracy.

The pipeline is useful enough to continue controlled full RAG evaluation, with the two generation failures and the remaining completeness/citation issues recorded.

## Evidence

- [Latest live results and API traces](llama_generation_final_v2_20_2026-10-08.json)
- [Combined progress source-review snapshot](llama_generation_final_v2_20_2026-10-08_review.json)
- [Source review of questions 1–10](final_v2_part1_review.json)

The current provider implementation matches the tested SHA256: `c8fde0dd9fbe666f14c66e87179aab7ed88589aab3bffb17ec4ecd4331fd2fc7`.
