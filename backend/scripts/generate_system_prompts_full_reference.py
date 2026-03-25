#!/usr/bin/env python3
"""Generate docs/SYSTEM_PROMPTS_FULL_REFERENCE.md from source files (no package imports).

Run from repo root:
  python backend/scripts/generate_system_prompts_full_reference.py
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
BACKEND = REPO / "backend"
OUT = REPO / "docs" / "SYSTEM_PROMPTS_FULL_REFERENCE.md"


def lines_slice(path: Path, start: int, end: int) -> str:
    """1-based inclusive line range."""
    text = path.read_text(encoding="utf-8")
    all_lines = text.splitlines(keepends=True)
    return "".join(all_lines[start - 1 : end])


def extract_regex(text: str, pattern: str) -> str:
    m = re.search(pattern, text, re.DOTALL)
    if not m:
        raise ValueError(f"Pattern not found: {pattern[:100]}...")
    return m.group(1)


def main() -> None:
    chunks: list[str] = []

    def add(title: str, body: str) -> None:
        chunks.append(f"\n\n{'=' * 80}\n## {title}\n{'=' * 80}\n\n")
        chunks.append(body.rstrip() + "\n")

    prompts_py = (BACKEND / "workflows" / "prompts.py").read_text(encoding="utf-8")
    doc_parser = extract_regex(
        prompts_py, r"DOCUMENT_PARSER_PROMPT = \"\"\"(.*?)\"\"\""
    )
    concept_raw = extract_regex(
        prompts_py, r"CONCEPT_EXTRACTOR_PROMPT = \"\"\"(.*?)\"\"\""
    )

    topics_json = (BACKEND / "subject_topics.json").read_text(encoding="utf-8")
    concept_resolved = concept_raw.replace("{subject_topics_json}", topics_json)

    add(
        "DOCUMENT_PARSER_PROMPT — backend/workflows/prompts.py (document_parser agent)",
        doc_parser,
    )
    add(
        "CONCEPT_EXTRACTOR_PROMPT (template) — backend/workflows/prompts.py\n"
        "Runtime: get_prompt() replaces {subject_topics_json} with full taxonomy or one subject slice.",
        concept_raw,
    )
    add(
        "CONCEPT_EXTRACTOR_PROMPT (resolved) — full subject_topics.json embedded as in production when subject=None",
        concept_resolved,
    )

    llm_eval = (BACKEND / "services" / "evaluation" / "llm_evaluator.py").read_text(
        encoding="utf-8"
    )
    add(
        "STRICT_SCORER_SYSTEM_PROMPT — backend/services/evaluation/llm_evaluator.py",
        extract_regex(
            llm_eval, r"STRICT_SCORER_SYSTEM_PROMPT = \"\"\"(.*?)\"\"\""
        ),
    )
    add(
        "FEEDBACK_SYSTEM_PROMPT — backend/services/evaluation/llm_evaluator.py",
        extract_regex(llm_eval, r"FEEDBACK_SYSTEM_PROMPT = \"\"\"(.*?)\"\"\""),
    )

    wf = (BACKEND / "workflows" / "workflow.py").read_text(encoding="utf-8")
    add(
        "Subject classifier — system_prompt f-string — backend/workflows/workflow.py "
        "(extract_subject_from_markdown; subject_choices_str and valid_subject_ids are dynamic)",
        lines_slice(BACKEND / "workflows" / "workflow.py", 296, 307),
    )

    sg_path = BACKEND / "services" / "study_guide_service.py"
    add(
        "_get_master_system_prompt return body — backend/services/study_guide_service.py "
        "(f-string: {context_block}, {output_language} injected at runtime)",
        lines_slice(sg_path, 232, 290),
    )

    # Concatenated string literals
    val_block = lines_slice(sg_path, 533, 542)
    add("_validate_guide_content — system_prompt — study_guide_service.py", val_block)

    ped_block = lines_slice(sg_path, 579, 584)
    add("_pedagogical_pass — system_prompt — study_guide_service.py", ped_block)

    add(
        "_generate_revision_cards_llm — system_prompt f-string — study_guide_service.py "
        "(runtime: output_lang, scope_instruction when subject/topic set)",
        lines_slice(sg_path, 1251, 1282),
    )

    tests_path = BACKEND / "api" / "v1" / "tests.py"
    add(
        "_build_coach_system_prompt — backend/api/v1/tests.py "
        "(runtime appends full [STUDY_GUIDE] and optional STUDENT ERROR CONTEXT)",
        lines_slice(tests_path, 1660, 1737),
    )

    qgen = BACKEND / "services" / "question_generation_service.py"
    add(
        "Question generation — single-concept system_prompt (f-string) — "
        "backend/services/question_generation_service.py "
        "(values for num_questions, target_subject, grade_level, difficulty, output_language, "
        "subject_profile_json, context_text, json_schema come from runtime)",
        lines_slice(qgen, 298, 451),
    )
    add(
        "Question generation — multi-concept system_prompt — "
        "backend/services/question_generation_service.py "
        "(.format() fills num_questions, target_subject, grade_level, difficulty, output_language, "
        "subject_profile_json, context_text, json_schema_placeholder; may append subject profile "
        "system_instructions and format_rules from subject_profiles.json)",
        lines_slice(qgen, 771, 831),
    )

    graph_eval = (BACKEND / "services" / "graph_evaluation_service.py").read_text(
        encoding="utf-8"
    )
    # User-message prompt (not a separate system role)
    ge = extract_regex(
        graph_eval,
        r"# Create prompt for LLM evaluation\s+prompt = f\"\"\"(.*?)\"\"\"",
    )
    add(
        "Graph evaluation — LLM prompt (USER message, not system_prompt) — "
        "backend/services/graph_evaluation_service.py",
        ge,
    )

    header = f"""# Zoria — full system & key LLM prompts (print reference)

**Generated by:** `backend/scripts/generate_system_prompts_full_reference.py`  
**Regenerate after editing prompts:** run the script from the repo root.

This file concatenates **system prompts** and closely related **instruction blocks** used with the LLM,
copied from source. Dynamic parts are marked in code as f-strings or `.format()` fields.

**Not duplicated here:** per-subject `llm_prompt_template.system_instructions` and `format_rules` in
`backend/subject_profiles.json` (appended at runtime to question-generation system prompts).

**Infrastructure:** `backend/services/llm_service.py` sends `system_prompt` as the model system message
where applicable; OpenAI Agents use `instructions` (see `backend/services/agent_logging_wrapper.py`).

---
"""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(header + "".join(chunks), encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
