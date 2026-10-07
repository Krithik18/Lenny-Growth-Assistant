# Reranking comparison: 50-candidate cap versus 40

20 questions previously judged complete, grounded, and on topic at 4,000 context tokens. Selection uses saved pools from the prior 49-question regression, requires more than 40 candidates, and rotates across available question categories. These questions are not a random sample of all 303 transcripts.

Both arms reuse identical saved candidates. Cap 40 takes the first 40 candidates in original retrieval order before reranking; cap 50 retains the full pool (41–49 after deduplication). Both use the current reranker default of 2,400 output tokens, return the top 20, pack 4,000 transcript tokens, and generate a fresh answer. Arm order alternates by question.

This tests reranking and one answer-generation pass, using the same protocol as the earlier context-budget audit. No database search is timed and the application's optional missing-topic refinement is not included. No production candidate cap is changed.

| Measure | Cap 50 | Cap 40 |
|---|---:|---:|
| questions | 20 | 20 |
| judged | 20 | 19 |
| complete | 20 | 19 |
| complete grounded on topic | 19 | 18 |
| grounded | 19 | 18 |
| errors | 0 | 1 |
| rerank fallbacks | 0 | 0 |
| rerank retries | 0 | 0 |
| median rerank seconds | 10.77429850003682 | 10.398905500071123 |
| median stage seconds | 18.034248650074005 | 15.165577000007033 |
| exact anchor top20 | 20 | 20 |
| exact anchor context | 20 | 20 |
| point issues | {'covered': 41} | {'covered': 39} |

Paired completeness: {"unjudged_pair": 1, "complete_both": 19}

## Per-question comparison

| Question | Category | Full pool | Complete at 50 | Complete at 40 | Rerank seconds at 50 | Rerank seconds at 40 |
|---|---|---:|---|---|---:|---:|
| What practical advice does Albert Cheng offer product teams about using AI in Chess.com’s products? | practical_advice | 45 | True | False | 15.37 | 17.26 |
| How did Ami Vora use WhatsApp’s face-to-face communication metaphor to guide its product design for people around the world? | process | 45 | True | True | 12.54 | 7.95 |
| How does Asha Sharma’s team plan roadmaps and strategy amid rapid changes in AI? | process | 47 | True | True | 10.91 | 10.40 |
| According to Carilu Dietrich, what should companies do to achieve hypergrowth? | process | 43 | True | True | 9.15 | 12.02 |
| In Christina Wodtke’s OKR advice, what new-game example does she give for Q1 and Q2 planning? | example | 44 | True | True | 5.99 | 10.83 |
| What practical approach does Dan Shipper recommend for helping engineering teams keep product copy on-brand without sending every edit to a single editor? | practical_advice | 49 | True | True | 12.03 | 8.18 |
| How does Deb Liu explain treating product growth as a “game of inches,” and why does she favor shipping many small experiments over waiting for a perfect plan? | explanation | 45 | True | True | 15.85 | 7.02 |
| In Elena Verna’s description of Lovable’s hiring culture, what do high agency and autonomy mean in practice? | definition | 43 | True | True | 16.88 | 11.66 |
| According to Evan LaPointe, what is the tradeoff between leaning into your strengths and ignoring your weaknesses on a team? | tradeoff | 46 | True | True | 15.51 | 12.71 |
| In Dr. Fei-Fei Li’s discussion of Marble’s uses, how did virtual production teams say it affected movie production time? | fact | 43 | True | True | 4.02 | 8.63 |
| What mistake does Airtable co-founder Howie Liu caution companies that predate GenAI against making as they adapt to AI? | mistake | 45 | True | True | 9.64 | 11.98 |
| In Jag Duggal’s view on category design, what mistake should companies avoid when entering an established market? | mistake | 42 | True | True | 19.42 | 7.89 |
| What mistake does Lane Shackleton caution a new product manager against when borrowing team rituals? | mistake | 45 | True | True | 12.12 | 10.46 |
| In Lulu Cheng Meservey’s startup communications framework, how should founders identify and prioritize the audiences they need to reach, and what should they learn about each group? | practical_advice | 41 | True | True | 7.12 | 6.87 |
| In Melissa Perri’s discussion of product operations, what background and strengths does she recommend for someone handling customer and market research? | explanation | 43 | True | True | 19.77 | 9.38 |
| Why does Nick Turley think natural language matters for AI interfaces, while turn-by-turn chat may not be the long-term solution? | explanation | 42 | True | True | 10.64 | 15.48 |
| When improving developer experience, what tradeoff does Nicole Forsgren recommend between building tools and first talking with developers? | tradeoff | 44 | True | True | 9.40 | 9.32 |
| What tradeoff does Sam Schillace say product builders must manage while pursuing an innovative product like Google Docs? | tradeoff | 45 | True | True | 8.40 | 10.40 |
| How does Sahil Bloom describe the “messy middle” of business? | definition | 46 | True | True | 10.26 | 11.39 |
| In Tomer Cohen’s discussion of product strategy, what does he mean by a “minus-one-to-one” product? | definition | 48 | True | True | 7.93 | 9.55 |

## Answer quality issues

**albert-cheng**

- Cap 50: The answer addresses the product-team advice and its Chess.com example. Its claims are supported by the cited context, with no unsupported unavailability claim.
- Cap 40: ProviderError


**teaser_2021**

- Cap 50: The answer usefully addresses the question and covers both expected points. However, it wrongly attributes the claim that the messy middle is fun to Sahil: the context attributes that statement to Greg Isenberg, while Sahil describes the stretch as difficult and full of repeated setbacks. This attribution error makes the answer not fully grounded.
- Cap 40: The answer usefully addresses the question and covers both expected points. However, it misattributes Greg Isenberg’s comments that the messy middle is full of rises and falls and that he finds it the most fun to Sahil Bloom. Bloom’s own description is the difficult slog between starting and finishing, with repeated blows, perseverance, teamwork, and feedback. No information-unavailable claim is made.


The same model generates and judges answers using synthetic, source-verified reference excerpts. Scores are automated proxies and single-run differences may reflect model variability. Exact-anchor presence is a diagnostic, not a complete semantic relevance measurement. Raw rankings, contexts, answers, reviews, and timings are saved in each question's JSON file.

## Supplemental answer-stage retry

A failed answer-generation or evaluation stage was retried once using the exact same saved context and ranking. Original failures remain in the first-pass table above; this does not change measured reranking timings or claim the application automatically recovered.

{
  "40": {
    "failed_answer_stages_retried": 1,
    "retry_errors": 0,
    "complete_after_answer_retry": 20,
    "complete_grounded_on_topic_after_answer_retry": 19
  }
}
