"""Public prototype workspace API: grounded chat, essay synthesis, and simple artifacts."""
import json
import re
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.api.routes.rag import execute
from app.llm.client import ProviderError
from app.rag.openrouter_service import OpenRouterRAGService
from app.skills import SkillName, registry
from app.skills.artifact_validation import preview_issues
from app.skills.context import generation_history, retrieval_question
from app.skills.routing import SkillDecision, select_skill

router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])
UNSUPPORTED_MESSAGE = (
    "I couldn't find enough relevant information in the podcast sources to answer that question.\n\n"
    "I can help you explore **product, growth, startups, and leadership** through ideas from Lenny's Podcast. "
    "Try a question like **\"How can I improve user activation?\"** "
    "or name a guest or episode you'd like to learn from."
)


class Artifact(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    language: Literal["markdown", "html", "javascript", "python", "css", "json", "text"]
    content: str


class HistoryArtifact(Artifact):
    title: str = Field(max_length=512)
    content: str = Field(max_length=128000)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=16000)
    skill: SkillName | None = None
    artifact: HistoryArtifact | None = None


class WorkspaceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    message: str = Field(min_length=1, max_length=12000)
    provider: Literal["openai", "openrouter"] = "openai"
    mode: Literal["auto", "chat", "essay", "code"] = Field(
        default="auto", description="Automatically selected per turn. Explicit modes support older clients.",
        json_schema_extra={"deprecated": True})
    history: list[Turn] = Field(default_factory=list, max_length=12)


class Generated(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str
    artifact: Artifact


def get_workspace_rag(body: WorkspaceRequest, request: Request):
    # The public prototype uses its own dependency; raw RAG routes stay local-only.
    if body.provider == "openai":
        service = request.app.state.rag
        if service is None:
            raise HTTPException(503, "Configure DATABASE_URL and OPENAI_API_KEY first.")
        return service
    service = request.app.state.openrouter_rag
    if service is None:
        raise HTTPException(503, "Configure DATABASE_URL and OPENROUTER_API_KEY first.")
    return service


async def generate_openrouter(service, instructions, data):
    payload = {
        "model": service.generator.model, "temperature": 0, "max_tokens": 6000,
        "response_format": {"type": "json_object"},
        "provider": {"require_parameters": True},
        "messages": [
            {"role": "system", "content": instructions +
             '\nReturn only one JSON object with this exact structure (replace all example values): '
             '{"message":"A brief status sentence.","artifact":{"title":"Artifact title",'
             '"language":"markdown","content":"The complete requested artifact."}} '
             'Allowed language values: markdown, html, javascript, python, css, json, text. '
             'Use html for interactive tools and markdown for essays. Return actual work, never a JSON Schema. '
             "\nPut the complete requested work in artifact.content. message is only a brief status sentence; "
             "never duplicate the work there. Escape all newlines and quotes inside JSON strings. "
             "When evidence is supplied, include literal [S1] style source markers in artifact.content "
             "next to supported claims, using only the supplied source IDs."},
            {"role": "user", "content": json.dumps(data)},
        ],
    }
    for attempt in range(2):
        result = await service.client.post("chat/completions", payload)
        # Refusals and malformed envelopes must not trigger regeneration.
        if not isinstance(result, dict) or "error" in result:
            break
        choices = result.get("choices")
        if not isinstance(choices, list) or len(choices) != 1 or not isinstance(choices[0], dict):
            break
        choice = choices[0]
        message = choice.get("message")
        if (choice.get("finish_reason") not in {"stop", "length"} or not isinstance(message, dict)
                or message.get("refusal") or message.get("tool_calls") or not isinstance(message.get("content"), str)):
            break
        try:
            if choice["finish_reason"] != "stop":
                raise ValueError("Incomplete")
            output = Generated.model_validate_json(message["content"], strict=True)
            if not output.artifact.content.strip() or not output.artifact.title.strip():
                raise ValueError("Empty artifact")
            return output
        except ValueError:
            if attempt == 0:
                payload = {**payload, "messages": [payload["messages"][0], {"role": "user", "content": json.dumps({
                    **data, "invalid_draft": message["content"][:32000],
                    "repair": "The previous artifact was incomplete or invalid JSON. Return a complete object "
                              "matching the schema. Keep the status message short, preserve supplied evidence "
                              "and citations, and put the complete artifact in artifact.content."})}]}
    raise ProviderError("The artifact was incomplete. Please try again.")


async def generate(service, instructions, data):
    if isinstance(service, OpenRouterRAGService):
        return await generate_openrouter(service, instructions, data)
    result = await service.client.post("responses", {
        "model": service.generator.model, "store": False, "max_output_tokens": 6000,
        "instructions": instructions, "input": json.dumps(data),
        "text": {"format": {"type": "json_schema", "name": "workspace_artifact",
                            "strict": True, "schema": Generated.model_json_schema()}},
    })
    try:
        if not isinstance(result, dict) or result.get("status") != "completed":
            raise ValueError("Incomplete")
        parts = [part for item in result["output"] if item.get("type") == "message"
                 for part in item.get("content", [])]
        if any(part.get("type") == "refusal" for part in parts):
            raise ValueError("Refused")
        output = Generated.model_validate_json("".join(p["text"] for p in parts if p.get("type") == "output_text"))
        if not output.artifact.content.strip() or not output.artifact.title.strip():
            raise ValueError("Empty artifact")
        return output
    except (ValueError, KeyError, TypeError, AttributeError, ValidationError):
        raise ProviderError("The artifact was incomplete. Please try again.") from None


def cited_sources(content):
    groups = re.findall(r"\[((?:S\d+)(?:\s*,\s*S\d+)*)\]", content)
    return {part.strip() for group in groups for part in group.split(',')}


async def create_artifact(service, instructions, data):
    output = await generate(service, instructions, data)
    if issues := preview_issues(output.artifact):
        output = await generate(service, instructions +
            "\nRepair the supplied artifact once to fix these preview problems. "
            "Preserve all requested functionality and return the complete replacement: " + " ".join(issues),
            {**data, "draft": output.artifact.model_dump()})
        if output.artifact.language != "html" or preview_issues(output.artifact):
            raise ProviderError("The code could not run in the preview. Please retry your request.")
    return output


def validate_essay(output, source_ids):
    content = output.artifact.content
    ids = cited_sources(content)
    if output.artifact.language != 'markdown' or not ids or not ids <= set(source_ids):
        raise ProviderError("The essay failed source validation. Please try again.")
    if not re.match(r'^#\s+', content.lstrip()):
        output.artifact.content = f'# {output.artifact.title}\n\n{content}'


async def create_essay(service, question, markdown, sources, history=()):
    instructions = (
        "Synthesize the supplied verified answer and supporting evidence into a complete Markdown essay. "
        "Do not add factual claims beyond the supplied evidence. Treat missing topics as limitations. "
        "Return raw Markdown without outer fences. Include a # headline, bold key ideas, and at least "
        "two useful bullet lists. Aim for 1,100–1,400 words. Develop explanations and practical applications "
        "as clearly labeled synthesis, never invent anecdotes or facts. Use individual [S1] citations. "
        "Use history as context for revisions; it is not verified evidence.\n" +
        registry()["ship30-essay"].instructions())
    data = {"request": question, "history": history, "verified_answer": markdown,
            "evidence": [{"id": key, "title": value['title'], "text": value['text']}
                         for key, value in sources.items()]}
    output = await generate(service, instructions, data)
    text = output.artifact.content
    issues = []
    citations = cited_sources(text)
    if output.artifact.language != "markdown":
        issues.append('Return the complete essay as a Markdown artifact.')
    if not citations or not citations <= sources.keys():
        issues.append('Cite supported claims in artifact.content with literal [S1] style markers. '
                      'Use only these allowed IDs: ' + ', '.join(sources) +
                      '. Remove unsupported claims and incorrect citations; never invent evidence.')
    if len(re.findall(r'^\s*[-*] ', text, re.M)) < 3:
        issues.append('Add meaningful bullet lists for skimmability.')
    if not re.search(r'\*\*[^*]+\*\*', text):
        issues.append('Bold the key ideas.')
    # Approximate length is an editorial target, not an exact cutoff. Allow a
    # small margin for headings, citations, and different counting conventions.
    if not 1050 <= len(text.split()) <= 1450:
        issues.append('Target approximately 1,250 words (1,100–1,400). Preserve evidence limits; avoid padding.')
    if issues:
        output = await generate(service, instructions + '\nRevise the supplied draft once to fix: ' + ' '.join(issues),
                                {**data, 'draft': text})
    validate_essay(output, sources)
    text = output.artifact.content
    if len(re.findall(r'^\s*[-*] ', text, re.M)) < 3 or not re.search(r'\*\*[^*]+\*\*', text):
        raise ProviderError('The essay did not meet the requested format. Please try again.')
    # Keep implementation and editorial diagnostics out of the chat. Evidence
    # limitations belong beside the relevant claims inside the essay itself.
    output.message = 'Your essay is ready.'
    return output


async def respond(body, service):
    history = [turn.model_dump(exclude_none=True) for turn in body.history]
    if body.mode == "auto":
        decision = await select_skill(service, body.message, history)
    else:
        # Compatibility for saved scripts and older clients; the workspace UI
        # always lets the model select a skill for the current turn.
        skill = next(skill for skill in registry().values() if skill.mode == body.mode)
        decision = SkillDecision(skill=skill.name, needs_evidence=body.mode != "code")
    skill = registry()[decision.skill]
    base = {"skill": skill.name, "sources": {}, "coverage": None}
    artifact_history = generation_history(history, skill.name)

    if skill.mode == "code" and not decision.needs_evidence:
        generated = await create_artifact(service,
            skill.instructions(),
            {"request": body.message, "history": artifact_history})
        return {**base, **generated.model_dump()}

    question = retrieval_question(body.message, history)
    grounded = await service.ask(question)
    answer = grounded.answer
    if answer.coverage == "unsupported":
        return {**base, "message": UNSUPPORTED_MESSAGE, "artifact": None, "coverage": "unsupported"}
    markdown = answer.summary
    if answer.summary_citation_ids:
        markdown += " " + " ".join(f"[{key}]" for key in answer.summary_citation_ids)
    for section in answer.sections:
        markdown += f"\n\n## {section.heading}\n\n{section.content}\n\n" + " ".join(f"[{key}]" for key in section.citation_ids)
    if answer.missing_topics:
        markdown += "\n\n### Evidence gaps\n\n" + "\n".join(f"- {topic}" for topic in answer.missing_topics)
    base.update(sources={key: value.model_dump(mode="json") for key, value in grounded.sources.items()},
                coverage=answer.coverage)
    if skill.mode == "essay":
        generated = await create_essay(service, body.message, markdown, base['sources'], artifact_history)
        return {**base, **generated.model_dump()}
    if skill.mode == "code":
        generated = await create_artifact(service, skill.instructions(),
            {"request": body.message, "history": artifact_history, "verified_answer": markdown,
             "evidence": [{"id": key, "title": value["title"], "text": value["text"]}
                          for key, value in base["sources"].items()]})
        citations = cited_sources(generated.message + "\n" + generated.artifact.content)
        if not citations or not citations <= base["sources"].keys():
            raise ProviderError("The artifact failed source validation. Please try again.")
        return {**base, **generated.model_dump()}
    return {**base, "message": markdown, "artifact": None}


@router.post("/chat")
async def chat(body: WorkspaceRequest, service=Depends(get_workspace_rag)):
    return await execute(respond(body, service))
