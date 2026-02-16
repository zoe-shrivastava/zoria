# Zoria — High-Level Architecture Diagrams

Mermaid diagrams for system context, components, and main flows. They render in GitHub, GitLab, VS Code markdown preview, and [Mermaid Live Editor](https://mermaid.live).

---

## 1. System Context (Users & External Systems)

```mermaid
flowchart LR
    subgraph users["Users"]
        Parent
        Child
        Admin
    end

    subgraph zoria["Zoria Platform"]
        WebApp["Web App\n(React SPA)"]
    end

    subgraph external["External Services"]
        OpenAI["OpenAI API\n(Agents, Embeddings, Chat)"]
    end

    Parent --> WebApp
    Child --> WebApp
    Admin --> WebApp
    WebApp --> OpenAI
```

---

## 2. Deployment / Containers

```mermaid
flowchart TB
    subgraph client["Client"]
        Browser["Browser\n(React 18 + Vite)"]
    end

    subgraph docker["Docker Compose"]
        subgraph backend["Backend Container"]
            API["FastAPI\n:8000"]
            Worker["Document Processor\n(background)"]
        end

        subgraph db["PostgreSQL Container"]
            PG["PostgreSQL 16\n+ pgvector\n:5432"]
        end

        subgraph front["Frontend Container"]
            Vite["Vite Dev Server\n:3000"]
        end

        subgraph optional["Optional"]
            Tunnel["Cloudflared\n(tunnel)"]
        end
    end

    subgraph storage["Storage"]
        Vol["Uploads Volume\n(PDF files)"]
    end

    Browser --> Vite
    Browser --> API
    Vite --> API
    API --> PG
    API --> Vol
    Worker --> PG
    Worker --> OpenAI
    API --> OpenAI
    Tunnel -.-> Vite
    Tunnel -.-> API
```

---

## 3. Backend Components & Data Stores

```mermaid
flowchart TB
    subgraph api["API Layer"]
        Auth["Auth\n(JWT, RBAC)"]
        Routers["Routers\n(auth, admin, parent, child,\ndocuments, tests, tikz)"]
    end

    subgraph services["Services Layer"]
        AuthSvc["Auth Service"]
        UserSvc["User Service"]
        DocSvc["Document Service"]
        TestSvc["Test / Scoring / Evaluation"]
        GuideSvc["Study Guide Service"]
        KGSvc["Knowledge Graph Service"]
        LLMSvc["LLM Service"]
        EmbSvc["Embedding Service"]
    end

    subgraph data["Data & External"]
        DB[(PostgreSQL\n+ pgvector)]
        Files[(File Store\nuploads)]
        OpenAI[OpenAI API]
    end

    Auth --> Routers
    Routers --> AuthSvc
    Routers --> UserSvc
    Routers --> DocSvc
    Routers --> TestSvc
    Routers --> GuideSvc
    Routers --> KGSvc

    AuthSvc --> DB
    UserSvc --> DB
    DocSvc --> DB
    DocSvc --> Files
    TestSvc --> DB
    TestSvc --> LLMSvc
    GuideSvc --> DB
    GuideSvc --> LLMSvc
    KGSvc --> DB
    KGSvc --> EmbSvc
    LLMSvc --> OpenAI
    EmbSvc --> OpenAI
```

---

## 4. Document Processing Flow

```mermaid
sequenceDiagram
    participant U as User (Parent/Admin)
    participant API as FastAPI
    participant DB as PostgreSQL
    participant FS as File Store
    participant Worker as Document Processor
    participant OpenAI as OpenAI API

    U->>API: Upload PDF (+ child_id)
    API->>FS: Save file
    API->>DB: Create document (processing)
    API-->>U: 201 Document created

    Note over Worker: Background processing
    Worker->>FS: Read PDF
    Worker->>OpenAI: Parse PDF → markdown
    OpenAI-->>Worker: Markdown
    Worker->>OpenAI: Extract concepts
    OpenAI-->>Worker: Concepts (JSON)
    Worker->>DB: Store concepts, build KG, chunks
    Worker->>DB: Update document (completed)
```

---

## 5. Request Flow (Typical API Call)

```mermaid
flowchart LR
    A[Browser] --> B[API Router]
    B --> C{Dependencies\nAuth / RBAC}
    C --> D[Service]
    D --> E[Repository]
    E --> F[(Database)]
    D -.-> G[LLM / Embedding]
    G -.-> H[OpenAI]
```

---

## 6. Data Model (Core Entities)

```mermaid
erDiagram
    parents ||--o{ children : "has"
    parents ||--o{ documents : "uploads"
    children ||--o{ documents : "assigned"
    documents ||--o{ chunks : "contains"
    documents ||--o{ concepts : "extracted"
    concepts }o--o{ concepts : "prerequisite"
    documents ||--o{ questions : "generated from"
    children ||--o{ tests : "takes"
    tests ||--o{ test_questions : "has"
    questions ||--o{ test_questions : "used in"
    tests ||--o{ test_responses : "has"
    children ||--o{ study_guides : "has"

    parents {
        uuid id PK
        string email
        string role
    }

    children {
        uuid id PK
        uuid parent_id FK
        string name
        string pin_hash
    }

    documents {
        uuid id PK
        uuid child_id FK
        string filename
        jsonb concepts
    }

    tests {
        uuid id PK
        uuid child_id FK
        string status
    }
```

---

## Exporting as Images

To get PNG/SVG for slides or wikis:

1. Copy a Mermaid code block into [Mermaid Live Editor](https://mermaid.live) and export.
2. Or use the Mermaid CLI: `npx @mermaid-js/mermaid-cli -i ARCHITECTURE_DIAGRAM.md -o diagrams/` (with appropriate config to split diagrams).

See also: [Architecture & Features (Technical)](ARCHITECTURE_AND_FEATURES_TECHNICAL.md).
