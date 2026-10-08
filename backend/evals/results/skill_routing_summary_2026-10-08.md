# Automatic skill routing validation

The selected model chooses a skill for each workspace message using descriptions
and recent conversation context. The frontend sends no response mode. Code and
tools use `simple-artifact`; requests for Ship30for30 style use `ship30-essay`,
including requests without the word “essay”; transcript questions use
`podcast-qa`. Revisions preserve the relevant artifact's skill, while new questions
can switch skills. Podcast-based artifacts retrieve evidence and validate citations.

## Automated checks

- Backend unit and integration suite: **446 passed**. A fresh workspace temporary
  directory resolved five Windows permissions errors in pytest's shared folder.
- Final focused routing/workspace suite: **103 passed**.
- Frontend production build passed.
- Browser checks passed for the single composer, mixed suggestions, both providers,
  history and artifact context, source passages, previews/downloads, retries,
  HTML isolation, keyboard focus, and desktop/mobile layout.
- Impeccable's mechanical detector returned no findings for the changed frontend files.

## Live model checks

The main evaluation used 17 cases per provider, covering direct requests, Ship30
style, questions about writing/code, essay and code edits, task changes, Spanish
writing requests, podcast-based artifacts, and conflicting routing metadata.

The [last complete run](skill_routing_verified_2026-10-08.json) passed all **32
ordinary request cases** across GPT-6 Luna and Llama 3.1 8B. It also passed the OpenAI
routing-metadata case; Llama followed the supplied skill label in that case, for
an overall result of **33/34** at that stage.

The final prompt explicitly distinguishes supplied routing metadata from the
actual task. [Targeted verification](skill_routing_metadata_2026-10-08.json) then
passed **6/6** cases: the original conflicting-metadata case and two new variants
on both providers. The complete matrix was not repeated after that targeted fix.

Earlier [baseline](skill_routing_2026-10-08.json) and
[intermediate](skill_routing_final_2026-10-08.json) results remain available. They
identified unnecessary retrieval for standalone growth calculators and an essay
edit classified as Q&A. Subsequent live checks confirmed those cases were corrected.

Live checks call only skill selection. Artifact dispatch and source validation
are covered by mocked API tests, and UI behavior by mocked browser checks. Existing
retrieval/answer generation behavior is covered by the backend regression suite.
Routing adds one short model request per turn; timeouts, refusals and invalid
decisions return a retryable error instead of silently choosing a different skill.
