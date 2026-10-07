"""Offline identity/context analysis; does not pretend to score claim support."""
from collections import Counter
import json
from pathlib import Path
from statistics import mean, median

from app.rag.query_intent import normalize, guest_name

SOURCE = Path(__file__).with_name("results") / "openrouter_retrieval_40_2026-10-07.json"


def identity_match(passage, people):
    text = " " + normalize(passage["text"]) + " "
    return guest_name(passage["guest"]) in people or any(" " + person + " " in text for person in people)


def main():
    report = json.loads(SOURCE.read_text(encoding="utf-8"))
    if len(report["cases"]) != 40 or len(report["results"]) != 80 or not report.get("finished_utc"):
        raise RuntimeError("Wait for all forty paired cases to finish.")
    runs = {(run["case_id"], run["enhanced"]): run for run in report["results"]}
    analysis = {"method": "Identity-scope and evidence availability checks, not semantic accuracy or answer grading.",
                "cases": [], "summary": {}}
    for case in report["cases"]:
        expected = [normalize(person) for person in case["expected_people"]]
        recognized = report["query_plans"][case["id"]]["people"]
        item = {"id": case["id"], "question": case["question"], "category": case["category"],
                "expected_people": expected, "recognized_people": recognized,
                "resolution_complete": bool(expected) and set(expected) <= set(recognized)}
        for enhanced, label in ((False, "original"), (True, "improved")):
            run = runs[(case["id"], enhanced)]
            context = list(run.get("context", {}).values())
            direct = {guest_name(p["guest"]) for p in context} & set(expected)
            outside = sum(not identity_match(p, expected) for p in context) if expected else None
            item[label] = {"error": run.get("error"), "seconds": run["seconds"],
                "context_passages": len(context), "outside_expected_identity": outside,
                "expected_guests_in_context": sorted(direct),
                "all_expected_guests_in_context": bool(expected) and set(expected) <= direct,
                "top_five_guests": [p["guest"] for p in run.get("passages", [])[:5]],
                "api_failures": sum(call.get("success") is False for call in run["api_calls"]),
                "rerank_attempts": sum(call["path"] == "rerank" for call in run["api_calls"])}
        item["flags"] = []
        if expected and not item["resolution_complete"]:
            item["flags"].append("Requested identity was not fully resolved; inspect spelling, ambiguity, or archive availability.")
        if case["category"] == "negated_entity" and recognized:
            item["flags"].append("Excluded person became the positive search scope: negation handling failure.")
        if len(expected) > 1 and not item["improved"]["all_expected_guests_in_context"]:
            item["flags"].append("Not every requested guest has a direct episode passage in the packed context.")
        if case["category"] in ("out_of_domain", "unanswerable", "ambiguous", "time_sensitive", "exhaustive_request"):
            item["flags"].append("Retrieval may return related passages; answer-stage scope/abstention is not tested here.")
        analysis["cases"].append(item)
    known = [case for case in analysis["cases"] if case["expected_people"] and case["category"] != "unknown_entity"]
    comparisons = [case for case in known if len(case["expected_people"]) > 1]
    calls = [call for run in report["results"] for call in run["api_calls"]]
    summary = analysis["summary"]
    summary.update(question_count=40, retrieval_runs=80,
        known_person_questions=len(known), fully_resolved_known_person_questions=sum(case["resolution_complete"] for case in known),
        paired_comparisons=len(comparisons), upstream_calls=len(calls),
        upstream_failed_attempts=sum(call.get("success") is False for call in calls),
        api_paths=dict(Counter(call["path"] for call in calls)),
        reported_cost=sum((call.get("usage") or {}).get("cost", 0) or 0 for call in calls),
        index_coverage=report["index_coverage"], post_run_index_coverage=report["post_run_index_coverage"])
    for label in ("original", "improved"):
        summary[label] = {"successful_runs": sum(not case[label]["error"] for case in analysis["cases"]),
            "nonempty_contexts": sum(case[label]["context_passages"] > 0 for case in analysis["cases"]),
            "median_seconds": round(median(case[label]["seconds"] for case in analysis["cases"]), 2),
            "mean_seconds": round(mean(case[label]["seconds"] for case in analysis["cases"]), 2),
            "outside_expected_identity_passages": sum(case[label]["outside_expected_identity"] for case in known),
            "total_person_question_context_passages": sum(case[label]["context_passages"] for case in known),
            "comparisons_with_all_direct_guests": sum(case[label]["all_expected_guests_in_context"] for case in comparisons)}
    SOURCE.with_name(SOURCE.stem + "_analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    lines = ["# Forty-question OpenRouter retrieval evaluation", "",
        "Forty distinct questions were run through both the original and improved retrieval paths: 80 real retrieval runs. "
        "Each used live OpenRouter BGE-M3 embeddings, Voyage reranking, and the same transcript archive. "
        "No Llama answers were generated. This tests the evidence selected for Llama, not answer correctness.", "",
        f"Known-person questions fully resolved: {summary['fully_resolved_known_person_questions']} / {summary['known_person_questions']}. "
        "Identity membership includes direct guest episodes and explicit full-name mentions; it is not proof that a passage supports a claim.", "",
        "| Measure | Original | Improved |", "| --- | ---: | ---: |"]
    for name, key in (("Successful retrieval runs", "successful_runs"), ("Nonempty answer contexts", "nonempty_contexts"),
                      ("Median seconds", "median_seconds"), ("Mean seconds", "mean_seconds"),
                      ("Passages outside requested identities (known-person questions)", "outside_expected_identity_passages"),
                      ("Total context passages for known-person questions", "total_person_question_context_passages"),
                      ("Comparisons with all requested guests' own episodes in context", "comparisons_with_all_direct_guests")):
        lines.append(f"| {name} | {summary['original'][key]} | {summary['improved'][key]} |")
    lines.extend(["", f"Recorded upstream calls: {summary['upstream_calls']}; failed attempts: {summary['upstream_failed_attempts']}. "
        "Retries can recover failed attempts, so these are separate from failed retrieval runs. "
        f"Reported API cost: ${summary['reported_cost']:.6f} (only costs returned in API usage metadata).", "",
        "## Each question", "", "Outside-ID counts below measure identity scope only. A dash means no specific person was requested.", "",
        "| # | Question | Original outside-ID / context | Improved outside-ID / context | Flags |", "| --- | --- | --- | --- | --- |"])
    for index, case in enumerate(analysis["cases"], 1):
        counts = [f"{case[label]['outside_expected_identity'] if case[label]['outside_expected_identity'] is not None else '—'} / {case[label]['context_passages']}" for label in ("original", "improved")]
        flags = " ".join(case["flags"]).replace("|", "/") or "—"
        question = case["question"].replace("|", "/")
        lines.append(f"| {index} | {question} | {counts[0]} | {counts[1]} | {flags} |")
    lines.extend(["", "## Evidence spot checks", "",
        "These are manual observations from selected passages, rather than an automated answer-accuracy score:", "",
        "- The Rahul threshold question puts his survey passage first, including the three disappointment options and the less-than/more-than-40-percent observation.",
        "- Teresa's opportunity-solution-tree question retrieves her explanation of the outcome, opportunity, and solution branches.",
        "- The Sean Ellis Lookout question retrieves the antivirus-first repositioning and onboarding discussion.",
        "- The Spanish survey question retrieves Rahul's three response options in the second passage. This provides relevant evidence without proving that Llama would answer correctly in Spanish.",
        "- The Brian Chesky quote question retrieves his distinction between micromanagement and being in the details.",
        "- The four-person question puts direct episode passages from Teresa, Sean, Ronny, and April in the first four positions.",
        "- The NPS question retrieves Judd Antin's criticism of the metric. The AI question retrieves relevant product-team material, but an introductory/promotional passage ranks first.",
        "- The Bill Carr process question includes customer-first and PR/FAQ evidence. Its second passage also contains a large Wix sponsor segment, reducing useful evidence per context token.",
        "- The first-name-only and fully misspelled April requests are not recognized as a person scope. Semantic search nevertheless retrieves April material; this should not be counted as complete identity-resolution failure or guaranteed success.",
        "- The excluded-person question incorrectly becomes an April-positive scope. It retrieves some other guests who explicitly mention April, but excludes other potentially relevant guests and also admits April's own passages.",
        "- The unknown-person query returns positioning material from real guests without any evidence establishing the invented requested identity. An answer must not transfer that advice to the unknown person.", "",
        "## Execution notes", "",
        "The evaluation resumed from 45 saved runs after a Windows/OneDrive checkpoint-write error. Completed saved pairs were preserved; "
        "missing pairs were run using the same retrieval code and archive. Checkpoints now use atomic replacement. "
        "API-call totals and returned-cost totals cover the saved runs; any in-flight calls lost during that interruption are not included. "
        "Archive coverage was unchanged at the end.", "",
        "## Limits", "",
        "Person recognition is based on archive names and unique surnames. Misspellings, ambiguous first names, unknown people, "
        "and negated names require separate handling. A person's name in a passage can be a third-party reference. "
        "A relevant episode can include unrelated sections or another speaker. None of these identity counts measures semantic correctness.", "",
        "Keyword matching uses English stemming; the Spanish question tests multilingual semantic retrieval but does not establish multilingual keyword quality. "
        "Weather, private credentials, future facts, ambiguous requests, and exhaustive requests require answer-stage restrictions. "
        "The retriever returns candidate evidence and does not itself establish whether those requests are answerable.", "",
        "The paired runs shared a live database and API. Timing includes network variability, query contention, and cache warmth, "
        "and should not be treated as a controlled speed benchmark. Full passages, packed contexts, query plans, and API-call metadata "
        "are saved in the accompanying JSON files. No production retrieval changes were made during this evaluation."])
    SOURCE.with_suffix(".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
