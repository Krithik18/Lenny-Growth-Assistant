# Backend development

Requires Python 3.11 or newer. Run these PowerShell commands from the backend folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

No environment activation or model API credentials are required to start the API.
Visit http://127.0.0.1:8000/docs for interactive API documentation.

Endpoints:

- `GET /health/live`: confirms the API responds.
- `GET /health/ready`: checks database connectivity and the expected migration revision.
  Returns 503 with `not_configured`, `unavailable`, or `migration_required` until ready,
  then 200 with `{"status":"ready","database":"ready"}`. It does not check model providers.
- `GET /openapi.json`: generated API schema.

To customize configuration, copy `.env.example` to `.env` if `.env` does not already exist.
Settings load from `backend/.env`; environment variables take precedence.
`CORS_ORIGINS` must be a JSON array of exact allowed frontend origins.
The initial CORS configuration supports bearer-token headers, not cross-origin cookies.

Run checks:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
```

See [DATABASE.md](DATABASE.md) for the database structure, configuration, and migration flow.
See [RAG.md](RAG.md) for the tested ZIP-only retrieval pilot and OpenAI integration.
Migration 0002 is applied; the five-episode pilot is indexed. Local POST endpoints
`/api/v1/rag/retrieve` and `/api/v1/rag/ask` separate retrieval from answer generation.
Authentication, chat CRUD routes, and Ollama remain future stages.
