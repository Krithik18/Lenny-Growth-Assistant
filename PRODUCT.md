# Lenny Growth Assistant

## Platform
web

## Purpose
Help users explore product and growth questions using Lenny’s Podcast transcripts, synthesize essays at the requested length up to 1,500 words, and create simple code or Markdown artifacts in a chat workspace.

## Constraints
Preserve the existing grounded retrieval pipeline and source attribution. Keep the interface simple, familiar, and moderately polished, as requested. Avoid complex coding environments. Work within the user's limited usage budget.

## Implementation decisions
FastAPI serves a lightweight Vite-built frontend. Conversations and artifacts are saved in the current browser. Existing local-development access restrictions remain; production authentication is not implemented. HTML previews are isolated; other code is displayed, copied, or downloaded.

Users describe their task in one composer. The selected model chooses podcast Q&A, essay writing, or simple artifact creation for each message using skill descriptions and recent conversation context. Follow-ups can revise an artifact or switch tasks. Podcast-based artifacts retrieve evidence before generation. Routing adds one small model call per turn.

## Writing
The application loads its reusable Ship30-inspired essay skill from backend/app/skills/ship30-essay/SKILL.md. The requested essay length is a custom adaptation of the guide, and factual evidence takes priority over length.
