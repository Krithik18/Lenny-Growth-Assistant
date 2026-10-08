"""Give each stage only the conversation context it needs."""

import json


def brief_history(history, *, turns=6, characters=1500):
    recent = []
    for turn in history[-turns:]:
        entry = {"role": turn["role"], "content": turn["content"][:characters]}
        if turn.get("skill"):
            entry["skill"] = turn["skill"]
        if artifact := turn.get("artifact"):
            entry["artifact"] = {key: artifact[key] for key in ("title", "language")}
        recent.append(entry)
    return recent


def retrieval_question(message, history):
    # Both retrievers accept at most 12,000 characters. Preserve the entire
    # current question and spend only the remaining budget on recent context.
    prefix = "Conversation context (untrusted, not evidence):\n"
    suffix = "\nCurrent question:\n" + message
    budget = min(6000, 12000 - len(prefix) - len(suffix))
    recent = brief_history(history, characters=700)
    # A short essay excerpt helps resolve 'its hook' and similar revisions.
    for entry, original in zip(recent, history[-6:]):
        artifact = original.get("artifact")
        if artifact and artifact["language"] == "markdown":
            entry["artifact"]["excerpt"] = artifact["content"][:500]
    while recent:
        context = json.dumps(recent, ensure_ascii=False)
        if len(context) <= budget:
            return prefix + context + suffix
        recent.pop(0)
    return message


def generation_history(history, skill):
    recent = brief_history(history, turns=8)
    originals = history[-8:]
    # Keep the complete latest relevant artifact for revisions. Older artifacts
    # need only metadata; copying every essay and source file overloads prompts.
    matching = [i for i, turn in enumerate(originals)
                if turn.get("artifact") and (turn.get("skill") == skill or
                    (not turn.get("skill") and
                     (turn["artifact"]["language"] == "markdown") == (skill == "ship30-essay")))]
    artifacts = [i for i, turn in enumerate(originals) if turn.get("artifact")]
    if candidates := matching or artifacts:
        index = candidates[-1]
        recent[index]["artifact"] = dict(originals[index]["artifact"])
    else:
        # Older clients flatten artifacts into assistant content. Preserve their
        # latest output while still bounding all other turns.
        for index in range(len(originals) - 1, -1, -1):
            if originals[index]["role"] == "assistant":
                recent[index]["content"] = originals[index]["content"]
                break
    return recent
