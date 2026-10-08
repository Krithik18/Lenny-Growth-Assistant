"""Workspace skills: short descriptions for routing, instructions for execution."""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

SkillName = Literal["podcast-qa", "ship30-essay", "simple-artifact"]


@dataclass(frozen=True)
class Skill:
    name: SkillName
    mode: Literal["chat", "essay", "code"]
    description: str
    path: Path | None = None

    def instructions(self) -> str:
        return self.path.read_text(encoding="utf-8") if self.path else ""


def _load(name: SkillName, mode: Literal["essay", "code"]) -> Skill:
    path = Path(__file__).parent / name / "SKILL.md"
    metadata = yaml.safe_load(path.read_text(encoding="utf-8").split("---", 2)[1])
    if metadata["name"] != name or not metadata["description"].strip():
        raise ValueError(f"Invalid workspace skill: {name}")
    return Skill(name, mode, metadata["description"], path)


@lru_cache
def registry() -> dict[SkillName, Skill]:
    # Q&A delegates to the existing retrieval and evidence-validated answer
    # providers. Its grounding instructions remain in those providers.
    skills = [
        Skill("podcast-qa", "chat", "Answer questions, explain ideas, summarize or compare podcast insights, "
              "and give product, growth, startup or leadership advice with source citations. "
              "The default for informational questions; does not create a standalone document or tool."),
        _load("ship30-essay", "essay"),
        _load("simple-artifact", "code"),
    ]
    return {skill.name: skill for skill in skills}


def catalog() -> list[dict[str, str]]:
    return [{"name": skill.name, "description": skill.description} for skill in registry().values()]
