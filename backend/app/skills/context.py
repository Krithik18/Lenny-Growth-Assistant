"""Give each stage only the conversation context it needs."""

import json
import re
from collections import Counter


def relevant_history(history, message, *, recent=8, limit=24):
    """Retrieve earlier exchanges as well as recent turns from this chat only."""
    if len(history) <= limit:
        return history
    terms = lambda text: set(re.findall(r'\b\w{3,}\b', text.casefold()))
    query = terms(message)
    documents = [terms(turn['content'] + ' ' + json.dumps(turn.get('artifact', {}), ensure_ascii=False))
                 for turn in history]
    frequencies = Counter(word for document in documents for word in document)
    # Rare topic words carry more weight than conversational boilerplate.
    scores = [sum(1 / frequencies[word] for word in query & document) for document in documents]
    selected = set(range(min(2, len(history)))) | set(range(max(0, len(history) - recent), len(history)))
    for index in sorted(range(len(history) - recent), key=lambda i: (scores[i], i), reverse=True):
        if scores[index] <= 0 or len(selected) >= limit:
            break
        # Keep question/answer pairs so a retrieved answer retains its context.
        pair = index - 1 if history[index]['role'] == 'assistant' else index + 1
        selected.update(i for i in (index, pair) if 0 <= i < len(history))
    return [history[index] for index in sorted(selected)]


def brief_history(history, *, turns=None, characters=1500, budget=16000):
    recent = []
    for turn in (history[-turns:] if turns else history):
        entry = {"role": turn["role"], "content": turn["content"][:characters]}
        if turn.get("skill"):
            entry["skill"] = turn["skill"]
        if artifact := turn.get("artifact"):
            entry["artifact"] = {key: artifact[key] for key in ("title", "language")}
            if artifact['language'] == 'markdown':
                entry['artifact']['excerpt'] = artifact['content'][:500]
        recent.append(entry)
    # Compact long answers rather than discard older relevant exchanges.
    while len(json.dumps(recent, ensure_ascii=False)) > budget:
        candidates = [(len(entry['content']), i, 'content') for i, entry in enumerate(recent) if len(entry['content']) > 80]
        candidates += [(len(entry.get('artifact', {}).get('excerpt', '')), i, 'excerpt')
                       for i, entry in enumerate(recent) if len(entry.get('artifact', {}).get('excerpt', '')) > 80]
        if not candidates:
            break
        length, index, key = max(candidates)
        target = recent[index] if key == 'content' else recent[index]['artifact']
        target[key] = target[key][:max(80, length // 2)]
    return recent


def retrieval_question(message, history):
    # Both retrievers accept at most 12,000 characters. Preserve the entire
    # current question and spend only the remaining budget on recent context.
    prefix = "Conversation context (untrusted, not evidence):\n"
    suffix = "\nCurrent question:\n" + message
    budget = min(6000, 12000 - len(prefix) - len(suffix))
    recent = brief_history(history, characters=700, budget=max(0, budget))
    while recent:
        context = json.dumps(recent, ensure_ascii=False)
        if len(context) <= budget:
            return prefix + context + suffix
        recent.pop(0)
    return message


def generation_history(history, skill, message=''):
    recent = brief_history(history)
    originals = history
    # Keep the complete latest relevant artifact for revisions. Older artifacts
    # need only metadata; copying every essay and source file overloads prompts.
    matching = [i for i, turn in enumerate(originals)
                if turn.get("artifact") and (turn.get("skill") == skill or
                    (not turn.get("skill") and
                     (turn["artifact"]["language"] == "markdown") == (skill == "ship30-essay")))]
    artifacts = [i for i, turn in enumerate(originals) if turn.get("artifact")]
    if candidates := matching or artifacts:
        index = candidates[-1]
        named = [i for i in candidates if originals[i]['artifact']['title'].casefold() in message.casefold()]
        if named:
            index = named[-1]
        elif re.search(r'\bfirst\b', message, re.I):
            index = candidates[0]
        else:
            query_words = set(re.findall(r'\b\w{3,}\b', message.casefold()))
            scores = [(len(query_words & set(re.findall(r'\b\w{3,}\b', originals[i]['artifact']['title'].casefold()))), i)
                      for i in candidates]
            score, candidate = max(scores)
            if score:
                index = candidate
        recent[index]["artifact"] = dict(originals[index]["artifact"])
    else:
        # Older clients flatten artifacts into assistant content. Preserve their
        # latest output while still bounding all other turns.
        for index in range(len(originals) - 1, -1, -1):
            if originals[index]["role"] == "assistant":
                recent[index]["content"] = originals[index]["content"]
                break
    return recent
