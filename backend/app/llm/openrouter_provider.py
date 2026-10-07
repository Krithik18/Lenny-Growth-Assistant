"""Llama answers grounded in supplied evidence through OpenRouter."""

import json
import logging

from pydantic import ValidationError

from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openai_provider import INSTRUCTIONS
from app.schemas.answer import GroundedAnswer


logger = logging.getLogger(__name__)
ERROR_MESSAGE = "OpenRouter answer was incomplete, refused, or failed evidence validation."
OUTPUT_RULES = """JSON format example ONLY (replace all example text and citations with supported evidence):
{"coverage":"complete","insufficient_evidence":false,"summary":"Supported summary",
"summary_citation_ids":["S1"],"sections":[{"heading":"Supported topic",
"content":"Claim supported by S1.","citation_ids":["S1"]}],"missing_topics":[]}
Final JSON checklist, checked by the server:
- Use actual JSON booleans true/false, never strings such as "false".
- Choose coverage AFTER checking every part of the question against the evidence.
  complete: insufficient_evidence=false, missing_topics=[], nonempty cited sections.
  partial: insufficient_evidence=true, nonempty missing_topics, nonempty cited sections.
  unsupported: insufficient_evidence=true, nonempty missing_topics, sections=[], summary_citation_ids=[].
- For a mixed supported/unsupported question, answer the supported parts and use partial.
  One unavailable part must not erase supported answers to the other parts.
- Write cited sections first; then summarize only those sections. Every summary citation ID
  must also occur in a section's citation_ids. Cite only supplied IDs, never an empty ID.
- Never create a section for an evidence gap: put the gap only in missing_topics.
- Attribute each claim to the speaker in its cited passage. Episode guest metadata does not
  make every statement in that episode the guest's statement. Do not transfer another guest's
  views to the person requested in the question. Preserve qualifications and uncertainty.
- Keep sections focused on the question; do not add unrelated frameworks or extra missing topics.
Return only the JSON object. Do not add fields, fences, or prose outside it."""


class AnswerValidationError(ValueError):
    """Static validation feedback safe to log and send on a repair attempt."""


class RefusedAnswer(AnswerValidationError):
    """A refusal must not trigger a repair attempt."""


def validate_answer(result, sources):
    if not isinstance(result, dict) or "error" in result:
        raise AnswerValidationError("Return a completed chat response containing the requested JSON object.")
    choices = result.get("choices")
    if not isinstance(choices, list) or len(choices) != 1:
        raise AnswerValidationError("Return exactly one answer containing the requested JSON object.")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise AnswerValidationError("Return a completed answer containing the requested JSON object.")
    message = choice.get("message")
    if choice.get("finish_reason") == "content_filter" or (isinstance(message, dict) and message.get("refusal")):
        raise RefusedAnswer("refused")
    if choice.get("finish_reason") != "stop":
        raise AnswerValidationError("The answer was incomplete. Return a shorter, complete JSON object.")
    if not isinstance(message, dict) or message.get("tool_calls"):
        raise AnswerValidationError("Return JSON content directly; do not call tools.")
    content = message.get("content")
    if not isinstance(content, str):
        raise AnswerValidationError("Return the requested JSON object as message content.")
    try:
        answer = GroundedAnswer.model_validate_json(content, strict=True)
    except ValidationError as error:
        details = []
        for issue in error.errors(include_input=False, include_url=False):
            if issue["loc"] == ("insufficient_evidence",) and issue["type"] == "bool_type":
                details.append('Write "insufficient_evidence":false or "insufficient_evidence":true without quotes around the value.')
            if issue["type"] == "extra_forbidden":
                details.append("Remove all extra fields, including question; return only the six schema fields.")
        raise AnswerValidationError(
            "Match the supplied JSON schema exactly. Use JSON booleans, the coverage values "
            "complete/partial/unsupported, arrays of strings for citation IDs and missing topics, "
            "and no extra fields. " + " ".join(dict.fromkeys(details))
        ) from None
    if answer.insufficient_evidence != (answer.coverage != "complete"):
        raise AnswerValidationError("Set insufficient_evidence=false only for complete coverage; otherwise true.")
    if bool(answer.missing_topics) != (answer.coverage != "complete"):
        raise AnswerValidationError("Use missing_topics=[] for complete coverage and actual unanswered topics otherwise.")
    if any(not topic.strip() for topic in answer.missing_topics):
        raise AnswerValidationError("Every missing topic must be nonempty text describing an unanswered part.")
    if answer.coverage == "unsupported":
        if answer.sections or answer.summary_citation_ids:
            raise AnswerValidationError("Unsupported coverage requires empty sections and summary_citation_ids.")
        answer.summary = "The retrieved podcast passages do not provide enough evidence to answer this question."
    else:
        if not answer.summary.strip() or not answer.sections or not answer.summary_citation_ids:
            raise AnswerValidationError("Complete and partial answers require a summary, cited sections, and summary citations.")
        section_ids = {citation for section in answer.sections for citation in section.citation_ids}
        if not set(answer.summary_citation_ids) <= section_ids:
            raise AnswerValidationError("Every summary citation must also occur in a supporting section's citation_ids.")
        if any(not section.heading.strip() or not section.content.strip() or
               not section.citation_ids or not set(section.citation_ids) <= sources.keys()
               for section in answer.sections):
            raise AnswerValidationError("Every section needs a nonempty heading, content, and only supplied source IDs.")
    return answer


class OpenRouterAnswerProvider:
    model = "meta-llama/llama-3.1-8b-instruct"

    def __init__(self, client: OpenRouterClient):
        self.client = client

    async def answer(self, question, sources) -> GroundedAnswer:
        if not sources:
            return GroundedAnswer(
                coverage="unsupported", insufficient_evidence=True,
                summary="No indexed podcast evidence was found for this question.",
                summary_citation_ids=[], sections=[], missing_topics=[question],
            )
        system = INSTRUCTIONS + "\nJSON Schema:\n" + json.dumps(GroundedAnswer.model_json_schema()) + "\n" + OUTPUT_RULES
        evidence = json.dumps({"question": question, "evidence": [
            {"id": key, "title": value.title, "guest": getattr(value, "guest", None), "text": value.text}
            for key, value in sources.items()
        ]})
        feedback = ""
        for attempt in range(2):
            # Regenerate from the original evidence; never feed unvalidated claims back as facts.
            try:
                result = await self.client.post("chat/completions", {
                    "model": self.model, "max_tokens": 1800,
                    "response_format": {"type": "json_object"},
                    "provider": {"require_parameters": True},
                    "messages": [
                        {"role": "system", "content": system + feedback},
                        {"role": "user", "content": evidence},
                    ],
                })
            except TimeoutError:
                raise ProviderError(ERROR_MESSAGE) from None
            try:
                return validate_answer(result, sources)
            except RefusedAnswer:
                raise ProviderError(ERROR_MESSAGE) from None
            except AnswerValidationError as error:
                logger.warning("OpenRouter answer validation attempt %s failed: %s", attempt + 1, error)
                feedback = "\nPrevious output failed server validation: " + str(error) + (
                    "\nRegenerate the entire answer from the original evidence. Recheck each requested part "
                    "and each claim's speaker attribution. Do not invent facts or change citations just to pass validation."
                )
        raise ProviderError(ERROR_MESSAGE) from None
