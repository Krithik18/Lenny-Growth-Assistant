from types import SimpleNamespace

import pytest

from evals.transcript_audit import point_issue, validate_cases


@pytest.mark.parametrize("supported,retrieved,context,covered,expected", [
    (False, False, False, False, "reference_label_needs_review"),
    (True, False, False, False, "retrieval_gap"),
    (True, True, False, False, "context_selection_gap"),
    (True, True, True, False, "generation_omission"),
    (True, True, True, True, "covered"),
])
def test_audit_distinguishes_where_a_supported_point_was_lost(supported, retrieved, context, covered, expected):
    assert point_issue({"reference_supported": supported, "retrieved_supported": retrieved,
                        "context_supported": context, "answer_covered": covered}) == expected


def test_audit_requires_every_source_and_verifies_reference_text():
    cases = [{"id": str(i), "member": str(i), "evidence_quote": "known evidence",
              "excerpt": "known evidence in the transcript"} for i in range(303)]
    episodes = {str(i): SimpleNamespace(transcript="known evidence in the transcript") for i in range(303)}
    validate_cases(cases, episodes)
    with pytest.raises(ValueError):
        validate_cases(cases[:40], episodes)
    cases[0]["evidence_quote"] = "invented evidence"
    with pytest.raises(ValueError, match="source verification"):
        validate_cases(cases, episodes)
