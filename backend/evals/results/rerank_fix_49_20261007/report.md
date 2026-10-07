# Reranking fallback regression — 49 previously affected questions

Context budget: **2,000 tokens**. Candidate cap: **50**, unchanged. Returned evidence: top 20 before context packing.

## Results

| Measure | Result |
|---|---:|
| questions | 49 |
| first attempt valid | 33 |
| recovered on retry | 16 |
| remaining fallbacks | 0 |
| failed attempt reasons | {'incomplete_response': 16} |
| median reranking seconds | 12.173349000047892 |
| candidate count range | [33, 49] |
| anchor in top20 | 43 |
| anchor in context | 43 |

## Change

The structured response now requires exactly as many IDs as candidates and restricts IDs to the supplied range. Strict application validation still requires a complete permutation, including uniqueness and integer types. No passages are removed or fabricated to repair an invalid response.

An invalid, incomplete, timed-out, or failed response gets one retry. Incomplete responses receive a larger output allowance on retry (2,400 rather than 1,200 tokens). Refusals are not retried. Each attempt has a 30-second timeout; two exhausted attempts preserve the original candidate order. External task cancellation propagates.

## Interpretation and limits

These are the same 49 questions whose historical run fell back: 46 completed but invalid rankings, one incomplete response, one provider error, and one timeout. The original full candidate pools were not saved, so this run uses fresh retrieval and is not an identical-input paired comparison. Every current candidate pool and attempt diagnostic is saved beside this report.

This is a ranking-validity regression, not an answer-generation or completeness evaluation. Exact reference-anchor presence is a supplementary diagnostic and is not a semantic relevance score. A successful run does not guarantee that future provider failures cannot occur. Retries add latency when needed. No 40-candidate experiment was run.

Verification: 96 backend tests passed, including strict validation, retry recovery, exhausted retry preserving original evidence, full 50-candidate ordering, cancellation, and the existing 2,000-token default checks.

## Per-question results

| Question | Candidates | Attempts | Failed attempt reasons | Fallback | Seconds |
|---|---:|---:|---|---|---:|
| In Adam Fishman’s discussion of building a high-performing growth team, how should a growth leader approach prioritization and roadmapping? | 41 | 1 | None | False | 12.92 |
| What practical advice does Albert Cheng offer product teams about using AI in Chess.com’s products? | 45 | 2 | incomplete_response | False | 28.15 |
| According to Alexander Embiricos, what should founders prioritize when building AI products now that software is faster to build? | 47 | 1 | None | False | 12.65 |
| How did Ami Vora use WhatsApp’s face-to-face communication metaphor to guide its product design for people around the world? | 45 | 1 | None | False | 10.60 |
| In April Dunford’s advice on product positioning and sales pitches, what mistake do companies make when a pitch isn’t working? | 37 | 1 | None | False | 6.16 |
| How does Asha Sharma’s team plan roadmaps and strategy amid rapid changes in AI? | 47 | 2 | incomplete_response | False | 30.79 |
| In the “How marketplaces win” episode, how did Benjamin Lauzier explain choosing a market-health metric to improve marketplace liquidity, using Lyft as an example? | 37 | 1 | None | False | 13.15 |
| What example of a repeatable working-backwards process did Bill Carr describe for deciding what a company should build? | 37 | 1 | None | False | 9.50 |
| In Brandon Chu’s discussion of writing about product management, what did the act of writing help him accomplish? | 48 | 2 | incomplete_response | False | 23.38 |
| According to Carilu Dietrich, what should companies do to achieve hypergrowth? | 43 | 1 | None | False | 7.24 |
| How does Christian Idiodi recommend product managers build their skills when they lack a good coach? | 39 | 1 | None | False | 10.06 |
| In Christina Wodtke’s OKR advice, what new-game example does she give for Q1 and Q2 planning? | 44 | 2 | incomplete_response | False | 20.63 |
| In Dan Hockenmaier’s marketplace growth strategy, if a marketplace can grow GMV either by acquiring more customers or by increasing share of wallet among existing customers, which tradeoff does he favor and why? | 35 | 1 | None | False | 14.20 |
| What practical approach does Dan Shipper recommend for helping engineering teams keep product copy on-brand without sending every edit to a single editor? | 49 | 1 | None | False | 7.33 |
| How does Deb Liu explain treating product growth as a “game of inches,” and why does she favor shipping many small experiments over waiting for a perfect plan? | 45 | 2 | incomplete_response | False | 23.29 |
| What mistake does Dr. Fei-Fei Li say people make when considering the potential of world models and spatial intelligence? | 38 | 1 | None | False | 7.45 |
| In her discussion of product-led sales, how does Elena Verna recommend involving sales when developing account qualification criteria? | 38 | 2 | incomplete_response | False | 21.89 |
| In Elena Verna’s description of Lovable’s hiring culture, what do high agency and autonomy mean in practice? | 43 | 2 | incomplete_response | False | 23.63 |
| According to Evan LaPointe, what is the tradeoff between leaning into your strengths and ignoring your weaknesses on a team? | 46 | 2 | incomplete_response | False | 25.35 |
| In Dr. Fei-Fei Li’s discussion of Marble’s uses, how did virtual production teams say it affected movie production time? | 43 | 1 | None | False | 5.01 |
| What practical advice does Gustaf Alströmer give startup founders in the YC/Airbnb episode for handling customers who don’t use their product? | 44 | 1 | None | False | 12.75 |
| What mistake does Airtable co-founder Howie Liu caution companies that predate GenAI against making as they adapt to AI? | 45 | 1 | None | False | 5.24 |
| According to Itamar Gilad, how should a company choose where to start when becoming more evidence-guided? | 39 | 1 | None | False | 12.17 |
| What practical approach does Jackson Shuttleworth describe for timing Duolingo streak practice reminders? | 35 | 1 | None | False | 5.72 |
| In Jag Duggal’s view on category design, what mistake should companies avoid when entering an established market? | 42 | 1 | None | False | 9.30 |
| How does Janna Bastow recommend separating soft and hard launches to help marketing and development teams coordinate? | 38 | 1 | None | False | 7.61 |
| What tradeoff does Jason Fried recommend when introducing Shape Up at a company: adopting it wholesale or changing how teams work incrementally? | 46 | 1 | None | False | 11.01 |
| In Joe Hudson’s approach to enjoying what you’re doing, how can someone experiment with enjoying a boring meeting 10% more? | 33 | 1 | None | False | 11.67 |
| What mistake does Julie Zhuo say people often make about feedback at work? | 46 | 2 | incomplete_response | False | 28.90 |
| What practical steps does Ken Norton recommend for product managers to build the people-side leadership skills their role requires? | 46 | 2 | incomplete_response | False | 28.91 |
| What mistake does Lane Shackleton caution a new product manager against when borrowing team rituals? | 45 | 1 | None | False | 9.01 |
| What example did Logan Kilpatrick give of OpenAI employees showing high agency and urgency? | 38 | 1 | None | False | 9.79 |
| In Lulu Cheng Meservey’s startup communications framework, how should founders identify and prioritize the audiences they need to reach, and what should they learn about each group? | 41 | 1 | None | False | 11.17 |
| What practical advice does Maya Prohovnik offer managers for giving feedback and addressing underperformance? | 41 | 1 | None | False | 15.27 |
| What did Melanie Perkins learn about copying practices from larger companies as Canva grew? | 47 | 1 | None | False | 11.27 |
| In Melissa Perri’s discussion of product operations, what background and strengths does she recommend for someone handling customer and market research? | 43 | 2 | incomplete_response | False | 29.17 |
| What process does Mike Maples Jr. recommend for finding a startup idea by learning from the future? | 40 | 1 | None | False | 13.02 |
| What communication mistake does Nancy Duarte warn leaders against when sharing a vision with their teams? | 49 | 2 | incomplete_response | False | 32.26 |
| Why does Nick Turley think natural language matters for AI interfaces, while turn-by-turn chat may not be the long-term solution? | 42 | 1 | None | False | 11.19 |
| When improving developer experience, what tradeoff does Nicole Forsgren recommend between building tools and first talking with developers? | 44 | 1 | None | False | 10.95 |
| What mistaken assumption about Nikita Bier’s school-by-school growth strategy does he say founders often make? | 43 | 1 | None | False | 10.11 |
| What tradeoff does Sam Schillace say product builders must manage while pursuing an innovative product like Google Docs? | 45 | 1 | None | False | 9.20 |
| What practical advice does Sanchan Saxena give product teams for pursuing ambitious ideas when outcomes are uncertain? | 49 | 2 | incomplete_response | False | 27.74 |
| What practical advice does Shaun Clowes give product leaders for using LLMs effectively in product management? | 44 | 1 | None | False | 12.49 |
| How does Sahil Bloom describe the “messy middle” of business? | 46 | 2 | incomplete_response | False | 20.78 |
| In Todd Jackson’s product-market-fit framework, what tradeoff did Looker make by having Lloyd Tabb work closely with prospects before they became customers, and what did the approach gain? | 38 | 1 | None | False | 10.38 |
| In Tomer Cohen’s discussion of product strategy, what does he mean by a “minus-one-to-one” product? | 48 | 1 | None | False | 6.13 |
| In Vijay Iyengar’s account of Mixpanel’s planning process, what drawback did leaders accept by joining teams’ solution-discovery sessions, and what benefit made it worthwhile? | 42 | 2 | incomplete_response | False | 40.21 |
| How does Figma CPO Yuhki Yamashita distinguish a PM’s role in explaining a product’s purpose from originating its ideas and defining its details? | 46 | 2 | incomplete_response | False | 26.84 |
