"""Opening speaker identity requires exact stored overlap, never guest metadata."""

from types import SimpleNamespace

import pytest

from app.llm.openrouter_provider import source_excerpts


def chunk(text, start, *, episode="episode-1", revision="revision-1", **overrides):
    fields = dict(text=text, start_char=start, end_char=start + len(text),
                  episode_id=episode, episode_revision_id=revision, guest="Patrick Campbell")
    fields.update(overrides)
    return SimpleNamespace(**fields)


def pair(*, donor_text=None):
    donor_text = donor_text or (
        'Lenny (00:27:00):\nThis feature tells people, "Your card is about to expire."\n\n'
    )
    opening = 'This feature tells people, "Your card is about to expire."\n\n'
    target_text = opening + 'Patrick Campbell (00:27:29):\nThanks. We handle recovery for you.'
    donor = chunk(donor_text, 100)
    target = chunk(target_text, 100 + donor_text.index(opening))
    return {"S2": donor, "S3": target}


def test_exact_same_revision_overlap_recovers_host_before_guest_turn():
    sources = pair()
    items = source_excerpts(sources)["S3"]
    assert [item["speaker"] for item in items] == ["Lenny", "Patrick Campbell", "Patrick Campbell"]
    without_overlap = source_excerpts({"S3": sources["S3"]})["S3"]
    assert [(item["id"], item["text"]) for item in items] == [
        (item["id"], item["text"]) for item in without_overlap
    ]


def test_recovery_uses_latest_explicit_donor_turn_not_episode_guest():
    sources = pair(donor_text=(
        'Patrick Campbell (00:26:34):\nA recovery funnel.\n\n'
        'Lenny (00:27:00):\nThis feature tells people, "Your card is about to expire."\n\n'
    ))
    assert source_excerpts(sources)["S3"][0]["speaker"] == "Lenny"


@pytest.mark.parametrize("field,value", [
    ("episode_id", "different-episode"),
    ("episode_revision_id", "different-revision"),
    ("episode_id", None),
    ("episode_revision_id", None),
])
def test_different_or_missing_identity_does_not_transfer_a_speaker(field, value):
    sources = pair()
    setattr(sources["S2"], field, value)
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_equal_revision_id_does_not_transfer_between_different_episodes():
    sources = pair()
    sources["S2"].episode_id = "episode-2"
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_any_mismatched_character_in_overlap_preserves_unknown_speaker():
    sources = pair()
    sources["S2"].text = sources["S2"].text.replace("expire", "delete")
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


@pytest.mark.parametrize("separation", [0, 10])
def test_adjacent_or_separated_chunks_do_not_bridge_a_gap(separation):
    sources = pair()
    target = sources["S3"]
    target.start_char = sources["S2"].end_char + separation
    target.end_char = target.start_char + len(target.text)
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_matching_text_at_different_offsets_does_not_establish_overlap():
    sources = pair()
    target = sources["S3"]
    target.start_char += 1
    target.end_char += 1
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_later_overlapping_chunk_cannot_establish_the_initial_speaker():
    sources = pair()
    sources["S2"] = chunk('Patrick Campbell (00:27:29):\nThanks. We handle recovery for you.',
                          sources["S3"].start_char + sources["S3"].text.index("Patrick Campbell"))
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_unlabeled_overlap_and_guest_metadata_do_not_invent_a_speaker():
    sources = pair()
    target = sources["S3"]
    sources["S2"] = chunk(target.text[:target.text.index("Patrick Campbell")], target.start_char)
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


@pytest.mark.parametrize("field,value", [
    ("start_char", None),
    ("start_char", True),
    ("start_char", -1),
    ("end_char", None),
    ("end_char", 101),
])
def test_invalid_stored_bounds_preserve_unknown_speaker(field, value):
    sources = pair()
    setattr(sources["S2"], field, value)
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_conflicting_explicit_donor_labels_preserve_unknown_speaker():
    sources = pair()
    target = sources["S3"]
    opening = target.text[:target.text.index("Patrick Campbell")]
    other_text = "Jane Doe (00:26:59):\n" + opening
    sources["S4"] = chunk(other_text, target.start_char - len("Jane Doe (00:26:59):\n"))
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_explicit_target_speaker_is_preserved_despite_conflicting_donor_context():
    donor_text = "Host (00:01):\nJane Doe (00:02):\nSupported advice."
    start = donor_text.index("Jane Doe")
    sources = {"S1": chunk(donor_text, 0), "S2": chunk(donor_text[start:], start)}
    assert source_excerpts(sources)["S2"][0]["speaker"] == "Jane Doe"


def test_recovery_does_not_depend_on_source_dictionary_order():
    sources = pair()
    reversed_sources = dict(reversed(list(sources.items())))
    assert source_excerpts(sources)["S3"] == source_excerpts(reversed_sources)["S3"]


CHAIN_TEXT = (
    "Patrick Campbell (00:24:00):\n"
    "alpha beta gamma delta epsilon zeta eta theta iota kappa."
)


def chain_sources():
    first_end = CHAIN_TEXT.index("epsilon")
    middle_start = CHAIN_TEXT.index("gamma")
    middle_end = CHAIN_TEXT.index("iota")
    last_start = CHAIN_TEXT.index("eta theta")
    return {
        "S1": chunk(CHAIN_TEXT[:first_end], 1000),
        "S2": chunk(CHAIN_TEXT[middle_start:middle_end], 1000 + middle_start),
        "S3": chunk(CHAIN_TEXT[last_start:], 1000 + last_start),
    }


def test_speaker_propagates_through_two_exact_overlaps_without_a_direct_anchor_overlap():
    sources = chain_sources()
    assert sources["S1"].end_char < sources["S3"].start_char
    items = source_excerpts(sources)
    assert items["S2"][0]["speaker"] == "Patrick Campbell"
    assert items["S3"][0]["speaker"] == "Patrick Campbell"
    original = source_excerpts({"S3": sources["S3"]})["S3"]
    assert [(item["id"], item["text"]) for item in items["S3"]] == [
        (item["id"], item["text"]) for item in original
    ]


def test_chain_recovery_is_independent_of_dictionary_order():
    sources = chain_sources()
    items = source_excerpts(dict(reversed(list(sources.items()))))
    assert items["S3"][0]["speaker"] == "Patrick Campbell"
    assert items == source_excerpts(sources)


@pytest.mark.parametrize("break_kind", ["mismatch", "revision", "gap"])
def test_unproven_edge_interrupts_a_chain(break_kind):
    sources = chain_sources()
    middle = sources["S2"]
    if break_kind == "mismatch":
        middle.text = middle.text.replace("eta theta", "eta wrong")
    elif break_kind == "revision":
        middle.episode_revision_id = "revision-2"
    else:
        middle.start_char += 10000
        middle.end_char += 10000
    assert source_excerpts(sources)["S3"][0]["speaker"] is None


def test_unseeded_equal_start_cycle_stays_unknown_despite_guest_metadata():
    text = "Advice with no speaker label."
    sources = {"S1": chunk(text, 1000), "S2": chunk(text, 1000)}
    assert all(item["speaker"] is None for items in source_excerpts(sources).values() for item in items)


def test_explicit_seed_resolves_a_duplicate_start_cycle():
    sources = pair()
    target = sources["S3"]
    sources["S4"] = chunk(target.text, target.start_char)
    items = source_excerpts(sources)
    assert items["S3"][0]["speaker"] == items["S4"][0]["speaker"] == "Lenny"


def conflicted_chain_sources():
    sources = chain_sources()
    original_header = "Patrick Campbell (00:24:00):\n"
    competing_header = "Jane Doe (00:24:00):\n"
    body = sources["S1"].text[len(original_header):]
    sources["S4"] = chunk(competing_header + body,
                          1000 + len(original_header) - len(competing_header))
    # This direct Patrick seed must not conceal the conflicting possibilities
    # reaching S3 through S2, where the other explicit anchor also overlaps.
    sources["S5"] = chunk(CHAIN_TEXT, 1000)
    return sources


def test_upstream_conflict_propagates_even_when_downstream_has_a_direct_seed():
    items = source_excerpts(conflicted_chain_sources())
    assert items["S2"][0]["speaker"] is None
    assert items["S3"][0]["speaker"] is None


def test_conflict_propagates_through_an_equal_start_cycle():
    sources = conflicted_chain_sources()
    target = sources["S3"]
    sources["S6"] = chunk(target.text, target.start_char)
    items = source_excerpts(sources)
    assert items["S3"][0]["speaker"] is None
    assert items["S6"][0]["speaker"] is None


def test_later_explicit_turn_overrides_a_conflicting_opening_identity():
    sources = conflicted_chain_sources()
    target = sources["S3"]
    target.text += "\n\nNew Speaker (00:25:00):\nThis is separate advice."
    target.end_char = target.start_char + len(target.text)
    items = source_excerpts(sources)["S3"]
    assert items[0]["speaker"] is None
    assert items[-1]["speaker"] == "New Speaker"


def test_long_chain_resolves_without_recursive_speaker_inference():
    header = "Patrick Campbell (00:24:00):\n"
    body = " ".join(f"word{i:03}" for i in range(90)) + "."
    whole = header + body
    sources = {"S0": chunk(whole[:whole.index("word006")], 1000)}
    for index in range(1, 21):
        start = whole.index(f"word{index * 3:03}")
        end = whole.index(f"word{index * 3 + 6:03}")
        sources[f"S{index}"] = chunk(whole[start:end], 1000 + start)
    items = source_excerpts(dict(reversed(list(sources.items()))))
    assert all(item["speaker"] == "Patrick Campbell" for excerpts in items.values() for item in excerpts)


def test_generic_heading_for_a_named_person_task_filters_other_explicit_speakers():
    from app.llm.openrouter_provider import Requirements, focus_requirement_evidence

    sources = {
        "S1": chunk("Patrick Campbell (00:25:26):\nBuild a failed-card recovery funnel.", 1000),
        "S2": chunk("Lenny (00:27:00):\nSend an expiring-card notification.", 2000),
    }
    requirements = Requirements(parts=[{"topic": "Failed-card recovery", "evidence": ["S1:E1", "S2:E1"]}])
    focused = focus_requirement_evidence(
        requirements, "What does Patrick Campbell recommend when payment cards fail?", sources
    )
    assert focused.parts[0].evidence == ["S1:E1"]
