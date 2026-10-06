# Source checks and interpretation

These are agent checks of selected saved answers against their returned transcript text,
not an independent human assessment or a review of every generated claim.

## Supported examples

- **comparison-design:** the Chesky passage S8 criticizes treating design as a service
  organization outside development; Dylan Field's S4 explicitly describes craft and design
  as differentiation. The answer distinguishes these views. Its additional ideal-experience
  example is attributed to Sachin Kansal's account, rather than presented as Chesky's own
  statement in that passage. The ZIP's guest metadata for that file is inconsistent with
  its title and body; source metadata remains uncorrected.
- **code:** the returned Python function implements a strict percentage > 40 comparison
  and labels itself as generated implementation. It is not robust code: invalid negative
  counts and counts above the total are not rejected. Code execution/artifact features
  remain separate product work.
- **partial-weather:** the response answers the survey portion and marks weather as missing.
  The reviewer flags "not act on feedback from every early user" versus the source's
  "not act on feedback from many early users." The response describes selective use of
  feedback; this wording is not clear evidence of a fabricated claim. Retain the automated
  flag for transparency rather than treating its groundedness score as a factual verdict.

## Retrieval/context gaps

- **ebi-atawodi:** returned S2 and S5 support the running problem document and stakeholder
  input. They do not contain the quarterly-update detail in the reference excerpt. The
  answer's statement that its evidence lacks an update schedule is consistent with those
  returned citations, but its complete-coverage flag is too optimistic for the question.
- **jen-abel-20:** S1 ends near the start of the design-partner discussion. The answer
  accurately describes partners as guides rather than dependable major pipeline and
  marks the fuller process missing. Selection, expectations, and pricing details present
  elsewhere in the reference excerpt were not included in the returned evidence.
- **carole-robin:** S3 supports Robin's off-site story, not the requested missed-deadline
  example. The answer admits that distinction, but supplying an alternative story does
  not answer the specific question. This is a retrieval/completeness failure, not proof
  that the cited off-site story was invented.
- **spanish:** the answer uses Spanish and acknowledges missing options, but retrieves
  incomplete evidence for a question that English queries can answer. Multilingual query
  handling requires improvement.

## Rubric and reference limits

- **chris-hutchins:** both fixed-evidence and RAG answers explain the podcast's learning
  benefit. The synthetic reference additionally expects niche-positioning advice, which
  is not necessary to answer the stated main-benefit question. Its expected-points failure
  is stricter than the question itself.
- **activation-plan:** the proposed steps are cited and useful; the rubric flags lack of
  an explicit statement that their organization is the assistant's synthesis.
- **ambiguous:** the answer admits that "he" is unidentified, but unnecessarily lists
  several guests. A clarification-focused response would be better.

The automated judge sees both reference excerpts and returned citations. Some negative
groundedness judgments conflate a missed reference detail with an unsupported assertion.
The reported scores are therefore advisory proxies. Inspect the actual evidence before
classifying a flag as hallucination.

Priority follow-up experiments: retrieve adjacent chunks around selected passages;
test episode-aware ranking and reranking; rewrite multilingual queries; improve ambiguity
handling and synthesis labels; validate generated code. Compare these changes on held-out
questions rather than tuning only to the failed cases in this run.
