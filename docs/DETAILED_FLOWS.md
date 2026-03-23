# Zoria — Detailed Flows: Document Ingestion, Test Generation & Evaluation, Reports

For a **compact view** with **Mermaid diagrams** (including Study Guide + AI Coach), see **[FLOWS.md](./FLOWS.md)**.

This document describes how three core pipelines work end-to-end: **document ingestion**, **test generation and evaluation**, and **evaluation reports**.

---

## 1. Document Ingestion (End-to-End)

Document ingestion turns an uploaded PDF into structured content (markdown, concepts, knowledge graph, questions, chunks with embeddings) that the rest of the platform uses.

### 1.1 Overview

- **Trigger:** User (parent, child, or admin) uploads a PDF via the API and optionally assigns it to one or more children.
- **Phases:**
  - **Synchronous (request):** Save file, create DB record, attach to children, set status `uploaded`, enqueue Phase 1.
  - **Phase 1 (background):** OpenAI Agents workflow — parse PDF to markdown, extract concepts, derive subject; store markdown + concepts + subject; then enqueue Phase 2.
  - **Phase 2 (background):** Build knowledge graph, create questions and visuals, chunk document, embed chunks, store everything; set status `ready` (or `failed`).

### 1.2 Entry Point: Upload API

**Endpoint:** `POST /api/v1/documents/upload`

**Parameters:**
- `file` (required): PDF file (multipart).
- `child_id` (optional): Single child UUID (legacy).
- `child_ids` (optional): Comma-separated child UUIDs (for multiple children).

**Access:**
- **Child:** Can upload only for themselves; `child_ids` is ignored and set to the child’s ID.
- **Parent / Admin:** Must provide `child_id` or `child_ids`; document is linked to those children via `document_children` and legacy `documents.child_id` (first child).

**Validation:**
- File size ≤ `settings.MAX_UPLOAD_SIZE_MB`.
- Filename must end with `.pdf`.

**Flow in handler:**
1. Read file bytes.
2. Resolve `child_ids_list` and `parent_id` from role.
3. Call `DocumentService.process_document(file_content, filename, child_ids_list, parent_id)`.
4. Return `DocumentUploadResponse`: `document_id`, `filename`, `status: "uploaded"`, message that processing runs in background.

### 1.3 DocumentService.process_document (Synchronous Part)

**File:** `backend/services/document_service.py`

1. **Save file:** `save_uploaded_file()` writes bytes to disk under `settings.UPLOAD_DIR` with a UUID-based filename; returns `(file_path, unique_filename)`.
2. **Create document row:** `document_repo.create_document()` with `filename`, `file_path`, `file_size`, `mime_type`, `child_id` (first child), `parent_id`. Status is initially whatever the repo default is (e.g. `uploaded` or unset).
3. **Attach to children:** If `child_ids` is provided, `document_repo.attach_document_to_children(document_id, child_ids, attached_by=parent_id)` fills the `document_children` junction table.
4. **Set status:** `document_repo.update_status(document_id, "uploaded", processing_started_at=...)`.
5. **Enqueue Phase 1:** `enqueue_document_phase1(document_id)` — schedules an asyncio task and returns; the HTTP response is sent immediately.

### 1.4 Background: Phase 1 (Workflow + Subject)

**Entry:** `core/background_tasks.py` — `enqueue_document_phase1(document_id)` creates an asyncio task that runs `process_phase1()`.

**Steps inside `process_phase1()`:**
1. Load document row to get `file_path`.
2. Set status to `processing`.
3. **Run OpenAI workflow:**  
   `WorkflowInput(pdf_path=file_path)` → `run_workflow(workflow_input)` in `workflows/workflow.py`.
4. **Persist Phase 1 output:**  
   `document_repo.update_document_processing(document_id, markdown_content=result["markdown"], concepts=result["concepts"], subject=result["subject"])`.
5. Set status to `parsed`.
6. **Enqueue Phase 2:** `enqueue_document_processing(document_id)` (no cleanup).

**run_workflow (workflows/workflow.py):**
- **Document Parser (OpenAI Agent):** PDF (as base64 input_file) + instruction to extract full document to structured Markdown. Output: `state["markdown"]`.
- **Concept Extractor (OpenAI Agent):** Markdown as input_text; structured output schema (`ConceptExtratorSchema`) with a list of concepts. Each concept has: `subject_name`, `topic_name`, `subtopic`, `difficulty`, `prerequisites`, `questions` (text, type, associated_visuals), `associated_visuals`, `keywords`.
- **Subject:** Taken from the most common `subject_name` in the concepts list and normalized to a subject_id (e.g. `mathematics`, `physics`, `other`) via `normalize_subject_name`.
- **Return:** `{ "markdown", "subject", "concepts" }` (concepts = full parsed schema).

All agent calls can be wrapped with `run_agent_with_logging` for LLM logging (e.g. `context_source="document_processing"`).

### 1.5 Background: Phase 2 (Knowledge Graph, Questions, Chunks, Embeddings)

**Entry:** `core/background_tasks.py` — `enqueue_document_processing(document_id)` creates an asyncio task that runs `DocumentProcessor.process_document(document_id, cleanup_first=False)`.

**File:** `backend/workers/document_processor.py` — class `DocumentProcessor`.

**Steps:**
1. Ensure status is `processing` (set at start if not already).
2. Optionally `cleanup_document_data(document_id)` when reprocessing (removes content_chunks, question_skills, questions, visuals, concept_relationships, document_concepts, and orphan concepts for this document).
3. Load document by ID; read `markdown_content`, `concepts` (JSON), `subject`.
4. Normalize concepts to a list of dicts with `name`, `subtopic`, `difficulty`, `questions`, `associated_visuals`, etc.
5. **Step 1 — Knowledge graph:**  
   `KnowledgeGraphService.process_concepts(document_id, normalized_concepts_list, subject=document_subject)`  
   - Deduplicates/merges concepts, creates or reuses concept rows, builds `concept_relationships` (e.g. prerequisites).  
   - Returns list of concept IDs in order.
6. **Step 2 — Questions and visuals:**  
   For each concept: create `questions` from `concept_data["questions"]` (text, type, difficulty, metadata including subject, document_id, answer); link to skills if applicable. Create `visuals` from `associated_visuals`. All inside a DB transaction.
7. **Step 3 — Chunking:**  
   `ChunkingService.chunk_document(document_id, markdown, concepts_json, subject=document_subject)` produces a list of chunks with metadata (e.g. concept_name, question_id). Chunks are optionally linked to `concept_id` and `question_id`.
8. **Step 4 — Embeddings:**  
   `EmbeddingService.embed_chunks(chunks, batch_size=10)` calls OpenAI embeddings API; returns chunks with `embedding` vectors.
9. **Step 5 — Store chunks:**  
   `ChunkRepository.create_chunks_batch(embedded_chunks)` inserts into `content_chunks` (or equivalent table with vector column).
10. **Step 6:**  
    `document_repo.update_status(document_id, "ready", processing_completed_at=...)`.

On any exception, status is set to `failed` with `failure_stage="background_processing"` and `error_message`.

### 1.6 Reprocessing

**Endpoint:** `POST /api/v1/documents/{document_id}/reprocess`  
**Body:** `{ "cleanup_existing": true, "skip_phase1": false }`

- **cleanup_existing:** If true, Phase 2 starts with `cleanup_document_data(document_id)`.
- **skip_phase1:** If true, Phase 1 is skipped; Phase 2 runs using existing markdown/concepts in the DB. If false, reprocess can still skip Phase 1 when markdown and concepts already exist (implementation in `document_service.reprocess_document`).

Reprocessing reuses the same Phase 1 (workflow) and Phase 2 (DocumentProcessor) pipeline; only the trigger and optional cleanup/skip logic differ.

### 1.7 Document Status Lifecycle

```
uploaded → processing (Phase 1 start) → parsed (Phase 1 done) →
  [Phase 2 runs with status already "processing" from worker] →
  ready | failed
```

Frontend can poll `GET /api/v1/documents` or `GET /api/v1/documents/{id}` to show status (`uploaded`, `processing`, `parsed`, `ready`, `failed`).

---

## 2. Test Generation and Evaluation (End-to-End)

Tests are generated from concepts or from subject/topics, then the child starts the test, submits answers, and the system grades them and updates mastery.

### 2.1 Overview

- **Generation:** Child (or parent/admin for question-only endpoint) requests a test. Backend creates a **draft** test and enqueues **background** question generation (from concepts or from subject/topics). When the background job finishes, the test is populated with questions and status becomes **active** (or **failed**).
- **Taking the test:** Child starts test → status **active**; submits answers per question via `POST .../answer`; finally `POST .../submit` triggers grading, status **completed**, and mastery update.

### 2.2 Generate Test API

**Endpoint:** `POST /api/v1/tests/generate`  
**Body (concept-based):** `concept_id`, optional: `include_prerequisites`, `difficulty`, `num_questions`, `time_limit_minutes`.  
**Body (topic-based):** `subject`, `topics` (list), same optional fields.

**Access:** Only **child** can generate tests (parent/admin get 403).

**Flow:**
1. **Concept path:**  
   `TestGenerationService.create_pending_test_from_concept(...)` creates a test row with status `draft`, metadata `generation_status: 'pending'`, `mode: 'concept'`.  
   Then `enqueue_test_generation_from_concept(test_id, child_id, concept_id, ...)` is called (fire-and-forget).
2. **Topic path:**  
   `TestGenerationService.create_pending_test_from_topics(...)` creates a test row with `concept_id=None`, metadata `subject`, `topics`, `generation_status: 'pending'`, `mode: 'topics'`.  
   Then `enqueue_test_generation_from_topics(test_id, child_id, subject, topics, ...)` is called.
3. Response returns the **pending** test (questions may still be empty or partial); frontend can poll `GET /api/v1/tests/{test_id}` until status becomes `active` or `failed`.

### 2.3 Background Test Generation

**Concept-based:** `background_tasks.enqueue_test_generation_from_concept` runs:
- `TestGenerationService.generate_questions_for_existing_test_from_concept(test_id, child_id, concept_id, ...)`.

**Topic-based:** `enqueue_test_generation_from_topics` runs:
- `TestGenerationService.generate_questions_for_existing_test_from_topics(test_id, child_id, subject, topics, ...)`.

**Inside TestGenerationService (concept path, simplified):**
- Resolve concept and optionally prerequisite concepts; get inclusive difficulty levels.
- If no questions (or need more), call **QuestionGenerationService** to generate questions via LLM (with similarity threshold to avoid duplicates), then store questions and link to concepts.
- Fetch questions for the concept(s), filter by difficulty, sample up to `num_questions`, organize into sections.
- **Populate test:** `_populate_test_with_questions(test_id, sections)` — for each question, `test_repo.add_question_to_test(test_id, question_id, order_index, section_title, max_score)`.
- **Activate:** `test_repo.update_test_status(test_id, 'active')`.

Topic path is analogous but resolves concepts from subject/topics (e.g. from document/concept tables or subject config) and then generates/selects questions.

### 2.4 Start Test

**Endpoint:** `POST /api/v1/tests/{test_id}/start`  
**Access:** Child only (`get_current_child`).

- Verifies test belongs to child; status must be `draft` or `active`.
- Sets `started_at` and status to `active`.
- Returns test with questions (for display in quiz UI).

### 2.5 Submit Answer (Per Question)

**Endpoint:** `POST /api/v1/tests/{test_id}/answer`  
**Body:** `question_id`, `answer` (text or structured, e.g. `{ "text", "graph", "diagram" }`), optional `time_spent_seconds`, `behavioral_data`.

- Saves the response in `test_responses` (or equivalent); no grading yet. Grading happens on **submit test**.

### 2.6 Submit Test (Grade and Complete)

**Endpoint:** `POST /api/v1/tests/{test_id}/submit`  
**Access:** Child only.

1. **Grade test:** `ScoringService.grade_test(test_id)`:
   - Loads test with all questions and responses.
   - For each answered question, calls `grade_response(test_id, question_id, answer, behavioral_data)`.
2. **grade_response (per question):**
   - Load question (type, metadata, max_score).
   - If answer is a drawing (e.g. graph/diagram), use **GraphEvaluationService** to grade (LLM or heuristic).
   - Otherwise, use **QuestionRouter.evaluate(...)**:
     - **multiple_choice**, **matching**, **fill_in_the_blank** → **DeterministicEvaluator** (exact or option index match).
     - **short_answer**, **problem_solving**, **conceptual_question**, etc. → **LLMEvaluator** (if available) for detailed feedback and partial credit; else fallback to deterministic.
   - Optional **behavioral penalties** applied to score.
   - **Persist:** `test_repo.update_response_score(test_id, question_id, score, is_correct, error_type, misconception, method_detected, detailed_feedback)`.
3. **Aggregate score:** `test_repo.calculate_test_score(test_id)` → total_score, max_score, percentage, correct_count, etc.
4. **Update test:** `test_repo.update_test_status(test_id, 'completed', completed_at=...)`.
5. **Update mastery:** `MasteryService.update_mastery_from_test(test_id)` updates per-concept or per-skill mastery from test results.
6. Return `TestSubmitResponse`: `total_score`, `max_score`, `percentage`, `correct_count`, `graded_count`, `mastery_updated`.

### 2.7 Evaluation Routing and Evaluators

**File:** `services/evaluation/question_router.py`

- **QuestionRouter** has a `routing_map`: question_type → `deterministic` | `heuristic` | `llm`.
- **DeterministicEvaluator:** MCQ, matching, fill-in-the-blank — exact or index-based comparison; no detailed feedback.
- **HeuristicEvaluator:** Numeric short answers with tolerance (e.g. 2%); used only when router chooses heuristic and answer is numerical.
- **LLMEvaluator:** Free-form and conceptual questions; returns is_correct, score, error_type, misconception, detailed_feedback (used for reports and study guides).

Error types (e.g. `Arithmetic`, `Conceptual`, `Procedural`, `Unit_Mismatch`, `No_Answer`, `Partial_Credit`, `Incorrect`) come from `error_library.ErrorType` and are stored on the response for reporting.

### 2.8 Test Lifecycle Summary

```
[Child] POST /tests/generate (concept_id or subject+topics)
  → Test row created (draft), background job enqueued
  → Background: generate/select questions, add to test, status → active (or failed)

[Child] POST /tests/{test_id}/start → status active, started_at set

[Child] POST /tests/{test_id}/answer (per question) → response stored

[Child] POST /tests/{test_id}/submit
  → ScoringService.grade_test → per-question grading (router → deterministic/heuristic/LLM)
  → update_response_score for each; calculate_test_score; update_test_status(completed); update_mastery
  → Response: total_score, max_score, percentage, mastery_updated
```

---

## 3. Evaluation Reports (End-to-End)

Reports aggregate completed tests over a time window, compute strengths and areas of focus, and optionally generate study guides for focus areas.

### 3.1 Overview

- **Trigger:** `GET /api/v1/tests/child/{child_id}/evaluation-report?days_back=30&generate_guides=true`.
- **Access:** Child (own report only); parent (their children); admin (any child).
- **Process:** Load completed tests in the window → aggregate by concept and subject → compute strengths (e.g. ≥70% performance) and areas of focus (<60%) → optionally create study guides for top focus areas → return report payload with links to study guides.

### 3.2 API and Service Entry

**Endpoint:** `GET /api/v1/tests/child/{child_id}/evaluation-report`  
**Query:** `days_back` (default 30, range e.g. 7–365), `generate_guides` (default true).

- Access check: child can only request own `child_id`; parent must own the child; admin can request any.
- `EvaluationReportService.generate_report(child_id, days_back=days_back, min_tests=1, generate_study_guides=generate_guides)` is called.
- The returned dict is sent as the response body (may include `error` and `tests_count` if insufficient data).

### 3.3 Data Aggregation (EvaluationReportService)

**File:** `backend/services/evaluation_report_service.py`

1. **Fetch tests:**  
   Completed tests for `child_id` with `completed_at >= cutoff_date` (now − days_back), ordered by `completed_at` DESC.
2. **Minimum tests:**  
   If count < `min_tests` (default 1), return `{ 'error': 'Insufficient data: Need at least N completed test(s)', 'tests_count': N }`.
3. **Loop over tests and questions:**  
   For each test, load full test with questions (and stored responses/scores) via `test_repo.get_test_with_questions(test_id)`. For each question:
   - **Correctness and score:** Use stored `is_correct`, `score`, `max_score`; if no answer, treat as incorrect and score 0.
   - **Subject:** From question metadata (`metadata.subject` or blueprint).
   - **Concept tags:** From `metadata.blueprint.concept_tags` or `metadata.concept_name`; fallback to `"{subject}_General"`.
   - **Subject-level stats:** Update `subject_performance[subject]`: total_questions, correct, total_score, max_score, error_types, concepts set.
   - **Concept-level stats:** Update `concept_performance[concept]`: total_questions, correct, total_score, max_score, error_types, error_details (list of explanations per error type), misconceptions, sample questions.
   - **Question-type stats:** Update `question_type_performance[type]`.
   - **Error patterns:** Count error_type (e.g. No_Answer, Arithmetic, Conceptual) across the report.

### 3.4 Strengths and Areas of Focus

- **Strengths:** Concepts with ≥2 questions and average performance ≥70% (average of accuracy and score_percentage). Sorted by score_percentage descending.
- **Areas of focus:** Concepts with ≥2 questions and average performance <60%. For each:
  - Common error types (top 3) with counts and **explanations** (from stored `detailed_feedback` or fallback text).
  - Unique misconceptions (from stored `misconception`).
  - Sample questions and full `error_details` for use in study guide generation.

### 3.5 Subject-Level Summary

- For each subject, compute accuracy, score_percentage, avg_performance, total_questions, correct_count, total_score, max_score, concepts_count, common_errors.
- Sort by avg_performance (ascending) so weaker subjects appear first.

### 3.6 Study Guide Generation (Optional)

If `generate_study_guides` is true and there are areas of focus:
- **StudyGuideService** is used to create a study guide per focus area (top 5).
- For each area, the service gets: concept name, common_errors (with explanations), misconceptions, child grade, subject.
- Study guides are created and their IDs (and optionally titles/links) are collected into `study_guide_links`.
- These links are attached to the report so the UI can open the Learning Workspace or guide viewer with the right guide.

### 3.7 Report Response Shape (Summary)

The returned object typically includes:
- **tests_count**, **days_back**.
- **overall_accuracy**, **overall_score**, **total_questions**, **correct_count**, **total_score**, **max_score**.
- **subject_performance**: list of subject summaries (subject, accuracy, score_percentage, avg_performance, total_questions, correct_count, total_score, max_score, concepts_count, common_errors).
- **strengths**: list of `{ concept, accuracy, score_percentage, questions_count, most_common_error }`.
- **areas_of_focus**: list of `{ concept, accuracy, score_percentage, questions_count, common_errors (with type, count, explanations), misconceptions, sample_questions, error_details }`.
- **study_guide_links**: list of study guide references (e.g. id, title, concept) for opening in the Learning Workspace or study guide viewer.
- **error_patterns**: counts by error_type across the report.

If insufficient tests: `error`, `tests_count` only.

### 3.8 Frontend Usage

- **Learning Workspace** loads the evaluation report for the selected child (e.g. `days_back=30`, `generate_guides=true`) and displays strengths, focus areas, and links to study guides and revision cards.
- **EvaluationReport** component (or similar) calls `GET /api/v1/tests/child/{child_id}/evaluation-report` and renders the summary, subject breakdown, and focus areas with links to guides.

---

## 4. Cross-References

| Flow | Key API Endpoints | Key Services | Key Background Tasks |
|------|-------------------|--------------|----------------------|
| Document ingestion | `POST /documents/upload`, `GET /documents`, `POST /documents/{id}/reprocess` | DocumentService | enqueue_document_phase1, enqueue_document_processing |
| Test generation & evaluation | `POST /tests/generate`, `POST /tests/{id}/start`, `POST /tests/{id}/answer`, `POST /tests/{id}/submit` | TestGenerationService, QuestionGenerationService, ScoringService, MasteryService | enqueue_test_generation_from_concept, enqueue_test_generation_from_topics |
| Reports | `GET /tests/child/{id}/evaluation-report` | EvaluationReportService, StudyGuideService | (none; report is synchronous, study guides created inline) |

For high-level architecture and diagrams, see [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md) and [ARCHITECTURE_AND_FEATURES_TECHNICAL.md](ARCHITECTURE_AND_FEATURES_TECHNICAL.md).
