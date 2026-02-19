# Zoria — Science Fair–Style Diagrams

This document contains **architecture**, **sequence**, **component**, and **flow** diagrams suitable for presentations, posters, or documentation. All diagrams use [Mermaid](https://mermaid.js.org/) and render in GitHub, GitLab, VS Code markdown preview, and [Mermaid Live Editor](https://mermaid.live).

---

## 1. High-Level Architecture (Layered View)

**Purpose:** One-page view of how users, the app, and external systems fit together.

```mermaid
flowchart TB
    subgraph users["👥 Users"]
        P[Parent]
        C[Child]
        A[Admin]
    end

    subgraph presentation["Presentation Layer"]
        SPA["Zoria Web App\n(React 18 + Vite)"]
    end

    subgraph application["Application Layer"]
        API["FastAPI Backend\n(JWT, RBAC, REST)"]
        Worker["Document Processor\n(Background Worker)"]
    end

    subgraph data["Data & AI"]
        DB[(PostgreSQL\n+ pgvector)]
        FS[(File Store\nPDFs)]
        CloudLLM[Cloud LLM]
        LocalLLM["Local LLM - Ollama"]
    end

    P --> SPA
    C --> SPA
    A --> SPA
    SPA --> API
    API --> DB
    API --> FS
    API --> CloudLLM
    API --> LocalLLM
    Worker --> DB
    Worker --> FS
    Worker --> CloudLLM
    Worker --> LocalLLM
```

---

## 2. System Context (Actors & Systems)

**Purpose:** Who uses Zoria and what external systems it talks to.

```mermaid
flowchart LR
    subgraph actors["Actors"]
        Parent["Parent\nUploads PDFs, views reports"]
        Child["Child\nTakes tests, study guides, coach"]
        Admin["Admin\nManages parents, reprocesses docs"]
    end

    subgraph zoria_system["Zoria"]
        Z["Web App + API\nPDFs → concepts, tests, study tools"]
    end

    subgraph external["External"]
        CloudLLM["Cloud LLM"]
        LocalLLM["Local LLM - Ollama"]
    end

    Parent --> Z
    Child --> Z
    Admin --> Z
    Z --> CloudLLM
    Z --> LocalLLM
```

---

## 2b. Architecture: Actors, Engines & Operations

**Purpose:** Actors (Admin, Parent, Child), main engines with sub-components, and labeled operations.

```mermaid
flowchart TB
    subgraph actors["Actors"]
        Admin[Admin]
        Parent[Parent]
        Child[Child]
    end

    subgraph doc_eng["Document Engine"]
        DocUpload[Upload & store]
        DocParse[Parser & concept extractor]
        DocKG[Knowledge graph]
        DocChunk[Chunking & embedding]
    end

    subgraph quiz_eng["Quiz Engine"]
        QuizGen[Test generation]
        QuizPool[Question pool]
        QuizDeliver[Test delivery]
        QuizScore[Scoring]
    end

    subgraph eval_eng["Evaluation Engine"]
        EvalAgg[Report aggregation]
        EvalFocus[Strengths & focus areas]
        EvalRec[Recommendations]
    end

    subgraph study_eng["Study & Learning Engine"]
        StudyGuide[Study guide generator]
        StudyCards[Revision cards]
        StudyCoach[AI coach]
    end

    Admin -->|reprocess, view KG| doc_eng
    Parent -->|upload PDF, list documents| doc_eng
    Child -->|list assigned docs| doc_eng

    Admin -->|reopen / reevaluate test| quiz_eng
    Parent -->|generate test, view tests| quiz_eng
    Child -->|take test, submit answers| quiz_eng

    Admin -->|view reports| eval_eng
    Parent -->|view evaluation report| eval_eng
    Child -->|view my report| eval_eng

    Admin -->|view guides| study_eng
    Parent -->|open guides, coach| study_eng
    Child -->|study guides, cards, chat coach| study_eng

    doc_eng -->|concepts, question pool| quiz_eng
    quiz_eng -->|test results, scores| eval_eng
    eval_eng -->|focus areas, trigger guides| study_eng

    DocUpload --> DocParse --> DocKG --> DocChunk
    QuizGen --> QuizPool --> QuizDeliver --> QuizScore
    EvalAgg --> EvalFocus --> EvalRec
    StudyGuide --> StudyCards
    EvalRec -.->|triggers| StudyGuide
```

**Notes:** **Document Engine:** Upload & store → Parser & concept extractor (LLM) → Knowledge graph (concepts, prerequisites) → Chunking & embedding. **Quiz Engine:** Test generation (from concepts) → Question pool → Test delivery → Scoring (deterministic / heuristic / LLM). **Evaluation Engine:** Report aggregation (completed tests) → Strengths & focus areas (e.g. ≥70% / &lt;60%) → Recommendations. **Study & Learning Engine:** Study guide generator (per focus area), Revision cards, AI coach (chat in context). Dotted arrow: evaluation recommendations trigger study guide generation. Internal arrows show flow within each engine.

---

## 3. Deployment Architecture

**Purpose:** Where each part of Zoria runs (containers and storage).

```mermaid
flowchart TB
    subgraph client["Client"]
        Browser["Browser"]
    end

    subgraph compose["Docker Compose"]
        subgraph backend["Backend"]
            API["FastAPI :8000"]
            Worker["Document Processor"]
        end
        subgraph db["Database"]
            PG["PostgreSQL 16\n+ pgvector :5432"]
        end
        subgraph front["Frontend"]
            Vite["Vite Dev :3000"]
        end
    end

    subgraph storage["Storage"]
        Vol["Uploads Volume"]
    end

    subgraph external["External"]
        CloudLLM["Cloud LLM"]
        Ollama["Local LLM - Ollama"]
    end

    Browser --> Vite
    Browser --> API
    API --> PG
    API --> Vol
    API --> CloudLLM
    API --> Ollama
    Worker --> PG
    Worker --> Vol
    Worker --> CloudLLM
    Worker --> Ollama
```

---

## 4. Sequence: Document Ingestion (Upload → Ready)

**Purpose:** Step-by-step flow from PDF upload to “ready” document (Phase 1 + Phase 2).

```mermaid
sequenceDiagram
    autonumber
    participant U as User
    participant API as APIGateway
    participant DB as DB & Vector Store
    participant FS as File Store
    participant P1 as Parser
    participant P2 as Indexer
    participant LLM as Cloud LLM

    U->>API: POST /documents/upload (PDF + child_id)
    API->>FS: Save file
    API->>DB: Create document (status: uploaded)
    API->>API: Queue Parsing
    API-->>U: 201 Document created

    rect rgb(240, 248, 255)
        Note over P1, LLM: Parse & Extract
        P1->>FS: Read PDF
        P1->>LLM: Parse PDF → Markdown
        LLM-->>P1: Markdown
        P1->>LLM: Extract concepts (structured)
        LLM-->>P1: Concepts (JSON)
        P1->>DB: Store markdown, concepts, subject (status: parsed)
        P1->>API: Queue Knowledge Graph Extraction and Chunking
    end

    rect rgb(255, 248, 240)
        Note over P2, DB: Knowledge Graph, Questions, Chunks
        P2->>DB: Load document
        P2->>DB: Build knowledge graph, create concepts/relationships
        P2->>DB: Create questions & visuals
        P2->>P2: Chunk document
        P2->>LLM: Embed chunks
        LLM-->>P2: Vectors
        P2->>DB: Store chunks (pgvector)
        P2->>DB: status = ready
    end
```

---

## 4b. Flow: Document Ingestion (Logical)

**Purpose:** Document ingestion at logical level — what happens, sync vs async, and where LLMs are used.

```mermaid
flowchart TB
    subgraph sync["Synchronous — user waits"]
        A[User uploads PDF and assigns to child]
        B[Save file and create document record]
        C[Attach document to selected children]
        D[Enqueue Phase 1 and return response to user]
    end

    subgraph async1["Asynchronous — Phase 1"]
        E[Read PDF]
        F[Call LLM: Parse PDF into structured Markdown]
        G[Call LLM: Extract concepts - topics, difficulty, prerequisites, sample questions]
        H[Derive subject from concepts]
        I[Save Markdown and concepts]
        J[Enqueue Phase 2]
    end

    subgraph async2["Asynchronous — Phase 2"]
        K[Load Markdown and concepts]
        L[Build knowledge graph - concepts and prerequisite links]
        M[Create questions and visuals from extracted concept data]
        N[Chunk document by sections and concepts]
        O[Call LLM: Generate embeddings for chunks]
        P[Store chunks with embeddings for later search]
        Q[Mark document ready]
    end

    LLM[Cloud LLM or Local LLM - Ollama]

    R[Document ready for tests and study]

    A --> B --> C --> D
    D -.->|background| E
    E --> F --> G --> H --> I --> J
    F --> LLM
    G --> LLM
    J -.->|background| K
    K --> L --> M --> N --> O --> P --> Q --> R
    O --> LLM
```

**Notes:** **Synchronous:** User gets a response right after the document is enqueued. **Asynchronous:** Phase 1 and Phase 2 run in the background (dotted arrows show handoff). **LLM calls:** Parse (Phase 1), Concept extraction (Phase 1), and Embeddings (Phase 2) use either **Cloud LLM** or **Local LLM (Ollama)** depending on configuration. The rest of Phase 2 (knowledge graph, questions, chunking, storage) uses the database and no LLM.

---

## 5. Sequence: Take Test & Get Score

**Purpose:** Flow from starting a test to receiving score and mastery update.

```mermaid
sequenceDiagram
    autonumber
    participant C as Child
    participant API as APIGateway
    participant DB as DB & Vector Store
    participant Score as Scoring Service
    participant Mastery as Mastery Service
    participant LLM as Cloud LLM / Local LLM (eval)

    C->>API: POST /tests/generate (concept_id or subject+topics)
    API->>DB: Create test (draft), Queue question generation
    API-->>C: Test created

    Note over API, DB: Background: generate questions → status active

    C->>API: POST /tests/{id}/start
    API->>DB: Start test, load questions
    API-->>C: Questions

    loop Per question
        C->>API: POST /tests/{id}/answer (question_id, response)
        API->>DB: Store response
        API-->>C: OK
    end

    C->>API: POST /tests/{id}/submit
    API->>Score: Evaluate each response (deterministic / heuristic / LLM)
    Score->>LLM: LLM evaluation (if needed)
    LLM-->>Score: Result
    Score->>DB: Update scores
    API->>Mastery: Update mastery by concept
    Mastery->>DB: Persist mastery
    API-->>C: total_score, percentage, mastery_updated
```

---

## 6. Component Diagram — Backend

**Purpose:** Main backend components and how they depend on each other.

```mermaid
flowchart TB
    subgraph api["API (Routers)"]
        AuthR["auth"]
        AdminR["admin"]
        ParentR["parent"]
        ChildR["child"]
        DocR["documents"]
        TestR["tests"]
        TikzR["tikz"]
    end

    subgraph services["Services"]
        AuthS["Auth Service"]
        UserS["User Service"]
        DocS["Document Service"]
        TestGenS["Test Generation"]
        ScoreS["Scoring Service"]
        EvalReportS["Evaluation Report"]
        GuideS["Study Guide Service"]
        KGS["Knowledge Graph"]
        ChunkS["Chunking Service"]
        EmbS["Embedding Service"]
        LLMS["LLM Service"]
    end

    subgraph data["Data & External"]
        DB[(PostgreSQL)]
        FS[(File Store)]
        CloudLLM[Cloud LLM]
        LocalLLM[Local LLM]
    end

    AuthR --> AuthS
    AdminR --> UserS
    ParentR --> UserS
    ParentR --> DocS
    ChildR --> DocS
    ChildR --> TestGenS
    DocR --> DocS
    TestR --> TestGenS
    TestR --> ScoreS
    TestR --> EvalReportS
    DocR --> KGS

    AuthS --> DB
    UserS --> DB
    DocS --> DB
    DocS --> FS
    TestGenS --> DB
    TestGenS --> LLMS
    ScoreS --> DB
    ScoreS --> LLMS
    EvalReportS --> DB
    GuideS --> DB
    GuideS --> LLMS
    KGS --> DB
    KGS --> EmbS
    ChunkS --> DB
    EmbS --> CloudLLM
    EmbS --> LocalLLM
    LLMS --> CloudLLM
    LLMS --> LocalLLM
```

---

## 7. Component Diagram — Frontend (Main UI)

**Purpose:** Main frontend areas and key components.

```mermaid
flowchart TB
    subgraph app["App"]
        AppJSX["App.jsx"]
        AuthState["Auth State\n(JWT, role)"]
    end

    subgraph pages["Pages"]
        AuthPage["Auth (Login / Register / Child PIN)"]
        Dashboard["Dashboard"]
        AdminSettings["Admin Settings"]
    end

    subgraph dashboard["Dashboard Components"]
        Tabs["TabNavigation"]
        DocUpload["DocumentUpload"]
        DocList["DocumentList"]
        CreateChild["CreateChild / EditChild"]
        TestLaunch["TestLauncher"]
        TestList["TestList / TestListGrouped"]
        Quiz["QuizPlayer"]
        EvalReport["EvaluationReport"]
        Workspace["LearningWorkspace"]
        Drawer["LearningDrawer"]
        StudyGuide["StudyGuide"]
        RevisionCards["RevisionCardsView"]
        Coach["AICoach"]
        KGView["KnowledgeGraphViewer"]
    end

    subgraph shared["Shared"]
        Header["Header"]
        Notifications["NotificationContainer"]
        API["api.js (API client)"]
    end

    AppJSX --> AuthState
    AuthState --> AuthPage
    AuthState --> Dashboard
    AuthState --> AdminSettings
    Dashboard --> Tabs
    Tabs --> DocUpload
    Tabs --> DocList
    Tabs --> CreateChild
    Tabs --> TestLaunch
    Tabs --> TestList
    Tabs --> Quiz
    Tabs --> EvalReport
    Tabs --> Workspace
    Workspace --> Drawer
    Drawer --> StudyGuide
    Drawer --> RevisionCards
    Drawer --> Coach
    Drawer --> KGView
    Dashboard --> Header
    Dashboard --> Notifications
    DocUpload --> API
    TestLaunch --> API
    Quiz --> API
```

---

## 8. User Flow: Parent → Document → Child Test

**Purpose:** End-to-end journey from parent uploading a PDF to child taking a test.

```mermaid
flowchart LR
    subgraph parent["Parent"]
        A[Login]
        B[Upload PDF]
        C[Assign to child]
        D[View documents list]
    end

    subgraph system["System"]
        E[Save file]
        F[Phase 1: Parse & concepts]
        G[Phase 2: KG, questions, chunks]
        H[Document ready]
    end

    subgraph child["Child"]
        I[Login with PIN]
        J[Choose test / topic]
        K[Take quiz]
        L[See score & report]
    end

    A --> B
    B --> C
    C --> E
    E --> F
    F --> G
    G --> H
    H --> D
    D -.-> I
    I --> J
    J --> K
    K --> L
```

---

## 9. Process Flow: Document Status Lifecycle

**Purpose:** States a document goes through from upload to ready or failed.

```mermaid
stateDiagram-v2
    [*] --> uploaded: PDF uploaded
    uploaded --> processing: Phase 1 starts
    processing --> parsed: Concepts extracted
    parsed --> processing: Phase 2 starts
    processing --> ready: KG, questions, chunks done
    processing --> failed: Error in Phase 1 or 2
    ready --> [*]
    failed --> [*]
```

---

## 9b. Example: Knowledge Graph (Visual)

**Purpose:** What the knowledge graph looks like — concepts as nodes, prerequisite relationships as directed edges (learn order). Example based on a Mathematics-style hierarchy.

```mermaid
flowchart LR
    subgraph foundations["Foundations"]
        F[Fractions]
        NO[Number & Operations]
    end

    subgraph middle["Build on foundations"]
        D[Decimals]
        RP[Ratios & Proportions]
        E[Expressions]
    end

    subgraph algebra["Algebra"]
        EQ[Equations]
        INEQ[Inequalities]
        FN[Functions]
    end

    F -->|prerequisite of| D
    F -->|prerequisite of| RP
    NO -->|prerequisite of| E
    E -->|prerequisite of| EQ
    E -->|prerequisite of| INEQ
    E -->|prerequisite of| FN
    EQ -->|prerequisite of| INEQ
    NO -->|prerequisite of| FN
```

**Same structure, vertical (learn order top → bottom):**

```mermaid
flowchart TB
    F[Fractions]
    NO[Number & Operations]
    D[Decimals]
    RP[Ratios & Proportions]
    E[Expressions]
    EQ[Equations]
    INEQ[Inequalities]
    FN[Functions]

    F --> D
    F --> RP
    NO --> E
    E --> EQ
    E --> INEQ
    E --> FN
    EQ --> INEQ
    NO --> FN
```

**Notes:** Each **node** is a concept (name, optional subtopic/difficulty). Each **arrow** is a `prerequisite_of` relationship: **A → B** means “learn A before B.” Stored in `concepts` and `concept_relationships` (from_concept_id, to_concept_id, relationship_type). Test generation can “include prerequisites” so a test on e.g. Equations also pulls in questions from Expressions. The real graph is built per document from the Concept Extractor output; this diagram is a typical Mathematics-style example.

---

## 10. Flow: Test Generation

**Purpose:** How a test is generated — inputs, vector/store usage, and question selection.

```mermaid
flowchart TB
    subgraph inputs["Inputs"]
        I1["concept_id OR subject + topics"]
        I2["include_prerequisites"]
        I3["difficulty - easy / medium / hard"]
        I4["num_questions, time_limit_minutes"]
        I5["language"]
    end

    subgraph api["API"]
        CreateDraft["Create draft test - status pending"]
        Enqueue["Enqueue background generation"]
    end

    subgraph bg["Background: Test Generation"]
        GetConcepts["Resolve concept IDs - main + prerequisites from KG"]
        GetChild["Get child profile - grade_level"]
        GetSubject["Get subject - from concept metadata / normalize"]
        CheckPool["Check question pool per concept - includes existing questions from document ingestion"]
        NeedMore{"Pool insufficient?"}
        GetChunks["Vector store: get_chunks_by_concept - content_chunks for concept_overview, explanation - up to 5 chunks as context"]
        LLMGen["LLM: generate additional questions - context = chunks + subject_profile + difficulty + language"]
        StoreQ["Store new questions - question_repo"]
        FetchAll["Fetch all questions by concept - from DB: document-origin questions + LLM-generated; filter status != rejected"]
        FilterDiff["Filter by inclusive difficulty - easy only / easy+medium / all"]
        Select["Random sample - num_questions"]
        Attach["Attach questions to test - test_questions"]
        Activate["Set test status = active"]
    end

    I1 --> CreateDraft
    I2 --> CreateDraft
    I3 --> CreateDraft
    I4 --> CreateDraft
    I5 --> CreateDraft
    CreateDraft --> Enqueue
    Enqueue --> GetConcepts
    GetConcepts --> GetChild
    GetConcepts --> GetSubject
    GetChild --> CheckPool
    GetSubject --> CheckPool
    CheckPool --> NeedMore
    NeedMore -->|Yes| GetChunks
    GetChunks --> LLMGen
    LLMGen --> StoreQ
    StoreQ --> FetchAll
    NeedMore -->|No| FetchAll
    FetchAll --> FilterDiff
    FilterDiff --> Select
    Select --> Attach
    Attach --> Activate
```

**Notes:** The **question pool** includes **existing questions from the uploaded document**: during document ingestion (Phase 2), the Concept Extractor’s per-concept `questions` are stored in the `questions` table. Test creation uses these when the pool is sufficient. When the pool is **insufficient**, the system fetches **content_chunks** (by concept_id) as context for the LLM, generates additional questions, stores them, then either uses only the newly generated set for this test or all questions for the concept (implementation may filter to the new batch when LLM ran). Question generation uses chunks as study context; no vector similarity search at generation time. Questions are stored with optional embeddings for **semantic deduplication** (e.g. find_similar_questions). Test can be created from **concept_id** or **subject + topics**.

---

## 11. Flow: Test Evaluation (Scoring)

**Purpose:** How a single response is graded — routing by question type and use of deterministic, heuristic, or LLM evaluator.

```mermaid
flowchart TB
    subgraph input["Input"]
        TestId["test_id"]
        QuestionId["question_id"]
        Answer["student answer - text or drawing payload"]
        Behavioral["optional behavioral_data"]
    end

    subgraph load["Load"]
        GetQ["Get question - type, metadata, correct_answer, expected_answer"]
        GetMax["Get max_score from test_questions"]
        Extract["Extract answer component - e.g. MCQ choice, FRQ text"]
    end

    subgraph route["Evaluation path"]
        IsDrawing{"Is drawing - graph/diagram?"}
        GraphEval["GraphEvaluationService - grade drawing - LLM if needed"]
        Router["QuestionRouter - route by question_type"]
        Det["Deterministic - MCQ, matching, fill_in_the_blank - exact match"]
        Heur["Heuristic - numerical short_answer - tolerance percent"]
        LLM["LLM Evaluator - short_answer text, problem_solving, essay - rubric + detailed_feedback"]
    end

    subgraph output["Output and persist"]
        Penalty["Apply behavioral penalties if any"]
        Persist["Persist score, error_type, misconception, detailed_feedback - test_responses"]
        Mastery["MasteryService - update concept mastery"]
    end

    TestId --> GetQ
    QuestionId --> GetQ
    Answer --> Extract
    GetQ --> GetMax
    GetQ --> Extract
    Extract --> IsDrawing
    IsDrawing -->|Yes| GraphEval
    IsDrawing -->|No| Router
    Router --> Det
    Router --> Heur
    Router --> LLM
    GraphEval --> Penalty
    Det --> Penalty
    Heur --> Penalty
    LLM --> Penalty
    Penalty --> Persist
    Persist --> Mastery
```

**Routing (question_type → evaluator):**  
- **multiple_choice, matching, fill_in_the_blank** → Deterministic (exact/match).  
- **short_answer** (numerical) → Heuristic (tolerance); (text) → LLM.  
- **problem_solving, conceptual_question, essay, free_response** → LLM (rubric, detailed feedback).

---

## 12. Flow: Evaluation Report and Study Guide

**Purpose:** How the evaluation report is built and how study guides are triggered for focus areas.

```mermaid
flowchart TB
    subgraph report_input["Report input"]
        ChildId["child_id"]
        DaysBack["days_back - e.g. 30"]
        MinTests["min_tests - e.g. 1"]
        GenGuides["generate_study_guides - bool"]
        Lang["language"]
    end

    subgraph fetch["Fetch and aggregate"]
        GetTests["Get completed tests - child_id, completed_at >= cutoff"]
        MinCheck{"tests count >= min_tests?"}
        ForEachTest["For each test - get_test_with_questions"]
        Aggregate["Aggregate by concept - total_questions, correct, total_score, max_score, error_types, error_details, misconceptions, sample questions"]
    end

    subgraph classify["Classify concepts"]
        Strength["Strengths - avg_performance >= 70%, at least 2 questions"]
        Focus["Areas of focus - avg_performance < 60%, at least 2 questions"]
    end

    subgraph study_guide["Study guide - per focus area - up to 5"]
        SGInput["Input: concept_name, focus_area, subject, topic_from_test, common_errors, misconceptions, sample_questions"]
        CheckExist["Existing guide for child + concept + focus_area?"]
        Reuse["Return existing guide"]
        BuildPrompt["Build prompt - concept_info from repo, child context - language, errors, misconceptions, sample Qs"]
        LLMSG["LLM - generate study guide markdown"]
        Cards["Generate revision cards from content"]
        SaveSG["Save study_guides + revision cards"]
    end

    subgraph report_out["Report output"]
        Overall["overall_performance - total_questions, correct_count, score_percentage"]
        StrengthsList["strengths - list"]
        FocusList["areas_of_focus - list - with common_errors, misconceptions, sample_questions"]
        GuideLinks["study_guide_links - placeholder if generating in background"]
        Recs["recommendations - from strengths and focus"]
    end

    ChildId --> GetTests
    DaysBack --> GetTests
    GetTests --> MinCheck
    MinCheck -->|No| report_out
    MinCheck -->|Yes| ForEachTest
    ForEachTest --> Aggregate
    Aggregate --> Strength
    Aggregate --> Focus
    Strength --> StrengthsList
    Focus --> FocusList
    Focus --> report_out
    StrengthsList --> report_out
    GenGuides --> GuideLinks
    Focus --> SGInput
    SGInput --> CheckExist
    CheckExist -->|Yes| Reuse
    CheckExist -->|No| BuildPrompt
    BuildPrompt --> LLMSG
    LLMSG --> Cards
    Cards --> SaveSG
    SaveSG --> GuideLinks
    Reuse --> GuideLinks
    Aggregate --> Overall
    Overall --> report_out
    FocusList --> report_out
    StrengthsList --> Recs
    FocusList --> Recs
```

**Notes:** Report uses **completed tests** in the window only. **Strengths** = concepts with avg (accuracy + score%) / 2 ≥ 70%; **areas of focus** = below 60%. Study guides are generated per focus area (subject + topic from test required); prompt uses concept info, common_errors, misconceptions, and sample questions — no vector search. Guides can be returned as placeholders while generated in background.

---

## 13. Data Flow: Core Entities

**Purpose:** How main entities relate (simplified ER for a poster).

```mermaid
erDiagram
    parents ||--o{ children : has
    parents ||--o{ documents : uploads
    children ||--o{ document_children : assigned
    documents ||--o{ document_children : assigned_to
    documents ||--o{ concepts : contains
    documents ||--o{ content_chunks : contains
    concepts }o--o{ concepts : prerequisite
    documents ||--o{ questions : generated_from
    children ||--o{ tests : takes
    tests ||--o{ test_questions : has
    tests ||--o{ test_responses : has
    children ||--o{ study_guides : has

    parents { uuid id string email }
    children { uuid id uuid parent_id string name }
    documents { uuid id string filename string status }
    concepts { uuid id string name string subject }
    tests { uuid id uuid child_id string status }
```

---

## Exporting as Images (Science Fair / Slides)

1. **Mermaid Live Editor:** Copy a code block into [mermaid.live](https://mermaid.live), then use **Export** → PNG or SVG.
2. **VS Code:** Use a “Mermaid” or “Markdown Preview Mermaid” extension and export from preview.
3. **CLI:**  
   `npx @mermaid-js/mermaid-cli -i docs/DIAGRAMS_SCIENCE_FAIR.md -o docs/diagrams/`  
   (with a config that outputs one image per diagram if needed.)

For a **science fair poster**, use the **Layered Architecture (Section 1)**, **Document Ingestion Sequence (Section 4)**, **User Flow (Section 8)**, and the **Test Generation / Evaluation / Report flows (Sections 10–12)** for a clear story: what Zoria is, how a document becomes ready, and how a child gets from PDF to quiz.

See also: [ARCHITECTURE_DIAGRAM.md](ARCHITECTURE_DIAGRAM.md), [DETAILED_FLOWS.md](DETAILED_FLOWS.md), [ARCHITECTURE_AND_FEATURES_TECHNICAL.md](ARCHITECTURE_AND_FEATURES_TECHNICAL.md).
