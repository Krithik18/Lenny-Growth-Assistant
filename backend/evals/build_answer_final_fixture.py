"""Freeze new generation questions against the previously reviewed source snapshots."""
import copy
import json
from pathlib import Path

ROOT = Path(__file__).parent
specs = [
    ("What can a churned customer's changed circumstances tell us, and why does Bob Moesta consider churn interviews useful?", "complete", "Changed context and struggling moments; switching does not mean the customer stopped making progress."),
    ("Does Radical Candor mean being blunt without caring? Explain Kim Scott's two dimensions and how they fit together.", "complete", "Care personally plus challenge directly; bluntness without care is obnoxious aggression."),
    ("Power users book four times more often. Why is that observation alone not actionable, and what better example does Crystal Widjaja give?", "complete", "Observation lacks context/why; high-GMV free-shipping power-user example enables a marketing decision."),
    ("What signals does Melissa Perri mention that very busy product teams aren't delivering business outcomes?", "complete", "Long hours and shipped features without moving metrics; missing linkage to business goals."),
    ("Separate Patrick Campbell's advice for failed credit cards from his advice for customers who choose to cancel.", "complete", "Payment-failure marketing funnel versus cancellation offboarding questions; do not conflate them."),
    ("Which questions help customers reconstruct a past experience, and why does Teresa Torres prefer this to hypothetical questions?", "complete", "Set scene, what happened next, summarize/listen/dig into friction; hypothetical opinions are unreliable."),
    ("A team is told to build named features by deadlines. Under Marty Cagan's distinction, what kind of team is it, and what assignment would an empowered team receive?", "complete", "Feature/output team versus customer/business problems to solve, not roadmap delivery alone."),
    ("78 of 200 respondents would be very disappointed without a product. Calculate the percentage and compare it with Rahul Vohra's 40% benchmark.", "complete", "39%, one percentage point below 40%; benchmark is a growth correlation, not a guarantee."),
    ("Give one short exact quote in which Brian Chesky explains why leaders need to know the details.", "complete", "Short verbatim detail-awareness quotation, clearly labeled as Brian's; no sponsor content."),
    ("Put Julie Zhuo's three hard-feedback tactics in order and explain why checking your intention matters.", "complete", "Mutual-feedback relationship, helpful intent, disclose nerves/vulnerability; avoid punishment/self-validation."),
    ("List the design-sprint activities in order and say what a team has at the end of the five days.", "complete", "Map, sketch, decide, prototype, test; a tested prototype and learning whether on right track."),
    ("What should Bill Carr's PR/FAQ clarify about the customer, problem and solution, and how does concentric-circle review improve it?", "complete", "Clear specific customer/problem/solution then iterative feedback through progressively wider groups."),
    ("Responde en español: ¿por qué Seth Godin recomienda elegir el público viable más pequeño y qué características hay que considerar?", "complete", "Spanish answer; customer choice shapes product/future, language/money/problem/technical facility/temperament/retention."),
    ("Did Brian Chesky eliminate all the people in product management, or change how they worked? Explain only what the passages state.", "complete", "Explicit not-all-fired correction; reassignment, smaller product-marketing group, program-management training."),
    ("Give the three product-market-fit survey response choices and the 40% benchmark, then tell me tomorrow's exact rainfall in Pune.", "partial", "Keep survey choices and growth benchmark; rainfall alone unavailable."),
    ("Which parts of a comparison between Rob Fitzpatrick and Teresa Torres can these passages support? Explain the available advice and identify the missing side.", "partial", "Teresa past-behavior/story advice supported; Rob unavailable so full comparison cannot be established."),
    ("Compare April Dunford's positioning advice with the customer-promise advice in the Jake Knapp and John Zeratsky episode.", "complete", "April beat status quo/shortlist then capabilities to value; other episode clear differentiated delivered customer promise."),
    ("Who describes the expiring-card and replacement-card prompts, and who recommends using engagement data for salvage or pause offers?", "complete", "Lenny describes prompts; Patrick describes engagement-based salvage/pause offers, not the reverse."),
    ("Based on these Kim Scott passages, who will win tomorrow's cricket match?", "unsupported", "Feedback evidence does not support a sports prediction; no unrelated business answer."),
    ("What evidence supports a precise customer-acquisition cost for this unavailable episode?", "unsupported", "Empty-source local response; no model call or invented cost."),
]
base = json.loads((ROOT / "answer_generation_fixed_sources_20.json").read_text(encoding="utf-8"))
cases = []
for index, (question, coverage, rubric) in enumerate(specs, 1):
    case = copy.deepcopy(base[index - 1])
    case.update(id=f"final-{index:02d}", question=question, expected_coverages=[coverage], rubric=rubric)
    case["source_fixture_origin"] = base[index - 1]["id"]
    cases.append(case)
target = ROOT / "answer_generation_final_sources_20.json"
if target.exists():
    raise ValueError("Final questions already frozen; preserve them.")
target.write_text(json.dumps(cases, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"Frozen {len(cases)} final questions before final API evaluation.")
