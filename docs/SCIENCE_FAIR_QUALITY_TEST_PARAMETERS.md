# Science Fair: Detailed Quality Test Parameters

This document defines **detailed parameters** to test three quality dimensions of the document ingestion pipeline:

1. **Markdown conversion quality** (including handwritten text and visual descriptions)
2. **Concept JSON extraction quality**
3. **Knowledge graph quality**

Use these parameters to design ground truth, scoring rubrics, and pass/fail or metric-based checks. No code changes are required; this is a testing specification only.

---

## Where to collect ground truth

Use this as the single reference for **where** to get your expected values for each step.


| Step                           | What you're testing               | Collect ground truth from                                          | What to capture                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| ------------------------------ | --------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **1. Markdown conversion**     | PDF → Markdown                    | **The PDF (source document)**                                      | From the PDF: section titles, exact phrases (5–15), visual count, question/part count, formulas, student-answer blocks. Compare system markdown to this list.                                                                                                                                                                                                                                                                                           |
| **2. Concept JSON extraction** | Markdown → Concept JSON           | **The Markdown**                                                   | From the markdown: expected concept count and names, expected question count (one per item/part/row/term), expected type per question, taxonomy (subject/topic/subtopic), which questions should have instruction prefix (inheritance formula), which question–visual links. You can use one “golden” markdown per document (e.g. from a trusted run) and annotate it once.                                                                             |
| **3. Knowledge graph**         | Concept JSON → KG (nodes + edges) | **Option A: Concept JSON** (recommended) or **Option B: Markdown** | **A.** Use the **Concept JSON** for that document (same run or golden run) as ground truth: expected nodes = concepts with name/subtopic/difficulty; expected edges = every prerequisite name in the JSON that resolves to another concept in the same JSON. **B.** Use **Markdown** only: annotate from the markdown the expected concept names and prerequisite pairs (A, B) where the text implies “B requires A”; then compare the KG to that list. |


**Practical choice:** If you want **one source of truth**, use **Markdown** for both Concept JSON and KG: create one annotated markdown per document (expected concepts, questions, types, visuals, prerequisites). For Markdown conversion itself, ground truth is the **PDF** (or a short checklist taken from the PDF). So you only need: **(1) the PDF** for step 1, and **(2) the Markdown + your annotations** for steps 2 and 3.

---

## 1. Markdown Conversion Quality

**Source:** Document Parser agent (`workflows/prompts.py` — DOCUMENT_PARSER_PROMPT). Input: PDF (or image). Output: structured Markdown (sections, questions, parts, student answers, visuals).

### 1.1 Parameters for Handwritten Text


| Parameter                                | Description                                                                                                                                       | How to measure / test                                                                                                                                                                                                                                                                                                                                         |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **OCR / handwritten legibility**         | Whether handwritten or low-quality print is transcribed into readable text in the markdown.                                                       | **Pre-label:** For each document, list 5–15 **exact or near-exact phrases** that appear in the original (handwritten or printed). **Verify:** Search markdown for each phrase (exact substring or normalized: strip punctuation, collapse spaces). **Metric:** % of pre-labeled phrases found (e.g. 12/15 = 80%).                                             |
| **Fragment merging**                     | Prompt says "Merge OCR fragments into logical units." Fragments (e.g. "veloc ity" or line-by-line noise) should appear as single words/sentences. | **Pre-label:** Note regions in the PDF that are handwritten or likely to produce fragments. **Verify:** In markdown, check that (a) no obvious mid-word splits remain (regex: `\w\s+\w` with very short tokens), (b) sentences in those regions are coherent (manual or sample check). **Metric:** Count of "fragmentation" defects per page or per document. |
| **Character-level accuracy (optional)**  | For a small set of handwritten lines, character error rate (CER) or word error rate (WER).                                                        | **Pre-label:** Transcribe 10–20 handwritten lines by hand as ground truth. **Verify:** Extract corresponding lines from markdown (by section/question ID); compute CER/WER vs ground truth. **Metric:** CER, WER, or % of lines with 0 errors.                                                                                                                |
| **Preservation of symbols and formulas** | Handwritten math (e.g. `a = -9.8 m/s^2`, `Δx`) should appear correctly.                                                                           | **Pre-label:** List 5–10 mathematical expressions or symbols that appear in the source. **Verify:** Each appears in markdown (exact or Unicode-equivalent). **Metric:** % of expressions preserved.                                                                                                                                                           |
| **Student-answer preservation**          | Handwritten "Student Answer" blocks must be captured.                                                                                             | **Pre-label:** Count of distinct "Student Answer" or answer blocks in the source. **Verify:** Markdown contains the same number of answer blocks; sample 3–5 and compare text to source. **Metric:** Count match + sample accuracy %.                                                                                                                         |


### 1.2 Parameters for Visual Descriptions


| Parameter                      | Description                                                                                                                   | How to measure / test                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ------------------------------ | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Visual coverage**            | Every figure, graph, or diagram in the PDF should have a corresponding "Associated Visual" (or equivalent) block in markdown. | **Pre-label:** Count of distinct visuals in the document (by eye or by counting "Figure N", "Graph", "Diagram"). **Verify:** Count of `Visual ID` or "Associated Visual" / "Type: graph                                                                                                                                                                                                                                                                                      |
| **Visual ID and association**  | Each visual should have an ID and be linked to a question/part when applicable.                                               | **Pre-label:** List (Visual description, Associated question ID) for each visual. **Verify:** For each, markdown has (a) a Visual ID, (b) "Associated Question" or "Associated Question/Part" matching the question. **Metric:** % of visuals with correct association.                                                                                                                                                                                                      |
| **Type classification**        | Visual type (graph, diagram, chart) should be present and correct.                                                            | **Pre-label:** For each visual, expected type. **Verify:** `Type:` in markdown matches. **Metric:** % correct type.                                                                                                                                                                                                                                                                                                                                                          |
| **Description quality**        | Prompt asks for Description, Axes (labels, units, min/max, step), Data Points, Key Features.                                  | **Pre-label:** For 3–5 key visuals, write a short expected description (e.g. "Position vs time; time (s) on x; position (m) on y; piecewise"). **Verify:** (a) Description field is non-empty and mentions the right quantities. (b) Axes: labels and units present when applicable. (c) Data Points / Key Features: non-empty when the source has data or key features. **Metric:** Rubric score (0–3) per visual: 0=missing, 1=partial, 2=good, 3=excellent; then average. |
| **Diagram relationships**      | Prompt: "Capture relationships in diagrams (arrows, vectors, labels)."                                                        | **Pre-label:** For 1–2 diagrams, list relationships (e.g. "Arrow from A to B labeled 'force'"). **Verify:** Markdown description or key features mention these relationships (keywords or paraphrase). **Metric:** % of pre-labeled relationships mentioned.                                                                                                                                                                                                                 |
| **Formula-derived graph data** | For graphs, prompt says to compute key points from the formula, not only visual inspection.                                   | **Pre-label:** For one graph with a known formula (e.g. given in the doc), expected vertex/intercept/slope. **Verify:** "Data Points / Key Features" or description reflect correct sign/direction (e.g. "slope positive", "vertex at (2, -1)"). **Metric:** Pass/fail or 0–2 score for correctness.                                                                                                                                                                         |


### 1.3 Parameters for General Markdown Quality


| Parameter                    | Description                                                                   | How to measure / test                                                                                                                                                                                                                    |
| ---------------------------- | ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Section hierarchy**        | Markdown should use clear hierarchy: section → question → parts → visuals.    | **Verify:** Headings or structure (e.g. `Question N`, `Part N(a)`, `Associated Visual`) follow a consistent pattern; no "orphan" parts without parent question. **Metric:** Count of structural violations (e.g. part without question). |
| **Completeness (sections)**  | All sections in the source should appear.                                     | **Pre-label:** List section titles or headers. **Verify:** Each appears in markdown (exact or normalized). **Metric:** % of sections present.                                                                                            |
| **Completeness (questions)** | Every numbered question/part (e.g. 1–133 or Q1–Q10 with parts) should appear. | **Pre-label:** Total count of distinct questions/parts from the source. **Verify:** Count of "Question"/"Part" blocks in markdown ≥ pre-labeled count. **Metric:** Ratio (markdown count / expected count); target ≥ 1.0.                |
| **No truncation**            | Output should not be cut off mid-document.                                    | **Verify:** Last section/question in markdown matches the last section/question in the document; markdown length is plausible (e.g. not capped at a fixed character count). **Metric:** Pass/fail.                                       |
| **Mathematical formulas**    | "Identify mathematical formulas" — formulas should be present and readable.   | **Pre-label:** 3–5 formulas or equations from the source. **Verify:** Each appears in markdown in recognizable form. **Metric:** % present.                                                                                              |


### 1.4 Suggested Scoring Summary (Markdown)

- **Handwritten:** Weight OCR phrase match (e.g. 40%) + fragment merge defects (20%) + student-answer count match (20%) + formula/symbol preservation (20%). Optionally add CER/WER for a subset.
- **Visuals:** Weight visual coverage (30%) + association (20%) + description quality rubric (30%) + axes/data (20%).
- **Overall markdown:** Combine section completeness, question count ratio, no truncation, and structure into a single completeness score (e.g. 0–100).

---

## 2. Concept JSON Extraction Quality

**Source:** Concept Extractor agent (`workflows/workflows.py` — ConceptExtratorSchema, `workflows/prompts.py` — CONCEPT_EXTRACTOR_PROMPT). Input: Markdown. Output: JSON with `concepts[]`; each concept has `subject_name`, `topic_name`, `subtopic`, `difficulty`, `prerequisites`, `questions[]`, `associated_visuals[]`, `keywords[]`; each question has `text`, `type`, `associated_visuals[]`.

### 2.1 Parameters for Schema and Completeness


| Parameter                      | Description                                                                                                                                                | How to measure / test                                                                                                                                                                                                                                                                                                             |
| ------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Valid JSON**                 | Output parses as JSON and conforms to ConceptExtratorSchema.                                                                                               | **Verify:** Parse JSON; root has `concepts` (array); each concept has required fields: `subject_name`, `topic_name`, `subtopic`, `difficulty`, `prerequisites`, `questions`, `associated_visuals`, `keywords`; each question has `text`, `type`, `associated_visuals`. **Metric:** Pass/fail; list any missing or invalid fields. |
| **Concept count**              | Number of concepts should be plausible (one per section or distinct subtopic).                                                                             | **Pre-label:** Minimum expected concept count (e.g. from section count or manual review). **Verify:** `len(concepts) >= min_expected` and not absurdly high (e.g. one concept per sentence). **Metric:** Pass/fail or band (under / ok / over).                                                                                   |
| **Question count vs markdown** | "Every question/part must appear exactly once" — total question objects across all concepts should match (or exceed) distinct questions/parts in markdown. | **Pre-label:** Count of distinct questions/parts in the markdown (from Step 1). **Verify:** `sum(len(c["questions"]) for c in concepts) >= pre_labeled_count`. **Metric:** Ratio (extracted / expected); target ≥ 1.0.                                                                                                            |
| **No single-concept dump**     | "Do NOT put all questions from the entire document into a single concept."                                                                                 | **Verify:** No concept has more than N questions (e.g. N = 50% of total questions) when there are multiple sections. **Metric:** Pass/fail (max questions per concept < threshold).                                                                                                                                               |


### 2.2 Parameters for Content Fidelity


| Parameter                         | Description                                                                                                                                 | How to measure / test                                                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **No placeholder text**           | Forbidden: generic "Part q1a" or "Question 2" as sole content of `text`. Must be actual content.                                            | **Pre-label:** N/A. **Verify:** Sample 10–20 question `text` values; none should be only "Question N" or "Part qNa"; each should contain substantive content (e.g. vocabulary term, question body). **Metric:** % of sampled questions with non-placeholder text.                                                                                                                                                                     |
| **Text formula**                  | "`[Section Header/Instruction] + [Specific Item Name/Question Body]`" — e.g. "Match vocabulary to definitions: Velocity".                   | **Verify:** For matching/fill-in sections, at least some questions have both context and specific item (e.g. "Match ... : TermName"). **Metric:** % of matching/fill-in questions following the formula (sample-based).                                                                                                                                                                                                               |
| **Answer preservation**           | If markdown has student answers/definitions, they should appear in question `answer` (when schema supports it) or in concept/question text. | **Note:** Current ConceptExtratorSchema in code has only `text`, `type`, `associated_visuals` per question; answer may be in metadata elsewhere. **Pre-label:** 5–10 (question, expected answer) pairs from markdown. **Verify:** For each, locate the corresponding question in JSON and check if answer appears in `answer` field or in question text. **Metric:** % of pairs with answer present (if your pipeline stores answer). |
| **Row-level / atomic extraction** | Tables: one question object per row. Matching: one per term or term-definition pair.                                                        | **Pre-label:** Count of table rows and matching items in markdown. **Verify:** Concept JSON has at least that many questions of type `fill_in_the_blank`/`matching` (or appropriate type). **Metric:** Count match or ratio.                                                                                                                                                                                                          |


### 2.3 Parameters for Type and Taxonomy


| Parameter                         | Description                                                                                                                       | How to measure / test                                                                                                                                                                                                                                        |
| --------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Question type validity**        | Only allowed types: `multiple_choice`, `short_answer`, `problem_solving`, `conceptual_question`, `matching`, `fill_in_the_blank`. | **Verify:** Every question has `type` in this set. **Metric:** Pass/fail; list invalid types if any.                                                                                                                                                         |
| **Question type appropriateness** | Type should match content (e.g. "Match X to Y" → `matching`; "Draw/Plot" → `problem_solving`).                                    | **Pre-label:** 10–15 questions with expected type from markdown. **Verify:** Extracted type matches expected. **Metric:** % agreement.                                                                                                                       |
| **Taxonomy compliance**           | "You may only use subject_name, topic_name, and subtopic from the provided subject_topics.json."                                  | **Pre-label:** Set of allowed (subject_name, topic_name, subtopic) from the taxonomy used for the run. **Verify:** Every concept has (subject_name, topic_name, subtopic) in the allowed set. **Metric:** % of concepts compliant; list any invented values. |
| **Subject consistency**           | All concepts should share the same subject for a single-subject document.                                                         | **Verify:** All `subject_name` values are the same (or document-level subject matches). **Metric:** Pass/fail.                                                                                                                                               |
| **Difficulty**                    | Each concept has difficulty in `easy                                                                                              | medium                                                                                                                                                                                                                                                       |


### 2.4 Parameters for Visual and Prerequisite Linkage


| Parameter                     | Description                                                                                               | How to measure / test                                                                                                                                                                                                                  |
| ----------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **associated_visuals**        | Questions/concepts that reference a Visual ID in markdown should have that ID in `associated_visuals`.    | **Pre-label:** List (question or concept, expected Visual IDs) from markdown. **Verify:** Corresponding question or concept has those IDs in `associated_visuals`. **Metric:** % of (question/concept, visual) pairs correctly linked. |
| **Prerequisites present**     | When the document implies order (e.g. "requires understanding of X"), concepts should list prerequisites. | **Pre-label:** Expected prerequisite pairs (concept A prerequisite of concept B). **Verify:** For each, concept B has concept A's name (or subtopic) in `prerequisites` array. **Metric:** % of expected prerequisite pairs present.   |
| **Prerequisites in-document** | Prerequisite names should be concept names from the same document (KG only links within document).        | **Verify:** Every string in any `prerequisites` list appears as another concept's `subtopic` or `topic_name` (or name) in the same JSON. **Metric:** % of prerequisite names that resolve to a concept in the output.                  |


### 2.5 Suggested Scoring Summary (Concept JSON)

- **Completeness:** Question count ratio (≥1.0) + concept count in range + no single-concept dump.
- **Fidelity:** Non-placeholder text % + type appropriateness % + row-level count match.
- **Taxonomy:** % compliant (subject/topic/subtopic) + subject consistency + difficulty valid.
- **Linkage:** associated_visuals % + prerequisite presence % + prerequisite resolution %.

You can report one overall score (e.g. average of four dimensions) or keep dimensions separate for the fair.

### 2.6 Attribute descriptions (Markdown → Concept JSON)

Brief description of each attribute used in the data capture table:


| Attribute               | Description                                                                                                                                                                                                                                                                                                                                                                                                      |
| ----------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Concept Nodes**       | Number of distinct concepts (topics/subtopics) the extractor should identify from the document. Each concept groups a set of questions under one `subject_name`, `topic_name`, and `subtopic`. Ground truth = expected count from the document’s sections or distinct topics; actual = number of concept objects in the output JSON.                                                                             |
| **Atomic Questions**    | Number of question objects that should appear in the JSON. The extractor must produce **one object per question, per part, per table row, and per matching term** (no grouping). Ground truth = count of all such items in the markdown; actual = total `questions[]` count across all concepts. Errors here are often “grouped extraction” (e.g. one object for “Match the following” instead of one per term). |
| **Type Mapping**        | Whether each question’s `type` matches the intended type from the markdown. Allowed types: `multiple_choice`, `short_answer`, `problem_solving`, `conceptual_question`, `matching`, `fill_in_the_blank`. Ground truth = number of questions to classify; actual = number correctly classified (e.g. “Graph the data” → `problem_solving`, not `short_answer`).                                                   |
| **Taxonomy Compliance** | Whether every concept uses only `subject_name`, `topic_name`, and `subtopic` values from the reference taxonomy (`subject_topics.json`). No invented topics or subtopics. Ground truth = number of concepts to check (often 1 per concept); actual = number that use only allowed values.                                                                                                                        |
| **Inheritance Formula** | Whether each question’s `text` follows the required pattern: `**[Section/Instruction] + [Specific Item or Question Body]**` (e.g. “Match the following: Velocity” instead of just “Velocity”). Ground truth = number of questions that should include the instruction/context; actual = number whose `text` includes it.                                                                                         |
| **Linkage (Visuals)**   | Number of correct question–visual (or concept–visual) links. When the markdown associates a question with a Visual ID (e.g. “Associated Visual: V1”), the output should list that ID in the question’s (or concept’s) `associated_visuals` array. Ground truth = number of such associations in the markdown; actual = number correctly present in the JSON.                                                     |


### 2.7 Example data capture (Markdown → Concept JSON)

When recording per-run results, you can use a table like the one below. **Total** can be defined in two ways; pick one and state it clearly:

- **Aggregate (total correct / total expected):** Sum "Ground Truth" and "System Output" across parameters; Difference = Actual − Expected; Accuracy = Actual / Expected (e.g. 16/25 = 64%). This weights each *expected item* equally.
- **Mean of parameter accuracies:** Average the Accuracy (%) column (e.g. (100 + 57.14 + 71.42 + 100 + 57.14 + 50) / 6 ≈ 72.6%). This weights each *dimension* equally.


| Parameter           | Ground Truth (Expected) | System Output (Actual) | Difference | Accuracy (%) | Notes (Error Type)                                                   |
| ------------------- | ----------------------- | ---------------------- | ---------- | ------------ | -------------------------------------------------------------------- |
| Concept Nodes       | 1                       | 1                      | 0          | 100%         | Correct: "Speed & Velocity"                                          |
| Atomic Questions    | 7                       | 4                      | -3         | 57.14%       | Grouped Extraction: 5 matching terms put into 2 objects              |
| Type Mapping        | 7                       | 5                      | -2         | 71.42%       | e.g. "Graph the data" marked short_answer instead of problem_solving |
| Taxonomy Compliance | 1                       | 1                      | 0          | 100%         | Used "Motion & Forces" correctly                                     |
| Inheritance Formula | 7                       | 4                      | -3         | 57.14%       | Instructions like "Match the following:" missing from text           |
| Linkage (Visuals)   | 2                       | 1                      | -1         | 50.00%       | e.g. Question 7 did not link to Visual ID: V1                        |
| **Total**           | **25**                  | **16**                 | **-9**     | **64.00%**   | Aggregate: 16/25. (Mean of above % = ~72.6% if reported separately.) |


---

## 3. Knowledge Graph Quality

**Source:** `KnowledgeGraphService` (`services/knowledge_graph_service.py`), `concept_repository`, tables: `concepts`, `document_concepts`, `concept_relationships` (types: `prerequisite_of`, `related_to`, `builds_on`, `requires`).

### 3.0 Ground truth for the Knowledge Graph

The pipeline builds the Knowledge Graph **from the Concept JSON** (Phase 2), not directly from Markdown. So you have two ways to define ground truth for KG testing, especially if **Markdown is your primary source of truth**:


| Approach                                | What to use as ground truth                                                                                         | How to test                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **A. Concept JSON as KG ground truth**  | Use the **Concept JSON** produced for that document (from the same run or a golden/canonical run) as the reference. | **Expected nodes:** One concept per object in `concepts[]` with correct `name`, `subtopic`, `difficulty`. **Expected edges:** For each concept, every name in its `prerequisites` array that matches another concept in the same JSON → one `prerequisite_of` edge (from prereq → concept). Query the DB after Phase 2 and compare: concept count, name/subtopic/difficulty per concept, and edge set.                                                                                                                                                                                                                             |
| **B. Markdown-derived KG ground truth** | Keep **Markdown as the single source of truth**. From the markdown, **annotate once** the expected KG state.        | **From the markdown (by hand or rubric):** (1) List **expected concept names** (e.g. from section headings or topic blocks: "Speed & Velocity", "Motion & Forces"). (2) List **expected prerequisite pairs** (A, B) where the document implies "B requires A" (e.g. "Before studying acceleration, complete velocity"). (3) Optionally expected difficulty/subtopic per concept if the markdown implies it. **Then:** After ingestion, query the KG for that document and check: concept count and names match (or are a subset/superset with clear rules); every expected (A, B) appears as a `prerequisite_of` edge from A to B. |


**Recommendation:** If you already measure Concept JSON quality (with Markdown as ground truth for that step), use **Concept JSON from that same run as ground truth for the KG**. That isolates “KG build” quality: “Given this Concept JSON, did the KG service create the right nodes and edges?” If you prefer a single source (Markdown only), use **approach B**: define expected concept names and prerequisite pairs from the markdown once per document, then compare the actual KG to that checklist.

#### Inputs to Knowledge Graph creation

The KG is built by `KnowledgeGraphService.process_concepts()` in Phase 2. **Inputs** are:


| Input           | Type          | Source                                    | Description                                                                                                                                                                        |
| --------------- | ------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **document_id** | UUID          | Document row                              | The document being processed. Used when creating new concepts (`concepts.document_id`) and when linking concepts to the document (`document_concepts`).                            |
| **concepts**    | List of dicts | Phase 1 output (Concept JSON), normalized | One dict per concept from the Concept Extractor. After normalization (workflow → internal shape), each dict is used to create or reuse a concept and to create prerequisite edges. |
| **subject**     | Optional str  | Document row (`documents.subject`)        | Document-level subject (e.g. `mathematics`, `physics`). Stored in each concept's `metadata.subject` and used for filtering/display.                                                |


**Fields read from each concept dict** (after `_normalize_concept_dict`):


| Field                     | Used for                                                                                                                                                                            |
| ------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **name**                  | Concept node identity; deduplication (name + subtopic); DB `concepts.name`.                                                                                                         |
| **subtopic**              | DB `concepts.subtopic`; deduplication; optional mapping from `topic_name` if `name` is missing.                                                                                     |
| **difficulty**            | Normalized to easy/medium/hard → `concepts.difficulty`.                                                                                                                             |
| **grade**                 | `concepts.grade` (list).                                                                                                                                                            |
| **prerequisites**         | List of concept **names**; each name resolved to `concept_id` within this document → creates `concept_relationships` rows with type `prerequisite_of` (from prereq → this concept). |
| **keywords**              | `concepts.keywords` (list).                                                                                                                                                         |
| **source_markdown**       | `concepts.source_markdown` (optional).                                                                                                                                              |
| **subject** (in metadata) | Set from the **subject** input; stored in `concepts.metadata`.                                                                                                                      |


**Not used for KG nodes/edges:** `questions`, `associated_visuals`, `subject_name`, `topic_name` (only for normalization into `name`/`subtopic`). Questions and visuals are created in a separate Phase 2 step (document processor Step 2), not inside `process_concepts()`.

#### Verification: Is everything needed for the KG present in the Concept JSON?

**Yes, for nodes and edges.** The only KG inputs that are **not** in the Concept Extractor schema are:


| Field               | In Concept JSON? | In DB / KG                                  | Note                                                                                  |
| ------------------- | ---------------- | ------------------------------------------- | ------------------------------------------------------------------------------------- |
| **grade**           | No               | `concepts.grade` (default `[]`)             | Extractor schema has no `grade`; pipeline defaults it to empty list. Optional for KG. |
| **source_markdown** | No               | `concepts.source_markdown` (default `NULL`) | Extractor does not output it; optional for KG.                                        |


All other KG node/edge inputs **are** in the Concept JSON:

- **name** → from `subtopic` or `topic_name` (via normalization).
- **subtopic** → from `topic_name` or `subtopic`.
- **difficulty** → present.
- **prerequisites** → present (list of concept names for edges).
- **keywords** → present.
- **subject** → passed separately from `documents.subject` (and/or from concept `subject_name` in metadata); not required per-concept in JSON for KG.

**Checked against live DB** (document `149cf72d-1700-4656-82f4-6283a8523de1`, filename `ANS_Zhang_8th_New 2.pdf`, subject `physics`):

- **Concept JSON** (from `documents.concepts`): First concept has `subject_name`, `topic_name`, `subtopic`, `difficulty`, `prerequisites`, `keywords`, `questions`, `associated_visuals`. No `grade`, no `source_markdown`.
- **KG `concepts` row:** `name` = "Speed & Velocity", `subtopic` = "Motion & Forces", `difficulty` = "easy", `grade` = `{}`, `prerequisites` = `{}`, `metadata` = `{"subject": "physics"}`. So name/subtopic/difficulty/keywords and subject came from the JSON (and document); grade and source_markdown are default empty/null.

**Conclusion:** You can use the Concept JSON as ground truth for the KG. For each concept object, the JSON contains everything the KG uses (name, subtopic, difficulty, prerequisites, keywords); `grade` and `source_markdown` are optional and default in the DB.

#### Admin Portal "Knowledge Graph" API response: what comes from where

The Admin endpoint `GET /api/v1/admin/documents/{document_id}/knowledge-graph` returns a **combined** payload. Only part of it is the Concept JSON or things built solely from it:


| Response field                                 | Source                                                                                 | From Concept JSON?                                                                                                                                                                                                                                                                                                                                                                                                                  |
| ---------------------------------------------- | -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **document_id**, **document_name**, **status** | Document row                                                                           | No (document metadata).                                                                                                                                                                                                                                                                                                                                                                                                             |
| **markdown_content**                           | `documents.markdown_content` (Phase 1 parser output)                                   | No. Parser output; not in Concept JSON.                                                                                                                                                                                                                                                                                                                                                                                             |
| **concepts_json**                              | `documents.concepts` (Phase 1 Concept Extractor output)                                | Yes. This is the raw Concept JSON.                                                                                                                                                                                                                                                                                                                                                                                                  |
| **concepts**                                   | `concepts` table (KG nodes, built in Phase 2 from Concept JSON)                        | Yes, **derived from** Concept JSON (name, subtopic, difficulty, keywords, prerequisites).                                                                                                                                                                                                                                                                                                                                           |
| **relationships**                              | `concept_relationships` table (from Concept JSON `prerequisites`)                      | Yes, **derived from** Concept JSON.                                                                                                                                                                                                                                                                                                                                                                                                 |
| **questions**                                  | `questions` table, filtered by this document’s concepts and `metadata->>'document_id'` | **Partly.** Includes (1) questions created in **Phase 2 from Concept JSON** (one row per item in `concept.questions[]`), and (2) **AI-generated questions** added later (e.g. when a test was generated). Those generated questions are linked to the same concept and have `metadata.document_id` set, so they appear in the KG view. So the **questions** array can have more items than `concepts_json.concepts[].questions[]**. |
| **skills**                                     | `skills` table via `question_skills` (created when questions are created)              | No. Comes from Phase 2 or from question generation.                                                                                                                                                                                                                                                                                                                                                                                 |


So: **Concept JSON alone** has one concept with 21 questions (all "Match the vocabulary..."). The **Admin KG response** can show 26+ questions because it includes **every question in the DB** for that document’s concepts—including questions generated later (e.g. "A person walks 6 m north...", "A cyclist travels 100 m north...") by the question generation service when building tests. For **ground truth and testing**, use **concepts_json** (and the DB **concepts** / **relationships**) as the source of “what the document ingestion produced”; treat **questions** in the API as “all questions tied to this document,” not “only from Concept JSON.”

#### How to see the raw KG at document ingestion time

1. **API with `ingestion_only=true`**
  Call:  
   `GET /api/v1/admin/documents/{document_id}/knowledge-graph?ingestion_only=true`  
   This returns the same shape as the normal KG response, but **questions** (and **skills** derived from them) are restricted to questions created at ingestion—i.e. those with `metadata.source = 'concept_extraction'`. Concepts and relationships are unchanged. The response includes `"ingestion_only": true`.  
   **Note:** Questions get `source: "concept_extraction"` only when created during document ingestion (Phase 2). Documents ingested before this flag was added will have no such questions, so `ingestion_only=true` will return **questions: []** for them; use option 2.
2. **Use `concepts_json` for the raw view (any document)**
  The **concepts_json** field is the exact Concept Extractor output: **nodes** = `concepts_json.concepts[]`, **edges** = each concept's `prerequisites[]`, **ingestion questions** = `concepts_json.concepts[].questions[]`. So for any document, **concepts_json** plus **concepts** and **relationships** from the API is the raw KG; the ingestion question list is inside **concepts_json**.
3. **Reprocess to get ingestion-only in the API**
  Reprocess the document (with cleanup) so Phase 2 runs again; new questions will have `metadata.source = 'concept_extraction'` and will appear when calling with `ingestion_only=true`.

#### How to read and verify a KG API response

Use this as a checklist when you have a JSON response from `GET .../knowledge-graph` (with or without `?ingestion_only=true`).

**1. Metadata**

- **document_id**, **document_name**, **status**: Identify the document; status should be `ready` for a full KG.
- **ingestion_only**: If `true`, **questions** (and **skills**) are only from document ingestion; otherwise they include later-generated questions.

**2. Raw extractor output: `concepts_json`**

- **concepts_json.concepts**: Array of concept objects from the Concept Extractor (Phase 1).
- For each concept note: **subtopic** (or topic_name), **topic_name**, **subject_name**, **difficulty**, **prerequisites**, **keywords**, **questions** (array of `{ text, type, associated_visuals }`).
- **Nodes (logical):** One node per element of `concepts_json.concepts`.
- **Edges (logical):** For each concept, each entry in **prerequisites** is an edge (prereq name → this concept). Prereq names must match another concept’s name/subtopic in the same document.
- **Ingestion questions:** All items in `concepts_json.concepts[].questions[]`; count = sum of `questions.length` over concepts.

**3. DB nodes: `concepts`**

- One object per KG concept (same count as `concepts_json.concepts` after normalization, or fewer if deduped).
- Each has **id**, **name**, **subtopic**, **difficulty**, **grade**, **keywords**, **prerequisites**.
- **Verify:** For each concept in `concepts_json.concepts`, there is a matching entry in **concepts** with:
  - **name** = concept’s subtopic (or topic_name, per normalization).
  - **subtopic** = concept’s topic_name (or subtopic).
  - **difficulty** matches (after normalizing to easy/medium/hard).
  - **keywords** and **prerequisites** match (order may differ).

**4. DB edges: `relationships`**

- Array of `{ from_concept_id, to_concept_id, from_concept_name, to_concept_name, relationship_type, strength }`.
- **Verify:** For each prerequisite pair (A, B) in `concepts_json` (A in concept B’s prerequisites), there is a relationship with `from_concept_name` = A, `to_concept_name` = B, `relationship_type` = `prerequisite_of`. If the document has no prerequisites, **relationships** = [].

**5. Questions: `questions`**

- If **ingestion_only** is `true`: only questions created at ingestion (metadata.source = 'concept_extraction'). May be [] for documents ingested before that flag existed.
- If **ingestion_only** is `false`: all questions for this document’s concepts (ingestion + generated).
- **Verify (ingestion view):** When non-empty, each **questions[].text** should appear in `concepts_json.concepts[].questions[].text` for some concept. Count should equal the total number of items in `concepts_json.concepts[].questions[]` when ingestion_only is true and questions were tagged.

**6. Skills: `skills`**

- Derived from questions; when **ingestion_only** is true and **questions** is [], **skills** will be [].

**Example verification for your sample response**

- **ingestion_only**: true → you are viewing raw KG (ingestion-only questions).
- **concepts_json.concepts**: 1 concept ("Speed & Velocity", topic "Motion & Forces", 21 questions, prerequisites []).
- **concepts**: 1 concept, id present, name = "Speed & Velocity", subtopic = "Motion & Forces", difficulty = easy, keywords match, prerequisites = [].
- **relationships**: [] (no prerequisites in Concept JSON).
- **questions**: [] (no questions in DB with source = 'concept_extraction' for this document yet; document was likely ingested before that metadata was added).
- **Conclusion:** The **raw KG at ingestion** is fully described by **concepts_json** + **concepts** + **relationships**. The ingestion question list (21 items) is in **concepts_json.concepts[0].questions**; use that for “questions from ingestion” until you reprocess and get them in **questions** with ingestion_only=true.

### 3.1 Parameters for Node Quality (Concepts)


| Parameter                      | Description                                                                                          | How to measure / test                                                                                                                                                                                                                                                                                                                                                          |
| ------------------------------ | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Concept creation**           | Every concept from the Concept JSON should result in a concept row or a link to an existing concept. | **Pre-label:** Concept count and names from Concept JSON (output of Step 2). **Verify:** For the document_id, count rows in `document_concepts` for that document + concepts with `document_id` = that document; total unique concepts linked to document = pre-labeled count (or fewer only due to deduplication). **Metric:** Expected count vs actual linked concept count. |
| **Name and subtopic**          | Stored `name` and `subtopic` should match the Concept JSON (after normalization).                    | **Pre-label:** List (concept name, subtopic) from JSON. **Verify:** Each concept in DB has matching name and subtopic (normalization: workflow may store subtopic as topic_name and name as subtopic). **Metric:** % of concepts with correct name/subtopic.                                                                                                                   |
| **Difficulty normalization**   | Difficulty is normalized to easy/medium/hard (invalid or pipe-separated values become "medium").     | **Pre-label:** Expected difficulty per concept from JSON (after normalizing). **Verify:** DB difficulty matches. **Metric:** % match.                                                                                                                                                                                                                                          |
| **Subject in metadata**        | Document-level subject should be in concept metadata.                                                | **Verify:** For each concept, metadata contains correct subject (when subject is set). **Metric:** % of concepts with correct subject in metadata.                                                                                                                                                                                                                             |
| **Keywords and prerequisites** | Keywords and prerequisites (list of names) stored as in JSON.                                        | **Verify:** keywords array and prerequisites array in DB match JSON (order may differ). **Metric:** % of concepts with correct keywords and prerequisites.                                                                                                                                                                                                                     |


### 3.2 Parameters for Deduplication


| Parameter                        | Description                                                                                                                                     | How to measure / test                                                                                                                                                                                                                                                               |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Same-name same-document**      | Two concepts with same name in same document: may be merged or kept separate depending on implementation.                                       | **Verify:** If Concept JSON has two concepts with identical (name, subtopic), KG may dedupe to one; then document should link to one concept. **Metric:** Documented behavior (e.g. "one concept per (name, subtopic) per document").                                               |
| **Cross-document deduplication** | When a second document has a concept with same or similar name, KG reuses existing concept (semantic similarity ≥ 0.85 or name+subtopic match). | **Pre-label:** Upload Doc A, then Doc B that clearly shares a concept (e.g. "Speed & Velocity"). **Verify:** Only one concept row for that name (or two linked via document_concepts); Doc B links to same concept_id for that concept. **Metric:** Pass/fail; concept reuse count. |
| **Link to document**             | Reused concepts must be linked to the new document via `document_concepts`.                                                                     | **Verify:** For each document_id, all concepts that appear in that document have a row in `document_concepts` or have `concepts.document_id` equal to that document. **Metric:** No orphan document-concept links; every concept used by a document is linked.                      |


### 3.3 Parameters for Relationship Quality (Edges)


| Parameter                 | Description                                                                                                | How to measure / test                                                                                                                                                                                                                                                                                                                                                  |
| ------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Prerequisite edges**    | Every prerequisite pair from Concept JSON should become a `prerequisite_of` edge (from prereq to concept). | **Pre-label:** Set of (prerequisite_concept_name, concept_name) from JSON (only names that resolve to concepts in the same document). **Verify:** For each pair, there is a row in `concept_relationships` with relationship_type = 'prerequisite_of', from_concept_id = prereq concept, to_concept_id = concept. **Metric:** % of pre-labeled pairs present as edges. |
| **Edge direction**        | Correct direction: "A is prerequisite of B" → from_concept_id = A, to_concept_id = B.                      | **Verify:** For a known A→B prerequisite, edge is (A, B, prerequisite_of). **Metric:** Pass/fail on direction.                                                                                                                                                                                                                                                         |
| **No duplicate edges**    | Unique (from_concept_id, to_concept_id, relationship_type).                                                | **Verify:** No duplicate rows for same (from, to, type). **Metric:** Pass/fail.                                                                                                                                                                                                                                                                                        |
| **Within-document scope** | Prerequisites are only created for concepts in the same document (name_to_id is document-scoped).          | **Pre-label:** One document with concepts A, B; A prerequisite of B. Another document with only C. **Verify:** No edge from C to A/B or A/B to C. **Metric:** Pass/fail.                                                                                                                                                                                               |
| **Strength (optional)**   | If strength is used, it should be in [0, 1].                                                               | **Verify:** All relationship rows have strength in range. **Metric:** Pass/fail.                                                                                                                                                                                                                                                                                       |


### 3.4 Parameters for Graph Structure


| Parameter                   | Description                                                                                                                                             | How to measure / test                                                                                                                                           |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Connectivity**            | Concepts with prerequisites should form a DAG or at least no self-loops.                                                                                | **Verify:** No row where from_concept_id = to_concept_id; optional: topological sort exists (no cycles). **Metric:** Pass/fail; cycle count = 0.                |
| **Orphan concepts**         | Every concept linked to the document should have at least one relationship (in or out) when the document has multiple concepts and prerequisites exist. | **Optional:** Count concepts with 0 in-edges and 0 out-edges; for a doc with known prerequisites, expect few orphans. **Metric:** Orphan count (informational). |
| **Relationship type usage** | Only allowed types: prerequisite_of, related_to, builds_on, requires.                                                                                   | **Verify:** All relationship_type values in allowed set. **Metric:** Pass/fail.                                                                                 |


### 3.5 Suggested Scoring Summary (Knowledge Graph)

- **Nodes:** Concept count match + name/subtopic/difficulty/metadata correctness.
- **Deduplication:** Cross-document reuse when expected + correct document_concepts links.
- **Edges:** % of expected prerequisite pairs present + correct direction + no duplicates + within-document only.
- **Structure:** No self-loops, valid types, optional cycle check.

Report per-document and, for dedup, per pair of documents.

---

## 4. Cross-Cutting: Run Design (5 Docs × 2 Subjects × 3 Runs)

- **Markdown:** Pre-label each of the 5 documents once (handwritten phrases, visual list, section list, question count, formulas). After each of the 3 runs, compute the metrics above; report mean and variance (e.g. phrase recall 78% ± 5%).
- **Concept JSON:** Pre-label expected concept count, question count, taxonomy, sample types, prerequisite pairs. Per run, compute schema compliance, completeness, fidelity, taxonomy, linkage; report averages and variance across 3 runs.
- **Knowledge graph:** After each run, query DB for concept count, relationship count, and sample edges; compare to pre-labeled expectations. For cross-doc dedup, use 2 documents from the same subject and check reuse.

Attributes to test Concepts JSON


| Attribute               | What the description covers                                                                                                                                  |
| ----------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Concept Nodes**       | Count of distinct concepts (topic/subtopic) the extractor should produce; one concept = one grouping of questions with shared subject/topic/subtopic.        |
| **Atomic Questions**    | Count of question objects: one per question, part, table row, or matching term (no grouping). Defines "grouped extraction" as the main error type.           |
| **Type Mapping**        | Correct assignment of type per question (multiple_choice, short_answer, problem_solving, conceptual_question, matching, fill_in_the_blank), with an example. |
| **Taxonomy Compliance** | Using only subject/topic/subtopic from the reference taxonomy (no invented values).                                                                          |
| **Inheritance Formula** | Question text must follow "[Section/Instruction] + [Specific Item or Body]" (e.g. "Match the following: Velocity").                                          |
| **Linkage (Visuals)**   | Question–visual (or concept–visual) links: markdown "Associated Visual: V1" must appear in the question's/concept's associated_visuals in the JSON.          |


