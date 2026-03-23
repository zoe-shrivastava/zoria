# Zoria — System flows (user input · DB · AI local/cloud · output)

This document summarizes the four main product flows with **what hits the database**, **which AI is local (Ollama) vs cloud (OpenAI)**, and **what is produced**. For API-level step-by-step detail, see [`DETAILED_FLOWS.md`](./DETAILED_FLOWS.md).

**Legend**

| Symbol | Meaning |
|--------|---------|
| **User** | Browser / API caller |
| **DB** | PostgreSQL (+ **pgvector** for chunk embeddings) |
| **Cloud AI** | OpenAI (Agents / Chat Completions); models like `gpt-5-mini`, `gpt-5-nano`, `QUESTION_GENERATION_MODEL` (e.g. `gpt-5-nano`) |
| **Local AI** | Ollama — embeddings (`mxbai-embed-large`), subject tag (`llama3.2`), study guide & coach & eval (`llama3.1`) |

**Code reference:** `LLMService` routes `gpt-*` → OpenAI; all other model names → Ollama (`OLLAMA_BASE_URL`).

---

## 1. Document ingestion

### Summary table

| Stage | User input | DB | AI | Output |
|-------|------------|----|----|--------|
| Upload | PDF + optional child link | `documents` (path, `uploaded`) | — | `document_id`; Phase 1 queued |
| Phase 1 | — | Read path; write `markdown_content`, `concepts`, `subject`; status `parsed` | **Cloud:** PDF→markdown (Document Parser), markdown→concepts (Concept Extractor). **Local:** subject from markdown snippet | Structured markdown + concept JSON + subject |
| Phase 2 / Rebuild KG | Admin “Rebuild KG” (optional) | Concepts, relationships, questions, `content_chunks` + vectors, skills links | **Local:** chunk embeddings via Ollama | KG + searchable chunks |

### Sequence (Mermaid)

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OC as Cloud AI (OpenAI)
    participant OL as Local AI (Ollama)

    U->>API: POST upload PDF
    API->>DB: INSERT documents, document_children
    API-->>U: document_id, status uploaded
    API->>API: enqueue Phase 1

    Note over API,DB: Phase 1 (background)
    API->>DB: SELECT file_path
    API->>OC: Document Parser (PDF → markdown)
    OC-->>API: markdown
    API->>OL: Subject classifier (markdown sample)
    OL-->>API: subject_id
    API->>OC: Concept Extractor (markdown → concepts JSON)
    OC-->>API: concepts
    API->>DB: UPDATE markdown, concepts, subject, status parsed
    API->>API: enqueue Phase 2

    Note over API,DB: Phase 2 (background)
    API->>DB: concepts, relationships, questions, chunks
    loop Per chunk
        API->>OL: embedding(text)
        OL-->>API: vector
        API->>DB: INSERT content_chunks + embedding (pgvector)
    end
    API->>DB: status ready (or failed)
```

---

## 2. Test generation & evaluation

### Summary table

| Step | User input | DB | AI | Output |
|------|------------|----|----|--------|
| Create / launch test | Topics/concept, difficulty, count, question types, language | `tests`, metadata; read `concepts`, chunks for context | — | Pending test |
| Generate questions | (background) | Read context; **INSERT** `questions`, link `test_questions` | **Cloud:** question LLM (`QUESTION_GENERATION_MODEL`). **Local:** optional embedding retrieval for context | Question set on test |
| Answer | MCQ / typed answers | UPDATE responses on test questions | Usually none until submit | Saved answers |
| Submit | Submit test | Read test+answers; WRITE scores, completion; mastery tables | **Local:** `llama3.1` for LLM rubric items; deterministic/heuristic for MCQ/numeric | Score, %, mastery update |
| Admin reevaluate | Reevaluate completed test | Clear eval fields; re-grade | Same as submit | Refreshed scores |

### Sequence — generation

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OL as Local AI (Ollama)
    participant OC as Cloud AI (OpenAI)

    U->>API: Create test (topics, types, N questions)
    API->>DB: INSERT tests (pending)
    API->>API: enqueue generation

    API->>DB: SELECT concepts, content_chunks (context)
    API->>OL: Optional embeddings / retrieval
    OL-->>API: context snippets
    API->>OC: generate_json (N questions)
    OC-->>API: questions JSON
    API->>DB: INSERT questions, test_questions
    API->>DB: UPDATE test status active
```

### Sequence — submit & grade

```mermaid
sequenceDiagram
    autonumber
    participant U as Child
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OL as Local AI (Ollama)

    U->>API: POST submit test
    API->>DB: SELECT test + questions + answers
    loop Each answered question
        alt MCQ / numeric heuristic
            API->>API: deterministic / heuristic score
        else Open-ended / LLM path
            API->>OL: llama3.1 evaluate
            OL-->>API: score, feedback
        end
        API->>DB: UPDATE question score, is_correct, metadata
    end
    API->>DB: test completed, aggregate score, mastery
    API-->>U: scores, percentage
```

---

## 3. Study guide generation

### Summary table

| Step | User input | DB | AI | Output |
|------|------------|----|----|--------|
| Request | child_id, concept, focus_area, **subject + topic from test**, errors/misconceptions optional | **Read** `study_guides` cache key | If cache hit: **none** | Cached guide |
| Generate | Same + force_regenerate | **INSERT/UPDATE** `study_guides` (content, key_points, practice_recommendations) | **Local:** `llama3.1` — outline → sections → optional validation | Long-form study guide |

### Sequence

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OL as Local AI (Ollama)

    U->>API: Request study guide (focus area, test metadata)
    API->>DB: SELECT study_guides (child, concept, focus)
    alt Cache exists and no force_regenerate
        DB-->>API: existing row
        API-->>U: content (no AI)
    else Generate
        API->>OL: llama3.1 pipeline (outline + sections)
        OL-->>API: markdown content
        API->>DB: INSERT/UPDATE study_guides
        API-->>U: new guide + id
    end
```

---

## 4. AI Assistant (AI Coach)

### Summary table

| Step | User input | DB | AI | Output |
|------|------------|----|----|--------|
| Chat | `guide_id`, `message`, `conversation_history`, optional language/context | **Read** study guide row; **Read** child profile (`get_child_context`) | **Local:** `llama3.1` chat (Socratic system prompt) | Assistant text + parsed `actions` |
| Persistence | Client sends history each turn | Optional **llm_call_logs** | — | — |

### Sequence

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as FastAPI
    participant DB as PostgreSQL
    participant OL as Local AI (Ollama)

    U->>API: POST study-guide/coach/chat
    API->>DB: SELECT study_guides by guide_id
    API->>DB: child context (profile, language)
    API->>OL: llama3.1 chat(messages + system prompt)
    OL-->>API: assistant text
    API->>API: parse actions (deep links, etc.)
    API-->>U: response + actions
```

---

## Quick reference — which model where

| Capability | Typical model | Provider |
|------------|---------------|----------|
| PDF → markdown | `gpt-5-mini` | OpenAI Agents |
| Markdown → concepts | `gpt-5-nano` | OpenAI Agents |
| Subject classification | `llama3.2:3b-instruct-fp16` | Ollama |
| Chunk embeddings | `mxbai-embed-large` | Ollama |
| Question generation | `QUESTION_GENERATION_MODEL` (default `gpt-5-nano`) | OpenAI |
| Test grading (LLM path) | `llama3.1` | Ollama |
| Study guide | `llama3.1` | Ollama |
| AI Coach | `llama3.1` | Ollama |

---

*Last updated to match backend layout: FastAPI routers under `backend/api/v1/`, workers in `backend/workers/`, workflows in `backend/workflows/workflow.py`.*
