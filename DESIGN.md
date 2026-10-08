# Design — Lenny Growth Assistant

## Design Goal

The UI is designed to make the application feel like a simple AI workspace rather than exposing the complexity of the underlying RAG and model pipelines.

The main goal is to let users:

- ask questions naturally
- switch between AI providers easily
- view grounded answers with sources
- generate essays and artifacts without changing pages
- preview generated content in a clear workspace

---

## UI Structure

The interface is organized around a single conversational workspace.

### 1. Chat Area

The main section contains the conversation between the user and the assistant.

It displays:

- user prompts
- assistant responses
- formatted Markdown
- source references
- loading states
- error messages

The chat interface is intentionally familiar so users can start using the application without learning a new interaction pattern.

### 2. Input Area

The input area is kept simple and focused on the user's request.

Users can enter normal questions, essay requests, or artifact-generation prompts using the same input.

The backend automatically decides which skill should handle the request, reducing the number of controls the user has to manage.

### 3. Provider Selector

The interface allows the user to switch between:

- OpenAI
- OpenRouter

The provider selector is visible but does not change the rest of the workflow.

This keeps model selection optional for users who want control without making the interface more complicated.

### 4. Artifact Viewer

Large generated outputs such as essays, Markdown documents, HTML, and code are displayed separately from the main chat.

This keeps the conversation readable while providing more space for generated content.

The artifact viewer supports content such as:

- Markdown
- HTML
- JavaScript
- Python
- CSS
- JSON
- plain text

---


## Grounding and Sources

Because the assistant is built around Lenny's Podcast transcripts, source visibility is an important part of the UX.

Answers include source references so users can see that the response is based on retrieved podcast content.

When enough evidence is not available, the interface returns an unsupported or partial response instead of presenting an ungrounded answer with high confidence.

---

## Feedback States

The interface includes clear feedback for different application states.

### Loading

A loading state is shown while retrieval and generation are running so the user knows the request is being processed.

### Errors

Provider, database, or generation failures are shown as readable messages rather than raw backend errors.

### Unsupported Questions

If the knowledge base does not contain enough information, the assistant explains that there is insufficient podcast evidence and encourages the user to ask a more relevant question.

---

## Visual Design

The visual design follows a minimal workspace style.

The main priorities are:

- readable typography
- clear separation between user and assistant messages
- limited visual clutter
- consistent spacing
- clear provider controls
- enough space for long-form content
- readable code and Markdown rendering

The interface avoids unnecessary navigation because most interactions can be completed from a single screen.

---

## Why This Structure

The application supports several capabilities, but exposing all of them as separate screens would make the product harder to use.

Instead, the design keeps the user experience simple:

```text
One Input
   ↓
One Workspace
   ↓
Different Skills Behind the Scenes
```

This allows the backend to handle complexity while the frontend remains easy to understand.

The final UI design focuses on making the application feel like a single intelligent workspace rather than a collection of separate AI tools.
