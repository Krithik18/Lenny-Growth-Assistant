# Backend development

Requires Python 3.11 or newer. Run these PowerShell commands from the backend folder:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

No environment activation or API credentials are required for this initial setup.
Visit http://127.0.0.1:8000/docs for interactive API documentation.

Endpoints:

- `GET /health/live`: confirms the API responds.
- `GET /health/ready`: reports API-only readiness. Database and model providers are not connected or checked yet.
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

Other modules are placeholders for later database, authentication, RAG, and model integrations.
