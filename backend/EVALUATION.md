# Full archive indexing and evaluation

Only the checksum-pinned ZIP is used as knowledge. `gpt-6-luna` is the only text model
used for answers, test-question authoring, and automated answer review. OpenAI embeddings
use `text-embedding-3-small` at 1,536 dimensions.

## Indexing

From `backend`, using the configured `.env`:

```powershell
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -u -m evals.index_full_archive
.\.venv\Scripts\python.exe -m evals.index_status
```

The importer stores every approved archive member. Migration 0003 permits different members
to reference the same video; it preserves the original metadata and keeps repository paths
unique. The source has 303 files and 291 exact distinct transcript bodies. Exact duplicate
passages are collapsed when retrieving and building context.

Embedding work uses two disjoint UUID partitions and batches of 64. API calls happen outside
database transactions. Each validated batch is committed atomically. A restart reuses committed
vectors. Transient embedding failures have bounded retries; generation requests are not silently
retried. If text import is already complete, resume embeddings with `--skip-import`. If an import
failed for specific members, `--resume-failed` retries those from the last failed ingestion run.

`evals/results/full_index.json` is written only after all 303 files have matching chunk and
embedding counts for the active archive, chunking version, and provider configuration.

Migration 0004 adds HNSW approximate cosine search for the primary OpenAI space and GIN
English keyword search. `evals.check_search_plan` verifies the actual vector query plan.
HNSW evaluations use `retrieval_hnsw_v1` and `end_to_end_hnsw_v1` caches; the older scan-based
snapshots are kept separate. Fixed-evidence caches remain valid because that stage bypasses retrieval.

## Three separate measurements

1. **Retrieval:** one generated question per transcript, with a verified source anchor. The
   test calls the real embedding and PostgreSQL retrieval path. It measures exact anchor hits
   at 5 and 20, and in the initial 2,000-token context. Duplicate copies of valid evidence count.
2. **Answers with fixed evidence:** 40 questions selected by a deterministic hash, five from
   each requested question category. The generator gets the original reference excerpt;
   retrieval cannot explain a failure at this stage.
3. **Answers through RAG:** the same 40 questions use actual retrieval and bounded refinement.
   Another 30 authored scenario prompts cover broader behavior, including unsupported requests.

```powershell
.\.venv\Scripts\python.exe -u -m evals.full_suite generate
.\.venv\Scripts\python.exe -u -m evals.full_suite fixed-answers
# Run these only after full_index.json confirms completed indexing:
.\.venv\Scripts\python.exe -u -m evals.full_suite retrieval
.\.venv\Scripts\python.exe -u -m evals.full_suite answers
.\.venv\Scripts\python.exe -u -m evals.broad_answers
.\.venv\Scripts\python.exe -m evals.report_full_suite
```

All live commands use API credits. Successful case results are cached under the ignored
`data/full_eval` directory so interrupted evaluation can resume. These caches are run snapshots:
after changing retrieval or prompting, archive the old cache and run a fresh evaluation; do not
mix old cached results with a new implementation when making comparisons.

## Interpreting results

The source-derived questions are synthetic labels, not independently authored human gold.
Requested question categories guide generation; they are not a separately adjudicated taxonomy.
The evidence quotes are exact source substrings, but their relevance is still a fallible label.
Exact-anchor misses can retrieve alternative valid evidence and are not automatically wrong answers.

The answer reviewer is the same model family as the answering model. Its groundedness and
completeness judgments are advisory proxies, with correlated biases. Inspect saved claims against
their citations, especially failed cases and a sample of passes. A reference point may be too
strict or irrelevant to the question, so model-judged misses require interpretation.

Do not call these percentages universal accuracy. One question per file does not test every
passage, source errors remain possible, and the initial context is bounded. Current facts,
exhaustive corpus lists, unspecified conversation references, and unsupported domains require
honest limitations rather than invented answers. Dedicated artifact and essay product modes
remain separate implementation work.

The final summary is `evals/results/full_evaluation.md`, with raw cases, answers, source passages,
and judgments in the neighboring JSON files.
