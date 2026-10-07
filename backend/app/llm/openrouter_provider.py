"""Llama answers grounded in supplied evidence through OpenRouter."""

import json

from app.llm.client import OpenRouterClient, ProviderError
from app.llm.openai_provider import INSTRUCTIONS
from app.schemas.answer import GroundedAnswer


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
        try:
            # This model supports JSON mode; enforce the schema locally as well.
            result = await self.client.post("chat/completions", {
                "model": self.model, "max_tokens": 1800,
                "response_format": {"type": "json_object"},
                "provider": {"require_parameters": True},
                "messages": [
                    {"role": "system", "content": INSTRUCTIONS +
                     "\nReturn only a JSON object matching this JSON Schema:\n" +
                     json.dumps(GroundedAnswer.model_json_schema())},
                    {"role": "user", "content": json.dumps({
                        "question": question, "evidence": [
                            {"id": key, "title": value.title, "text": value.text}
                            for key, value in sources.items()
                        ],
                    })},
                ],
            })
            if not isinstance(result, dict) or "error" in result:
                raise ValueError("Invalid response")
            choices = result.get("choices")
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError("Missing answer")
            choice = choices[0]
            if not isinstance(choice, dict) or choice.get("finish_reason") != "stop":
                raise ValueError("Incomplete response")
            message = choice.get("message")
            if not isinstance(message, dict) or message.get("refusal") or message.get("tool_calls"):
                raise ValueError("Refused or unexpected tool call")
            content = message.get("content")
            if not isinstance(content, str):
                raise ValueError("Missing content")
            answer = GroundedAnswer.model_validate_json(content, strict=True)
            if answer.insufficient_evidence != (answer.coverage != "complete"):
                raise ValueError("Inconsistent coverage flag")
            if bool(answer.missing_topics) != (answer.coverage != "complete"):
                raise ValueError("Inconsistent missing topics")
            if any(not topic.strip() for topic in answer.missing_topics):
                raise ValueError("Empty topic")
            if answer.coverage == "unsupported":
                if answer.sections or answer.summary_citation_ids:
                    raise ValueError("Abstention contains claims")
                answer.summary = "The retrieved podcast passages do not provide enough evidence to answer this question."
            else:
                if not answer.summary.strip() or not answer.sections or not answer.summary_citation_ids:
                    raise ValueError("Missing answer or summary citations")
                section_ids = {citation for section in answer.sections for citation in section.citation_ids}
                if not set(answer.summary_citation_ids) <= section_ids:
                    raise ValueError("Summary references unsupported sources")
                if any(not section.heading.strip() or not section.content.strip() or
                       not section.citation_ids or not set(section.citation_ids) <= sources.keys()
                       for section in answer.sections):
                    raise ValueError("Missing or unknown citations")
            return answer
        except (KeyError, TypeError, ValueError, TimeoutError):
            raise ProviderError(
                "OpenRouter answer was incomplete, refused, or failed evidence validation."
            ) from None
