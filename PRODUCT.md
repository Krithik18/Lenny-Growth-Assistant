# Product Requirements Document — Lenny Growth Assistant

## Overview

The Lenny Growth Assistant is an AI-powered web application built using transcripts from **Lenny's Podcast**.

It allows users to ask product, growth, startup, and leadership questions and receive answers grounded in podcast content.

The application can also generate Ship30-style essays and lightweight artifacts.

## Problem

Lenny's Podcast contains a large amount of useful information, but manually searching through episodes takes time.

This project makes that information easier to access through a conversational AI interface.

## Goals

- Answer questions using podcast transcripts
- Show sources for grounded answers
- Support OpenAI and OpenRouter
- Automatically route requests to the correct skill
- Generate essays and artifacts
- Keep the interface simple

## Main Features

### Grounded Q&A
Users can ask questions and receive answers based on relevant transcript chunks.

### Provider Selection
Users can switch between **OpenAI** and **OpenRouter**.

### Automatic Routing
The backend automatically selects between:

- Q&A
- Ship30 Essay
- Artifact Generation

### Essay Generation
Users can generate structured essays using retrieved podcast evidence.

### Artifact Generation
The application can generate:

- Markdown
- HTML
- JavaScript
- Python
- CSS
- JSON
- Text

## User Flow

1. User enters a request
2. User selects a provider if needed
3. Backend selects the correct skill
4. Podcast evidence is retrieved when required
5. The LLM generates the response
6. The response is validated
7. The answer, sources, or artifact are displayed

## Tech Requirements

- **Frontend:** Vite + Vanilla JavaScript
- **Backend:** FastAPI
- **Database:** Supabase PostgreSQL + pgvector
- **AI Providers:** OpenAI and OpenRouter
- **RAG:** Hybrid retrieval, reranking, and grounded generation
- **Deployment:** Docker + Railway

## Success Criteria

The project is successful if:

- Podcast questions return grounded answers
- Sources are shown correctly
- Both providers work
- Skill routing works
- Essays and artifacts can be generated
- Unsupported questions are handled properly
- The application runs locally and in production

## Limitations

- Limited to the supplied Lenny's Podcast transcripts
- Retrieval may miss information for broad questions
- The RAG pipeline used with Llama is not perfect and may sometimes return less accurate or less relevant answers, although it works for the intended use case
- Different providers may produce slightly different responses
- Multi-stage RAG can increase response time
