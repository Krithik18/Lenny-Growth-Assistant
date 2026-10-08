"""Conservative request-shape detection; it never establishes answer support."""

import re
from collections.abc import Iterable

from app.rag.query_intent import normalize, plan_query


# Restrict the topic itself, rather than treating one domain keyword as permission
# to simplify an otherwise unrelated or more specific request.
_TOPIC_WORDS = set("""
product products growth grow growing customer customers user users startup startups
business businesses company companies saas b2b b2c acquisition activation retention
monetization revenue pricing price value strategy strategies strategic management
leadership team teams hiring onboarding engagement discovery research experimentation
experiment experiments testing marketing sales positioning differentiation competitive
competition market markets fit pmf plg nps survey surveys feedback roadmap roadmaps
innovation design development decision decisions metrics measurement loyalty referral
referrals virality viral conversion conversions churn funnel funnels habits habit
experience experiences lifecycle cycle cycles go to market led customer centric
productivity collaboration culture career careers problem problems solution solutions
opportunity opportunities north star metric experiment driven data driven lifetime
rate rates model models
""".split())
_CONNECTORS = {"a", "an", "the", "of", "for", "in"}
_SUBJECT_WORDS = _TOPIC_WORDS - {
    "go", "to", "led", "centric", "north", "star", "driven", "data",
}
_FORBIDDEN = re.compile(
    r"\b(?:and|or|also|then|compare|comparison|versus|vs|difference|differences|"
    r"quote|quotes|quotation|quotations|verbatim|exact|list|steps|examples|"
    r"best|most|top|effective|recommend|recommendations|calculate|calculation|"
    r"count|percent|percentage|benchmark|not|no|never|without|except|exclude|"
    r"excluding|current|currently|latest|today|tomorrow|now|forecast|weather|"
    r"arithmetic|numbers|integers|multiply|sum|ignore|previous|instructions?|"
    r"system|prompt|json|code|write|return|according|said|says|say|"
    r"he|she|they|him|her|them|his|their|my|our|your)\b",
    re.IGNORECASE,
)
_REQUEST = re.compile(
    r"^(?:please\s+)?(?:(?:can|could|would)\s+you\s+(?:please\s+)?)?"
    r"(?:explain(?:\s+to\s+me)?(?:\s+about)?|tell\s+me\s+about|describe|"
    r"what\s+(?:is|are)|"
    r"give\s+me\s+(?:a|an)\s+(?:(?:basic|simple|brief|short)\s+)?"
    r"(?:explanation|overview|introduction)\s+(?:of|to|about))\s+"
    r"(?P<topic>.+)$",
    re.IGNORECASE,
)
_LEADING_SIMPLICITY = re.compile(
    r"^(?:(?:a|an|the)\s+)?(?:(?:basic|simple|brief|short)\s+)?"
    r"(?:(?:basics|fundamentals)\s+of\s+)?",
    re.IGNORECASE,
)
_TRAILING_SIMPLICITY = re.compile(
    r"\s+(?:in\s+(?:simple|plain)\s+(?:terms|language)|"
    r"for\s+(?:a\s+)?beginners?|simply)$",
    re.IGNORECASE,
)
_CONCEPT_GROUPS = (
    {"growth", "grow", "growing"}, {"activation"}, {"retention"},
    {"acquisition"}, {"monetization"}, {"pricing", "price"}, {"leadership"},
    {"hiring"}, {"onboarding"}, {"discovery"}, {"research"},
    {"experimentation", "experiment", "experiments", "testing"},
    {"positioning"}, {"differentiation"}, {"fit", "pmf"}, {"plg"},
    {"churn"}, {"conversion", "conversions"}, {"virality", "viral"},
)


def introductory_topic(question: str, guest_catalog: Iterable[str] = ()) -> str | None:
    """Return the normalized topic of a simple unnamed introductory request.

    A match only permits a shorter planning path. The caller must still retrieve
    relevant evidence and validate the resulting explanation against those sources.
    Specific, multi-part, ambiguous and unfamiliar request shapes retain full planning.
    """
    if not isinstance(question, str) or not question.strip() or len(question) > 180:
        return None
    if any(char in question for char in "\n\r") or re.search(r"\d", question):
        return None
    text = question.strip()
    # Only a terminal politeness phrase and sentence mark may be removed. Interior
    # punctuation can separate tasks, quotation requests, or conversation history.
    text = re.sub(r"[?.!]$", "", text).strip()
    text = re.sub(r",?\s+please$", "", text, flags=re.IGNORECASE).strip()
    if re.search(r"[^A-Za-z\s-]", text) or len(text.split()) > 24:
        return None
    if _FORBIDDEN.search(text):
        return None
    intent = plan_query(text, guest_catalog, domain_checked=True)
    if intent.people or intent.excluded_people or intent.unresolved or intent.blocked_reason:
        return None
    request = _REQUEST.fullmatch(text)
    if not request:
        return None
    topic = _TRAILING_SIMPLICITY.sub("", request["topic"].strip())
    topic = _LEADING_SIMPLICITY.sub("", topic, count=1)
    words = normalize(topic).split()
    if not 1 <= len(words) <= 8 or not set(words) <= _TOPIC_WORDS | _CONNECTORS:
        return None
    if not set(words) & _SUBJECT_WORDS or words[0] in _CONNECTORS or words[-1] in _CONNECTORS:
        return None
    # Adjacent independent topics without a conjunction are still multiple tasks.
    if sum(bool(set(words) & group) for group in _CONCEPT_GROUPS) > 1:
        return None
    return " ".join(words)
