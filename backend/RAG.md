# RAG and OpenAI: implementation flow

## Current scope

The backend uses only the supplied transcript ZIP. All 303 transcripts parse successfully.
The live Supabase pilot contains five episodes (Ada Chen Rekhi, Adam Fishman, Brian Chesky,
Rahul Vohra, and Sean Ellis), 369 chunks, and 369 OpenAI embeddings. The other episodes
are not yet indexed. Migration `0002_zip_retrieval` is applied.

Answer generation is restricted to `gpt-6-luna`. Embeddings use `text-embedding-3-small`
with 1,536 dimensions: this model produces vectors, not answers. Ollama is deferred.
The endpoints are stateless: chat history and generated answers are not persisted yet.
Authentication is deferred, so RAG routes allow local development only and reject production mode.
Run Uvicorn on 127.0.0.1 and do not expose these routes through a public proxy.

## Import: ZIP -> transcripts -> chunks -> database

1. `app/ingestion/source.py` pins the archive path and SHA-256 checksum.
2. `fetch.py` verifies that checksum and reads only transcript members. It never executes
   archive scripts, extracts files, or fetches another knowledge source.
3. `parser.py` separates YAML episode metadata from the transcript and normalizes text.
4. `chunker.py` creates chunks of at most 400 tokens with up to 60 tokens of overlap.
   Original text, character offsets, speaker labels and observed timestamps are preserved.
5. `pipeline.py` saves episode metadata, the immutable source revision, and versioned chunks
   in transactions. Rerunning the same import skips complete existing chunk sets.
6. `rag/indexing.py` loads missing chunks, calls the embedding provider outside the transaction,
   validates vectors, then writes a batch into `chunk_embeddings`. Restarting resumes missing work.

Chunking version: `turn-char-v2-cl100k-400-60`.
Each vector records its provider, model, dimensions, and preprocessing version so incompatible
OpenAI and future Ollama vectors cannot be mixed. RLS is enabled and browser roles cannot
access the embedding table directly. The backend accesses the private `app_data` schema.

## Question -> retrieval -> answer

1. `main.py` creates the database pool and OpenAI HTTP client at startup and closes them at shutdown.
2. `api/routes/rag.py` validates a question and checks the development-only access restriction.
3. `rag/service.py` coordinates the separate retrieval and generation stages.
4. `rag/openai_embeddings.py` embeds the question with the same model used for stored chunks.
5. `rag/retrieval.py` performs exact cosine search in PostgreSQL. It filters by the approved
   archive, active episode revisions, chunking version, and compatible embedding configuration.
6. `/retrieve` returns the five highest-ranked passages with source metadata; it does not call Luna.
7. `/ask` retrieves 20 candidates. `rag/context.py` packs whole passages into a 2,000-token
   transcript budget in rank order. Metadata, question, and instructions are additional tokens.
8. `llm/openai_provider.py` sends the question and evidence to GPT-6 Luna through the Responses API
   with a strict JSON schema and `store=false`. No tools or web search are supplied.
9. The model returns `coverage` (`complete`, `partial`, or `unsupported`),
   `insufficient_evidence`, `summary`, `summary_citation_ids`, sections with citation IDs,
   and `missing_topics`. Partial answers preserve supported sections; `insufficient_evidence`
   is true whenever any requested part remains unsupported, not a signal to hide the answer.
   The server rejects unknown/missing citations, incomplete responses, or malformed answers.
   Citation metadata comes from the database, not the model. No alternative answer model is tried.
10. When topics remain unanswered, the service makes one follow-up retrieval round for at most
    two missing topics (five candidates each). It keeps the original evidence and adds at most
    2,000 transcript tokens, then calls Luna once more if new passages were found. The total
    evidence budget is at most 4,000 tokens. A failed refinement preserves the first valid answer.
    This can add up to two query embedding calls and one generation call to a request.
11. With no evidence the service abstains without calling Luna. With unrelated evidence the model
    is instructed to abstain; this behavior is tested but is not a guarantee against hallucinations.
    Unsupported responses use a fixed, factual-claim-free summary. Supported summaries require
    citations also used by their sections. The server returns the sources for all validated citations.

`llm/client.py` handles timeouts and safe errors. Provider failures return HTTP 502 and database
errors return 503. There are no automatic generation retries that could silently multiply charges.
Citation validation verifies IDs, not whether every claim is logically supported by its source.
Missing topics describe gaps in retrieved evidence, not proof of absence from the entire ZIP.

## Retrieval tests (no answer generation)

`evals/compare_chunks.py` compares three sizes on 10 labeled questions across five full episodes.
All three configurations preserve the source text and meet token limits.

| Chunk / overlap | Chunks | Expected evidence in top five | Evidence within 2,000 tokens |
|---|---:|---:|---:|
| 400 / 60 | 369 | 9 / 10 | 9 / 10 |
| 700 / 100 | 190 | 7 / 10 | 6 / 10 |
| 1000 / 150 | 126 | 7 / 10 | 5 / 10 |

400/60 is the provisional default because of evidence coverage. The 700-token option had
slightly higher MRR, so 400 is not superior on every metric. This small, source-specific test
set was used for selection; add held-out questions and a full-corpus evaluation before generalizing.
The missed question concerns the PMF survey as a leading indicator versus continued usage.

`evals/check_database_retrieval.py` independently checks the actual Supabase path, vector counts,
RLS, and the ten questions. Its exact-anchor hit rate is also 9/10.
Results: `evals/results/chunk_comparison.md`, `chunk_comparison.json`, `database_retrieval.json`.

## Answer tests (retrieval held fixed)

`evals/check_openai.py` supplies fixed gold excerpts for three questions (brand promise,
PMF response choices, and the 40% threshold), then checks an unsupported weather question.
It separately exercises both FastAPI endpoints against the populated database.
Generated outputs are saved in `evals/results/openai_answers.json` for review.
These are bounded smoke checks, not a comprehensive answer-quality score.

`evals/check_grounding.py` adds regressions for the Brian Chesky multipart question, a fixed
partial-answer case, a supported question, unrelated weather, and a request to invent facts.
Results are saved to `evals/results/grounding_regression.json` for manual evidence review.

## Run locally

From `backend`, with DATABASE_URL and OPENAI_API_KEY in `.env`:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000/docs and try either POST route:

- `/api/v1/rag/retrieve`: evidence only.
- `/api/v1/rag/ask`: structured answer and cited source passages.

Example JSON:

```json
{"question": "What three response choices does Rahul describe for the product-market-fit survey?"}
```

Reproducible commands (live scripts use network/API credits):

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m evals.compare_chunks --semantic
.\.venv\Scripts\python.exe -m evals.prepare_pilot
.\.venv\Scripts\python.exe -m evals.check_database_retrieval
.\.venv\Scripts\python.exe -m evals.check_openai
.\.venv\Scripts\python.exe -m evals.check_grounding
```

`prepare_pilot` imports the five evaluation episodes and indexes any missing chunks of the
current version. Keep it scoped to this pilot database; it will also index other approved
current-version chunks if they have already been imported.

Next stages: index/evaluate the complete archive, add held-out and adversarial answer cases,
then authenticated conversation persistence, streaming, essay/artifact modes, and Ollama.
Exact search is adequate for this pilot; larger deployments need measured index planning.

API contract reference: https://developers.openai.com/api/docs/guides/structured-outputs
