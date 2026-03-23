"""Evaluator helpers for MD -> Concepts and Concepts -> KG."""

from __future__ import annotations

import re
from typing import Any, Dict, Set


def _estimate_expected_questions(markdown: str) -> int:
    # Support both:
    # - "Question q1"
    # - "Question ID: q1"
    # Question IDs can appear as:
    # - "Question q1"
    # - "Question ID: q1"
    # They may also be preceded by list markers or extra spacing, so we match
    # without requiring the whole line to equal the pattern.
    q_main_inline = len(re.findall(r"Question\s+(?!ID\b)q[\w\-]+", markdown, flags=re.IGNORECASE))
    q_main_id = len(re.findall(r"Question\s+ID\s*:\s*(q[\w\-]+)", markdown, flags=re.IGNORECASE))

    # Support multiple part styles:
    # - "Part q1_a"
    # - "- 9(a) ..."
    # - "- 12(k) ..."
    q_parts_named = len(re.findall(r"^\s*Part\s+[a-zA-Z0-9_()\-]+", markdown, flags=re.MULTILINE | re.IGNORECASE))
    q_parts_numbered = len(re.findall(r"^\s*-\s*\d+\([a-z]\)\b", markdown, flags=re.MULTILINE | re.IGNORECASE))
    # Matching rows like "- A. Velocity — ..."
    q_matching_rows = len(re.findall(r"^\s*-\s*[A-Z]\.\s+.+$", markdown, flags=re.MULTILINE))
    # Table-like atomic rows often represented as single bullet labels:
    # "- Distance", "- Displacement", etc.
    q_atomic_label_rows = len(
        re.findall(r"^\s*-\s*[A-Za-z][A-Za-z0-9 &/\-]{1,80}\s*$", markdown, flags=re.MULTILINE)
    )

    q_bullets = len(re.findall(r"^\s*-\s+Text:\s+", markdown, flags=re.MULTILINE))
    q_final = len(re.findall(r"^\s*Final\s+Question\b", markdown, flags=re.MULTILINE | re.IGNORECASE))
    q_main = q_main_inline + q_main_id
    q_parts = q_parts_named + q_parts_numbered
    estimated_total = q_main + q_parts + q_matching_rows + q_final
    # Include atomic label rows as a weak signal only when there are many.
    if q_atomic_label_rows >= 8:
        estimated_total += q_atomic_label_rows
    return max(estimated_total, q_main, q_bullets)


def _estimate_expected_questions_atomic(markdown: str) -> Dict[str, int]:
    """Count expected questions using explicit atomic buckets for extracted markdown."""
    md = markdown or ""

    # Match question IDs without requiring full-line match (tolerates bullets/extra text).
    question_ids = len(re.findall(r"Question\s+ID\s*:\s*(q[\w\-]+)", md, flags=re.IGNORECASE))
    final_questions = len(re.findall(r"Final\s+Question\b", md, flags=re.IGNORECASE))

    # Lettered/numbered subparts in bullets: "- 12(a) ..."
    numbered_parts = len(re.findall(r"^\s*-\s*\d+\([a-z]\)\b", md, flags=re.MULTILINE | re.IGNORECASE))

    # Named parts blocks: "Part q1_a", "Part ID: q1_a"
    named_parts = len(re.findall(r"^\s*Part\s+(?:ID\s*:\s*)?[a-zA-Z0-9_()\-]+\s*$", md, flags=re.MULTILINE | re.IGNORECASE))

    # Matching rows like "- A. Velocity — ..."
    matching_rows = len(re.findall(r"^\s*-\s*[A-Z]\.\s+.+$", md, flags=re.MULTILINE))

    # Table/chart atomic rows represented as single bullet labels.
    # We exclude bullets that are clearly metadata fields.
    label_rows = 0
    for m in re.findall(r"^\s*-\s*([A-Za-z][A-Za-z0-9 &/\-]{1,100})\s*$", md, flags=re.MULTILINE):
        t = m.strip().lower()
        if t in {
            "definition", "symbol", "si units", "base units", "classification",
            "student answer", "text", "type", "axes", "data points", "key features",
            "description", "document header", "notes and observations",
        }:
            continue
        if t.startswith(("student answer", "classification", "visual", "associated question")):
            continue
        label_rows += 1

    total = question_ids + final_questions + numbered_parts + named_parts + matching_rows + label_rows
    return {
        "total": total,
        "question_ids": question_ids,
        "final_questions": final_questions,
        "numbered_parts": numbered_parts,
        "named_parts": named_parts,
        "matching_rows": matching_rows,
        "label_rows": label_rows,
    }


def _normalize_type(q_type: Any) -> str:
    t = str(q_type or "").strip().lower()
    # Remove descriptive suffixes like "(calculation)" and trim separators.
    t = re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()
    mapping = {
        "multiple choice": "multiple_choice",
        "conceptual_problem": "problem_solving",
        "multiple_choice/short_answer": "short_answer",
        "conceptual / estimation": "conceptual_question",
        "graph_interpretation": "problem_solving",
        "multiple_part_problem": "problem_solving",
    }
    return mapping.get(t, t)


def _count_expected_question_visual_links(markdown: str) -> int:
    """Count visual links from question context in markdown.

    This intentionally counts question-linked visual mentions (occurrences), not
    visual description blocks.
    """
    if not markdown:
        return 0

    # Ignore consolidated appendix blocks to avoid double counting visual catalogs.
    main_body = re.split(r"^\s*#\s+All\s+Visuals\b", markdown, maxsplit=1, flags=re.MULTILINE | re.IGNORECASE)[0]

    count = 0

    # 1) "Visual referenced: ... (see Visual v_xxx)"
    for line in re.findall(r"^\s*Visual\s+referenced\s*:\s*(.+?)\s*$", main_body, flags=re.MULTILINE | re.IGNORECASE):
        ids = re.findall(r"\b(v_[A-Za-z0-9_\-]+)\b", line)
        if ids:
            count += len(ids)
        elif line.strip() and line.strip().lower() not in {"none", "none (text only)"}:
            count += 1

    # 2) "Associated Visual:" / "Associated Visuals:" / "Visual associated:"
    for line in re.findall(
        r"^\s*(?:Associated\s+Visuals?|Visual\s+associated)\s*:\s*(.+?)\s*$",
        main_body,
        flags=re.MULTILINE | re.IGNORECASE,
    ):
        raw = (line or "").strip()
        if not raw:
            continue
        lower = raw.lower()
        if lower in {"none", "none (text only)"} or lower.startswith("none "):
            continue
        ids = re.findall(r"\b(v_[A-Za-z0-9_\-]+)\b", raw)
        if ids:
            count += len(ids)
        else:
            # Non-ID but still a linked visual mention (e.g., "small squirrel illustration").
            count += 1

    # 3) Inline "Visual ID: v_xxx" in question blocks (still in main body only)
    count += len(re.findall(r"^\s*Visual\s+ID\s*:\s*v_[A-Za-z0-9_\-]+\s*$", main_body, flags=re.MULTILINE | re.IGNORECASE))

    # 4) Generic "Visual: ..." lines in questions, excluding explicit none.
    for line in re.findall(r"^\s*Visuals?\s*:\s*(.+?)\s*$", main_body, flags=re.MULTILINE | re.IGNORECASE):
        raw = (line or "").strip()
        if not raw:
            continue
        lower = raw.lower()
        if lower in {"none", "none (text only)"} or lower.startswith("none "):
            continue
        ids = re.findall(r"\b(v_[A-Za-z0-9_\-]+)\b", raw)
        count += len(ids) if ids else 1

    return count


def _extract_question_identity_from_text(text: str) -> str:
    """Extract stable question identity from question text when possible."""
    if not text:
        return ""
    t = str(text).strip()
    # Common patterns in extracted markdown / generated concepts text:
    # "Question q11_a: ...", "Question ID: q11_a", "q11_a: ..."
    patterns = [
        r"\bQuestion\s+ID\s*:\s*(q[\w\-]+)\b",
        r"\bQuestion\s+(q[\w\-]+)\s*:",
        r"^\s*(q[\w\-]+)\s*:",
    ]
    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            return m.group(1).lower()
    return ""


def _extract_expected_from_markdown(markdown: str) -> Dict[str, Any]:
    markdown = markdown or ""
    expected_questions = _estimate_expected_questions(markdown)

    topic_matches = re.findall(r"^\s*Topic(?:\s+Name)?\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    subtopic_matches = re.findall(r"^\s*Subtopic\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    concept_name_matches = re.findall(r"^\s*Concept(?:\s+Name)?\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)

    # Heading-style markdown support:
    #   ## Topic: Work and Energy
    #   ### Subtopic: Work-Energy Theorem
    #   #### Concept: Net Work
    # and plain headings:
    #   ## Work and Energy
    #   ### Work-Energy Theorem
    topic_heading_explicit = re.findall(r"^\s{0,3}#{1,2}\s+Topic(?:\s+Name)?\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    subtopic_heading_explicit = re.findall(r"^\s{0,3}#{3,4}\s+Subtopic\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    concept_heading_explicit = re.findall(r"^\s{0,3}#{3,6}\s+Concept(?:\s+Name)?\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    # Prefer section headings over generic heading text to avoid over-counting metadata blocks.
    section_topic_matches = re.findall(r"^\s{0,3}#*\s*Section\s*:\s*(.+?)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)

    def _clean_heading(text: str) -> str:
        t = re.sub(r"\s+", " ", str(text or "")).strip()
        t = re.sub(r"^[\-*`>\s]+", "", t)
        t = re.sub(r"[:\-\s]+$", "", t)
        return t

    def _is_noise_heading(text: str) -> bool:
        t = _clean_heading(text).lower()
        if not t:
            return True
        # Ignore separators and common non-topic headings.
        if t in {"---", "questions", "question", "answers", "answer", "visuals", "visual", "metadata", "notes"}:
            return True
        if re.fullmatch(r"q[\w\-]+", t):
            return True
        if t.startswith("visual "):
            return True
        return False

    def _is_noise_section_label(text: str) -> bool:
        t = _clean_heading(text).lower()
        if not t:
            return True
        # Ignore non-conceptual document wrappers/appendix sections.
        if any(
            token in t
            for token in [
                "document extraction",
                "document header",
                "document metadata",
                "appendix",
                "all visuals",
                "all mathematical formulas",
                "notes and observations",
            ]
        ):
            return True
        return False
    # Keep type extraction single-line; avoid swallowing separators/newlines.
    q_type_matches = re.findall(r"^\s*-?\s*Type\s*:\s*([^\r\n]+)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)

    # Expected visual links are question-link occurrences from markdown, not
    # visual description entry counts.
    visual_desc_links = _count_expected_question_visual_links(markdown)

    topic_set = {
        _clean_heading(m)
        for m in (topic_matches + topic_heading_explicit + section_topic_matches)
        if m and _clean_heading(m) and not _is_noise_heading(m)
    }
    subtopic_set = {
        _clean_heading(m)
        for m in (subtopic_matches + subtopic_heading_explicit)
        if m and _clean_heading(m) and not _is_noise_heading(m)
    }
    concept_name_set = {
        _clean_heading(m)
        for m in (concept_name_matches + concept_heading_explicit)
        if m and _clean_heading(m) and not _is_noise_heading(m)
    }
    # Only include canonical question types from type lines.
    valid_question_types = {
        "multiple_choice",
        "short_answer",
        "problem_solving",
        "conceptual_question",
        "matching",
        "fill_in_the_blank",
    }
    composite_aliases = {
        "conceptual/matching": "matching",
        "instruction / chart fill-in": "fill_in_the_blank",
        "graph analysis / problem_solving": "problem_solving",
        "graph sketching / short answer": "short_answer",
        "equation analysis / graphing": "problem_solving",
        "data analysis / spring constant": "problem_solving",
        "conceptual/diagram": "conceptual_question",
        "conceptual/unit_conversion": "conceptual_question",
    }
    # Exclude visual/meta types.
    disallowed_type_tokens = {
        "diagram",
        "chart",
        "fbd",
        "fbd diagram",
        "instruction_fields",
        "problem_solving_collection",
    }
    q_types_norm = set()
    for m in q_type_matches:
        raw = str(m or "").strip().lower()
        if not raw:
            continue
        mapped = composite_aliases.get(raw, _normalize_type(raw))
        if not mapped or mapped in disallowed_type_tokens:
            continue
        candidates = [mapped]
        if "/" in raw and raw not in composite_aliases:
            candidates = [_normalize_type(part.strip()) for part in raw.split("/") if part.strip()]
        for c in candidates:
            if c in valid_question_types:
                q_types_norm.add(c)

    # More reliable concept estimate for this markdown style:
    # "Question q_concept_*" entries correspond to concept items.
    concept_question_ids = set(
        re.findall(r"^\s*Question\s+(q_concept_[A-Za-z0-9_\-]+)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    )
    concept_question_ids.update(
        re.findall(r"^\s*Question\s+ID\s*:\s*(q_concept_[A-Za-z0-9_\-]+)\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE)
    )

    # Also support section-based concept grouping for extracted markdown formats
    # like: "Section: Vocabulary Matching (Question 1)".
    # Be tolerant: match "Section:" anywhere on a line, not only exact line anchors.
    section_label_candidates = re.findall(r"Section\s*:\s*([^\r\n]+)", markdown, flags=re.IGNORECASE)
    section_labels = set(
        _clean_heading(m)
        for m in section_label_candidates
        if m and _clean_heading(m) and not _is_noise_section_label(m)
    )

    expected_concepts = len(concept_name_set)
    if expected_concepts == 0 and concept_question_ids:
        expected_concepts = len(concept_question_ids)
    if expected_concepts == 0 and section_labels:
        expected_concepts = len(section_labels)
    if expected_concepts == 0 and subtopic_set:
        expected_concepts = len(subtopic_set)

    # Subtopic fallback for documents that organize by concept/practice/challenge families
    # but do not label subtopics explicitly.
    if len(subtopic_set) == 0:
        has_concepts_block = bool(re.search(r"^\s*#*\s*Section\s*:\s*Concept\s+questions\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE))
        has_practice_block = bool(re.search(r"^\s*#*\s*Section\s*:\s*Practice\s+Questions\s*$", markdown, flags=re.MULTILINE | re.IGNORECASE))
        has_challenge_block = bool(re.search(r"^\s*Challenge\s+Problem\b", markdown, flags=re.MULTILINE | re.IGNORECASE))
        inferred_subtopics = int(has_concepts_block) + int(has_practice_block) + int(has_challenge_block)
        if inferred_subtopics > 0:
            subtopic_set = {f"inferred_{i}" for i in range(inferred_subtopics)}

    return {
        "concepts": expected_concepts,
        "questions": expected_questions,
        "unique_question_types": len(q_types_norm),
        "unique_question_types_values": sorted(q_types_norm),
        "topic_count": len(topic_set),
        "subtopic_count": len(subtopic_set),
        "visual_description_links": visual_desc_links,
    }


def evaluate_markdown_concepts(markdown: str, concepts_json: Dict[str, Any]) -> Dict[str, Any]:
    concepts = concepts_json.get("concepts", []) if isinstance(concepts_json, dict) else []
    if not isinstance(concepts, list):
        concepts = []

    expected_questions = _estimate_expected_questions(markdown or "")
    expected_atomic = _estimate_expected_questions_atomic(markdown or "")
    output_questions = 0
    types_raw: Set[str] = set()
    types_normalized: Set[str] = set()
    topic_names: Set[str] = set()
    subtopics: Set[str] = set()
    concept_keys: Set[str] = set()
    duplicate_concepts = 0
    concepts_with_prereq = 0
    invalid_prereq_refs = 0
    visual_desc_links = 0
    unique_visual_ids: Set[str] = set()
    seen_question_visual_links: Set[str] = set()
    seen_questions: Set[str] = set()

    concept_name_set: Set[str] = set()
    for c in concepts:
        if not isinstance(c, dict):
            continue
        cname = str(c.get("subtopic") or "").strip()
        if cname:
            concept_name_set.add(cname.lower())

    for c in concepts:
        if not isinstance(c, dict):
            continue
        topic = str(c.get("topic_name") or "").strip()
        subtopic = str(c.get("subtopic") or "").strip()
        if topic:
            topic_names.add(topic)
        if subtopic:
            subtopics.add(subtopic)

        ckey = f"{topic.lower()}::{subtopic.lower()}"
        if ckey in concept_keys:
            duplicate_concepts += 1
        concept_keys.add(ckey)

        prereqs = c.get("prerequisites") or []
        if isinstance(prereqs, list) and len(prereqs) > 0:
            concepts_with_prereq += 1
            for p in prereqs:
                ptxt = str(p or "").strip().lower()
                if ptxt and ptxt not in concept_name_set:
                    invalid_prereq_refs += 1

        c_visuals = c.get("associated_visuals") or []
        if isinstance(c_visuals, list):
            for vid in c_visuals:
                if vid:
                    unique_visual_ids.add(str(vid))

        questions = c.get("questions") or []
        if not isinstance(questions, list):
            continue
        for q in questions:
            if not isinstance(q, dict):
                continue
            q_identity = str(q.get("id") or "").strip()
            if not q_identity:
                q_identity = _extract_question_identity_from_text(str(q.get("text") or ""))
            if not q_identity:
                q_identity = re.sub(r"\s+", " ", str(q.get("text") or "").strip().lower())
            if not q_identity:
                continue
            is_new_question = q_identity not in seen_questions
            if is_new_question:
                seen_questions.add(q_identity)
                output_questions += 1

            q_type = str(q.get("type") or "").strip()
            if q_type and is_new_question:
                types_raw.add(q_type)
                types_normalized.add(_normalize_type(q_type))
            q_visuals = q.get("associated_visuals") or []
            if isinstance(q_visuals, list):
                for vid in q_visuals:
                    vid_str = str(vid or "").strip()
                    if not vid_str:
                        continue
                    unique_visual_ids.add(vid_str)
                    link_key = f"{q_identity}::{vid_str.lower()}"
                    if link_key not in seen_question_visual_links:
                        seen_question_visual_links.add(link_key)
                        visual_desc_links += 1

    concept_count = len(concepts)
    coverage = (output_questions / expected_questions) if expected_questions > 0 else 1.0
    prereq_coverage = (concepts_with_prereq / concept_count) if concept_count else 0.0
    duplicate_ratio = (duplicate_concepts / concept_count) if concept_count else 0.0

    expected = _extract_expected_from_markdown(markdown or "")
    expected["questions"] = max(expected.get("questions", 0), expected_atomic.get("total", 0), expected_questions)
    actual = {
        "concepts": concept_count,
        "questions": output_questions,
        "unique_question_types": len(types_normalized),
        "unique_question_types_values": sorted(types_normalized),
        "topic_count": len(topic_names),
        "subtopic_count": len(subtopics),
        "visual_description_links": visual_desc_links,
    }

    return {
        "attributes": {
            "concepts": {"expected": expected["concepts"], "actual": actual["concepts"]},
            "questions": {"expected": expected["questions"], "actual": actual["questions"]},
            "unique_question_types": {"expected": expected["unique_question_types"], "actual": actual["unique_question_types"]},
            "topic_count": {"expected": expected["topic_count"], "actual": actual["topic_count"]},
            "subtopic_count": {"expected": expected["subtopic_count"], "actual": actual["subtopic_count"]},
            "visual_description_links": {"expected": expected["visual_description_links"], "actual": actual["visual_description_links"]},
        },
        "values": {
            "question_types_expected": expected["unique_question_types_values"],
            "question_types_actual": actual["unique_question_types_values"],
            "question_types_raw_actual": sorted(types_raw),
        },
        "quality_flags": {
            "low_coverage": coverage < 0.95,
            "has_duplicate_concepts": duplicate_ratio > 0.10,
            "prerequisites_missing": prereq_coverage == 0.0,
            "has_invalid_prereq_refs": invalid_prereq_refs > 0,
        },
        "diagnostics": {
            "coverage_ratio": round(coverage, 4),
            "prereq_coverage": round(prereq_coverage, 4),
            "invalid_prereq_refs": invalid_prereq_refs,
            "duplicate_concept_ratio": round(duplicate_ratio, 4),
            "unique_visual_ids_count": len(unique_visual_ids),
            "expected_question_buckets": expected_atomic,
        },
    }


def summarize_concepts_for_kg_expected(concepts_json: Dict[str, Any]) -> Dict[str, Any]:
    concepts = concepts_json.get("concepts", []) if isinstance(concepts_json, dict) else []
    if not isinstance(concepts, list):
        concepts = []

    name_to_key: Dict[str, str] = {}
    unique_nodes: Set[str] = set()
    difficulty_distribution: Dict[str, int] = {}
    node_details: Dict[str, Dict[str, Any]] = {}
    diff_rank = {"easy": 1, "medium": 2, "hard": 3, "unknown": 0}

    for c in concepts:
        if not isinstance(c, dict):
            continue
        topic = str(c.get("topic_name") or "").strip()
        subtopic = str(c.get("subtopic") or "").strip()
        name = subtopic or str(c.get("name") or "").strip()
        if not name:
            continue
        key = f"{topic.lower()}::{name.lower()}"
        unique_nodes.add(key)
        name_to_key[name.lower()] = key

        difficulty = str(c.get("difficulty") or "unknown").strip().lower() or "unknown"
        difficulty_distribution[difficulty] = difficulty_distribution.get(difficulty, 0) + 1
        if key not in node_details:
            node_details[key] = {
                "concept_key": key,
                "concept_name": name,
                "topic_name": topic,
                "difficulty": difficulty,
                "prerequisites": [],
            }
        else:
            existing_diff = node_details[key].get("difficulty", "unknown")
            if diff_rank.get(difficulty, 0) > diff_rank.get(existing_diff, 0):
                node_details[key]["difficulty"] = difficulty

    prereq_edges: Set[str] = set()
    for c in concepts:
        if not isinstance(c, dict):
            continue
        topic = str(c.get("topic_name") or "").strip()
        subtopic = str(c.get("subtopic") or "").strip()
        to_name = subtopic or str(c.get("name") or "").strip()
        to_key = name_to_key.get(to_name.lower()) if to_name else None
        if not to_key:
            continue
        prereqs = c.get("prerequisites") or []
        if not isinstance(prereqs, list):
            continue
        for p in prereqs:
            p_name = str(p or "").strip()
            if not p_name:
                continue
            from_key = name_to_key.get(p_name.lower())
            if from_key and from_key != to_key:
                prereq_edges.add(f"{from_key}->{to_key}")
                to_node = node_details.get(to_key)
                if to_node is not None:
                    prereq_name = p_name
                    if prereq_name and prereq_name not in to_node["prerequisites"]:
                        to_node["prerequisites"].append(prereq_name)

    prereq_targets = {edge.split("->", 1)[1] for edge in prereq_edges}
    expected_nodes = [
        node_details[key]
        for key in sorted(unique_nodes)
    ]
    expected_edges = [
        {
            "from_key": edge.split("->", 1)[0],
            "to_key": edge.split("->", 1)[1],
            "relationship_type": "prerequisite_of",
        }
        for edge in sorted(prereq_edges)
    ]
    return {
        "all_nodes": len(unique_nodes),
        "all_edges": len(prereq_edges),
        "difficulty_distribution": difficulty_distribution,
        "prerequisites": {
            "total_prerequisite_edges": len(prereq_edges),
            "concepts_with_prerequisites": len(prereq_targets),
        },
        "nodes": expected_nodes,
        "edges": expected_edges,
    }

