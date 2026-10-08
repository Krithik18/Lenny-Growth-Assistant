"""Regression checks for focused evidence and actual user-requested gaps."""

from types import SimpleNamespace

import pytest

from app.llm.openrouter_provider import (
    AnswerPart,
    AnswerValidationError,
    Requirement,
    Requirements,
    focus_requirement_evidence,
    remove_unrequested_gaps,
)


def source(guest, text):
    return SimpleNamespace(guest=guest, text=text)


INTERVIEW_SOURCES = {
    "S1": source("Zoelle Egner", "Use a template email to invite customers to a call."),
    "S2": source("Jessica Livingston", "Podcast guests can review their interview before publication."),
    "S3": source("Matt Abrahams", "Feedback is an opportunity to solve a problem together."),
    "S4": source("Teresa Torres", "Ask about the customer's last actual experience."),
}

PAYMENT_SOURCES = {
    "S1": source(
        "Patrick Campbell",
        "Patrick Campbell (00:25:26):\nUse a marketing funnel when payment cards fail.\n\n"
        "Lenny Rachitsky (00:27:00):\nThe product tells me my payment card is about to expire.",
    ),
    "S2": source(
        "Teresa Torres",
        "Teresa Torres (00:39:57):\nAsk what a customer actually did.",
    ),
    "S3": source("Patrick Campbell", "Payment failure recovery is tactical retention."),
}


@pytest.mark.parametrize("part_type", [Requirement, AnswerPart])
def test_unrequested_evidence_guests_do_not_become_missing_user_requests(part_type):
    supported = part_type(topic="Zoelle Egner's customer interview advice", evidence=["S1:E1"],
                          **({"content": "Invite customers to a call."} if part_type is AnswerPart else {}))
    jessica = part_type(topic="Jessica Livingston's customer interview advice", evidence=[],
                        **({"content": ""} if part_type is AnswerPart else {}))
    matt = part_type(topic="Matt Abrahams' customer interview advice", evidence=[],
                     **({"content": ""} if part_type is AnswerPart else {}))

    kept = remove_unrequested_gaps(
        [supported, jessica, matt],
        "Find advice on running customer interviews from guests other than Teresa Torres.",
        INTERVIEW_SOURCES,
    )

    assert kept == [supported]
    assert isinstance(kept[0], part_type)


def test_supported_parts_are_preserved_even_without_a_named_request():
    parts = [Requirement(topic="Zoelle Egner's advice", evidence=["S1:E1"]),
             Requirement(topic="Teresa Torres's advice", evidence=["S4:E1"])]
    assert remove_unrequested_gaps(parts, "How should I interview customers?", INTERVIEW_SOURCES) == parts


def test_explicitly_requested_known_person_gap_is_preserved():
    requested = Requirement(topic="Jessica Livingston's customer interview advice", evidence=[])
    other = Requirement(topic="Matt Abrahams' customer interview advice", evidence=[])
    kept = remove_unrequested_gaps(
        [requested, other], "What does Jessica Livingston recommend about customer interviews?",
        INTERVIEW_SOURCES,
    )
    assert kept == [requested]


def test_misspelled_person_request_preserves_the_canonical_name_gap():
    requested = Requirement(topic="Patrick Campbell's failed-card recovery advice", evidence=[])
    unrelated = Requirement(topic="Teresa Torres's failed-card recovery advice", evidence=[])
    kept = remove_unrequested_gaps(
        [requested, unrelated], "What does Patrick Campbel recommend when payment cards fail?",
        PAYMENT_SOURCES,
    )
    assert kept == [requested]


def test_explicitly_requested_unknown_person_gap_is_preserved():
    unknown = Requirement(topic="Martin Parker's customer interview advice", evidence=[])
    known_unrequested = Requirement(topic="Jessica Livingston's customer interview advice", evidence=[])
    kept = remove_unrequested_gaps(
        [unknown, known_unrequested],
        "Compare Zoelle Egner's advice with Martin Parker's advice about customer interviews.",
        INTERVIEW_SOURCES,
    )
    assert kept == [unknown]


def test_nonperson_weather_gap_survives_removal_of_unrequested_guests():
    weather = Requirement(topic="Tomorrow's weather in Pune", evidence=[])
    irrelevant = Requirement(topic="Jessica Livingston's customer interview advice", evidence=[])
    kept = remove_unrequested_gaps(
        [weather, irrelevant], "Explain customer interviews and tomorrow's weather in Pune.",
        INTERVIEW_SOURCES,
    )
    assert kept == [weather]


def test_excluded_known_guest_is_not_reported_as_missing():
    excluded = Requirement(topic="Teresa Torres's customer interview advice", evidence=[])
    supported = Requirement(topic="Zoelle Egner's customer interview advice", evidence=["S1:E1"])
    kept = remove_unrequested_gaps(
        [excluded, supported], "Find customer interview advice excluding Teresa Torres.",
        INTERVIEW_SOURCES,
    )
    assert kept == [supported]


def test_misspelled_excluded_guest_is_not_reported_as_missing():
    excluded = Requirement(topic="Patrick Campbell's customer interview advice", evidence=[])
    weather = Requirement(topic="Tomorrow's weather", evidence=[])
    assert remove_unrequested_gaps(
        [excluded, weather], "Find customer interview advice other than Patrick Campbel and forecast tomorrow's weather.",
        PAYMENT_SOURCES,
    ) == [weather]


def test_missing_people_explicitly_requested_in_a_comparison_are_preserved():
    parts = [Requirement(topic="Jessica Livingston's customer interview advice", evidence=[]),
             Requirement(topic="Matt Abrahams' customer interview advice", evidence=[])]
    assert remove_unrequested_gaps(
        parts, "Compare Jessica Livingston and Matt Abrahams on customer interviews.",
        INTERVIEW_SOURCES,
    ) == parts


def test_single_named_guest_task_excludes_other_explicit_speakers():
    requirements = Requirements(parts=[Requirement(
        topic="Patrick Campbell's failed-card recovery advice",
        evidence=["S1:E1", "S1:E2", "S2:E1", "S3:E1"],
    )])
    focused = focus_requirement_evidence(
        requirements, "What does Patrick Campbell recommend when payment cards fail?", PAYMENT_SOURCES,
    )
    assert isinstance(focused, Requirements)
    assert focused.parts[0].evidence == ["S1:E1", "S3:E1"]


def test_misspelled_named_guest_still_excludes_host_implementation_details():
    requirements = Requirements(parts=[Requirement(
        topic="Patrick Campbell's failed-card recovery advice", evidence=["S1:E1", "S1:E2"],
    )])
    focused = focus_requirement_evidence(
        requirements, "What does Patrick Campbel recommend when payment cards fail?", PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S1:E1"]


def test_explicitly_requested_host_uses_his_own_labeled_evidence():
    requirements = Requirements(parts=[Requirement(
        topic="Lenny Rachitsky's expiring-card example", evidence=["S1:E1", "S1:E2"],
    )])
    focused = focus_requirement_evidence(
        requirements, "What does Lenny Rachitsky say about expiring-card prompts?", PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S1:E2"]


def test_cross_person_comparison_preserves_both_speakers():
    requirements = Requirements(parts=[Requirement(
        topic="Compare Patrick Campbell's advice with Lenny Rachitsky's example",
        evidence=["S1:E1", "S1:E2"],
    )])
    focused = focus_requirement_evidence(
        requirements, "Compare Patrick Campbell's failed-card advice with Lenny Rachitsky's prompts.",
        PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S1:E1", "S1:E2"]


def test_cross_guest_comparison_is_not_reduced_to_one_named_person():
    requirements = Requirements(parts=[Requirement(
        topic="Compare Patrick Campbell and Teresa Torres", evidence=["S1:E1", "S2:E1"],
    )])
    focused = focus_requirement_evidence(
        requirements, "Compare Patrick Campbell and Teresa Torres on customer behavior.", PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S1:E1", "S2:E1"]


def test_question_without_a_requested_person_keeps_different_speakers():
    requirements = Requirements(parts=[Requirement(
        topic="Payment failure recovery", evidence=["S1:E1", "S1:E2"],
    )])
    focused = focus_requirement_evidence(requirements, "How can I recover failed payments?", PAYMENT_SOURCES)
    assert focused.parts[0].evidence == ["S1:E1", "S1:E2"]


def test_unlabeled_evidence_is_preserved_for_a_named_task():
    requirements = Requirements(parts=[Requirement(topic="Patrick Campbell's advice", evidence=["S3:E1"])])
    focused = focus_requirement_evidence(
        requirements, "What does Patrick Campbell recommend about payment recovery?", PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S3:E1"]


def test_wrong_speaker_only_selection_requires_planner_repair_instead_of_a_false_gap():
    requirements = Requirements(parts=[Requirement(
        topic="Patrick Campbell's failed-card recovery advice", evidence=["S1:E2", "S2:E1"],
    )])
    with pytest.raises(AnswerValidationError):
        focus_requirement_evidence(
            requirements, "What does Patrick Campbell recommend when payment cards fail?", PAYMENT_SOURCES,
        )


def test_empty_weather_requirement_survives_person_focusing():
    requirements = Requirements(parts=[
        Requirement(topic="Patrick Campbell's failed-card recovery advice", evidence=["S1:E1", "S1:E2"]),
        Requirement(topic="Tomorrow's weather", evidence=[]),
    ])
    focused = focus_requirement_evidence(
        requirements, "What does Patrick Campbell recommend about failed cards, and what's tomorrow's weather?",
        PAYMENT_SOURCES,
    )
    assert focused.parts[0].evidence == ["S1:E1"]
    assert focused.parts[1].topic == "Tomorrow's weather" and focused.parts[1].evidence == []
