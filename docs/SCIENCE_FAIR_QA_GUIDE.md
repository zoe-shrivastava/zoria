# Zoria — Science Fair Q&A Guide

This guide answers a set of questions about Zoria’s vision, emotional inference, architecture, data, evaluation, and gaps. **Where the codebase or docs do not provide an answer, this is stated explicitly.**

---

## Project Vision & Purpose

### The Problem: "What is the biggest problem with current online learning platforms that Zoria aims to fix?"

**Answer:** The codebase and business docs do not state a single “biggest problem” or explicit competitive critique. What is documented:

- Zoria turns **uploaded PDFs** into **structured learning**: concepts, knowledge graph, tests, study guides, revision cards, and an AI coach, all tied to **each child’s progress**.
- It aims to give families and educators “one place” for content and progress, with a closed loop: **Upload → Process → Concepts/Graph → Tests & Study Guides → Child takes tests → Evaluation reports → Study guides & coach.**

So the implied focus is: **lack of personalization from raw materials** (PDFs) and **no single loop from assessment to targeted study**. A science-fair narrative could be: “Current platforms often use fixed curricula and one-size-fits-all tests; Zoria personalizes from the family’s own materials and connects test results directly to study guides and practice.”

---

### The Name: "What does the name 'Zoria' represent in the context of a student's learning journey?"

**Answer:** The codebase and documentation do **not** define or explain the name “Zoria” (no README, vision doc, or comment). You would need to define this for the science fair (e.g. “dawn” / “new beginning” of understanding, or a backronym, or team choice).

---

### Middle School Focus: "Why is middle school the critical age for an emotional adaptive system like this?"

**Answer:** The codebase does **not** state that Zoria is “middle school only” or why middle school is critical. The business doc mentions “Middle School level” in the study guide tone. Child profiles support a **grade** field, and there is no hard restriction to middle school. So: **no documented rationale for “middle school as the critical age.”** You can add your own (e.g. identity formation, readiness for self-regulated learning, transition to abstract thinking).

---

### Differentiation: "If I use Khan Academy or Google Classroom, how is Zoria fundamentally different in its decision-making?"

**Answer:** The docs do **not** compare Zoria to Khan Academy or Google Classroom. From the architecture, the **fundamental differences** you can state are:

- **Content source:** Zoria builds the learning graph from **PDFs you upload** (your curriculum), not from a fixed course library.
- **Decision-making:** Tests and study guides are generated from **document-derived concepts** and a **per-document knowledge graph**; evaluation reports then drive **which concepts** get study guides and practice (strengths vs areas of focus).
- **Loop:** Zoria explicitly connects **test results → evaluation report → study guides & AI coach** in one workspace; the “decision” of what to study next is driven by **performance (e.g. &lt;60% = area of focus)** and optional **behavioral/session state** (see Emotional section below).

So the difference is: **curriculum-from-your-PDFs + concept-level assessment + automated “what to study next” from report data (and optionally behavior).**

---

## The Emotional Inference Engine

### Camera-less Sensing: "How can you tell if a student is frustrated without using a webcam or facial recognition?"

**Answer:** Zoria does **not** use a camera. It infers session state from **behavioral and response data** only. The logic lives in `backend/services/state_inference.py`:

- **Inputs:** Per-question and aggregate: `latency_ms`, `idle_time_ms`, `edit_count`, `hints_accessed`, `confidence_score` (1–5), `navigation_actions` (e.g. skip, flag), and **correctness/score**.
- **“Frustrated”** is inferred when: at least 2 questions, **many hints** (≥2), **low score** (&lt;40%), and either **high idle ratio** (≥0.4) or **many skip/flag actions** (≥2).

So frustration is inferred from: **slow or idle time, heavy hint use, low score, and avoidant behavior (skips/flags)** — no face or voice.

---

### Confidence Calibration: "If a student is 'overconfident' (getting questions wrong but rating themselves high), how does Zoria adjust the lesson?"

**Answer:** The system does **not** change the “lesson” in real time. It uses confidence for **mastery and reporting**:

- **Scoring:** No direct score penalty for overconfidence. **Hint use** does apply a **score penalty** (e.g. −10% per hint in `scoring_service.py`).
- **Mastery (MasteryService):** Confidence is used to **weight** how much each response affects mastery:
  - **Correct + high confidence** → more positive weight.
  - **Wrong + high confidence** → treated as **deeper misconception**: higher penalty via `ErrorLibrary.get_mastery_penalty(error_type)` (e.g. conceptual errors get 50% penalty). So overconfident-wrong answers **reduce mastery more** than wrong-with-low-confidence.
- **Session state:** High confidence + low score can contribute to labels like **“rushing”** or **“frustrated”** in `state_inference.py`; that state is stored on the test (e.g. for reporting) but there is **no documented in-session change of lesson or difficulty** based on it.

So: **adjustment is in mastery weighting and session labeling, not in live lesson content.**

---

### The Frustration Loop: "If the system detects a 'rapid wrong streak,' what specific scaffolded steps does it take to help?"

**Answer:** The codebase does **not** implement a “rapid wrong streak” detector or **scaffolded steps** during a test. Session state is inferred **after** the test (e.g. “frustrated,” “struggling”) and stored; there is no logic that, mid-test, detects a streak and then changes questions, difficulty, or hints. So: **no specific scaffolded steps are implemented for a wrong streak.** You could propose this as a future feature (e.g. “after N wrong in a row, offer a hint or easier question”).

---

### Engagement: "How does the system distinguish between a student who is 'thoughtful and slow' versus 'bored and disengaged'?"

**Answer:** Partially. `state_inference.py` uses **latency, idle time, edits, hints, score, and navigation**:

- **Slow but engaged:** High latency, lower idle ratio, few skips, decent score → can fall into **“engaged”** or **“struggling”** (e.g. hints or edits with score &lt;70%).
- **Rushing:** Very low latency + low score + skips → **“rushing.”**
- **Frustrated:** Many hints, low score, high idle ratio or many skips → **“frustrated.”**

The code does **not** explicitly label “bored and disengaged.” High idle ratio and skips could contribute to “frustrated”; “thoughtful and slow” is not a distinct state—slow + good score would likely be **“engaged”** or **“confident.”** So: **distinction is implicit via latency vs idle vs score vs skips, not via a dedicated “bored” vs “thoughtful” label.**

---

## System Architecture & Logic

### The "Brain": "Can you explain the difference between the 'Adaptive Decision Engine' and the 'LLM Content Generator'?"

**Answer:** The docs do **not** use the terms “Adaptive Decision Engine” or “LLM Content Generator” as named components. In practice:

- **Decision/control logic:** Handled by **services and API**: e.g. which concepts to test (concept_id or subject+topics, optional prerequisites), which questions to show (from pool + difficulty filter), how to grade (question_router: deterministic/heuristic/LLM), and what to report (evaluation report: strengths vs areas of focus). No single “Adaptive Decision Engine” module.
- **LLM “content”:** LLMs are used for: **document parsing and concept extraction** (workflow), **question generation** (QuestionGenerationService), **evaluation of free-form answers** (LLMEvaluator), **study guide generation**, **revision cards**, and **AI coach**. So: **“decision” = backend services + rules + DB; “content” = LLM for text/generation tasks.** You can describe it that way at the fair.

---

### Knowledge Graphs: "How does the system know that Concept A must be learned before Concept B?"

**Answer:** Concepts and prerequisites come from **document processing** and are stored in the **knowledge graph**:

- **Concept extractor (Phase 1):** The LLM workflow extracts concepts from markdown; each concept can include a **`prerequisites`** list (e.g. concept names).
- **Phase 2 (DocumentProcessor):** `KnowledgeGraphService.process_concepts()` creates/merges concept rows and builds **`concept_relationships`** with types like **`prerequisite_of`** and **`requires`** (see `test_generation_service._get_prerequisite_concepts`: it queries `concept_relationships` for these types).
- **Test generation:** When **“include prerequisites”** is enabled, the system resolves **prerequisite concept IDs** from `concept_relationships` and includes those concepts (and their questions) in the test.

So: **prerequisite order is defined at extraction time (LLM) and stored in the DB; test generation uses it to include prerequisite concepts when requested.**

---

### Vector Search: "What is a 'vector embedding,' and how does it help Zoria find the right study 'chunk' for a specific question?"

**Answer:**

- **Vector embedding:** A numerical vector (e.g. 1024 dimensions) that represents the **semantic meaning** of a piece of text (from an embedding model, e.g. Cloud LLM or Local LLM / Ollama). Similar meaning → vectors that are “close” in distance (e.g. cosine similarity).
- **In Zoria:**  
  - **Content chunks** (e.g. `content_chunks` table) store **chunk_text** and an **embedding**; **questions** can have an optional **embedding** for deduplication.  
  - **Question generation:** The system fetches **chunks by concept** (`get_chunks_by_concept`) to use as **context** for the LLM—it does **not** use vector similarity at that step; it uses concept_id.  
  - **Vector similarity** is used in the **question repository** (`find_similar_questions`) for **semantic deduplication** (avoid generating near-duplicate questions for a concept). So: **embeddings help “find the right chunk” indirectly (by concept) and help find similar questions (vector search) for quality control.**

---

### Local vs. Cloud: "What are the advantages of running a Local LLM via Ollama compared to a Cloud LLM?"

**Answer:** The codebase supports **both** (diagrams refer to “Cloud LLM” and “Local LLM - Ollama”); it does **not** document a formal comparison. You can state typical advantages of local (Ollama) vs cloud:

- **Local (Ollama):** Privacy (data stays on your machine), no per-call cost, lower latency for local requests, works offline, configurable models.
- **Cloud:** No GPU/host management, often stronger or more specialized models, automatic scaling. Zoria can use either depending on configuration.

---

### Deterministic vs. LLM Scoring: "Why can't you use a simple 'exact match' to grade a problem-solving essay?"

**Answer:** Because problem-solving and essay answers are **free-form**: different wording, different order of steps, and partial credit. The code reflects this:

- **Deterministic evaluator:** Used for **multiple_choice**, **matching**, **fill_in_the_blank** — exact or structured match.
- **LLM evaluator:** Used for **short_answer** (text), **problem_solving**, **conceptual_question**, **essay**, **free_response** — rubric-based scoring (e.g. 4-point scale), step-by-step feedback, and misconception tagging. The LLM can judge **conceptual correctness** and **logical consistency** and assign partial credit; exact match cannot.

So: **exact match fails for open-ended answers; LLM grading allows semantic and partial-credit evaluation.**

---

## Data & Development

### Document Ingestion: "Walk me through what happens to a PDF between the moment a parent uploads it and the moment it becomes 'Ready.'"

**Answer:** (From `DETAILED_FLOWS.md` and architecture.)

1. **Upload (synchronous):** Parent (or admin) calls `POST /api/v1/documents/upload` with PDF and child_id/child_ids. Backend saves the file to disk, creates a **document** row (status e.g. **uploaded**), attaches it to children, and **enqueues Phase 1**; response returns immediately.
2. **Phase 1 (background):** Status → **processing**. Workflow runs: **Document parser** (LLM) turns PDF → **markdown**. **Concept extractor** (LLM) returns **concepts** (subject, topic, subtopic, difficulty, prerequisites, questions, keywords). Subject is derived (e.g. most common subject_name). Markdown, concepts, and subject are saved; status → **parsed**; **Phase 2** is enqueued.
3. **Phase 2 (background):** **Knowledge graph:** concepts and **concept_relationships** (e.g. prerequisites) are created/merged. **Questions and visuals** from concept data are created. **Chunking:** document is chunked (with metadata). **Embeddings:** chunks are embedded (Cloud or Local LLM). Chunks are stored in **content_chunks** (with vectors). Status → **ready** (or **failed** on error).

So: **Upload → save + DB record → Phase 1 (parse + concepts) → Phase 2 (KG + questions + chunk + embed) → Ready.**

---

### FastAPI & React: "Why did you choose FastAPI for the backend instead of a simpler framework?"

**Answer:** The project docs do **not** state why FastAPI was chosen. You can say: **FastAPI** gives async support, automatic OpenAPI docs (`/docs`), Pydantic validation, and good performance; **React** gives a component-based UI and a rich ecosystem. Together they support a modern, API-first SPA with clear contracts. So: **no explicit “why” in repo; this is a reasonable technical justification.**

---

### Database Design: "How does PostgreSQL with pgvector store both student grades and the 'meaning' of the textbook?"

**Answer:**

- **Grades and structured data:** PostgreSQL stores **users, children, documents, concepts, tests, test_questions, test_responses** (with scores, correctness, error_type, etc.), **study_guides**, and **student_concept_mastery**. So grades and test results are normal relational rows.
- **“Meaning” of the textbook:** The **content_chunks** table (and similar) store **chunk_text** plus an **embedding** column (e.g. `vector(1024)`). The embedding is a dense vector from an embedding model over that text; **pgvector** provides index and operators (e.g. cosine distance) so you can do **similarity search**. So: **“meaning” is stored as vectors; grades and metadata as standard columns.**

---

### Testing Mode: "How does the 'Adaptive Testing Mode' change in real-time if a student starts experiencing an emotional spike?"

**Answer:** The codebase does **not** implement **real-time adaptive testing** that changes the test when an “emotional spike” is detected. Session state (**engaged**, **struggling**, **frustrated**, **rushing**, **confident**) is computed **after** the test from behavioral and response data and stored in test metadata (e.g. `inferred_session_state`). It is used for **reporting and context**, not for changing the next question or difficulty during the test. So: **no real-time change of testing mode based on emotional spike.**

---

## Evaluation & Impact

### Measuring Success: "What are the three system variants you would compare to prove that emotional logic actually helps students learn faster?"

**Answer:** The codebase does **not** define “three system variants” or an experiment design. You could propose, for example: (1) **Baseline:** no behavioral data, no confidence, no session inference. (2) **Behavioral only:** collect latency, hints, etc., but no mastery weighting or report. (3) **Full:** behavioral + confidence-weighted mastery + session state in reports. Compare outcomes (e.g. same-concept retest scores, time to reach mastery, or engagement metrics). So: **no predefined variants; this is a suggested research design.**

---

### Retention: "How does Zoria track 'Stability' to ensure a student hasn't just memorized a fact for five minutes?"

**Answer:** The codebase does **not** implement a “stability” or **retention** metric (e.g. forgetting curves, spaced repetition, or “memory strength”). **Mastery** is updated from test results (and optionally weighted by confidence and error type); there is no separate tracking of **when** the student last demonstrated mastery or decay over time. So: **stability/retention is not implemented; you’d need to add it (e.g. time-weighted or repeated-test logic).**

---

### The "Aha" Moment: "Can you give me an example of a specific recommendation the system would generate in the 'Evaluation Report'?"

**Answer:** Yes. Recommendations are built in `evaluation_report_service._generate_recommendations()` and returned in the report. Examples from the code:

- **From top area of focus:**  
  *"Focus on improving [concept name] - current performance: [score_percentage]%"*
- **From common errors in that area:**  
  *"Most common error type: [error_type] ([count] occurrences)"*
- **From global error patterns:**  
  *"Practice more on [error_type] errors - appeared [count] times"*
- **Positive reinforcement:**  
  *"Great work on [strength concept]! Keep practicing to maintain this strength."*

So an “aha” moment could be: **“Focus on improving Speed & Velocity - current performance: 45%”** plus **“Most common error type: Unit_Mismatch (3 occurrences)”** — pointing the student to a specific concept and error type with a link to a study guide.

---

### Scalability: "Could Zoria be used for subjects like Art or Physical Education, or is it strictly for academic subjects like Math and Science?"

**Answer:** The system is **subject-agnostic** in design: subjects come from **subject_profiles.json** and from **concept extraction** (LLM). Documents can be any PDF; the concept extractor and chunking are not limited to math/science. **Study guides and question generation** use subject profiles (e.g. mathematics, physics, “other”); adding **Art** or **Physical Education** would mean adding profiles and validation rules for those subjects. So: **not strictly math/science; extendable to other subjects (including Art/PE) with subject configuration and content that the LLM can parse into concepts.**

---

## The "Gap" Questions (Where you must lead)

### Behavioral Data: "What specific 'behavioral data' triggers a penalty or a boost in a student's mastery score?"

**Answer:**

- **Score penalty (during grading):** Only **hints_accessed**: −10% of **max_score** per hint (in `ScoringService._apply_behavioral_penalties`). No penalty for latency, idle time, or confidence on the **displayed score**.
- **Mastery (weighting, not a direct “penalty/boost” label):**  
  - **Confidence:** Correct + higher confidence → more positive weight; wrong + higher confidence → larger **downward** effect (deeper misconception).  
  - **Error type:** Each error type has a **mastery penalty multiplier** (e.g. Conceptual 0.5, Arithmetic 0.8, Unit_Mismatch 0.9) in `ErrorLibrary.get_mastery_penalty`. So: **hints reduce question score; confidence and error type weight mastery updates.**

---

### The Subject Matter: "During your testing, what specific subject did you use, and how did the Concept Graph for that subject look?"

**Answer:** The codebase and **subject_config** reference subjects like **mathematics**, **physics**, and **other**; sample/export data (e.g. `output.json`) shows **Physics** concepts (e.g. “Speed & Velocity,” “Motion & Forces”) with **prerequisites** arrays (often empty in that sample). The **concept graph** is built per document: nodes = concepts, edges = **concept_relationships** (e.g. `prerequisite_of`, `requires`). So: **for demos, Physics (and Math) appear; the graph is document-driven and can show prerequisite links when the extractor and KG pipeline populate them.** You would describe the actual subject and graph you used in your own testing.

---

### User Feedback: "When a student sees their 'Evaluation Report,' how do you present their 'Areas of Focus' without making them feel discouraged?"

**Answer:** The UI does not document a formal “discouragement-free” framework. From `EvaluationReport.jsx`, **Areas of Focus** are presented as:

- **Task-oriented cards** with concept name, question count, and accuracy.
- A **progress bar** (e.g. score_percentage) with color (e.g. red &lt;60%, primary 60–70%, green ≥70%).
- **Common Issues:** error types and counts in small chips.
- A **“Master this concept”** (or similar) **button** that opens the **study guide** or practice, framing the area as something to **work on** with a clear next step.

So: **framing is “areas to work on” with progress and a concrete action (study guide), not only “you failed.”** The child profile also supports **prefer_indirect_guidance** for emotional/sensitive topics, which can be used to soften language in guides/coach. You could add explicit copy (e.g. “Here’s where to grow”) to make the tone more encouraging.

---

*This guide was generated from the Zoria codebase and docs. Where an answer is not found, it is marked; you can extend it with your own vision, experiments, and messaging for the science fair.*
