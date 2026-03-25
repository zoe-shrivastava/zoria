# System prompts registry (Zoria)

This document lists **where LLM `system` / agent `instructions` prompts are defined** and how they are used.  
**Full prompt text** lives in the cited source files; this file is an index with short descriptions.

**Printable / single-file copy of all prompts:** [`docs/SYSTEM_PROMPTS_FULL_REFERENCE.md`](SYSTEM_PROMPTS_FULL_REFERENCE.md) (regenerate with `python backend/scripts/generate_system_prompts_full_reference.py` from the repo root).

---

## Shared infrastructure (not prompts themselves)

| Location | Role |
|----------|------|
| `backend/services/llm_service.py` | Accepts `system_prompt` and sends it as the `system` / first system message to OpenAI-compatible or Ollama backends. |
| `backend/services/llm_logging_service.py` | Persists `system_prompt` on LLM log rows for admin debugging. |
| `frontend/src/components/LLMLogsViewer.jsx` | Displays stored `system_prompt` in the admin LLM logs UI. |
| `backend/schemas/llm_log.py` | Schema field for logged `system_prompt`. |

---

## Document ingestion workflow (OpenAI Agents)

| Prompt key / symbol | File | Used by | Description |
|---------------------|------|---------|-------------|
| `DOCUMENT_PARSER_PROMPT` | `backend/workflows/prompts.py` | `document_parser` agent (`backend/workflows/workflow.py`, `instructions=get_prompt("document_parser")`) | Instructs the parser to extract full document content into structured Markdown (questions, parts, visuals). |
| `CONCEPT_EXTRACTOR_PROMPT` | `backend/workflows/prompts.py` | `concept_extractor` agent (`instructions=get_prompt("concept_extractor", subject=...)`) | Domain-agnostic atomic extraction from Markdown to structured concepts JSON; injects `subject_topics.json` (full or per-subject slice). |
| `get_prompt()` / `PROMPTS` registry | `backend/workflows/prompts.py` | Same | Central registry with metadata (`description`, `used_by`, `output_format`). |

---

## Subject classification (Phase 1 helper)

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| Inline `system_prompt` (subject classifier JSON) | `backend/workflows/workflow.py` (`extract_subject_from_markdown` or similar) | `LLMService.generate_json(...)` | Classifies document excerpt into one `subject_id` from configured subject profiles; returns JSON `{"subject_id": "..."}`. |

---

## Test evaluation (FRQ / short answer)

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| `STRICT_SCORER_SYSTEM_PROMPT` | `backend/services/evaluation/llm_evaluator.py` | `LLMEvaluator.evaluate()` → `generate_json(...)` | Strict STEM grader: JSON `score` / `errors` / `reasoning`; rules for relevance, partial credit, variable/unit sensitivity. |
| `FEEDBACK_SYSTEM_PROMPT` | `backend/services/evaluation/llm_evaluator.py` | `LLMEvaluator._generate_feedback()` → `generate(...)` | Report-style feedback tone (no chat); three-part structure, word limit. |
| `_build_strict_scoring_prompt()` (user/task prompt, not system) | Same file | Bundled with scorer | Adds question, student answer, expected answer, optional solution steps. |

**Routing:** `backend/services/evaluation/question_router.py` sends `short_answer`, `problem_solving`, `conceptual_question`, etc. to the LLM evaluator when configured.

---

## Study guide generation

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| `_get_master_system_prompt()` | `backend/services/study_guide_service.py` | `_generate_outline()`, `_generate_section()` | “Zoria Structured Educational Content Engine”: one section at a time; Markdown/LaTeX rules; grade-level and subject-accuracy guardrails. |
| Validation pass `system_prompt` (inline string) | Same file | `_validate_guide_content()` | Fact/structure checker; must return full document with minimal fixes. |
| Pedagogical pass `system_prompt` (inline string) | Same file | `_pedagogical_pass()` | Tone/clarity editor for full guide without changing structure. |
| Revision cards `system_prompt` (f-string, `# Role: Expert Educational Content Extractor`) | Same file | `_generate_revision_cards_llm()` (or equivalent) | JSON array of `{front, back}` cards; LaTeX/KaTeX rules; language scope. |
| User prompts (`_build_outline_prompt`, `_build_section_prompt`, etc.) | Same file | Paired with master system prompt | Task-specific user messages (outline vs section N). |

---

## AI Coach (study guide chat)

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| `_build_coach_system_prompt()` | `backend/api/v1/tests.py` | `POST /api/v1/tests/study-guide/coach/chat` | Socratic tutor: language/script rules, profile preferences, study guide as `[STUDY_GUIDE]`, error context, navigation tags (`[NAV:...]`), LaTeX note. |

---

## Question generation (tests from concepts / context)

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| Single-concept `system_prompt` (starts with `## System Instruction` + Assessment Engine rules) | `backend/services/question_generation_service.py` | `generate_questions_for_concept(...)` (method name may vary) | High-fidelity JSON question generation: types, hints, solution_steps, TikZ/diagram rules, `metadata`; appends subject profile `system_instructions` and `format_rules` when present. |
| Multi-concept `system_prompt` (starts with `**Role:** You are a high-fidelity **Question Engine**`) | Same file | Multi-concept generation path | Same intent as single-concept; schema/placeholders differ; appends subject-specific blocks. |

Subject-specific lines come from `backend/subject_profiles.json` → `llm_prompt_template.system_instructions` and `format_rules` (per subject).

---

## Agent logging (dynamic system text)

| Source | File | Description |
|--------|------|-------------|
| `agent.instructions` | `backend/services/agent_logging_wrapper.py` | When an OpenAI Agents `Agent` runs, its `instructions` field is logged as `system_prompt` for LLM logging—**content depends on which agent** (e.g. same parser/extractor prompts as above if those are the agent definitions). |

---

## Graph drawing evaluation (LLM path)

| Prompt | File | Used by | Description |
|--------|------|---------|-------------|
| Inline prompt in `_evaluate_with_llm()` | `backend/services/graph_evaluation_service.py` | Optional LLM graph grading | **User message only** (no separate `system_prompt`): instructs the model to return JSON `correct`, `score`, `feedback` from drawing features + question text. |

---

## Not LLM system prompts (for clarity)

| Area | Note |
|------|------|
| `backend/services/concept_evaluation_service.py` | Deterministic/heuristic checks for MD→concepts and concepts→KG; **no** LLM system prompt. |
| `backend/services/evaluation/heuristic_evaluator.py` / `deterministic_evaluator.py` | Numeric / exact-match logic; **no** system prompt. |
| `backend/services/evaluation/error_library.py` | `get_mastery_penalty()` is for mastery weighting, **not** an LLM prompt. |

---

## Maintenance

- **Workflow ingestion prompts:** edit `backend/workflows/prompts.py` and use `get_prompt("document_parser" | "concept_extractor", subject=...)`.
- **Evaluator prompts:** edit `LLMEvaluator` class constants in `backend/services/evaluation/llm_evaluator.py`.
- **Coach:** edit `_build_coach_system_prompt()` in `backend/api/v1/tests.py`.
- **Question generation:** edit `question_generation_service.py` strings; optionally tune per subject in `backend/subject_profiles.json`.

When adding a new prompt, prefer a **named constant** or a **registry dict** (like `PROMPTS` in `workflows/prompts.py`) and wire it through `LLMService.generate` / `generate_json` so it appears in LLM logs.
