"""Reproducible ZIP-only pilot. Structural checks are not semantic retrieval scores.

Run from backend: python -m evals.compare_chunks [--semantic]
Semantic mode uses OpenAI embeddings and local exact cosine search, not hosted DB writes.
"""

import argparse
from collections import Counter
from dataclasses import asdict
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import time

from dotenv import dotenv_values
import httpx

from app.ingestion.fetch import read_transcripts
from app.ingestion.parser import parse_transcript
from app.ingestion.chunker import TranscriptChunker
from app.ingestion.source import ARCHIVE_SHA256

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "results"
CONFIGS = [(400, 60), (700, 100), (1000, 150)]
MODEL = "text-embedding-3-small"
BUDGET = 2000


def embedding_vectors(texts, key):
    cache_dir = ROOT / "data" / "embedding_eval_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    vectors = [None] * len(texts)
    missing = []
    for i, value in enumerate(texts):
        digest = hashlib.sha256((MODEL + "|1536|" + value).encode()).hexdigest()
        path = cache_dir / (digest + ".json")
        if path.exists():
            vectors[i] = json.loads(path.read_text())
        else:
            missing.append((i, value, path))
    usage = 0
    with httpx.Client(timeout=90, trust_env=False) as client:
        for offset in range(0, len(missing), 32):
            batch = missing[offset:offset + 32]
            response = None
            for attempt in range(4):
                response = client.post("https://api.openai.com/v1/embeddings", headers={"Authorization": f"Bearer {key}"}, json={
                    "model": MODEL, "dimensions": 1536, "input": [entry[1] for entry in batch],
                })
                if response.status_code not in (429, 500, 502, 503, 504):
                    break
                time.sleep(2 ** attempt)
            if response.status_code != 200:
                raise RuntimeError(f"Embedding API returned HTTP {response.status_code}; no response body logged.")
            payload = response.json()
            data = sorted(payload["data"], key=lambda entry: entry["index"])
            if len(data) != len(batch):
                raise ValueError("Embedding count mismatch")
            for (i, _, path), entry in zip(batch, data, strict=True):
                vector = entry["embedding"]
                if len(vector) != 1536 or not all(math.isfinite(v) for v in vector):
                    raise ValueError("Invalid embedding vector")
                norm = math.sqrt(sum(v * v for v in vector))
                if norm == 0:
                    raise ValueError("Zero embedding vector")
                vector = [v / norm for v in vector]
                vectors[i] = vector
                path.write_text(json.dumps(vector), encoding="utf-8")
            usage += payload.get("usage", {}).get("total_tokens", 0)
    return vectors, usage


def coverage(selected, case, episodes):
    body = episodes[case["member"]].transcript
    anchor = case["anchor"]
    occurrences = []
    position = body.find(anchor)
    while position != -1:
        occurrences.append((position, position + len(anchor)))
        position = body.find(anchor, position + 1)
    best = 0.0
    for start, end in occurrences:
        intervals = sorted((max(start, c["start_char"]), min(end, c["end_char"])) for c in selected
                           if c["member"] == case["member"] and c["end_char"] > start and c["start_char"] < end)
        total, cursor = 0, start
        for a, b in intervals:
            total += max(0, b - max(a, cursor))
            cursor = max(cursor, b)
        best = max(best, total / (end - start))
    return best


def run(semantic=False):
    OUT.mkdir(exist_ok=True)
    cases = json.loads((ROOT / "evals/retrieval_cases.json").read_text())
    selected_members = {f"episodes/{c['episode']}/transcript.md" for c in cases}
    episodes, failures = {}, []
    total = 0
    for member, content in read_transcripts():
        total += 1
        try:
            parsed = parse_transcript(member, content)
            if member in selected_members:
                episodes[member] = parsed
        except Exception as error:
            failures.append({"member": member, "error": type(error).__name__, "detail": str(error)[:250]})
    for case in cases:
        case["member"] = f"episodes/{case['episode']}/transcript.md"
        if case["member"] not in episodes or case["anchor"] not in episodes[case["member"]].transcript:
            raise ValueError(f"Unverified evidence anchor: {case['id']}")
    report = {"archive_sha256": ARCHIVE_SHA256, "transcripts_inspected": total,
              "parse_failures": failures, "pilot_episodes": sorted(episodes),
              "labeled_questions": len(cases), "semantic_executed": False,
              "token_budget": BUDGET, "configs": [],
              "limitations": ["Five-episode pilot, not a full-corpus benchmark.",
                  "Evidence anchors are a small non-exhaustive set, not human-reviewed relevance judgments.",
                  "No answer generation or answer quality measured.",
                  "Local exact search does not validate the PostgreSQL retrieval path."]}
    indexed = []
    for size, overlap in CONFIGS:
        chunker = TranscriptChunker(size, overlap)
        start_time = time.perf_counter()
        corpus, source_tokens, covered_characters = [], 0, 0
        overlap_actual = []
        for member, parsed in sorted(episodes.items()):
            chunks = chunker.split(parsed.transcript)
            source_tokens += chunker.count(parsed.transcript)
            cursor = 0
            for index, chunk in enumerate(chunks):
                assert chunk.content == parsed.transcript[chunk.start_char:chunk.end_char], 'Source mismatch'
                assert 0 < chunk.token_count <= size, 'Token limit violation'
                assert chunk.token_count == chunker.count(chunk.content), 'Incorrect token count'
                assert chunk.start_char <= cursor, 'Gap in source coverage'
                if index:
                    assert chunk.start_char > chunks[index-1].start_char, 'No forward progress'
                    actual_overlap = chunker.count(parsed.transcript[chunk.start_char:cursor])
                    assert actual_overlap <= overlap, 'Overlap budget exceeded'
                    overlap_actual.append(actual_overlap)
                cursor = max(cursor, chunk.end_char)
                corpus.append({"member": member, **asdict(chunk)})
            assert cursor == len(parsed.transcript), 'Transcript tail missing'
            covered_characters += cursor
        counts = [c["token_count"] for c in corpus]
        stats = {"size": size, "overlap": overlap, "chunks": len(corpus),
                 "source_tokens": source_tokens, "embedding_input_tokens": sum(counts),
                 "mean_chunk_tokens": round(statistics.mean(counts), 1),
                 "max_chunk_tokens": max(counts), "overlap_mean_tokens": round(statistics.mean(overlap_actual), 1),
                 "duplication_ratio": round(sum(counts)/source_tokens, 3),
                 "character_coverage": 1.0, "chunking_seconds": round(time.perf_counter()-start_time, 3)}
        report["configs"].append(stats)
        indexed.append(corpus)
        print(json.dumps(stats), flush=True)
    report_path = OUT / "chunk_comparison.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    if semantic:
        values = dotenv_values(ROOT / ".env")
        key = os.environ.get("OPENAI_API_KEY") or values.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("OPENAI_API_KEY is missing; structural results were saved, semantic testing not run.")
        queries, usage = embedding_vectors([c["question"] for c in cases], key)
        for stats, corpus in zip(report["configs"], indexed, strict=True):
            vectors, used = embedding_vectors([c["content"] for c in corpus], key)
            usage += used
            results = []
            for case, query in zip(cases, queries, strict=True):
                started = time.perf_counter()
                scores = [sum(a*b for a,b in zip(query, vector, strict=True)) for vector in vectors]
                ranking = sorted(range(len(corpus)), key=lambda i: (-scores[i], i))
                chosen, remaining = [], BUDGET
                for i in ranking[:20]:
                    if corpus[i]["token_count"] <= remaining:
                        chosen.append(corpus[i]); remaining -= corpus[i]["token_count"]
                    if len(chosen) >= 20 or remaining == 0:
                        break
                # Match production: budget whole chunks from the top 20 candidates.
                top5 = [corpus[i] for i in ranking[:5]]
                relevant_rank = next((rank for rank,i in enumerate(ranking, 1) if coverage([corpus[i]], case, episodes) >= 0.8), None)
                results.append({"id": case["id"], "coverage_top5": coverage(top5,case,episodes),
                    "coverage_budget": coverage(chosen,case,episodes),
                    "reciprocal_rank": 1/relevant_rank if relevant_rank else 0,
                    "context_tokens": BUDGET-remaining, "search_ms": (time.perf_counter()-started)*1000,
                    "top5": [{"member":corpus[i]["member"], "start_char":corpus[i]["start_char"],
                              "end_char":corpus[i]["end_char"], "score":scores[i]} for i in ranking[:5]]})
            stats["semantic"] = {"anchor_hit_at_5": statistics.mean(r["coverage_top5"]>=0.8 for r in results),
                "budget_anchor_hit": statistics.mean(r["coverage_budget"]>=0.8 for r in results),
                "mean_budget_anchor_coverage": statistics.mean(r["coverage_budget"] for r in results),
                "mrr":statistics.mean(r["reciprocal_rank"] for r in results), "questions":results}
        report["semantic_executed"] = True
        report["embedding_model"] = MODEL
        report["new_api_input_tokens"] = usage
        report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    lines = ["# Chunk-size comparison", "", f"Source: supplied ZIP; {len(episodes)} episodes, {len(cases)} evidence-anchored questions.",
             f"Inspected {total} transcript files; parser failures: {len(failures)}.", "",
             "| Limit / overlap | Chunks | Embedding input tokens | Mean chunk tokens | Duplication ratio | Coverage |",
             "|---|---:|---:|---:|---:|---:|"]
    for row in report["configs"]:
        lines.append(f"| {row['size']} / {row['overlap']} | {row['chunks']} | {row['embedding_input_tokens']} | {row['mean_chunk_tokens']} | {row['duplication_ratio']} | 100% |")
    lines += ["", "Semantic retrieval: " + ("executed; see JSON for scores." if report["semantic_executed"] else "NOT RUN. An OpenAI key is required."),
              "", "Structural checks alone cannot identify the best retrieval configuration."]
    if semantic:
        lines += ["", "| Token limit | Evidence hit @ 5 | Evidence hit within 2,000 tokens | MRR |",
                  "|---|---:|---:|---:|"]
        for row in report["configs"]:
            metrics = row["semantic"]
            lines.append(f"| {row['size']} | {metrics['anchor_hit_at_5']:.0%} | {metrics['budget_anchor_hit']:.0%} | {metrics['mrr']:.3f} |")
        lines += ["", "Initial application default: 400 tokens / 60 overlap, based on this pilot's evidence coverage.",
                  "This is provisional; evaluate held-out questions across the full corpus before generalizing."]
    lines += ["", "Limitations:"]
    lines += ["- " + value for value in report["limitations"]]
    (OUT / "chunk_comparison.md").write_text("\n".join(lines)+"\n", encoding="utf-8")
    print('Saved report:', report_path, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--semantic", action="store_true")
    args = parser.parse_args()
    run(args.semantic)
