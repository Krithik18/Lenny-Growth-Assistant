# ZIP-only retrieval: implementation walkthrough

## Current state

This stage implements the ingestion and retrieval foundation as code. At the user's request,
no tests, import, embedding calls, or database migration were run. PyYAML and tiktoken are
declared dependencies; dependency installation was not run in this stage either.
Runtime correctness and retrieval quality are therefore unverified.

The source was inspected read-only to understand its format: it contains 303 transcript
members with YAML frontmatter and timestamped speaker turns. Scripts, Git data, indexes,
and README files in the archive are not knowledge sources and are never executed.

OpenAI is the planned default, but no embedding adapter or answer-generating model is
implemented in this stage. The provider-neutral interface is ready for OpenAI first and
Ollama later. There is no public retrieval endpoint yet.

## 1. Approved source: ingestion/source.py and fetch.py

The only accepted source is:

`C:/Users/91990/OneDrive/Desktop/lennys-podcast-transcripts.zip`

SHA-256: `5915e40e36e0511a3befc5aa22c3ed37ba4f4e0d9971367332810da71a817bf6`

`read_transcripts()` verifies the checksum, then reads only `episodes/<guest>/transcript.md`
members. It does not extract files or follow links. A relocated byte-identical copy is allowed;
another ZIP is rejected. Changing the approved corpus requires an explicit source change.
Size bounds, duplicate detection, and path checks protect the reader from malformed archives.

## 2. Parsing: ingestion/parser.py

`parse_transcript()` normalizes line endings, uses `yaml.safe_load` to parse frontmatter,
validates episode fields, and takes text after the `## Transcript` heading. Metadata is stored
as metadata; embeddings will use transcript text. No instruction inside a transcript controls
the application. A content hash makes changes identifiable.

Source metadata can contain mistakes. For example, one inspected sample has a video duration
shorter than its transcript timestamps. The importer preserves source values and does not
guess replacements or invent timestamped video links. Source links are not fetched.

## 3. Chunking: ingestion/chunker.py

`TranscriptChunker` uses the cl100k_base tokenizer to target at most 700 tokens per chunk,
with an overlapping suffix of up to approximately 100 tokens. It prefers paragraph boundaries
when available and falls back to smaller text ranges for long paragraphs. Slices are made on
Python character boundaries so Unicode characters remain intact.

Every chunk retains its exact transcript substring, character offsets, token count, and
observed speaker/timestamp labels. A single speaker is recorded only when the observed range
has one speaker; otherwise it is null. Timestamp-only turns inherit the last named speaker.
The end timestamp is the last observed label, not an estimated audio end time. Character
offsets are the authoritative passage boundaries. Sponsor sections remain in the source.

The chunking version includes algorithm, tokenizer, target size, and overlap. Changing these
settings creates a separate chunk set rather than rewriting passages used by old citations.
The tokenizer may download its vocabulary on first use; that is a tokenizer resource, not
additional knowledge. Provider adapters must later enforce their own input limits as well.

## 4. Persistence: ingestion/pipeline.py

An explicit import command creates an `ingestion_runs` record and processes episodes:

```text
Approved ZIP member
  → Parse and chunk
  → Find/create episode
  → Find/create archive-specific transcript revision
  → Insert that revision's chunk set if absent
  → Mark revision ready and make it active in the same transaction
```

One episode is one transaction. If saving it fails, its changes roll back. Previously
committed episodes remain, and a repeat import skips existing chunk sets. An advisory lock
prevents overlapping imports from concurrently creating the same episode. An incomplete
existing chunk set is reported rather than silently overwritten.

Archive provenance is stored in `episode_revisions.source_archive_sha256`. The older
`source_commit` columns contain the archive checksum for ZIP imports, not a Git commit.
The original member path is stored in the existing `repository_path` field.

A revision marked `ready` means its text/chunks are ready. It does not imply that embeddings
exist. Import counts and sanitized errors are stored in `ingestion_runs`. An abruptly killed
process can leave a run marked running; rerunning creates a new run and reuses committed work.

## 5. Separate embeddings: models and 0002_zip_retrieval.py

The prepared Alembic migration adds `chunk_embeddings`, archive provenance, and character
offsets. It does not remove the legacy vector columns or copy vectors of unknown provenance.
The new code never searches those legacy fields.

```text
transcript_chunks: one copy of passage text
  ├── chunk_embeddings: OpenAI provider/model/dimensions/input version
  └── chunk_embeddings: Ollama provider/model/dimensions/input version
```

The database prevents duplicate embeddings for the same chunk/configuration. RLS and the
existing private-schema restrictions also apply to the new table. Existing records without
the approved archive checksum are excluded from retrieval.

## 6. Embedding interface and indexing: rag/embeddings.py, rag/indexing.py

An `EmbeddingProvider` supplies its configuration and two methods:

- `embed_documents(texts)`: one vector per chunk, in the same order.
- `embed_query(question)`: a compatible question vector.

The adapter owns any model-specific document/query prefixes. Its `input_version` must change
when preprocessing changes. Provider, model, dimension count, and input version identify a
compatible embedding space; equal dimensions alone do not imply compatibility.

`embed_pending_chunks()` selects missing vectors in batches, closes the database read session,
calls the provider, checks result count/dimensions/finite nonzero values, then saves a batch
in a new transaction. It resumes by skipping saved vectors. Repeated concurrent indexers can
make duplicate provider calls, but the uniqueness constraint prevents duplicate stored rows;
run one indexing worker initially. The returned count is processed inputs, not billable usage.

This code cannot generate vectors until an actual provider adapter is implemented.

## 7. Retrieval: rag/retrieval.py and schemas/retrieval.py

```text
Question
  → Provider embeds the question
  → Restrict vectors to exactly matching provider/model/dimensions/input version
  → Compare cosine distance
  → Restrict passages to approved ZIP + active revision + chunking version
  → Return top-k original passages with source metadata
```

The compatible-vector query is a materialized CTE so vectors with another dimension count
are excluded before calculating distance. This is exact search with a configuration index,
not an approximate vector index; optimize after measuring the corpus and selecting models.

Results contain text, IDs, archive member/checksum, source URL, offsets, timestamps, and cosine
similarity. Similarity is a ranking measure, not a confidence probability. The first version
has no calibrated relevance cutoff or reranker; even weak matches can be returned. With no
compatible embeddings, results are empty. These limitations belong in later retrieval tests.

No answer is generated, and no transcript text is treated as a system instruction. Answer
generation and its independent evaluation suite remain later stages.

## Prepared commands — not run in this stage

From `backend`, after reviewing the process:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m alembic upgrade head
.\.venv\Scripts\python.exe -m app.ingestion --limit 5
# Later, omit --limit to import all approved transcripts.
```

The import command writes text and chunks to Supabase but makes no embedding calls.
The expected migration revision is now `0002_zip_retrieval`. Until it is applied, a restarted
API correctly reports `migration_required` from `/health/ready`; `/health/live` still works.

After review, separately evaluate retrieval with questions and known relevant passages.
Only after retrieval is satisfactory should answer generation and answer testing be added.
