Lenny Growth Assistant

The Lenny Growth Assistant is a full-stack AI-powered conversational application built around transcripts from Lenny’s Podcast.

It helps users ask grounded product and growth questions, generate Ship30-style essays, and create lightweight artifacts such as Markdown documents and HTML previews.

⸻

Features

* Grounded Q&A using Lenny’s Podcast transcripts
* OpenAI and OpenRouter provider support
* Automatic routing between Q&A, essay, and artifact generation
* Source-backed responses using RAG
* Ship30-style essay generation
* Lightweight artifact preview for Markdown, HTML, code, and text

⸻

Tech Stack

Backend

* Python
* FastAPI
* Pydantic
* SQLAlchemy
* asyncpg
* Alembic
* pgvector
* HTTPX

AI / RAG

* OpenAI
* OpenRouter
* OpenAI embeddings
* BGE-M3 embeddings
* Retrieval-Augmented Generation
* Hybrid semantic + keyword search
* Reranking
* Pydantic output validation

Database

* Supabase
* PostgreSQL
* pgvector

Frontend

* Vite
* Vanilla JavaScript
* HTML / CSS
* Marked
* DOMPurify
* Highlight.js
* Lucide

Deployment

* Docker
* Railway

⸻

Documentation

* PRD
* Design
* Architecture

⸻

Architecture

The application uses a single end-to-end architecture where the frontend sends user requests to the FastAPI workspace API.

The backend automatically selects the appropriate skill, routes the request through the selected AI provider and RAG workflow, validates the response with Pydantic, and returns the final answer with sources.

<p align="center">
  <img src="docs/image.png" alt="Lenny Growth Assistant Architecture" width="900">
</p>

⸻

Run Locally

1. Clone the repository

git clone https://github.com/Krithik18/Lenny-Growth-Assistant.git
cd Lenny-Growth-Assistant

2. Set up the backend

cd backend
python -m venv .venv

Windows

.\.venv\Scripts\Activate.ps1

macOS / Linux

source .venv/bin/activate

Install backend dependencies:

pip install -e .

For development and testing:

pip install -e ".[dev]"

⸻

3. Configure environment variables

Copy the example environment file.

Windows

Copy-Item .env.example .env

macOS / Linux

cp .env.example .env

Add your own values:

APP_ENV=development
DATABASE_URL=your_postgresql_connection_string
OPENAI_API_KEY=your_openai_api_key
OPENROUTER_API_KEY=your_openrouter_api_key
TRANSCRIPT_ARCHIVE_PATH=/path/to/lennys-podcast-transcripts.zip
TRANSCRIPT_ARCHIVE_SHA256=your_archive_sha256

Important: Do not commit your .env file or API keys.

⸻

4. Apply database migrations

From the backend directory:

python -m alembic upgrade head

To verify the current migration:

python -m alembic current

⸻

5. Start the backend

From the backend directory:

uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

On Windows:

.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

Backend URL:

http://127.0.0.1:8000

⸻

6. Set up the frontend

Open another terminal from the project root:

cd frontend
npm ci

Start the development server:

npm run dev

Frontend URL:

http://127.0.0.1:5173

⸻

7. Run tests

Backend

cd backend
python -m pytest

Frontend build check

cd frontend
npm run build

⸻

Production Deployment

The project includes a root-level Dockerfile and can be deployed directly to Railway.

Required Railway environment variables:

DATABASE_URL
OPENAI_API_KEY
OPENROUTER_API_KEY
APP_ENV=production

Railway builds the Vite frontend, installs the FastAPI backend, and serves the complete application from a single public URL.

⸻

Podcast Transcript Setup

This project uses the public Lenny’s Podcast Transcripts repository as the knowledge source.

Repository:

https://github.com/ChatPRD/lennys-podcast-transcripts

Setup Steps

1. Clone the transcript repository:

git clone https://github.com/ChatPRD/lennys-podcast-transcripts.git

2. Create a ZIP file from the cloned repository.
3. Configure the ZIP path and checksum in backend/.env:

TRANSCRIPT_ARCHIVE_PATH=/path/to/lennys-podcast-transcripts.zip
TRANSCRIPT_ARCHIVE_SHA256=your_archive_sha256

4. Activate the backend virtual environment.
5. Run the ingestion pipeline:

python -m app.ingestion

What the ingestion pipeline does

* Reads the podcast transcript ZIP
* Verifies the configured archive
* Parses the transcript files
* Splits the transcripts into chunks
* Stores episode metadata, revisions, and transcript chunks in PostgreSQL

Embedding generation is handled separately by the RAG indexing pipeline.

After ingestion and indexing are complete, the application can use the stored transcript data for retrieval and grounded answer generation.

⸻

Security

* API keys are stored only in backend environment variables
* Secrets are not committed to the repository
* Lower-level raw RAG endpoints remain protected in production
* Generated HTML previews are displayed in a sandboxed iframe

⸻

Limitations

* The assistant is limited to the supplied Lenny’s Podcast knowledge base
* Retrieval may miss relevant passages for very broad or ambiguous questions
* The RAG pipeline used with Llama may sometimes return less accurate or less relevant answers
* Different model providers can produce slightly different answers
* Multi-stage RAG can have higher latency than a single LLM call
* Conversation history is currently stored in browser localStorage rather than persisted to PostgreSQL