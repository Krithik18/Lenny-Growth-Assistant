"""Llama writes cited sections; the application assembles their Markdown."""

import json
import re

from pydantic import BaseModel, ConfigDict, Field, StrictStr, ValidationError

from app.llm.client import ProviderError

MAX_ESSAY_WORDS = 1500


def requested_length_feedback(content, request):
    """Give one editorial correction for an explicit word target; never pad by default."""
    match = re.search(r'\b(\d[\d,]*)[\s-]+words?\b', request, re.I)
    if match:
        target = min(int(match[1].replace(',', '')), MAX_ESSAY_WORDS)
        if target > 0 and not target * .85 <= len(content.split()) <= target * 1.15:
            return (f'Match the requested length of approximately {target} words, counting headings and citations. '
                    'Keep a complete argument, source support, and conclusion; avoid padding.')
    return None


class EssaySection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    heading: StrictStr
    content: StrictStr
    source_ids: list[StrictStr]


class EssayDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: StrictStr
    sections: list[EssaySection] = Field(min_length=1, max_length=8)


async def create_llama_essay(service, instructions, data):
    allowed = {source["id"] for source in data["evidence"]}
    if not allowed:
        raise ProviderError("The essay has no verified sources. Please try again.")
    first = next(iter(source["id"] for source in data["evidence"]))
    contract = (
        '\nReturn JSON with ONLY title and sections, like '
        '{"title":"A useful headline","sections":[{"heading":"One clear idea",'
        '"content":"Markdown paragraphs with **bold key ideas** and useful bullet lists.",'
        '"source_ids":["' + first + '"]}]}. '
        'Match the requested length, using as few sections as a short essay needs. '
        'Never exceed 1,500 words including headings and citations. There is no minimum length. '
        'The first section is the hook; the final section is the takeaway and practical next step. '
        'Write the essay yourself using the supplied verified evidence. Each section must list '
        'the IDs of sources supporting its claims in source_ids. The app adds citation markers. '
        'Never return an artifact object or a JSON Schema. Do not include a status message. '
        'Use these allowed IDs: ' + ', '.join(allowed) + '.'
    )
    feedback = ""
    draft = None
    for attempt in range(2):
        result = await service.client.post("chat/completions", {
            "model": service.generator.model, "temperature": 0.1, "max_tokens": 6000,
            "response_format": {"type": "json_object"}, "provider": {"require_parameters": True},
            "messages": [{"role": "system", "content": instructions + contract + feedback},
                         {"role": "user", "content": json.dumps({**data, **({"draft": draft} if draft else {})})}],
        })
        try:
            choices = result.get("choices") if isinstance(result, dict) and "error" not in result else None
            if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
                raise ValueError("Return a completed essay JSON object.")
            message = choices[0].get("message")
            if not isinstance(message, dict) or message.get("refusal") or message.get("tool_calls"):
                raise ProviderError("The essay was incomplete. Please try again.")
            raw = message.get("content")
            draft = raw[:32000] if isinstance(raw, str) else None
            if choices[0].get("finish_reason") != "stop" or not isinstance(raw, str):
                raise ValueError("Return a complete, shorter JSON object.")
            essay = EssayDraft.model_validate_json(raw, strict=True)
            if not essay.title.strip() or any(not section.heading.strip() or not section.content.strip() for section in essay.sections):
                raise ValueError("Develop every section with a heading and complete Markdown content.")
            if any(not section.source_ids or not set(section.source_ids) <= allowed for section in essay.sections):
                raise ValueError("Every section needs supporting source_ids; use only the allowed IDs.")
            # Avoid duplicate or invented inline IDs. Structured source_ids own
            # the citation mapping, so editorial revisions cannot drop markers.
            sections = []
            for section in essay.sections:
                groups = re.findall(r"\[((?:S\d+)(?:\s*,\s*S\d+)*)\]", section.content)
                inline_ids = {source.strip() for group in groups for source in group.split(',')}
                if not inline_ids <= allowed:
                    raise ValueError("Remove unsupported claims and incorrect inline citations; recheck the original evidence.")
                content = re.sub(r"\[((?:S\d+)(?:\s*,\s*S\d+)*)\]", "", section.content).strip()
                citations = " ".join(f"[{source}]" for source in dict.fromkeys(section.source_ids))
                sections.append(f"## {section.heading}\n\n{content}\n\n{citations}")
            markdown = f"# {essay.title}\n\n" + "\n\n".join(sections)
            if not re.search(r"^\s*[-*] ", markdown, re.M) or not re.search(r"\*\*[^*]+\*\*", markdown):
                raise ValueError("Use bold key ideas and a useful bullet list; keep the requested length.")
            if len(markdown.split()) > MAX_ESSAY_WORDS:
                raise ValueError("Shorten the complete essay to at most 1,500 words including headings and citations; preserve source support.")
            if attempt == 0 and (issue := requested_length_feedback(markdown, data['request'])):
                raise ValueError(issue)
            return {"message": "Your essay is ready.", "artifact": {
                "title": essay.title, "language": "markdown", "content": markdown}}
        except (ValueError, ValidationError) as error:
            if attempt == 1:
                break
            issue = str(error) if not isinstance(error, ValidationError) else "Return only title and 1–8 sections, each with heading, content, and source_ids."
            feedback = "\nRevise the draft once: " + issue + " Recheck it against the original evidence, not just the draft."
    raise ProviderError("The essay failed source or format validation. Please try again.")
