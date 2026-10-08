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

## Automatic skills

Describe what you want in the composer. The selected model analyzes each message and recent conversation, then chooses a skill:

- **Podcast Q&A:** grounded answers with expandable source passages.
- **Ship30 essay:** grounded answer followed by essay synthesis into a Markdown artifact. Follows the requested length, usually 200–400 words for short essays, with no minimum and a hard maximum of 1,500 words including headings and citations.
- **Simple artifact:** HTML demos, snippets, templates, or Markdown documents. Standalone tools skip retrieval; artifacts based on podcast advice retrieve evidence and validate citations.

For example, ask about activation, follow with “Turn this into an essay,” then “Build a calculator.” No skill buttons are needed. Questions about essays or code remain questions. Each turn adds one bounded routing call to the selected model. Invalid or timed-out decisions show a retryable error instead of silently executing another skill.

The frontend sends no mode. The API defaults to `mode: "auto"` and returns the selected `skill` alongside the message, artifact and sources. Explicit `chat`, `essay` and `code` modes remain available for older API clients. Reusable writing and artifact instructions live in `backend/app/skills/*/SKILL.md`; the router receives their descriptions, and generation receives the selected instructions. Podcast Q&A uses the existing grounded answer providers.

Artifacts support reading/preview, highlighted source, copy, and download. HTML runs inside an iframe with a unique origin and a restrictive network policy. Local form handlers work; form navigation and external submissions remain blocked. Python and other non-HTML code are displayed, not executed.

History carries artifacts separately from chat text. Routing receives short text and artifact metadata; retrieval receives a bounded summary that fits its 12,000-character limit and preserves the current question. Generation receives the complete most recent relevant artifact, so revisions keep source code beyond the former 16,000-character cutoff. Older clients with flattened history are still supported. HTML using unsupported preview features such as `eval`, external scripts, or browser storage gets one repair attempt before it is returned.

Conversation history and artifacts are stored locally in this browser. They are not synchronized to the database. Deleting browser data removes them; download important work. Stop cancels waiting in the browser, but an already-started model request may still finish on the server.

The composer’s model selector defaults to OpenAI. Choose Llama 3.1 8B to send `provider: "openrouter"`; OpenAI sends `provider: "openai"`. The selection applies to routing, answers, artifact generation, and retries, and resets to OpenAI when the page reloads.

The backend requires DATABASE_URL and the selected provider’s API key: OPENAI_API_KEY or OPENROUTER_API_KEY. No credentials are sent to the frontend. The API remains local-development-only; production authentication is outside this change. No deployment was performed.

## Checks

`npm run build` compiles the UI. `node tests/workspace.mjs` runs mocked browser checks against a frontend at port 5173 and captures desktop evidence without using model credits. `node tests/model-selector.mjs` checks model defaults, automatic requests, retries, busy state, and mobile layout. Backend tests run with `python -m pytest tests/unit tests/integration -q` from backend.

For live routing validation, run `python -m evals.skill_routing_live` from backend with configured provider keys. It calls only the router, not retrieval or artifact generation. Use `--providers openrouter` to check one provider or `--cases 16 17 18` to check only the routing-metadata cases. These checks spend model credits. Results are saved under `backend/evals/results`.

For real workspace validation, run `python -m evals.workspace_runtime_live --history-tests --structured-history --code-edit --output evals/results/workspace_runtime.json`. This tests retrieval and generation, including mixed conversations and older history formats. Then run `node tests/runtime-artifacts.mjs ../backend/evals/results/workspace_runtime.json` from frontend to exercise the actual generated calculators and essay previews. `node tests/runtime-conversation.mjs` checks a real browser request using the saved baseline fixtures. Live API checks use model credits; artifact preview checks reuse saved outputs.

