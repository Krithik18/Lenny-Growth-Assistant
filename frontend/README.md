# Growth workspace

From the repository root, start the existing backend:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

In a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open http://127.0.0.1:5173. The development server forwards API calls to port 8000.

For one-server use, run `npm run build` in frontend, then start or restart the backend. Open http://127.0.0.1:8000; FastAPI serves the compiled workspace.

## Modes

- **Ask:** existing podcast-grounded answers with expandable source passages.
- **Essay:** grounded answer followed by Ship30-inspired synthesis into a Markdown artifact. Targets 1,100–1,400 words; insufficient evidence can produce a shorter response.
- **Create:** simple HTML demos, snippets, or Markdown documents. Does not retrieve podcast evidence or claim generated code was tested.

Artifacts support reading/preview, highlighted source, copy, and download. HTML runs inside an iframe with a unique origin and a restrictive network policy. Python and other non-HTML code are displayed, not executed. Follow-up messages include recent conversation context and artifact content.

Conversation history and artifacts are stored locally in this browser. They are not synchronized to the database. Deleting browser data removes them; download important work. Stop cancels waiting in the browser, but an already-started model request may still finish on the server.

The composer’s model selector defaults to OpenAI. Choose Llama 3.1 8B to send `provider: "openrouter"`; OpenAI sends `provider: "openai"`. The selection applies to Ask, Essay, Create, and retries, and resets to OpenAI when the page reloads.

The backend requires DATABASE_URL and the selected provider’s API key: OPENAI_API_KEY or OPENROUTER_API_KEY. No credentials are sent to the frontend. The API remains local-development-only; production authentication is outside this change. No deployment was performed.

## Checks

`npm run build` compiles the UI. `node tests/workspace.mjs` runs mocked browser checks against a frontend at port 5173 and captures desktop evidence without using model credits. `node tests/model-selector.mjs` checks model defaults, provider selection in all modes, retries, busy state, and mobile layout. Backend tests run with `python -m pytest tests/unit tests/integration -q` from backend.

