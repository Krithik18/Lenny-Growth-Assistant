# Lenny-Growth-Assistant
AI assistant for product and growth insights using Lenny’s Podcast transcripts.

The workspace now chooses its skill automatically from each request and recent
conversation. Ask a transcript question, request something in Ship30for30 style,
or describe code to build in the same composer. The selected model routes to
podcast Q&A, essay synthesis, or artifact creation; podcast-based outputs retain
evidence and citations. See [the workspace guide](frontend/README.md) for usage
and [routing validation](backend/evals/results/skill_routing_summary_2026-10-08.md)
for the checks.

OpenRouter retrieval combines BGE-M3 semantic search with keyword search. It resolves
known guest names from archive metadata, cautiously corrects spelling and unambiguous
first names, scopes person-specific questions to relevant episodes or explicit mentions,
and handles excluded guests and compilation speakers separately. A bounded OpenRouter
semantic scope check runs before archive access, classifies the requested task rather than
isolated keywords, and translates supported non-English questions for retrieval. Clear
unsupported requests skip transcript search; mixed requests retain supported topics.
Invalid or unavailable scope decisions raise ProviderError instead of falling back to keyword
matching. The scope check uses Qwen3 30B A3B Instruct through OpenRouter; answer generation
continues to use Llama 3.1 8B. Semantic and keyword database searches run concurrently in
independent sessions by default, then merge before reranking. Reranking uses episode
identity, relevance scores, and soft penalties for promotional and introductory text.
Whole chunks and source offsets are preserved. These enhancements are opt-in
for the OpenRouter path; OpenAI keeps its existing retrieval behavior.

See [the semantic routing and retrieval report](backend/evals/results/openrouter_scope_refinement_2026-10-08.md)
for live evidence and current limits.
