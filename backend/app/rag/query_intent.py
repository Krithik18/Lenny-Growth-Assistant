"""Deterministic query intent from archive identities; no generated search facts."""

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata


STOP = set("a an the and or but how what why when where who which is are was were do does did can could should would will to of for from in on at with by as it its their me tell explain describe give question suggest suggests according about compare between versus vs s say says recommend recommends based podcast guests other than excluding except apart without discuss".split())
DOMAIN = set("product products growth grow growing customer customers user users startup startups company companies business work working backwards career quit job team teams leadership leader leaders design designers discovery experiment experiments experimentation pricing price value strategy strategic positioning differentiation competitive alternatives onboarding activation retention acquisition monetization revenue survey surveys pmf nps ai podcast episode transcript marketing sales founder founders feedback decision decisions hiring roadmap virality innovation culture collaboration metrics learning airbnb amazon superhuman lookout b2b saas loyalty trust research interview interviews manager managers pm improve building build success details opportunity solution tree goals values productivity motivation burnout conflict disagreement negotiation health emotions calm pressure mindset".split())


def normalize(value):
    value = unicodedata.normalize("NFKC", value).casefold().replace("’", "'")
    return " ".join(re.findall(r"[^\W_]+", value, re.UNICODE))


def guest_name(value):
    # Episode variants retain the identity, e.g. April Dunford 2.0.
    value = re.sub(r"\s*\([^)]*\)|\s+\d+(?:\.\d+)*\s*$", "", value or "").strip()
    name = normalize(value)
    if name.startswith(("various", "unknown")) or len(name.split()) < 2:
        return ""
    return name


@dataclass(frozen=True)
class QueryIntent:
    people: tuple[str, ...]
    guests: tuple[str, ...]
    terms: tuple[str, ...]
    phrases: tuple[str, ...]
    excluded_people: tuple[str, ...] = ()
    excluded_guests: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()
    search_question: str = ""
    blocked_reason: str | None = None


def supported_query(question, *, strict_only=False):
    """Gate clear unsupported requests, preserving supported clauses in mixed queries."""
    if re.search(r"\b(?:database password|api key|access token|private credentials)\b", question, re.I):
        return "", "private_information"
    if re.search(r"\b(?:current|today)\b", question, re.I) and re.search(r"\b(?:head of|ceo|employment|every company)\b", question, re.I):
        return "", "current_facts"
    if re.search(r"\b(?:exact revenue|will .{0,50}earn|forecast .{0,30}revenue)\b", question, re.I):
        return "", "future_forecast"
    if normalize(question) in ("what did he recommend", "what did she recommend", "what did they recommend", "what are the three options"):
        return "", "ambiguous_reference"
    clauses = re.split(r"\s+and\s+|[;\n]", question, flags=re.I)
    relevant = [clause for clause in clauses if not re.search(r"\b(?:weather|temperature forecast|lottery numbers|sports score)\b", clause, re.I)]
    if not relevant:
        return "", "out_of_domain"
    supported = " and ".join(relevant).strip()
    if (not strict_only and not set(normalize(supported).split()) & DOMAIN
            and not re.search(r"\b[A-Z][a-z]+\s+[A-Z][a-z]+\b", supported)
            and not re.search(r"\b(?:what does|how does|according to|advice from)\s+\w+", supported, re.I)):
        return "", "out_of_domain"
    return supported, None


def name_catalog(catalog):
    names = {}
    for guest in catalog:
        # Multi-guest episodes give each person their own identity alias.
        for part in re.split(r"\s*(?:\+|&| and )\s*", guest or ""):
            name = guest_name(part)
            if name:
                names.setdefault(name, []).append(guest)
    return names


def plan_query(question, catalog, *, domain_checked=False):
    search_question, blocked = (question, None) if domain_checked else supported_query(question)
    names = name_catalog(catalog)
    question = search_question or question
    normalized = " " + normalize(question) + " "
    matches = [name for name in names if " " + name + " " in normalized]
    # A surname is usable only if it uniquely identifies an archive guest.
    surnames = {}
    for name in names:
        surnames.setdefault(name.split()[-1], []).append(name)
    for surname, identities in surnames.items():
        if len(identities) == 1 and len(surname) > 3 and " " + surname + " " in normalized:
            matches.extend(identities)
    aliases = {name: name for name in matches}
    for surname, identities in surnames.items():
        if len(identities) == 1 and len(surname) > 3 and " " + surname + " " in normalized:
            aliases[surname] = identities[0]
    words = normalize(question).split()
    # Correct two-word misspellings only when both names agree and the winner
    # clearly beats the next archive identity. Never use broad fuzzy surnames.
    for left, right in zip(words, words[1:]):
        alias = left + " " + right
        if left in STOP or right in STOP or min(len(left), len(right)) < 3:
            continue
        candidates = []
        for name in names:
            pieces = name.split()
            if len(pieces) != 2:
                continue
            a, b = SequenceMatcher(None, left, pieces[0]).ratio(), SequenceMatcher(None, right, pieces[1]).ratio()
            score = (a + b) / 2
            if (a >= .72 and b >= .78 and score >= .83) or (a >= .6 and b == 1 and score >= .8):
                candidates.append((score, name))
        candidates.sort(reverse=True)
        if candidates and (len(candidates) == 1 or candidates[0][0] - candidates[1][0] >= .08):
            name = candidates[0][1]
            matches.append(name)
            aliases[alias] = name
    # First names need explicit person grammar, rather than calendar/month usage.
    for match in re.finditer(r"\b(?:what does|how does|according to|advice from)\s+([\w]+)(?=\s+(?:recommend|suggest|say|approach|on|think)|['’]s)", question, re.I):
        alias = normalize(match.group(1))
        identities = [name for name in names if name.split()[0] == alias]
        if len(identities) == 1:
            matches.append(identities[0])
            aliases[alias] = identities[0]
    excluded = []
    for alias, name in aliases.items():
        occurrence = re.search(r"\b" + re.escape(alias) + r"\b", normalize(question))
        if occurrence and re.search(r"(?:other than|excluding|except|apart from|not|without)\s*$", normalize(question)[:occurrence.start()]):
            excluded.append(name)
    people = tuple(name for name in dict.fromkeys(matches) if name not in excluded)
    excluded = tuple(dict.fromkeys(excluded))
    corrected = question
    for alias, name in sorted(aliases.items(), key=lambda item: -len(item[0])):
        if alias != name and " " + name + " " not in " " + normalize(corrected) + " ":
            corrected = re.sub(r"\b" + r"\s+".join(re.escape(w) for w in alias.split()) + r"\b", name, corrected, flags=re.I)
    for person in excluded:
        corrected = re.sub(r"\b(?:other than|excluding|except|apart from|without|not)\s+" + re.escape(person), "", corrected, flags=re.I)
    corrected = " ".join(corrected.split())
    # Explicit unknown/ambiguous person requests cannot borrow another guest's advice.
    unresolved = []
    for match in re.finditer(r"\b(?:what does|how does|according to|advice from)\s+([\w]+(?:\s+[\w]+){0,2}?)\s+(?:recommend|suggest|say|think|approach|on)\b", question, re.I):
        alias = normalize(match.group(1))
        if not set(alias.split()) & DOMAIN and not any(alias == a or " " + a + " " in " " + alias + " " for a in aliases):
            unresolved.append(alias)
    if unresolved and not people:
        blocked = "unknown_or_ambiguous_person"
    person_words = {word for person in (*people, *excluded, *aliases) for word in person.split()}
    terms = tuple(dict.fromkeys(word for word in normalize(question).split()
                               if word not in STOP | person_words and (len(word) > 1 or word.isdigit())))[:24]
    phrases = tuple(dict.fromkeys(normalize(match) for match in re.findall(r'["“]([^"”]{2,100})["”]', question)))[:4]
    return QueryIntent(people, tuple(dict.fromkeys(guest for name in people for guest in names[name])), terms, phrases,
        excluded, tuple(dict.fromkeys(guest for name in excluded for guest in names[name])),
        tuple(unresolved), corrected, blocked)


def lexical_queries(intent):
    # Quote every term so words such as OR cannot become query operators.
    quote = lambda value: '"' + value.replace('"', '') + '"'
    broad = " OR ".join(quote(term) for term in intent.terms)
    focused = " ".join(quote(term) for term in intent.terms[:12])
    phrases = " OR ".join(quote(phrase) for phrase in intent.phrases)
    return broad, focused, phrases


def balance_people(passages, question):
    """Keep one best-ranked passage per named guest before filling remaining slots."""
    intent = plan_query(question, [p.guest for p in passages if p.guest])
    if len(intent.people) < 2:
        return passages
    selected = []
    for person in intent.people:
        match = next((p for p in passages if person in name_catalog([p.guest])), None)
        if match is not None and match not in selected:
            selected.append(match)
    return selected + [p for p in passages if p not in selected]
