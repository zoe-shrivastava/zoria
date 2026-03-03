# Science & Engineering Fair: Document Ingestion Pipeline Test Plan

**Scope:** Test every step of the document ingestion pipeline using **5 documents across 2 subjects**, with **3 runs per document** (15 runs total per document for full pipeline coverage, or 3 full pipeline runs per document depending on how you structure the experiment).

**Pipeline reference:** `DETAILED_FLOWS.md` §1, `backend/workers/document_processor.py`, `backend/workflows/workflow.py`, `backend/services/document_service.py`.

---

## Test Setup (5 docs × 2 subjects × 3 runs)

- **Documents:** 5 PDFs total (e.g. 2–3 from Subject A, 2–3 from Subject B) so you can measure subject-specific behavior and cross-subject consistency.
- **Runs:** 3 ingestions per document (same file uploaded/processed 3 times, or 3 reprocesses with `cleanup_existing: true`) to assess **repeatability** and **variance** (LLM non-determinism, deduplication, chunk boundaries).
- **Pre-labeling:** Done once per document (or once per “document type” if you reuse the same PDF across runs). Verification and metrics are recorded per run.

---

## Pipeline Steps: Pre-Labeling, Verification, and What the Test Accomplishes

---

### Step 0: Upload (Synchronous)

**What happens:** File saved to disk, document row created, attached to children, status `uploaded`, Phase 1 enqueued.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) Expected **subject** (e.g. Mathematics, Physics). (b) **Child IDs** (or single child) the document should be attached to. (c) **File metadata:** original filename, file size in bytes, page count (optional; for later comparison with markdown completeness). (d) **MAX_UPLOAD_SIZE_MB** boundary: one PDF at or just under limit, one over limit (for rejection test). |
| **2. Verify** | (a) HTTP 201, response has `document_id`, `filename`, `status: "uploaded"`. (b) File exists on disk at `UPLOAD_DIR` with UUID-style filename. (c) DB: one row in `documents` with that `document_id`, correct `file_path`, `file_size`, `mime_type`, `child_id` (first child), `parent_id`. (d) Rows in `document_children` for each `child_id` in `child_ids`. (e) Rejected upload (e.g. oversized or non-PDF) returns 4xx and no document row created. |
| **3. What this test accomplishes** | Confirms **ingestion entry point**: file persistence, DB record creation, child association, and that Phase 1 is enqueued (no need to run Phase 1 in this step). Establishes baseline for “same document, multiple runs” (same file_path/content, different document_id per upload if you upload 3 times). |

---

### Step 1: Phase 1 — Document Parser (PDF → Markdown)

**What happens:** PDF read from disk, sent to Document Parser agent (OpenAI); output is full-document **markdown** stored in `documents.markdown_content`.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Expected structural elements:** list of section titles, presence of “Questions” or “Problems” sections, count of numbered problems (e.g. “Problems 1–20”), presence of figures/tables (you can note “Figure 1”, “Table 2”). (b) **Expected text anchors:** 5–10 short unique phrases (1–2 sentences) that must appear in the markdown (e.g. key definitions, problem statements). (c) **Page count** (optional): to compare “pages mentioned” vs markdown length. |
| **2. Verify** | (a) After Phase 1: `documents.status` = `parsed`, `markdown_content` is non-null and length > threshold (e.g. > 500 chars). (b) **Completeness:** All pre-labeled section titles (or normalized forms) appear in markdown. (c) **Anchors:** Each pre-labeled phrase appears in markdown (substring or normalized). (d) **No truncation:** Markdown length is plausible (e.g. not capped at an obvious token limit; compare across 3 runs). (e) **Across 3 runs:** Variance in length and presence of edge content (e.g. last problem); note if any run drops sections. |
| **3. What this test accomplishes** | Measures **parser reliability and completeness**: whether the LLM consistently extracts the full document into markdown and whether results are stable across runs. Critical for downstream concept extraction (garbage markdown → bad concepts). |

---

### Step 2: Phase 1 — Concept Extractor (Markdown → Concepts)

**What happens:** Markdown is sent to Concept Extractor agent; structured output (`ConceptExtratorSchema`) with **concepts** (subject_name, topic_name, subtopic, difficulty, prerequisites, questions, associated_visuals, keywords). Subject is derived from most common `subject_name`; stored in `documents.concepts` (JSONB) and `documents.subject`.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Expected subject** (e.g. Physics, Mathematics) — must match `subject_profiles` / `subject_topics` if you use taxonomy. (b) **Minimum concept count:** e.g. “at least 3 concepts.” (c) **Expected concept names (or topics):** 3–7 concept/subtopic names that should appear (e.g. “Speed & Velocity”, “Newton’s Laws”). (d) **Expected prerequisite pairs:** e.g. “Concept A is prerequisite of Concept B” (optional; only if document clearly states order). (e) **Taxonomy constraint:** If using subject-specific taxonomy, list allowed `topic_name`/`subtopic` values from `subject_topics.json` for that subject. |
| **2. Verify** | (a) `documents.concepts` is valid JSON with key `concepts` (array). (b) **Count:** `len(concepts) >= 1` (and >= your minimum). (c) **Schema:** Each concept has `subject_name`, `topic_name`, `subtopic`, `difficulty`, `prerequisites`, `questions`, `associated_visuals`, `keywords` (lists/strings as per schema). (d) **Subject:** `documents.subject` equals normalized subject (e.g. `mathematics`, `physics`) and matches pre-labeled expected subject. (e) **Coverage:** Pre-labeled concept/topic names appear in at least one concept’s `topic_name` or `subtopic`. (f) **Prerequisites:** Pre-labeled prerequisite pairs appear in `prerequisites` (concept name strings). (g) **Taxonomy:** No invented topics; only allowed `subject_name`/`topic_name`/`subtopic` from taxonomy. (h) **Across 3 runs:** Concept count variance; same concepts detected or not; subject stability. |
| **3. What this test accomplishes** | Validates **concept extraction quality and schema compliance**: correct subject, taxonomy adherence, prerequisite capture, and repeatability. This step feeds the knowledge graph and questions; errors here propagate. |

---

### Step 3: Phase 2 — Knowledge Graph (Concepts → Concepts + Relationships)

**What happens:** `KnowledgeGraphService.process_concepts(document_id, normalized_concepts_list, subject)` creates/merges concept rows, links them to the document, and creates **concept_relationships** (e.g. `prerequisite_of`, `requires`).

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Expected concept count** (from Step 2; same number or after deduplication). (b) **Expected relationship count:** e.g. “at least N prerequisite edges” from pre-labeled prerequisite pairs. (c) **Concept names** that must appear as `concepts.name` (or equivalent) in DB. |
| **2. Verify** | (a) One row per extracted concept in `document_concepts` (or equivalent link table) for this `document_id`; concept rows exist in `concepts` with correct `name`, `subtopic`, `difficulty`, `subject` in metadata. (b) **Relationships:** Rows in `concept_relationships` for this document’s concepts with types `prerequisite_of` / `requires`; count >= pre-labeled minimum. (c) **Deduplication:** Re-run with same document (or second document with overlapping concept name): same concept_id reused where expected (no duplicate concept rows for same logical concept). (d) **Across 3 runs:** Same document processed 3 times (with cleanup): concept_ids may differ (new rows each time) but relationship structure (who points to whom) should be consistent. |
| **3. What this test accomplishes** | Ensures **knowledge graph construction and prerequisite ordering** are correct and stable; supports “include prerequisites” in test generation and downstream reporting. |

---

### Step 4: Phase 2 — Questions and Visuals

**What happens:** For each concept, questions from `concept_data["questions"]` are inserted into `questions` (with concept_id, text, type, difficulty, metadata); visuals from `associated_visuals` into `visuals`; optional skill linking.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Expected question count:** minimum number of questions (e.g. sum over concepts from Step 2). (b) **Question type distribution:** e.g. “at least one multiple_choice, one short_answer.” (c) **Sample question text:** 2–3 exact or near-exact strings that should appear in `questions.text`. (d) **Visual count (optional):** expected number of visuals if document has figures/diagrams. |
| **2. Verify** | (a) Total `questions` rows for this document (via concept_id → document) >= expected minimum. (b) Each question has `concept_id`, `text` non-empty, `question_type` in allowed set, `difficulty` normalized (easy/medium/hard). (c) Pre-labeled sample question texts appear in `questions.text`. (d) Question types present as expected. (e) **Visuals:** Count of `visuals` rows for document’s concepts matches or is close to expected; no crash on malformed `associated_visuals`. (f) **Across 3 runs:** Question count variance; same questions created (by text) or not. |
| **3. What this test accomplishes** | Confirms **assessment material creation**: questions and visuals are correctly derived from concepts and linked to concepts/documents for tests and study guides. |

---

### Step 5: Phase 2 — Chunking

**What happens:** `ChunkingService.chunk_document(document_id, markdown, concepts_json, subject)` produces a list of **chunks** with metadata (concept_name, subtopic, difficulty, chunk_type, etc.); chunks may be linked to concept_id and question_id.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Expected chunk count range:** e.g. based on markdown length and target token size (e.g. 400 tokens); approximate min chunks = ceil(markdown_tokens / 800). (b) **Expected chunk types:** e.g. “concept overview”, “section”, “question” (from ChunkingService logic). (c) **Key phrases:** A few phrases that must appear in at least one chunk (to ensure content is not lost in boundaries). |
| **2. Verify** | (a) Chunk list length within expected range (not 0, not absurdly large). (b) Each chunk has `chunk_text`, `metadata` with at least `concept_name` or `subtopic`, `chunk_type` where applicable. (c) **Coverage:** Pre-labeled key phrases appear in at least one `chunk_text`. (d) **Token bounds:** Chunk sizes (if you have tokenizer) within service limits (e.g. min/max tokens). (e) **Concept linkage:** Chunks that should map to a concept have correct `metadata.concept_name` (and after DB write, `concept_id` where applicable). (f) **Across 3 runs:** Chunk count and boundaries may vary slightly if markdown or concept list varies; document same → similar chunk count. |
| **3. What this test accomplishes** | Validates **chunking correctness and coverage**: content is split into usable pieces for retrieval and embedding without dropping important text or misattributing to concepts. |

---

### Step 6: Phase 2 — Embeddings

**What happens:** `EmbeddingService.embed_chunks(chunks, batch_size=10)` calls OpenAI (or local) embeddings API; each chunk gets an **embedding** vector.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) **Embedding model** and **dimension** (e.g. 1024 or 1536) from config. (b) **Expected vector count** = number of chunks from Step 5. |
| **2. Verify** | (a) Every chunk has non-null `embedding`; length of vector = expected dimension. (b) No duplicate vectors for clearly different chunk texts (sample a few pairs). (c) **Semantic sanity:** Two chunks with very similar text have higher cosine similarity than two unrelated chunks (spot-check). (d) **Across 3 runs:** Same chunk text → same embedding (deterministic); different runs may have different chunk boundaries so different vectors. |
| **3. What this test accomplishes** | Ensures **embedding generation** is correct and consistent; required for vector search (e.g. semantic deduplication of questions, future retrieval). |

---

### Step 7: Phase 2 — Store Chunks and Final Status

**What happens:** Chunks (with embeddings) are written to **content_chunks** (or equivalent table with vector column); document status set to **ready**.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | **Per document:** (a) Same as Step 5 for chunk count; (b) document_id for this run. |
| **2. Verify** | (a) Row count in `content_chunks` for this document = number of chunks produced. (b) Each row has `document_id`, `chunk_text`, `embedding` (vector type), and metadata fields (concept_id, question_id if applicable). (c) **pgvector:** Query by document_id returns all chunks; optional: run a simple similarity search (e.g. embed one chunk text, retrieve top-k) and confirm same document’s chunks are retrievable. (d) `documents.status` = `ready`, `processing_completed_at` set. (e) **Across 3 runs:** With cleanup, each run replaces chunks; final status is always `ready` for successful runs. |
| **3. What this test accomplishes** | Confirms **persistence and indexing**: chunks and vectors are stored correctly and document is marked ready for the rest of the platform (tests, study guides, search). |

---

### Step 8: End-to-End (Optional but Recommended)

**What happens:** Full pipeline from upload to ready for the same 5 documents × 3 runs.

| Aspect | Details |
|--------|--------|
| **1. Pre-labeling** | Aggregate of all pre-labels above per document. |
| **2. Verify** | (a) For each run: status reaches `ready`; no intermediate `failed`. (b) **Metrics per run:** document_id, subject, concept_count, question_count, chunk_count, total time (or per-phase time if logged). (c) **Variance table:** For each document, across 3 runs: min/max/mean concept count, question count, chunk count; subject consistency (all 3 runs same subject?). (d) **Failure mode:** Intentionally fail one step (e.g. invalid PDF, or mock LLM error) and confirm status = `failed` and `failure_stage` / `error_message` set. |
| **3. What this test accomplishes** | Demonstrates **pipeline reliability and repeatability** for the fair: same inputs lead to consistent outcomes (with acceptable LLM variance), and failure handling is correct. |

---

## Summary Table (Quick Reference)

| Step | Pre-labeling | Verify | Accomplishes |
|------|--------------|--------|--------------|
| **0. Upload** | Subject, child_ids, file metadata, size limit | 201, file on disk, DB row, document_children | Entry point and persistence |
| **1. Parser** | Sections, anchors, page count | status=parsed, markdown complete, anchors present | Parser completeness and stability |
| **2. Concept extractor** | Subject, min concepts, concept names, prerequisites, taxonomy | concepts schema, subject, coverage, taxonomy, repeatability | Extraction quality and schema |
| **3. Knowledge graph** | Concept count, relationship count | document_concepts, concept_relationships, dedup | KG and prerequisite graph |
| **4. Questions & visuals** | Min questions, types, sample texts | question/visual counts, types, sample text present | Assessment material creation |
| **5. Chunking** | Chunk count range, chunk types, key phrases | Count, metadata, coverage, token bounds | Chunk coverage and boundaries |
| **6. Embeddings** | Model, dimension, vector count | Non-null vectors, dimension, semantic sanity | Embedding correctness |
| **7. Store + status** | Chunk count, document_id | content_chunks rows, status=ready | Persistence and readiness |
| **8. E2E** | Full pre-labels | ready, metrics, variance, failure handling | Pipeline reliability and repeatability |

---

## Suggested Data Collection (5 docs × 2 subjects × 3 runs)

- **Pre-labeled assets:** One spreadsheet or JSON per document with: expected subject, section list, text anchors, expected concept names, prerequisite pairs, min concept/question/chunk counts, sample question texts, key phrases for chunks.
- **Per run:** document_id, run index (1–3), status at each phase, final subject, concept_count, question_count, chunk_count, markdown_length, and any failure_stage/error_message.
- **Analysis:** By document: mean and variance of concept/question/chunk counts; subject consistency. By subject: compare the 2 subjects on concept count, question count, or taxonomy adherence if you use subject-specific taxonomy.

This structure gives you a clear, defensible test plan for the science and engineering fair without requiring any code changes.
