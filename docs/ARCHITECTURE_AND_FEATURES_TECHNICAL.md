# Zoria — High-Level Technical Architecture & Feature Review

**Document purpose:** Technical overview of system architecture, components, data flow, and feature implementation for engineers and technical stakeholders.

---

## 1. System Overview

Zoria is a **full-stack educational learning platform** with:

- **Backend:** FastAPI (Python), PostgreSQL (with pgvector), background document processing, OpenAI/LLM integration for extraction and evaluation.
- **Frontend:** React 18 + Vite, single-page app with role-based views (parent, child, admin).
- **Deployment:** Docker Compose (Postgres, backend, frontend); optional Cloudflare Tunnel; Nginx for production frontend serving.

---

## 2. High-Level Architecture Diagrams

**Full set of Mermaid diagrams:** [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) (system context, deployment, components, document flow, request flow, data model).

**ASCII (logical) sketch:**

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              CLIENT (Browser)                                 │
│  React 18 + Vite │ Dashboard │ Documents │ Tests │ Reports │ Learning Workspace │
└─────────────────────────────────────┬───────────────────────────────────────┘
                                      │ HTTPS / REST
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                         BACKEND (FastAPI, port 8000)                          │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │ Auth (JWT)  │  │ API v1      │  │ Services    │  │ Background / Workers │  │
│  │ RBAC        │  │ Routers     │  │ (business   │  │ Document processor   │  │
│  │ Parent/     │  │ auth, admin,│  │  logic)     │  │ (OpenAI workflow)    │  │
│  │ Child/Admin │  │ parent,     │  │             │  │                      │  │
│  └─────────────┘  │ documents,  │  └──────┬──────┘  └──────────┬──────────┘  │
│                   │ tests, tikz │         │                     │             │
│                   └──────┬──────┘         │                     │             │
│                          │               ▼                     ▼             │
│                          │  ┌────────────────────────────────────────────┐   │
│                          └─►│ Repositories │ Embedding │ LLM │ Evaluators │   │
│                             └────────────────────┬───────────────────────┘   │
└──────────────────────────────────────────────────┼───────────────────────────┘
                                                   │
                    ┌──────────────────────────────┼──────────────────────────────┐
                    ▼                              ▼                              ▼
           ┌───────────────┐             ┌─────────────────┐             ┌──────────────┐
           │  PostgreSQL   │             │  OpenAI API     │             │  File store  │
           │  + pgvector   │             │  (Agents,       │             │  (uploads)   │
           │  (all data)   │             │   embeddings,   │             │              │
           │               │             │   chat)         │             │              │
           └───────────────┘             └─────────────────┘             └──────────────┘
```

---

## 3. Tech Stack Summary

| Layer | Technology | Notes |
|-------|------------|--------|
| **Backend** | FastAPI | Async, OpenAPI docs at `/docs` |
| **Language** | Python 3.10+ | |
| **Database** | PostgreSQL 16 + pgvector | Migrations in `backend/database/migrations/` |
| **Auth** | JWT, bcrypt | Passwords and child PINs hashed |
| **AI/LLM** | OpenAI (Agents SDK, embeddings, chat) | Document parsing, concept extraction, question gen, evaluation, coach |
| **Frontend** | React 18, Vite | SPA, env: `VITE_API_BASE` |
| **Containers** | Docker, Docker Compose | postgres, backend, frontend; optional cloudflared |
| **Production** | Nginx (frontend), Cloudflare (optional) | HTTPS via tunnel or reverse proxy |

---

## 4. Backend Structure

```
backend/
├── main.py                 # FastAPI app, lifespan, CORS, router includes
├── api/v1/                 # API layer
│   ├── auth.py             # Login, child login, MFA complete, /me
│   ├── admin.py            # Parents, children, documents, KG, reprocess, LLM logs, test reopen/reevaluate
│   ├── parent.py           # Children CRUD
│   ├── child.py            # Child profile
│   ├── documents.py        # Upload, list, get, delete, reprocess
│   ├── tests.py            # Tests: generate, list, start, answer, submit; study guides; evaluation report; coach chat
│   └── tikz.py             # TikZ render (math/diagrams)
├── core/                   # Cross-cutting
│   ├── config.py           # Settings from env
│   ├── database.py         # DB connection (async)
│   ├── security.py         # JWT, password/PIN hashing
│   ├── dependencies.py     # get_current_user, get_current_parent, get_current_admin, get_current_child, get_db
│   └── background_tasks.py # Background job handling
├── services/               # Business logic
│   ├── auth_service.py
│   ├── user_service.py
│   ├── document_service.py
│   ├── chunking_service.py
│   ├── embedding_service.py
│   ├── knowledge_graph_service.py
│   ├── test_generation_service.py
│   ├── question_generation_service.py
│   ├── question_validator_service.py
│   ├── scoring_service.py
│   ├── mastery_service.py
│   ├── study_guide_service.py
│   ├── evaluation_report_service.py
│   ├── graph_evaluation_service.py
│   ├── tikz_render_service.py
│   ├── llm_service.py
│   ├── llm_logging_service.py
│   ├── agent_logging_wrapper.py
│   └── evaluation/         # LLM, heuristic, deterministic evaluators; question router; error library
├── workflows/              # Document processing pipeline
│   ├── workflow.py         # OpenAI Agents: document parser, concept extractor; PDF → concepts
│   └── prompts.py         # Prompt templates
├── workers/                # Async/background processing
│   └── document_processor.py
├── database/
│   ├── repositories/       # Data access (users, documents, concepts, tests, etc.)
│   └── migrations/         # SQL migrations (001–017)
└── schemas/                # Pydantic request/response models
```

**Request flow:** `HTTP → Router → Dependencies (auth) → Service → Repository → DB` (and/or LLM, file store).

---

## 5. API Surface (High-Level)

| Prefix | Purpose |
|--------|--------|
| `GET /`, `GET /health` | Root and health check |
| `/api/v1/auth` | Login, child login, MFA complete, get current user |
| `/api/v1/admin` | Parents CRUD, list children/documents, document reprocess, KG, LLM logs, test reopen/reevaluate |
| `/api/v1/parent` | Children CRUD |
| `/api/v1/child` | Child profile |
| `/api/v1/documents` | Upload, list, get, delete, reprocess |
| `/api/v1/tests` | Subjects/topics, generate test, generate questions, get test, list by child, admin grouped list, start/answer/submit test, delete; evaluation report; study guide get/regenerate/list; coach chat |
| `/api/v1/tikz` | Render TikZ |

Auth: JWT in `Authorization: Bearer <token>`. Role in token: `parent`, `child`, or `admin`; dependencies enforce per-route role and ownership.

---

## 6. Data Model (Conceptual)

- **parents** — email, password_hash, role (parent|admin), MFA, refresh token, is_active.
- **children** — parent_id, name, pin_hash, grade, age, avatar_url, is_active.
- **documents** — child_id, parent_id, filename, file_path, markdown_content, concepts (JSONB), processed_at, status metadata.
- **document_children** — junction (document can be shared with multiple children).
- **chunks** — document_id, chunk_text, embedding (vector), for semantic search.
- **concepts** — extracted from documents; subject, topic, subtopic, difficulty, prerequisites, keywords; links to knowledge graph.
- **knowledge graph** — nodes/edges (concepts, relationships); tables from migrations 009.
- **questions** — linked to concepts/documents; question text, type, options, embeddings (013).
- **tests** — child_id, status, timestamps; test_questions link tests to questions.
- **test_responses** — answers per test/question; scoring and evaluation inputs.
- **mastery_tracking** — per-concept or per-skill progress (010).
- **behavioral_tracking** — engagement/behavior (016).
- **study_guides** — generated guides per document/topic (017).
- **llm_logs** — LLM request/response logging for cost and debugging (014).

Migrations: `001_initial_schema.sql` through `017_study_guides_table.sql`; pgvector used for chunks and question embeddings.

---

## 7. Feature Implementation (Technical)

### 7.1 Authentication & Authorization

- **JWT:** Issued on login; contains user_id (parent_id or child_id), role, email/name as needed.
- **Bcrypt:** Password and child PIN hashing.
- **Dependencies:** `get_current_user` (any authenticated), `get_current_parent`, `get_current_admin`, `get_current_child`; used on routers to enforce role and ownership (e.g. document/child belongs to parent).

### 7.2 Document Processing Pipeline

1. **Upload:** PDF stored on disk; document row created with `processing` status.
2. **Background:** Worker/workflow loads PDF, runs **OpenAI Agents** workflow:
   - **Document parser:** PDF → structured markdown.
   - **Concept extractor:** Markdown → structured concepts (subject, topic, subtopic, difficulty, questions, keywords, etc.) with schema (e.g. `ConceptExtratorSchema`).
3. **Post-processing:** Concepts stored (DB); **knowledge graph** built/updated (deduplication, relationships via `KnowledgeGraphService`); **chunks** and **embeddings** for semantic search; **questions** may be generated from concepts.
4. **Status:** Document marked completed (or failed); frontend polls or refreshes list.

Workflow and prompts live in `workflows/workflow.py` and `workflows/prompts.py`; subject classification can use config (e.g. `subject_profiles.json`, `subject_topics.json`).

### 7.3 Test Generation & Execution

- **Generation:** Services use document/concept data (and optionally question blueprints) to generate questions; stored in `questions` and linked to tests via `test_questions`.
- **Test lifecycle:** Create test → start (timestamps) → submit answers (one or more requests) → submit final → **scoring_service** and **evaluation** (deterministic + heuristic + optional LLM) produce grades and feedback.
- **Evaluation pipeline:** `evaluation_report_service` aggregates results; can use `graph_evaluation_service`; **question_router** or evaluators in `services/evaluation/` decide how each question is evaluated (e.g. LLM vs heuristic).

### 7.4 Study Guides & AI Coach

- **Study guides:** Generated from concepts/documents; stored in `study_guides` (017); API: get, list by child, regenerate.
- **Coach chat:** Stateless chat endpoint (e.g. `POST .../study-guide/coach/chat`) with context (guide, child, etc.); uses LLM service for replies; can be wired to same LLM logging as rest of app.

### 7.5 Evaluation Report & Learning Workspace

- **Report API:** Returns summary for a child over a time window (e.g. last N days): strengths, gaps, suggested study guides/cards.
- **Frontend Learning Workspace:** Combines report + study guides + revision cards + coach chat in one layout (e.g. `LearningWorkspace.jsx`, `EvaluationReport.jsx`, `LearningDrawer.jsx`, `AICoach.jsx`).

### 7.6 Admin & Observability

- **Admin API:** Full parent/child/document access; document reprocess; knowledge graph endpoint (per document); LLM logs list and stats; test reopen/reevaluate.
- **LLM logging:** Wrapper or service logs requests/responses and tokens for cost and debugging (table 014).

### 7.7 TikZ Rendering

- **Service:** Renders TikZ (LaTeX) to image (e.g. SVG/PNG) for display in UI (e.g. math in questions or guides).
- **API:** `POST /api/v1/tikz/render` with TikZ source; returns URL or blob.

---

## 8. Frontend Architecture (Brief)

- **App.jsx:** Auth state (JWT in localStorage/sessionStorage), role (parent/child/admin), routing between Dashboard and AdminSettings; session-expired and inactivity handling.
- **Dashboard:** Role-specific tabs (overview, children, documents, tests, reports, learning workspace); child selector for parent/admin; document list, test list/launcher, quiz player, evaluation report, learning workspace.
- **AdminSettings:** Parent management, children/documents (read-only), LLM logs, test actions as exposed by admin API.
- **API client:** Centralized in `services/api.js` (auth, children, documents, tests, admin); base URL from `VITE_API_BASE`; Bearer token attached; error handling (e.g. 401 → session expired event).

---

## 9. Security (Technical)

- **Transport:** HTTPS in production (e.g. Cloudflare or Nginx); backend trusts `X-Forwarded-Proto` for redirects.
- **Secrets:** JWT secret, DB password, OpenAI API key from env (e.g. `.env`); no secrets in frontend except what’s in JWT (minimal claims).
- **Auth:** JWT validation on protected routes; role and ownership checks in dependencies and services (e.g. document/child belongs to parent).
- **Input:** File type/size checks on upload; Pydantic validation on API inputs.

---

## 10. Deployment (Technical)

- **Docker Compose:** `postgres` (pgvector), `backend` (uvicorn), `frontend` (Node dev server or static build); volumes for DB, uploads, and frontend node_modules.
- **Env:** `DATABASE_URL`, `OPENAI_API_KEY`, `JWT_SECRET_KEY`, `QUESTION_GENERATION_MODEL`, etc.; optional `CLOUDFLARE_TUNNEL_TOKEN` for cloudflared.
- **Migrations:** Applied via mounted SQL in `docker-entrypoint-initdb.d` or manually; `migrate.py` / shell scripts for later migrations.

---

## 11. Feature vs Component Map (Technical)

| Feature | Backend | Frontend |
|--------|---------|----------|
| Auth | auth.py, auth_service, security, dependencies | Auth.jsx, api auth |
| Children | parent.py, admin.py, user_service | CreateChild, EditChild, Dashboard child selector |
| Documents | documents.py, document_service, workers/workflow | DocumentUpload, DocumentList |
| Tests | tests.py, test_generation, question_generation, scoring, evaluation | TestLauncher, TestList, TestListGrouped, QuizPlayer |
| Reports | tests.py (evaluation-report), evaluation_report_service | EvaluationReport |
| Study guides / coach | tests.py (study-guides, coach chat), study_guide_service, llm_service | LearningDrawer, AICoach, StudyGuide, RevisionCardsView |
| Learning workspace | — | LearningWorkspace (report + drawer + coach) |
| Admin | admin.py, user_service, document_service, llm_logging | AdminSettings |
| Knowledge graph | admin.py (documents/{id}/knowledge-graph), knowledge_graph_service | KnowledgeGraphViewer (if used) |
| TikZ | tikz.py, tikz_render_service | MathText or similar |

---

## 12. Summary

- **Architecture:** React SPA → FastAPI → PostgreSQL + pgvector, OpenAI, file store; background document processing; JWT + RBAC.
- **Features:** User and child management, PDF upload and AI-powered concept extraction, knowledge graph, test generation and evaluation, study guides, revision cards, AI coach, evaluation reports, learning workspace, admin and LLM observability, TikZ rendering.
- **Scalability considerations:** Stateless API; DB and file store can be scaled separately; background processing can be moved to a queue/worker pool; LLM usage and token logging already in place for cost control.

For a non-technical, business-oriented view of the same product, see `ARCHITECTURE_AND_FEATURES_BUSINESS.md`.

For step-by-step flows (document ingestion, test generation and evaluation, reports), see [DETAILED_FLOWS.md](DETAILED_FLOWS.md).

---

*Last updated: February 2025.*
