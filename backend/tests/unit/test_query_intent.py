import pytest
from types import SimpleNamespace

from app.rag.query_intent import plan_query, lexical_queries, balance_people, supported_query


GUESTS = ["April Dunford", "April Dunford 2.0", "Brian Chesky", "Rahul Vohra",
          "Various (Year-End Review)", "Alex Smith", "Jane Smith"]


@pytest.mark.parametrize("question", [
    "What does April Dunford say about positioning?",
    "april dunford’s competitive alternatives",
    "Dunford's positioning framework",
])
def test_known_person_and_episode_variants(question):
    intent = plan_query(question, GUESTS)
    assert intent.people == ("april dunford",)
    assert intent.guests == ("April Dunford", "April Dunford 2.0")
    assert "april" not in intent.terms and "dunford" not in intent.terms


@pytest.mark.parametrize("question", ["Advice from Smith", "What happens in April?", "Unknown Person's advice", "Growth strategy"])
def test_ambiguous_or_unknown_names_do_not_scope_to_wrong_person(question):
    assert plan_query(question, GUESTS).people == ()


def test_multiple_people_are_preserved():
    intent = plan_query("Compare Rahul Vohra and Brian Chesky on growth", GUESTS)
    assert set(intent.people) == {"rahul vohra", "brian chesky"}
    assert intent.terms == ("growth",)


def test_phrases_short_keywords_and_numbers_are_preserved_as_data():
    intent = plan_query('Explain "product-market fit" and AI at 40 percent', GUESTS)
    assert intent.phrases == ("product market fit",)
    assert "ai" in intent.terms and "40" in intent.terms
    broad, focused, phrases = lexical_queries(intent)
    assert '"ai"' in broad and '"40"' in focused
    assert phrases == '"product market fit"'


def test_keyword_queries_do_not_interpret_user_operators():
    broad, focused, _ = lexical_queries(plan_query('growth OR activation -retention', []))
    assert broad == '"growth" OR "activation" OR "retention"'
    assert focused == '"growth" "activation" "retention"'


def test_comparison_keeps_both_people_without_changing_passage_objects():
    rahul = SimpleNamespace(guest="Rahul Vohra", text="Survey")
    sean = SimpleNamespace(guest="Sean Ellis", text="Threshold")
    extras = [SimpleNamespace(guest="Rahul Vohra", text=str(i)) for i in range(5)]
    ranked = balance_people([rahul, *extras, sean], "Compare Rahul Vohra and Sean Ellis")
    assert ranked[0] is rahul and ranked[1] is sean
    assert len(ranked) == 7


def test_general_question_preserves_reranker_order():
    passages = [SimpleNamespace(guest="Rahul Vohra"), SimpleNamespace(guest="Sean Ellis")]
    assert balance_people(passages, "How do I measure product-market fit?") is passages


@pytest.mark.parametrize("question", [
    "What does Apryl Dunfrd recommend about competitive alternatives?",
    "What does April recommend about positioning?",
    "Dunford's advice on positioning",
])
def test_cautious_name_correction_uses_canonical_name(question):
    intent = plan_query(question, GUESTS)
    assert intent.people == ("april dunford",)
    assert "april dunford" in intent.search_question.casefold()
    assert not intent.blocked_reason


def test_full_name_does_not_get_duplicated_by_surname_correction():
    intent = plan_query("What does Brian Chesky say about designers?", GUESTS)
    assert intent.search_question.count("Brian Chesky") == 1


@pytest.mark.parametrize("prefix", ["other than", "excluding", "except", "apart from"])
def test_exclusion_does_not_become_positive_scope(prefix):
    intent = plan_query(f"Which guests {prefix} April Dunford discuss positioning?", GUESTS)
    assert intent.people == ()
    assert intent.excluded_people == ("april dunford",)
    assert set(intent.excluded_guests) == {"April Dunford", "April Dunford 2.0"}


def test_unknown_named_person_is_blocked_instead_of_borrowing_other_advice():
    intent = plan_query("What does Alexandra Exampleton recommend about positioning?", GUESTS)
    assert intent.people == ()
    assert intent.blocked_reason == "unknown_or_ambiguous_person"


def test_ambiguous_first_name_is_not_guessed():
    intent = plan_query("What does Alex recommend about pricing?", ["Alex Smith", "Alex Jones"])
    assert intent.people == ()
    assert intent.blocked_reason == "unknown_or_ambiguous_person"


def test_multi_guest_episode_identities_are_independent():
    intent = plan_query("What does John Zeratsky say about design?", ["Jake Knapp + John Zeratsky 2.0"])
    assert intent.people == ("john zeratsky",)
    assert intent.guests == ("Jake Knapp + John Zeratsky 2.0",)


@pytest.mark.parametrize("question", [
    "What is the exact weather in Mumbai tomorrow?", "What is my Supabase database password?",
    "What exact revenue will Airbnb earn in 2030?", "Who is the current head of product at every company today?",
    "What did he recommend?", "What is the atomic mass of uranium?",
])
def test_unsupported_questions_are_blocked_before_search(question):
    assert supported_query(question)[1]


def test_mixed_supported_question_preserves_survey_and_removes_weather():
    query, reason = supported_query("Explain Rahul Vohra's product-market-fit survey and tell me tomorrow's exact Mumbai weather.")
    assert reason is None
    assert "Rahul Vohra" in query
    assert "weather" not in query


@pytest.mark.parametrize("question", [
    "How can AI change product management work?", "I feel stuck at work and want career advice.",
    "Explain Richard Rumelt's strategy kernel.", "What does April recommend about positioning?",
    "Compare Brian Chesky and Dylan Field on design.",
])
def test_supported_questions_are_not_blocked(question):
    assert supported_query(question)[1] is None
