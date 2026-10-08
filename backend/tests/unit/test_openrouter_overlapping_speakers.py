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
