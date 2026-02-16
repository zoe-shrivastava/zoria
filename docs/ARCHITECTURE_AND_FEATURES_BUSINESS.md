# Zoria — Architecture & Feature Review (Business User Perspective)

**Document purpose:** High-level overview of what Zoria is, who it serves, and what it does—written for product, stakeholders, and business users.

---

## 1. What Is Zoria?

**Zoria** is an **educational learning platform** that helps families and educators turn uploaded learning materials (PDFs) into structured, personalized learning: concepts, tests, study guides, and an AI coach—all tied to each child’s progress.

---

## 2. Who Uses Zoria?

| Role | Who they are | What they do |
|------|----------------|--------------|
| **Parent** | Guardian at home | Manages children, uploads documents, views reports and tests, uses learning workspace. |
| **Child** | Student | Takes tests, sees own documents and reports, uses study guides and AI coach. |
| **Admin** | Platform / org admin | Manages parents (create, list, deactivate), can view all children/documents, reprocess documents, view LLM usage, reopen/reevaluate tests. |

---

## 3. High-Level “Architecture” (How It Feels to Users)

- **One place to learn:** Web app (browser). Parents and children sign in and see a dashboard.
- **Content comes from PDFs:** Parent (or admin) uploads PDFs for a child. The system processes them in the background and extracts concepts, builds a knowledge graph, and can generate tests and study guides.
- **Progress is per child:** Each child has a profile. Documents, tests, study guides, and reports are scoped to that child.
- **Learning loop:** Upload → Process → Concepts/Graph → Tests & Study Guides → Child takes tests → Evaluation reports → Study guides & AI coach to improve.

No need for users to understand servers or databases; they experience “upload, wait a bit, then use documents, tests, and learning tools.”

---

## 4. Feature Review (Business User Perspective)

### 4.1 Getting Started & Access

- **Registration / login:** Parents register with email and password; admins can also create parent accounts.
- **Child login:** Children sign in with a PIN (and child identity) for a simple, age-appropriate experience.
- **Session & security:** Logout, session expiry, and optional inactivity timeout (e.g. 15 minutes) keep access controlled.

### 4.2 Child & Profile Management (Parents & Admins)

- **Create and manage children:** Parents create child profiles (name, grade, age, etc.); admins can see all children.
- **Child profiles:** Each child has a dedicated profile; documents and learning data are linked to that profile.

### 4.3 Documents

- **Upload PDFs:** Parents (or admins) upload PDFs and assign them to a child.
- **Processing:** After upload, the system:
  - Extracts text and structure (e.g. markdown).
  - Identifies **concepts** (subject, topic, subtopic, difficulty, keywords, sample questions).
  - Builds a **knowledge graph** (concepts and relationships) for better tests and study guides.
- **Document list & status:** Users see documents per child, with processing status (e.g. processing, completed, failed).
- **Reprocess:** Failed or updated documents can be reprocessed.

**Business value:** Learning content is automatically structured so the platform can generate tests and study guides without manual tagging.

### 4.4 Tests & Quizzes

- **Generate tests:** Tests are generated from document concepts (by subject/topic), so they align with what the child is studying.
- **Take tests:** Child (or parent viewing as child) starts a test, answers questions (multiple choice, fill-in-blank, matching, etc.), and submits.
- **Scoring & evaluation:** Answers are evaluated (deterministic, heuristic, and/or LLM-based). The system produces scores and an **evaluation report**.
- **Admin actions:** Admins can reopen or reevaluate tests (e.g. after fixing evaluation logic).

**Business value:** Automated, curriculum-aligned assessment with clear results for parents and children.

### 4.5 Evaluation Reports

- **Per-child reports:** Summary of test performance over a time window (e.g. last 30 days).
- **Strengths and gaps:** Highlights what the child knows well and where they need more practice.
- **Link to study:** Reports connect to **study guides** and **revision cards** so the next step is clear.

**Business value:** Parents and children see progress at a glance and know where to focus.

### 4.6 Study Guides & Revision

- **Study guides:** Generated from concepts (e.g. per document or topic). Guide content can be regenerated if needed.
- **Revision cards:** Bite-sized revision content (e.g. flashcards) to reinforce concepts.
- **AI coach chat:** Child (or parent) can chat with an AI coach in context of a study guide or topic for extra explanation and practice.

**Business value:** Learning doesn’t stop at the test; the platform suggests what to study and how (guides, cards, coach).

### 4.7 Learning Workspace

- **Unified view:** Combines evaluation report, study guides/revision cards, and AI coach in one workspace.
- **Flow:** View report → See suggested guides/cards → Open a guide or chat with the coach.

**Business value:** One place to “see how I did” and “what to do next,” improving engagement and follow-through.

### 4.8 Admin-Only Capabilities

- **Parent management:** Create parents, list them, deactivate accounts.
- **Cross-child view:** List all children and documents across the platform.
- **Document reprocess:** Trigger reprocessing for any document.
- **Knowledge graph view:** Inspect the concept graph for a document (useful for support or content quality).
- **LLM logs & usage:** View logs and usage stats for AI/LLM calls (cost and usage oversight).
- **Test operations:** Reopen or reevaluate tests.

**Business value:** Operational control, support, and visibility into platform usage and content quality.

### 4.9 Optional / Supporting

- **TikZ rendering:** If the product uses math/diagrams (e.g. LaTeX TikZ), the system can render them for display in the UI (e.g. in questions or guides).
- **MFA (optional):** Multi-factor authentication can be part of parent/admin login flow where configured.

---

## 5. User Journeys (Simplified)

**Parent:**  
Register → Create child → Upload PDF(s) → Wait for processing → Open dashboard → See documents/tests/reports → Optionally use Learning Workspace with child.

**Child:**  
Log in with PIN → See own dashboard → Open “Tests” and take a test → View report → Open Learning Workspace → Use study guides and AI coach.

**Admin:**  
Log in → Use Admin Settings → Manage parents and/or inspect children, documents, knowledge graphs, LLM logs → Reopen/reevaluate tests or reprocess documents as needed.

---

## 6. Summary Table (Business View)

| Area | Main capability | Primary users |
|------|-----------------|---------------|
| Access | Register, login (parent/child/admin), session management | All |
| Children | Create, edit, list children; view profiles | Parent, Admin |
| Documents | Upload PDFs, assign to child, view status, reprocess | Parent, Admin |
| Content intelligence | Auto concept extraction, knowledge graph | System (visible in admin/document views) |
| Tests | Generate from concepts, take test, score, evaluate | Child, Parent, Admin |
| Reports | Evaluation report per child, strengths/gaps | Parent, Child, Admin |
| Study & practice | Study guides, revision cards, AI coach | Child, Parent |
| Learning workspace | Report + guides + cards + coach in one place | Child, Parent |
| Admin | Parents, children, documents, KG, LLM logs, test actions | Admin |

---

## 7. What “Architecture” Means Here (Plain Language)

- **Frontend:** The website users open in their browser (dashboard, documents, tests, reports, learning workspace).
- **Backend:** The service that stores users, documents, and results; runs document processing and AI; and generates tests, reports, and study guides.
- **Database:** Where parents, children, documents, concepts, tests, and responses are stored.
- **AI/LLM:** Used for parsing PDFs, extracting concepts, building the knowledge graph, generating and evaluating questions, and powering the AI coach.

For business users, the important “architecture” is: **one app, one place per child for content and progress, with clear roles (parent / child / admin) and a closed loop from upload → concepts → tests → reports → study and coach.**

---

*Last updated: February 2025. For technical architecture and implementation details, see `ARCHITECTURE_AND_FEATURES_TECHNICAL.md`.*
