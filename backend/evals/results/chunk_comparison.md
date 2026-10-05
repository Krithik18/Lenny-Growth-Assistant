# Chunk-size comparison

Source: supplied ZIP; 5 episodes, 10 evidence-anchored questions.
Inspected 303 transcript files; parser failures: 0.

| Limit / overlap | Chunks | Embedding input tokens | Mean chunk tokens | Duplication ratio | Coverage |
|---|---:|---:|---:|---:|---:|
| 400 / 60 | 369 | 119605 | 324.1 | 1.223 | 100% |
| 700 / 100 | 190 | 116265 | 611.9 | 1.189 | 100% |
| 1000 / 150 | 126 | 115915 | 920.0 | 1.186 | 100% |

Semantic retrieval: executed; see JSON for scores.

Structural checks alone cannot identify the best retrieval configuration.

| Token limit | Evidence hit @ 5 | Evidence hit within 2,000 tokens | MRR |
|---|---:|---:|---:|
| 400 | 90% | 90% | 0.576 |
| 700 | 70% | 60% | 0.591 |
| 1000 | 70% | 50% | 0.485 |

Initial application default: 400 tokens / 60 overlap, based on this pilot's evidence coverage.
This is provisional; evaluate held-out questions across the full corpus before generalizing.

Limitations:
- Five-episode pilot, not a full-corpus benchmark.
- Evidence anchors are a small non-exhaustive set, not human-reviewed relevance judgments.
- No answer generation or answer quality measured.
- Local exact search does not validate the PostgreSQL retrieval path.
