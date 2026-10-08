# Lenny Growth Assistant — Architecture

This document describes the technical structure of the Lenny Growth Assistant, including the database schema, API endpoints, agentic routing logic, LLM provider toggle, and RAG workflow.

## Overall Architecture

The application follows a single end-to-end architecture where the frontend communicates with the FastAPI backend. The backend handles skill routing, provider selection, retrieval, generation, validation, and access to the Supabase knowledge base.

<p align="center">
  <img src="docs/image.png" alt="Lenny Growth Assistant Architecture" width="900">
</p>

The backend uses **Supabase PostgreSQL + pgvector** for transcript storage, retrieval, and provider-specific embeddings.

---

## Database Schema

The PostgreSQL schema is divided into two main areas:

- Application data
- Podcast knowledge-base data

### Application Tables

| Table | Purpose |
| --- | --- |
| `profiles` | Stores user preferences such as preferred provider and model |
| `conversations` | Represents individual chat sessions |
| `messages` | Stores user and assistant messages |
| `generations` | Records provider, model, token usage, status, and generation metadata |
| `artifacts` | Stores generated artifact metadata |
| `artifact_versions` | Stores versioned artifact content |
| `message_sources` | Connects generated answers to transcript chunks used as evidence |

### Knowledge Base Tables

| Table | Purpose |
| --- | --- |
| `episodes` | Stores podcast episode metadata |
| `episode_revisions` | Stores transcript revisions for each episode |
| `transcript_chunks` | Stores searchable sections of podcast transcripts |
| `chunk_embeddings` | Stores vector embeddings for transcript chunks |
| `ingestion_runs` | Tracks transcript ingestion runs |

### Key Relationships

- A profile can have multiple conversations.
- A conversation contains multiple messages and artifacts.
- Generations are associated with model-generated messages.
- Artifacts can have multiple versions.
- An episode can have multiple transcript revisions.
- Transcript revisions are divided into chunks.
- Each chunk can contain separate embeddings for supported providers.
- `message_sources` connects generated answers to the transcript chunks used as evidence.

### Provider-Specific Embeddings

The same transcript chunks are shared between both provider pipelines, but their vector embeddings are stored separately.

Each embedding record contains:

- provider
- embedding model
- vector dimensions
- embedding vector
- input version

The supported embedding providers are:

```text
openai
openrouter
```

This prevents vectors created by different embedding models from being mixed during similarity search.

---

## API Endpoints

### Workspace API

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/workspace/chat` | Main endpoint used by the frontend for Q&A, essay, and artifact requests |

Example request:

```json
{
  "message": "How can I improve user activation?",
  "provider": "openai",
  "mode": "auto",
  "history": []
}
```

The workspace endpoint handles:

1. Provider selection
2. Automatic skill routing
3. Retrieval when evidence is required
4. Answer, essay, or artifact generation
5. Response validation
6. Source handling

### RAG Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `POST` | `/api/v1/rag/retrieve` | Retrieves relevant transcript evidence |
| `POST` | `/api/v1/rag/ask` | Runs the direct grounded Q&A pipeline |

These are lower-level development endpoints and remain protected from direct production use.

The deployed UI communicates through `/api/v1/workspace/chat`.

### Health Endpoints

| Method | Endpoint | Purpose |
| --- | --- | --- |
| `GET` | `/health/live` | Checks whether the FastAPI process is running |
| `GET` | `/health/ready` | Checks database availability and schema readiness |

The readiness endpoint also verifies that the database migration revision matches the version expected by the application.

---

## Agentic Routing Logic

The application uses automatic skill routing so users can interact through a single chat interface without manually selecting a separate tool for each type of request.

The default mode is:

```text
auto
```

In automatic mode, the backend evaluates the current request and relevant conversation history before selecting one of the available skills.

### Grounded Q&A

Used for normal questions that should be answered using evidence from Lenny's Podcast.

Example:

```text
What are the best ways to improve user activation?
```

The system retrieves relevant transcript evidence, generates a grounded response, validates its citations, and returns the answer with its sources.

### Ship30 Essay

Used when the user requests a structured long-form essay.

The system first retrieves relevant podcast evidence and produces grounded context. That context is then passed to the Ship30 essay skill to generate a Markdown essay.

Source citations are validated before the essay is returned.

### Artifact Generation

Used when the user requests a standalone artifact such as:

- Markdown
- HTML
- JavaScript
- Python
- CSS
- JSON
- Plain text

The generated artifact is returned separately from the conversational response so that it can be displayed in the artifact viewer.

### Evidence-Aware Routing

The routing decision also determines whether podcast evidence is required.

Requests that do not depend on the podcast knowledge base can avoid unnecessary retrieval, while grounded questions, essays, or evidence-dependent artifacts use the RAG pipeline.

---

## LLM Provider Toggle

The frontend allows users to switch between:

- **OpenAI**
- **OpenRouter**

The selected provider is sent directly in the workspace request.

OpenAI:

```json
{
  "provider": "openai"
}
```

OpenRouter:

```json
{
  "provider": "openrouter"
}
```

The FastAPI backend reads this value and selects the corresponding RAG service.

### OpenAI

The OpenAI provider uses:

- OpenAI embeddings
- OpenAI retrieval configuration
- OpenAI generation model
- Structured output validation

### OpenRouter

The OpenRouter provider uses:

- BGE-M3 embeddings
- OpenRouter retrieval configuration
- OpenRouter-hosted generation models
- Structured output validation

Both providers return the same application-level response format.

This means the frontend does not require separate rendering logic when the user switches between providers.

---

## RAG Workflow

The grounded Q&A system uses a multi-stage Retrieval-Augmented Generation pipeline.

### 1. Query Embedding

The user's question is converted into an embedding using the embedding model associated with the selected provider.

Query vectors are compared only with compatible stored embeddings.

### 2. Hybrid Retrieval

The retrieval system combines:

- Semantic vector similarity search using pgvector
- PostgreSQL keyword search

This allows the application to find both semantically related passages and exact names or terms.

### 3. Reranking

Retrieved candidates are reranked before they are passed to the generation model.

This prioritizes the most relevant evidence and reduces unnecessary context.

### 4. Context Construction

The strongest transcript chunks are combined into a bounded context package for answer generation.

This keeps prompts manageable while retaining the most useful supporting evidence.

### 5. Grounded Generation

The selected LLM receives the retrieved transcript evidence and generates an answer based on that evidence.

### 6. Pydantic Validation

Both provider pipelines return the same `GroundedAnswer` structure.

Important fields include:

```text
coverage
insufficient_evidence
summary
summary_citation_ids
sections
missing_topics
```

Validation checks that:

- The response matches the expected schema
- Citation IDs refer to actual retrieved sources
- Unsupported answers do not invent evidence
- Coverage and evidence status remain consistent

### 7. Missing-Topic Retrieval

If the first generated response identifies important missing topics, the RAG service can perform one bounded follow-up retrieval.

The additional evidence is added to the existing context and the answer can then be regenerated.

The follow-up is deliberately limited to prevent uncontrolled retrieval loops.

---

## Response Structure

The workspace returns a common response format regardless of the selected provider.

A response can include:

```text
skill
provider
model
message
sources
coverage
artifact
```

Using the same response structure for both OpenAI and OpenRouter keeps the frontend independent of the underlying model provider.

---

## Production Deployment

The project is packaged using Docker and deployed on Railway.

During deployment:

- The Vite frontend is built
- The FastAPI backend is installed
- FastAPI serves both the API and the compiled frontend
- OpenAI and OpenRouter are accessed through backend API calls
- Supabase PostgreSQL + pgvector provides the knowledge database

This allows the complete application to run from a single Railway public URL.

API keys and the database connection string are supplied through environment variables and are never committed to the repository.
