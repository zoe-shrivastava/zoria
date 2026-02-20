"""Service for generating personalized study guides."""

import logging
import re
import uuid
import json
from typing import Dict, Any, Optional, List

from services.llm_service import LLMService
from database.repositories.concept_repository import ConceptRepository
from core.database import Database
from core.child_context import get_child_context

logger = logging.getLogger(__name__)


def _normalize_study_guide_revision_latex(text: Optional[str]) -> Optional[str]:
    """Study guide body only: collapse over-escaped LaTeX (\\\\ -> \).
    Do not use for revision cards; use normalize_revision_card_latex() instead.
    Do not reuse for quiz; question_generation_service has its own normalizer."""
    if text is None or not isinstance(text, str):
        return text
    out = text
    while "\\\\" in out:
        out = out.replace("\\\\", "\\")
    return out


def _normalize_revision_card_latex_one(text: str) -> str:
    """One pass of LaTeX normalization. Used by normalize_revision_card_latex.
    Use B+name for replacements to avoid re.sub interpreting \\f as form feed (0x0c)."""
    if not text or not isinstance(text, str):
        return text or ""
    B = chr(92)  # single backslash; use lambdas so re.sub never sees \\f (form feed) in replacement
    def _r(s): return lambda m: s  # replacement that returns s literally
    out = text
    _tf = r"(\\[tf]|\\\\[tf])+\s*"
    out = re.sub(_tf + r"ext(?=\w)", _r(B + "text"), out)
    out = re.sub(_tf + r"imes", _r(B + "times"), out)
    out = re.sub(_tf + r"rac", _r(B + "frac"), out)
    out = re.sub(_tf + r"oxed", _r(B + "boxed"), out)
    out = re.sub(_tf + r"\\\\text", _r(B + "text"), out)
    out = re.sub(_tf + r"\\\\frac", _r(B + "frac"), out)
    out = re.sub(r"(\\[tf])+ext", _r(B + "text"), out)
    out = re.sub(r"(\\[tf])+imes", _r(B + "times"), out)
    out = re.sub(r"(\\[tf])+rac", _r(B + "frac"), out)
    out = re.sub(r"(\\[tf])+oxed", _r(B + "boxed"), out)
    out = re.sub(r"(\\[tf])+\\text", _r(B + "text"), out)
    out = re.sub(r"(\\[tf])+\\frac", _r(B + "frac"), out)
    _cc = r"[\x08\x09\x0c]+\s*"
    out = re.sub(_cc + r"oxed", _r(B + "boxed"), out)
    out = re.sub(_cc + r"ext", _r(B + "text"), out)
    out = re.sub(_cc + r"imes", _r(B + "times"), out)
    out = re.sub(_cc + r"rac", _r(B + "frac"), out)
    out = re.sub(_cc + r"\\text", _r(B + "text"), out)
    out = re.sub(_cc + r"\\frac", _r(B + "frac"), out)
    out = re.sub(r"[\x08\x09\x0c]+oxed", _r(B + "boxed"), out)
    out = re.sub(r"[\x08\x09\x0c]+ext", _r(B + "text"), out)
    out = re.sub(r"[\x08\x09\x0c]+imes", _r(B + "times"), out)
    out = re.sub(r"[\x08\x09\x0c]+rac", _r(B + "frac"), out)
    out = re.sub(r"[\x08\x09\x0c]+\\text", _r(B + "text"), out)
    out = re.sub(r"[\x08\x09\x0c]+\\frac", _r(B + "frac"), out)
    out = re.sub(r"\x0crac", _r(B + "frac"), out)
    out = re.sub(r"\x0cext", _r(B + "text"), out)
    out = re.sub(r"\x0cimes", _r(B + "times"), out)
    out = re.sub(r"\x0coxed", _r(B + "boxed"), out)
    def _backslash_cmd(m):
        g = m.group(1)
        if g == "rac": return B + "frac"
        if g == "ext": return B + "text"
        if g == "imes": return B + "times"
        if g == "oxed": return B + "boxed"
        return B + g
    out = re.sub(r"\x0c([a-z]+)", _backslash_cmd, out)
    out = re.sub(r"\x0c(?!\w)", "", out)
    out = re.sub(r"\x0c\\", lambda m: B, out)
    out = out.replace("\\textDelta", B + "Delta")
    out = out.replace("\\textdelta", B + "delta")
    out = re.sub(r"\\\[([\s\S]*?)\](?=\s*(\n|$))", B + r"[\1" + B + "]", out)
    while "\\\\" in out:
        out = out.replace("\\\\", B)  # B is single char, no re.sub
    out = re.sub(r"([^\\])rac\{", lambda m: m.group(1) + B + "frac{", out)
    out = re.sub(r"^rac\{", _r(B + "frac{"), out)
    out = re.sub(r"([^\\])ext\{", lambda m: m.group(1) + B + "text{", out)
    out = re.sub(r"^ext\{", _r(B + "text{"), out)
    out = re.sub(r"\$1\\text\{", _r("$" + B + "text{"), out)
    out = out.replace("\\frac\\frac", B + "frac")
    out = re.sub(r"\\f\\frac", _r(B + "frac"), out)
    out = re.sub(r"\\fracrac\{?", _r(B + "frac{"), out)
    out = re.sub(r"\\fracrac", _r(B + "frac"), out)
    out = re.sub(r"\$\\text\{", _r(B + "text{"), out)
    out = re.sub(r"(\\text\{[^}]*\})\s*\$", r"\1", out)
    return out


def normalize_revision_card_latex(text: str) -> str:
    """Single source of truth for revision-card LaTeX. Apply to card front/back when building or serving.
    Do not use on study guide body or quiz content. Frontend must NOT repair LaTeX—only split and render.
    Runs multiple passes until stable so ordering does not matter."""
    if not text or not isinstance(text, str):
        return text or ""
    prev, out = None, text
    while prev != out:
        prev, out = out, _normalize_revision_card_latex_one(out)
    return out


# Pipeline constants for stable, subject-accurate study guide generation
STUDY_GUIDE_GEN_TEMPERATURE = 0.2
STUDY_GUIDE_VALIDATION_TEMPERATURE = 0.1
STUDY_GUIDE_TOP_P = 0.8
STUDY_GUIDE_REPEAT_PENALTY = 1.1
STUDY_GUIDE_OUTLINE_MAX_TOKENS = 800
STUDY_GUIDE_SECTION_MAX_TOKENS = 1200
STUDY_GUIDE_VALIDATION_MAX_TOKENS = 18000  # Must fit full 8-section guide
STUDY_GUIDE_DOCUMENT_MAX_CHARS = 35000    # Max chars sent to validation/pedagogical (full guide)
REVISION_CARDS_MAX_TOKENS = 12000         # Enough for 10–20 cards with LaTeX (5–8 defs + 5–8 formulas + 3–5 procedural)
REVISION_CARDS_CONTENT_MAX_CHARS = 22000  # Max study guide chars in prompt so system+user+response fit in model context
NUM_SECTIONS = 8

# Section titles and one-line requirements for outline/section prompts
SECTION_HEADINGS = [
    "Section 1: Concept Foundation",
    "Section 2: Core Principles & Formulas",
    "Section 3: The Systematic Problem-Solving Protocol",
    "Section 4: Worked Examples (Increasing Complexity)",
    "Section 5: The Pitfall Audit (Addressing Student Errors)",
    "Section 6: Misconceptions Debunked",
    "Section 7: Practice Quest (Guided Practice)",
    "Section 8: Summary & Quick Reference Sheet",
]


class StudyGuideService:
    """Service for generating study guides for focus areas.
    
    Uses the Zoria master pipeline: input normalization -> outline -> section-by-section
    generation -> validation pass -> optional pedagogical pass.
    """

    def __init__(self, db: Database):
        """Initialize study guide service.

        Args:
            db: Database instance
        """
        self.db = db
        self.concept_repo = ConceptRepository(db)

        # Initialize LLM service with llama3.1
        self.llm_service = LLMService(
            model_name="llama3.1",
            enable_logging=True,
            context_source="study_guide_generation"
        )

    def _build_context_block(self, normalized: Dict[str, Any]) -> str:
        """Build the dynamic context block injected into the master system prompt."""
        return f"""
-------------------------------------------------
CONTEXT (Dynamically Injected)
-------------------------------------------------
Subject: {normalized.get('subject', '')}
Concept: {normalized.get('concept_name', '')}
Grade Level: {normalized.get('grade_level', '')}
Focus Area: {normalized.get('focus_area', '')}
Language: {normalized.get('output_language', 'English')}
Cultural Tone Block: {normalized.get('cultural_block', '')}
-------------------------------------------------
"""

    def _get_master_system_prompt(self, context_block: str, output_language: str) -> str:
        """Zoria master system prompt (subject-agnostic). Injected with context_block."""
        return f"""You are Zoria's Structured Educational Content Engine.

Your task is to generate ONE section of a structured study guide at a time (or only the outline when asked).

You must strictly follow structural, formatting, grade-level, and subject-accuracy rules.

{context_block}

-------------------------------------------------
GLOBAL RULES
-------------------------------------------------

1. Audience Calibration
- Content must match the stated Grade Level cognitive level.
- Do not introduce concepts typically taught 2+ grade levels above.
- Avoid university-level formalism unless Grade Level explicitly allows it.

2. Subject Accuracy Rule (Critical)
- All definitions must be correct for the stated Subject.
- Do NOT borrow definitions from other disciplines.
- Do NOT mix related terms incorrectly.
- Use standard curriculum-appropriate definitions.

3. Complexity Guardrail
- Use only tools appropriate for the grade level (e.g. no calculus unless grade allows; no advanced symbolic formalism in science; no graduate-level language in humanities).
- Keep explanations conceptually precise but age-appropriate.

4. Formatting Rules
- Use strict Markdown hierarchy (H1 > H2 > H3). Never skip heading levels.
- Bold terms only the first time defined.
- Use blockquotes only for "Mission" or strategic prompts.
- No extra sections. No renamed sections. No meta commentary.
- Output language: generate all text in **{output_language}** only.

5. Math & Symbol Rules
- Inline math: $...$
- Display math: $$...$$
- Never use code blocks for math. Use \\\\ for LaTeX backslashes in strings.
- Use \\text{{}} inside LaTeX for units if applicable.
- Recalculate all numerical examples before finalizing. Do not invent values.

6. Structural Discipline
- Generate ONLY the requested section (or outline when asked).
- Do not preview other sections. Do not summarize future sections. Do not add filler.

7. Analogy Rule (Section 1 only)
- Include exactly ONE relatable analogy. Include exactly ONE real-world "Why" explanation.
- Do not repeat the same reasoning elsewhere.

8. Error Handling Rule
- Use provided common_errors exactly as given. Expand them into specific, actionable corrections.
- If error is "No_Answer", provide blank-page strategy and partial-credit method.

9. Misconceptions Rule
Each must include: Misconception, Fact (subject-correct), Why (brief explanation).

10. Self-Verification Before Output
Silently check: Definitions correct for Subject? Examples grade-appropriate? Formulas correct? Headings correct? Section requirements followed exactly? If anything is incorrect, fix before finalizing.
"""

    def _normalize_study_guide_input(
        self,
        *,
        subject: str,
        concept_name: str,
        focus_area: str,
        grade_level: Optional[str],
        concept_info: Optional[Dict],
        common_errors: List[str],
        misconceptions: List[str],
        sample_questions: List[Dict],
        topic_from_test: Optional[str],
        topics_from_test: List[str],
        output_language: str,
        cultural_block: str,
    ) -> Dict[str, Any]:
        """Step 0: Validate and normalize all inputs before pipeline."""
        subject = (subject or "").strip()
        if not subject:
            raise ValueError("Study guide requires subject.")
        topic_or_subtopic = (topic_from_test or "").strip() if topic_from_test else None
        if not topic_or_subtopic and topics_from_test:
            topic_or_subtopic = next((str(t).strip() for t in topics_from_test if t and str(t).strip()), None)
        if not topic_or_subtopic:
            raise ValueError("Study guide requires topic_from_test or non-empty topics_from_test.")

        topics_list: List[str] = []
        if topics_from_test:
            topics_list.extend(t for t in topics_from_test if t and str(t).strip())
        if concept_name and concept_name not in topics_list:
            topics_list.insert(0, concept_name)
        if concept_info:
            kw = concept_info.get("keywords")
            if isinstance(kw, list) and kw:
                topics_list.extend(str(k).strip() for k in kw[:10] if k and str(k).strip())
            elif isinstance(kw, str) and kw.strip():
                topics_list.append(kw.strip())
        if not topics_list:
            topics_list = [concept_name]

        valid_errors = [
            e for e in (common_errors or [])
            if e and isinstance(e, str) and e.strip() and e.lower() not in ("none", "null", "")
        ]
        valid_misconceptions = [m for m in (misconceptions or []) if m and isinstance(m, str) and m.strip()]
        sample_questions = sample_questions or []
        if not isinstance(sample_questions, list):
            sample_questions = []

        grade_level = (grade_level or "").strip() or "Middle School"
        output_language = (output_language or "English").strip() or "English"

        concept_anchor = ""
        if concept_info:
            sm = concept_info.get("source_markdown", "")
            if isinstance(sm, str) and sm:
                concept_anchor = sm[:1200]

        return {
            "subject": subject,
            "concept_name": concept_name,
            "focus_area": focus_area,
            "grade_level": grade_level,
            "topic_or_subtopic": topic_or_subtopic,
            "topics_list": topics_list,
            "concept_info": concept_info,
            "concept_anchor": concept_anchor,
            "common_errors": valid_errors,
            "misconceptions": valid_misconceptions,
            "sample_questions": sample_questions[:5],
            "output_language": output_language,
            "cultural_block": cultural_block or "",
        }

    def _build_outline_prompt(self, normalized: Dict[str, Any]) -> str:
        """Prompt for Step 1: outline only (headings + bullet outline)."""
        parts = [
            "Generate ONLY the required Section 1–8 headings and a short bullet outline.",
            "No explanations. No examples. No filler.",
            "",
            f"Subject: {normalized.get('subject', '')}",
            f"Concept: {normalized.get('concept_name', '')}",
            f"Focus Area: {normalized.get('focus_area', '')}",
            f"Topics to cover: {', '.join(normalized.get('topics_list', [])[:12])}",
            "",
            "Required headings (use exactly these titles):",
        ]
        for h in SECTION_HEADINGS:
            parts.append(f"- {h}")
        parts.append("")
        parts.append("Output: list each section heading followed by 2–4 bullet points outlining what that section will cover. Nothing else.")
        return "\n".join(str(p) for p in parts)

    def _build_section_requirements_text(self) -> str:
        """Full section requirements text for inclusion in section prompts."""
        return """
## Section 1: Concept Foundation
- Start the document with a single H1 title (the concept or focus area name), then Section 1 content.
- Give a correct, subject-specific definition of the concept (and any core terms). Do not use definitions from another discipline.
- Define the concept using exactly ONE relatable analogy (e.g. explaining Inertia with a skateboard). Do NOT add a separate heading for the analogy—it belongs in Section 1.
- In the same section, explain the 'Why' in one place: How does this make the world work? (Real-world context). Do not repeat elsewhere.

## Section 2: Core Principles & Formulas
- Break down the theory into bite-sized principles. Use subject-correct definitions for every term and formula.
- Formulas: Provide the formula, then a bulleted list 'Legend' explaining every variable. Use display math ($$) for primary equations.

## Section 3: The Systematic Problem-Solving Protocol
- Create a numbered 'Universal Strategy' that applies to any problem in this concept. Include a 'Self-Question' step.

## Section 4: Worked Examples (Increasing Complexity)
- Minimum 3 examples: Entry-Level, Intermediate, Challenge/Multi-step. For each: Problem, 'The Logic', then Step-by-Step Solution. High-quality LaTeX for every step.

## Section 5: The Pitfall Audit (Addressing Student Errors)
- Directly address the specific errors provided in the context. For each: Label the mistake, explain the 'Logic Trap', provide the 'Correction'. If No_Answer errors: provide First-Step Strategy and partial-credit method.

## Section 6: Misconceptions Debunked
- For each item: **Misconception:** (wrong belief), **Fact:** (correct statement), **Why:** (brief explanation). Every Fact must be correct for the stated Subject and topic.

## Section 7: Practice Quest (Guided Practice)
- Provide 3–5 problems. Do not give full solution; provide Checkpoints (e.g. 'After Step 1, your value for X should be ...').

## Section 8: Summary & Quick Reference Sheet
- A Markdown table of all Formulas, Units, and Key Rules. A 'One-Minute Review' bulleted list of vital takeaways.
"""

    def _build_section_prompt(
        self,
        normalized: Dict[str, Any],
        section_number: int,
        outline: str,
        previous_sections: str,
    ) -> str:
        """Build user prompt for generating a single section (Step 2)."""
        if section_number < 1 or section_number > NUM_SECTIONS:
            raise ValueError(f"section_number must be 1..{NUM_SECTIONS}")
        heading = SECTION_HEADINGS[section_number - 1]
        parts = [
            f"Generate Section {section_number} only: **{heading}**.",
            "Follow the required structure for this section exactly. Do not generate any other section.",
            "",
            "--- Outline for this guide (follow it) ---",
            outline.strip(),
            "--- End outline ---",
            "",
        ]
        if previous_sections:
            parts.append("--- Previously generated sections (for continuity only; do not repeat) ---")
            parts.append(previous_sections[:3000])
            parts.append("--- End previous ---")
            parts.append("")

        parts.extend([
            f"Subject: {normalized.get('subject', '')}",
            f"Concept: {normalized.get('concept_name', '')}",
            f"Focus Area: {normalized.get('focus_area', '')}",
            f"Grade Level: {normalized.get('grade_level', '')}",
            f"Topics: {', '.join(normalized.get('topics_list', [])[:12])}",
            "",
        ])
        if normalized.get("concept_anchor"):
            parts.extend([
                "--- Concept information (from learning material) ---",
                normalized["concept_anchor"],
                "",
            ])
        if section_number == 5 and normalized.get("common_errors"):
            parts.extend([
                "--- Common errors to address in this section ---",
                *[f"- {e}" for e in normalized["common_errors"]],
                "",
            ])
        if section_number == 6 and normalized.get("misconceptions"):
            parts.extend([
                "--- Misconceptions to debunk (use in Section 6) ---",
                *[f"- {m}" for m in normalized["misconceptions"]],
                "",
            ])
        if section_number == 4 and normalized.get("sample_questions"):
            parts.append("--- Sample problem questions (use to tailor examples) ---")
            for i, q in enumerate(normalized["sample_questions"][:3], 1):
                text = (q.get("text") or "")[:200] if isinstance(q.get("text"), str) else ""
                parts.append(f"{i}. {text}")
            parts.append("")

        parts.append("--- Section requirements (for this section only) ---")
        parts.append(self._build_section_requirements_text())
        return "\n".join(str(p) for p in parts)

    async def _generate_outline(self, normalized: Dict[str, Any]) -> str:
        """Step 1: Generate outline only."""
        context_block = self._build_context_block(normalized)
        system_prompt = self._get_master_system_prompt(context_block, normalized["output_language"])
        user_prompt = self._build_outline_prompt(normalized)
        response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=STUDY_GUIDE_GEN_TEMPERATURE,
            max_tokens=STUDY_GUIDE_OUTLINE_MAX_TOKENS,
            top_p=STUDY_GUIDE_TOP_P,
            repeat_penalty=STUDY_GUIDE_REPEAT_PENALTY,
        )
        text = (response.get("text") or response.get("content") or "").strip()
        if not text or len(text) < 20:
            raise ValueError("LLM returned insufficient outline.")
        return text

    async def _generate_section(
        self,
        normalized: Dict[str, Any],
        section_number: int,
        outline: str,
        previous_sections: str,
    ) -> str:
        """Step 2: Generate one section only."""
        context_block = self._build_context_block(normalized)
        system_prompt = self._get_master_system_prompt(context_block, normalized["output_language"])
        user_prompt = self._build_section_prompt(normalized, section_number, outline, previous_sections)
        response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=STUDY_GUIDE_GEN_TEMPERATURE,
            max_tokens=STUDY_GUIDE_SECTION_MAX_TOKENS,
            top_p=STUDY_GUIDE_TOP_P,
            repeat_penalty=STUDY_GUIDE_REPEAT_PENALTY,
        )
        text = (response.get("text") or response.get("content") or "").strip()
        if not text or len(text) < 30:
            logger.warning(f"Section {section_number} returned short content ({len(text) if text else 0} chars)")
        return text or f"\n## {SECTION_HEADINGS[section_number - 1]}\n\n(Content unavailable.)\n"

    def _document_has_all_sections(self, text: str) -> bool:
        """Return True if text contains at least 6 of the 8 section headings (allows minor rephrasing)."""
        if not text:
            return False
        count = sum(1 for h in SECTION_HEADINGS if h in text or h.replace(" & ", " and ") in text)
        return count >= 6

    async def _validate_guide_content(self, document: str, normalized: Dict[str, Any]) -> str:
        """Step 3: Subject and structure validation pass. Fix only if needed."""
        context_block = self._build_context_block(normalized)
        doc_len = min(len(document), STUDY_GUIDE_DOCUMENT_MAX_CHARS)
        system_prompt = (
            "You are a fact and structure checker for educational content. "
            "Verify: (1) All definitions are correct for the stated Subject. "
            "(2) No cross-discipline mixing. (3) Grade-level appropriate depth. "
            "(4) No advanced-level drift. (5) All math/examples correct. (6) Section rules followed. "
            "Fix only errors. Do not change correct content. "
            "CRITICAL: Your reply must be the COMPLETE study guide—every section from start to end. "
            "Do NOT summarize, truncate, or return only one section. "
            "Your output length must be similar to the input (thousands of characters). Copy the full document and apply only minimal fixes."
        )
        doc_slice = document[:STUDY_GUIDE_DOCUMENT_MAX_CHARS]
        user_prompt = f"""
{context_block}

Check the study guide below and fix only definition, grade-level, or structural errors. Return the ENTIRE guide with fixes applied—do not shorten it.
Required: Your response must include all 8 sections and be at least {doc_len} characters. Do not stop after one section.

--- Document to verify (return this full document with only small fixes) ---

{doc_slice}

--- End document ---

Remember: Reply with the COMPLETE document above, with only necessary corrections. Do not truncate."""
        response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=STUDY_GUIDE_VALIDATION_TEMPERATURE,
            max_tokens=STUDY_GUIDE_VALIDATION_MAX_TOKENS,
        )
        text = (response.get("text") or response.get("content") or "").strip()
        if not text or len(text) < 100:
            return document
        # Safeguard: if model returned much less content or dropped sections, keep original
        if len(text) < 0.5 * len(document) or not self._document_has_all_sections(text):
            logger.warning(
                "Validation pass returned shortened or incomplete guide (len=%s, sections ok=%s); keeping original",
                len(text), self._document_has_all_sections(text),
            )
            return document
        return text

    async def _pedagogical_pass(self, document: str, normalized: Dict[str, Any]) -> str:
        """Step 4 (optional): Improve tone and clarity without changing structure."""
        context_block = self._build_context_block(normalized)
        doc_len = min(len(document), STUDY_GUIDE_DOCUMENT_MAX_CHARS)
        system_prompt = (
            "You are an educational editor. Improve tone (encouraging), clarity, and actionability. "
            "Do NOT change structure, headings, or section order. Do NOT add or remove sections. "
            "CRITICAL: Your reply must be the COMPLETE study guide—every section from start to end. "
            "Do NOT summarize or truncate. Your output length must be similar to the input. Return the full guide with only clarity/tone improvements."
        )
        doc_slice = document[:STUDY_GUIDE_DOCUMENT_MAX_CHARS]
        user_prompt = f"""
{context_block}

Improve the study guide below for tone and clarity only. Keep all sections and structure unchanged. Return the ENTIRE guide—do not shorten it.
Required: Your response must include all 8 sections and be at least {doc_len} characters. Do not stop after one section.

--- Document (return this full document with only tone/clarity edits) ---

{doc_slice}

--- End ---

Remember: Reply with the COMPLETE document above, with only minor tone/clarity improvements. Do not truncate."""
        response = await self.llm_service.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=STUDY_GUIDE_VALIDATION_TEMPERATURE,
            max_tokens=STUDY_GUIDE_VALIDATION_MAX_TOKENS,
        )
        text = (response.get("text") or response.get("content") or "").strip()
        if not text or len(text) < 100:
            return document
        # Safeguard: if model returned much less content or dropped sections, keep original
        if len(text) < 0.5 * len(document) or not self._document_has_all_sections(text):
            logger.warning(
                "Pedagogical pass returned shortened or incomplete guide (len=%s, sections ok=%s); keeping original",
                len(text), self._document_has_all_sections(text),
            )
            return document
        return text

    async def _generate_guide_content_pipeline(
        self,
        normalized: Dict[str, Any],
        run_validation_pass: bool = False,
        pedagogical_pass: bool = False,
    ) -> str:
        """Run Zoria pipeline: outline -> sections 1..8 -> optional validation -> optional pedagogical pass.
        Validation/pedagogical are off by default because many models truncate when asked to return the full document."""
        logger.info("Study guide pipeline: generating outline")
        outline = await self._generate_outline(normalized)
        logger.info("Study guide pipeline: outline received")

        sections: List[str] = []
        for i in range(1, NUM_SECTIONS + 1):
            logger.info(f"Study guide pipeline: generating section {i}/{NUM_SECTIONS}")
            previous = "\n\n".join(sections) if sections else ""
            section_text = await self._generate_section(normalized, i, outline, previous)
            sections.append(section_text)

        combined = "\n\n".join(sections)
        if run_validation_pass:
            logger.info(
                "Study guide pipeline: combined %s sections (%s chars), running validation pass",
                len(sections), len(combined),
            )
            combined = await self._validate_guide_content(combined, normalized)
        else:
            logger.info("Study guide pipeline: combined %s sections (%s chars), skipping validation pass", len(sections), len(combined))
        if pedagogical_pass:
            logger.info("Study guide pipeline: running pedagogical pass")
            combined = await self._pedagogical_pass(combined, normalized)
        return combined

    async def generate_study_guide(
        self,
        child_id: str,
        concept_name: str,
        focus_area: str,
        test_id: Optional[str] = None,
        grade_level: Optional[str] = None,
        subject: Optional[str] = None,
        common_errors: Optional[List[str]] = None,
        misconceptions: Optional[List[str]] = None,
        sample_questions: Optional[List[Dict]] = None,
        force_regenerate: bool = False,
        language: Optional[str] = None,
        topic_from_test: Optional[str] = None,
        topics_from_test: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Generate a personalized study guide for a focus area.
        
        Args:
            child_id: Child UUID
            concept_name: Name of the concept
            focus_area: Specific area of focus (e.g., "Arithmetic errors")
            test_id: Optional test ID that triggered this guide
            grade_level: Grade level of the student
            subject: Subject name
            common_errors: List of common errors made
            misconceptions: List of misconceptions
            sample_questions: Sample questions that were answered incorrectly
            language: Language for guide and cards (e.g. 'English', 'Hindi', 'Spanish'). None = English.
            topic_from_test: Primary topic from the test that triggered this focus area (overrides concept-based topic).
            topics_from_test: List of topics from test metadata (from tests that contributed to this focus area).
            
        Returns:
            Dictionary with study guide data
        """
        logger.info(f"generate_study_guide called: child_id={child_id}, concept={concept_name}, focus_area={focus_area}, force_regenerate={force_regenerate}, topic_from_test={topic_from_test}, topics_from_test={topics_from_test}")
        
        # Check if study guide already exists (unless forcing regeneration)
        if not force_regenerate:
            try:
                existing = await self.db.fetchrow(
                    """
                    SELECT id, content, key_points, practice_recommendations
                    FROM study_guides
                    WHERE child_id = $1 
                        AND concept_name = $2 
                        AND focus_area = $3
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """,
                    child_id, concept_name, focus_area
                )
                
                if existing:
                    logger.info(f"Using existing study guide for {concept_name} - {focus_area}, id={existing['id']}")
                    return {
                        'id': str(existing['id']),
                        'concept_name': concept_name,
                        'focus_area': focus_area,
                        'content': existing['content'],
                        'key_points': existing['key_points'] or [],
                        'practice_recommendations': existing['practice_recommendations'] or [],
                        'is_new': False
                    }
            except Exception as e:
                logger.warning(f"Error checking for existing study guide: {e}, will create new one")
        else:
            logger.info(f"Force regeneration requested, will update existing guide or create new one")
            # Check if guide exists - we'll update it instead of deleting
            # This preserves the same guide_id
        
        # Require subject and topic from test (no fallbacks)
        if not subject or not str(subject).strip():
            raise ValueError("Study guide requires subject. Test metadata must provide subject.")
        effective_topic = (topic_from_test or "").strip() if topic_from_test else None
        if not effective_topic and topics_from_test:
            effective_topic = next((str(t).strip() for t in topics_from_test if t and str(t).strip()), None)
        if not effective_topic:
            raise ValueError(
                "Study guide requires topic_from_test or non-empty topics_from_test. "
                "Tests must be created with subject+topics so metadata.topics is set."
            )
        
        # Get concept information if available
        concept_info = None
        concepts = await self.concept_repo.get_all_concepts()
        for concept in concepts:
            if concept['name'].lower() == concept_name.lower():
                concept_info = concept
                break
        
        # Load child context for cultural/context flexibility (language, tone, examples, etc.)
        child_ctx = await get_child_context(child_id=child_id, language_override=language)
        output_language = (child_ctx.get("language") or "English").strip() or "English"
        cultural_block = child_ctx.get("prompt_block") or ""

        # Step 0: Normalize inputs
        normalized = self._normalize_study_guide_input(
            subject=subject,
            concept_name=concept_name,
            focus_area=focus_area,
            grade_level=grade_level,
            concept_info=concept_info,
            common_errors=common_errors or [],
            misconceptions=misconceptions or [],
            sample_questions=sample_questions or [],
            topic_from_test=topic_from_test,
            topics_from_test=topics_from_test or [],
            output_language=output_language,
            cultural_block=cultural_block,
        )

        # Generate study guide via Zoria pipeline (outline -> sections 1..8; validation/pedagogical skipped to avoid model truncation)
        try:
            logger.info(f"Calling study guide pipeline for {concept_name}")
            content = await self._generate_guide_content_pipeline(
                normalized,
                run_validation_pass=False,
                pedagogical_pass=False,
            )
            content = _normalize_study_guide_revision_latex(content) or content

            if not content or len(content.strip()) < 50:
                raise ValueError(f"Pipeline returned insufficient content: {len(content) if content else 0} characters")

            logger.info(f"Pipeline content length: {len(content)} characters")
            
            # Use empty arrays - the markdown content already contains all information
            # No need for intermediate JSON extraction since markdown is the source of truth
            structured_data = {
                'key_points': [],
                'practice_recommendations': [],
                'related_concepts': []
            }
            
            # Topic and subject already validated above (no fallbacks)
            logger.info(f"Generating revision cards for {concept_name} (subject={subject}, topic={effective_topic})")
            revision_cards = await self._generate_revision_cards(
                content, concept_name, language=output_language,
                subject=subject, topic=effective_topic
            )
            logger.info(f"Generated {len(revision_cards)} revision cards")
            
            # Save study guide to database
            logger.info("Saving study guide to database")
            valid_common_errors = normalized.get("common_errors", [])
            logger.info(f"Saving {len(valid_common_errors)} valid common errors")
            
            # When force_regenerate is True, check for existing guide to update
            replace_existing = False
            if force_regenerate:
                existing = await self.db.fetchrow(
                    """
                    SELECT id FROM study_guides
                    WHERE child_id = $1 
                        AND concept_name = $2 
                        AND focus_area = $3
                    ORDER BY generated_at DESC
                    LIMIT 1
                    """,
                    child_id, concept_name, focus_area
                )
                if existing:
                    replace_existing = True
                    logger.info(f"Found existing guide {existing['id']}, will update it instead of creating new one")
                else:
                    # No existing guide with same focus_area, delete old guides for this concept
                    try:
                        deleted = await self.db.execute(
                            """
                            DELETE FROM study_guides
                            WHERE child_id = $1 
                                AND concept_name = $2
                            """,
                            child_id, concept_name
                        )
                        logger.info(f"Deleted {deleted} old study guide(s) for {concept_name}")
                    except Exception as e:
                        logger.warning(f"Error deleting old study guides: {e}")
            
            guide_id = await self._save_study_guide(
                child_id=child_id,
                concept_name=concept_name,
                focus_area=focus_area,
                content=content,
                grade_level=grade_level,
                subject=subject,
                key_points=structured_data.get('key_points', []),
                practice_recommendations=structured_data.get('practice_recommendations', []),
                common_errors=normalized.get("common_errors", []),
                related_concepts=structured_data.get('related_concepts', []),
                test_id=test_id,
                replace_existing=replace_existing,
                revision_cards=revision_cards
            )
            
            logger.info(f"Study guide saved successfully with ID: {guide_id}")
            
            return {
                'id': guide_id,
                'concept_name': concept_name,
                'focus_area': focus_area,
                'content': content,
                'key_points': structured_data.get('key_points', []),
                'practice_recommendations': structured_data.get('practice_recommendations', []),
                'common_errors': normalized.get("common_errors", []),
                'related_concepts': structured_data.get('related_concepts', []),
                'is_new': True
            }
            
        except Exception as e:
            logger.error(f"Error generating study guide for {concept_name}: {e}", exc_info=True)
            raise
    
    def _build_study_guide_prompt(
        self,
        concept_name: str,
        focus_area: str,
        grade_level: Optional[str],
        subject: Optional[str],
        concept_info: Optional[Dict],
        common_errors: List[str],
        misconceptions: List[str],
        sample_questions: List[Dict],
        topic_from_test: Optional[str] = None,
        topics_from_test: Optional[List[str]] = None,
    ) -> str:
        """Build prompt for study guide generation. Requires subject and topic from test (no fallbacks)."""
        if not subject or not str(subject).strip():
            raise ValueError("Study guide prompt requires subject.")
        topic_or_subtopic = (topic_from_test or "").strip() if topic_from_test else None
        if not topic_or_subtopic and topics_from_test:
            topic_or_subtopic = next((str(t).strip() for t in topics_from_test if t and str(t).strip()), None)
        if not topic_or_subtopic:
            raise ValueError("Study guide prompt requires topic_from_test or non-empty topics_from_test.")

        # Build topics list: from test, then concept name; optional concept_info keywords
        topics_list = []
        if topics_from_test:
            topics_list.extend(t for t in topics_from_test if t and str(t).strip())
        if concept_name and concept_name not in topics_list:
            topics_list.insert(0, concept_name)
        if concept_info:
            kw = concept_info.get('keywords')
            if isinstance(kw, list) and kw:
                topics_list.extend(str(k).strip() for k in kw[:10] if k and str(k).strip())
            elif isinstance(kw, str) and kw.strip():
                topics_list.append(kw.strip())
        if not topics_list:
            topics_list = [concept_name]

        prompt_parts = [
            "=" * 60,
            "SUBJECT & TOPICS (use this scope for the entire guide)",
            "=" * 60,
            f"Subject: {subject}",
            f"Primary concept: {concept_name}",
            f"Topic / Subtopic (from test and incorrect answers): {topic_or_subtopic}",
            f"Topics to cover: {', '.join(topics_list[:12])}",
            "",
            "DEFINITIONS RULE: Every definition in this guide (especially in Section 1 and Section 2) MUST be correct for the stated Subject. Use standard, curriculum-appropriate definitions for that discipline (e.g. in Physics: speed = scalar magnitude of rate of change of distance; velocity = vector with magnitude and direction; in Mathematics: use precise mathematical definitions). Do NOT swap or mix definitions between related terms (e.g. speed vs velocity, force vs pressure). If Concept Information is provided below, align the core concept definition with it.",
            "",
            "=" * 60,
            f"Create a comprehensive study guide for: {concept_name}",
            "",
            f"Focus Area: {focus_area}",
            ""
        ]
        
        if grade_level:
            prompt_parts.append(f"Grade Level: {grade_level}")
        if concept_info:
            source_markdown = concept_info.get('source_markdown', '')
            if source_markdown:
                prompt_parts.extend([
                    "",
                    "=" * 60,
                    "CONCEPT INFORMATION (from learning material — use for accurate definitions)",
                    "=" * 60,
                    f"Name: {concept_info.get('name', '')}",
                    f"Description: {source_markdown[:1200]}",
                    "",
                    "Use the above description to anchor the core concept definition in Section 1 and Section 2 so definitions match the subject and the learning material.",
                ])
        
        if common_errors:
            # Filter out None, empty, or invalid error entries
            valid_errors = [e for e in common_errors if e and isinstance(e, str) and e.strip() and e.lower() not in ['none', 'null', '']]
            if valid_errors:
                prompt_parts.extend([
                    "",
                    "=" * 60,
                    "COMMON ERRORS MADE (with detailed explanations from student's incorrect/partially correct answers):",
                    "=" * 60,
                    "",
                    "CRITICAL: Each error below includes detailed feedback from actual student answers.",
                    "You MUST use these detailed explanations to create specific, actionable guidance.",
                    "Do NOT use generic error descriptions - use the actual detailed feedback provided.",
                    ""
                ])
                for i, error in enumerate(valid_errors, 1):
                    prompt_parts.append(f"{i}. {error}")
                prompt_parts.extend([
                    "",
                    "IMPORTANT INSTRUCTIONS FOR SECTION 5 (Common Errors & How to Fix Them):",
                    "",
                    "For EACH error listed above:",
                    "1. **Use the detailed explanation provided** - The explanation after the colon (:) contains",
                    "   specific feedback from the student's actual incorrect or partially correct answers.",
                    "   This is the MOST IMPORTANT information - use it to understand exactly what went wrong.",
                    "",
                    "2. **Expand on the detailed explanation**:",
                    "   - Explain what the mistake looks like in practice (use the detailed feedback as context)",
                    "   - Explain WHY students make this specific mistake (based on the detailed feedback)",
                    "   - Show the CORRECT approach or solution (contrast with what the student did wrong)",
                    "   - Provide specific examples showing the wrong way (from the detailed feedback) vs. the right way",
                    "   - Give concrete strategies to avoid repeating this exact error",
                    "",
                    "3. **If the error type is 'No_Answer'**:",
                    "   - Explain the importance of attempting all questions",
                    "   - Show how partial credit can be earned by showing work",
                    "   - Provide strategies for approaching questions when unsure",
                    "",
                    "4. **If detailed explanation is missing or generic**:",
                    "   - Still provide helpful guidance based on the error type",
                    "   - But emphasize that the student should review their specific answers",
                    "",
                    "REMEMBER: The detailed explanations are from REAL student answers. Use them to create",
                    "personalized, specific guidance that directly addresses what the student actually did wrong."
                ])
        
        if misconceptions:
            prompt_parts.extend([
                "",
                "Misconceptions Identified (use these in Section 6; ensure every Fact is correct for",
                f"Subject: {subject} and Topic: {topic_or_subtopic or concept_name}):",
            ])
            for i, misc in enumerate(misconceptions, 1):
                prompt_parts.append(f"{i}. {misc}")
        
        if sample_questions:
            def _num(x, default=0.0):
                if x is None:
                    return default
                try:
                    return float(x)
                except (TypeError, ValueError):
                    return default
            prompt_parts.extend([
                "",
                "=" * 60,
                "PROBLEM QUESTIONS (incorrect or partially correct with answer analysis):",
                "=" * 60,
                "",
                "Use these to tailor the Pitfall Audit and examples. For each: question, student answer, expected answer, score, and feedback.",
                ""
            ])
            for i, q in enumerate(sample_questions[:3], 1):
                q_text = (q.get('text') or '')[:300] if isinstance(q.get('text'), str) else str(q.get('text', ''))[:300]
                student_answer = q.get('answer') or '(no answer)'
                if isinstance(student_answer, str) and len(student_answer) > 200:
                    student_answer = student_answer[:200] + '...'
                expected_answer = q.get('expected_answer') or '(not provided)'
                if isinstance(expected_answer, str) and len(expected_answer) > 200:
                    expected_answer = expected_answer[:200] + '...'
                score_str = f"{_num(q.get('score'), 0):.2f}/{_num(q.get('max_score'), 1):.2f}"
                if q.get('detailed_feedback'):
                    feedback = (q.get('detailed_feedback') or '')[:400]
                    if len((q.get('detailed_feedback') or '')) > 400:
                        feedback += '...'
                else:
                    feedback = '(no detailed feedback)'
                prompt_parts.append(
                    f"{i}. Question: {q_text}\n"
                    f"   Student answer: {student_answer}\n"
                    f"   Expected answer: {expected_answer}\n"
                    f"   Score: {score_str}\n"
                    f"   Answer analysis: {feedback}"
                )
        
        prompt_parts.extend([
    "",
    "## CRITICAL REQUIREMENTS FOR THIS STUDY GUIDE",
    "This guide must be the 'Definitive Masterclass' for the student. It must take them from ",
    "confusion to total confidence using clear, structured pedagogy.",
    "",
    "### MARKDOWN & LATEX FORMATTING RULES:",
    "- Use strict H1 > H2 > H3 hierarchy. Never skip a heading level.",
    "- Use **bolding** for terms the first time they are defined.",
    "- For math: Use inline $formula$ for variables and equations within sentences.",
    "- For math: Use $$formula$$ on a new line for core laws and final steps in examples.",
    "- Use `\\text{...}` inside LaTeX for units (e.g., $10 \\text{ m/s}^2$).",
    "- Use standard Markdown tables for comparisons and summaries.",
    "",
    "### REQUIRED CONTENT STRUCTURE:",
    "",
    "## Section 1: Concept Foundation",
    "- Give a correct, subject-specific definition of the concept (and any core terms) as used in the stated Subject. Do not use definitions from another discipline or mix up related terms.",
    "- Define the concept using exactly ONE relatable middle-school analogy (e.g., explaining 'Inertia' using a skateboard). Do NOT add a separate heading or block called 'Zoria Analogy'—the analogy is part of Section 1.",
    "- In the same section, explain the 'Why' in one place: How does this make the world work? (Real-world context). Do not repeat the same 'Why' elsewhere.",
    "",
    "## Section 2: Core Principles & Formulas",
    "- Break down the theory into 'Bite-Sized' principles. Use subject-correct definitions for every term and formula (e.g. for Physics: correct units, vector vs scalar; for Mathematics: precise notation and domain).",
    "- Formulas: Provide the formula, then a bulleted list 'Legend' explaining every variable.",
    "- Use display math ($$) for the primary equations so they stand out visually.",
    "",
    "## Section 3: The Systematic Problem-Solving Protocol",
    "- Create a numbered 'Universal Strategy' that applies to any problem in this concept.",
    "- Include a 'Self-Question' step (e.g., 'Ask yourself: What am I trying to find?').",
    "",
    "## Section 4: Worked Examples (Increasing Complexity)",
    "- Minimum 3 examples: 1. Entry-Level, 2. Intermediate, 3. Challenge/Multi-step.",
    "- For each: State the Problem, 'The Logic' (thinking process), then the 'Step-by-Step Solution'.",
    "- High-quality LaTeX rendering for every calculation step is mandatory.",
    "",
    "## Section 5: The Pitfall Audit (Addressing Student Errors)",
    "- CRITICAL: Directly address the specific errors provided in the context.",
    "- For each error: Label the mistake clearly, explain the 'Logic Trap' (why it's tempting to do it wrong), ",
    "  and provide the 'Correction' using a side-by-side comparison or table.",
    "- If the student has 'No_Answer' errors, provide a 'First-Step Strategy' to overcome blank-page anxiety.",
    "",
    "## Section 6: Misconceptions Debunked",
    "- Contrast 'Common Sense' (which is often wrong in science) with 'Scientific Fact'.",
    "- CRITICAL: Every 'Fact' must be scientifically correct for this subject and topic. Do not swap or mix",
    "  definitions between related terms (e.g. keep each concept's definition accurate; do not assign one",
    "  term's meaning to another). Verify the Fact contradicts the misconception and is correct.",
    "- For each item use: **Misconception:** (wrong belief), **Fact:** (correct statement), **Why:** (brief explanation).",
    "- Explain the 'Why' behind the correct understanding.",
    "",
    "## Section 7: Practice Quest (Guided Practice)",
    "- Provide 3-5 problems. Do not provide the full solution, but provide 'Checkpoints' ",
    "  (e.g., 'After Step 1, your value for Velocity should be $5 \\text{ m/s}$').",
    "",
    "## Section 8: Summary & Quick Reference Sheet",
    "- A final Markdown table containing all Formulas, Units, and Key Rules.",
    "- A 'One-Minute Review' bulleted list of the most vital takeaways.",
    "",
    "### TONE, STYLE, AND QUALITY:",
    "- Tone: Academic yet conversational. Avoid 'dry' textbook language.",
    "- Clarity: Use short sentences. Use bullet points heavily for scannability.",
    "- Depth: Aim for 1500+ words. Elaborate on the 'How' and 'Why' rather than just stating facts.",
    "- No Meta-Talk: Start immediately with the H1 title. Do not say 'Here is your guide'.",
    "",
    "=" * 60
])
        
        return "\n".join(prompt_parts)
    
    async def _generate_revision_cards(
        self,
        content: str,
        concept_name: str,
        language: Optional[str] = None,
        subject: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Generate revision cards from study guide content using LLM.
        
        Args:
            content: The study guide markdown content
            concept_name: Name of the concept
            language: Language for card text (e.g. 'English', 'Hindi'). None = English.
            subject: Subject name (e.g. Physics, Biology) for scoping cards.
            topic: Topic or subtopic name for scoping cards.
            
        Returns:
            List of revision card objects with 'front' and 'back' keys
        """
        output_lang = (language or "English").strip() or "English"
        scope_line = ""
        if subject or topic:
            scope_parts = []
            if subject:
                scope_parts.append(f"Subject: {subject}")
            if topic:
                scope_parts.append(f"Topic: {topic}")
            scope_line = "\n".join([f"- {p}" for p in scope_parts]) + "\n\n"

        # Truncate content so system + user prompt + response fit in model context; cut at newline to avoid mid-sentence
        content_for_cards = content
        if len(content) > REVISION_CARDS_CONTENT_MAX_CHARS:
            cap = REVISION_CARDS_CONTENT_MAX_CHARS
            cut = content[:cap]
            last_nl = cut.rfind("\n")
            if last_nl > cap // 2:
                content_for_cards = cut[: last_nl + 1].rstrip()
            else:
                content_for_cards = cut.rstrip()
            content_for_cards += "\n\n[Study guide truncated for length; extract cards from the sections above.]"
            logger.info(
                "Revision cards: truncated study guide from %s to %s chars so prompt fits context",
                len(content), len(content_for_cards),
            )
        prompt = f"""
Extract revision cards from this study guide. Write ALL card "front" and "back" text in **{output_lang}** only. Keep LaTeX and math unchanged.

**Context (use this scope for definitions and formulas):**
Concept: {concept_name}
{scope_line}
**Study guide content:**

{content_for_cards}

### TASK: Structural Content Extraction
Review the provided text and generate MULTIPLE cards (do not stop after one card):
1. **5-8 Definitions**: Focus on fundamental terms found in Sections 1 and 2.
2. **5-8 Formulas**: Extract core equations. Use LaTeX.
3. **3-5 Procedural Examples**: Extract full problems and all steps from Sections 4 or 7.

You MUST output at least 10 cards total (e.g. 5 definitions + 3 formulas + 2 procedural minimum). Aim for 13–20 cards when the guide has enough content.

### OUTPUT RULES:
- If a problem in the text has a calculation error or uses an incorrect formula for the given variables, correct it in the card output.
- Every card must be self-contained (no "as seen in example 1" references).
- Use actual newlines (\n) to separate steps, NOT escaped backslashes.
- Remove any [LaTeX] markers - just include the actual LaTeX formulas.
- CRITICAL: For sample problems, include the COMPLETE problem statement in the "front" field - do NOT truncate with "..." or ellipsis. Include all given values and what is being asked.
- CRITICAL: Return a JSON ARRAY of cards, starting with [ and ending with ]. Do NOT return a single object. Output the COMPLETE array of all cards; do not truncate the list.

### LaTeX RULES (cards are rendered with KaTeX):
- In JSON string values use DOUBLE backslash before every LaTeX command: write \\\\frac, \\\\text, \\\\vec, \\\\Delta (so after JSON parsing the card gets one backslash: \\frac, \\text, etc.). A single backslash in JSON (e.g. \\f) becomes a control character and breaks the formula.
- KaTeX only supports \\Delta and \\delta for Greek letters; do NOT use \\textDelta or \\textdelta (they will not render).
- For units inside math use \\\\text{{...}}: e.g. $10 \\\\text{{ m/s}}$ or $v = 5 \\\\text{{ m/s}}$.
- Close every math block: each $ with $, each $$ with $$, and each \\\\[ with \\\\].
- Inline math: wrap every formula in $...$ (e.g. $v_f = v_i + (a) \\cdot t$). Display math: $$...$$ or \\\\[...\\\\]. Do NOT leave formulas as plain text like v_f = v_i (underscores break in the UI).

### OUTPUT JSON EXAMPLE:
[
  {{
    "front": "What is the definition of a Variable?",
    "back": "A variable represents an unknown value or quantity in a mathematical expression or equation."
  }},
  {{
    "front": "Sample Problem: [Insert Full Question from Source Text here, e.g., Solve for x: 3x + 4 = 10]",
    "back": "Step 1: [First logical step, e.g., Subtract 4 from both sides]\\\\nStep 2: [Second logical step, e.g., Divide by 3 to isolate x]\\\\n\\\\nFinal Answer: [Result, e.g., x = 2]"
  }}
]
"""

        scope_instruction = ""
        if subject or topic:
            parts = [f"Concept: {concept_name}"]
            if subject:
                parts.append(f"Subject: {subject}")
            if topic:
                parts.append(f"Topic: {topic}")
            scope_instruction = f"\n\n## 0b. SCOPE\nCards must stay within this scope: {' | '.join(parts)}. Definitions and formulas should match the subject and topic.\n"
        system_prompt = f"""
# Role: Expert Educational Content Extractor (Llama 3.1)
You are a specialist in transforming long-form Study Guides into high-utility active recall Revision Cards.
{scope_instruction}
## 0. OUTPUT LANGUAGE
Generate ALL "front" and "back" text for every card in **{output_lang}** only. Keep LaTeX and math notation unchanged. If the language is a code (en, hi, es), use the full language name (English, Hindi, Spanish).

## 1. EXTRACTION & AUDIT PROTOCOL
- **Definitions**: Identify core terms. Format: Front: "What is [Term]?"; Back: Scientific definition.
- **Formulas**: Extract LaTeX formulas. You MUST provide a "Variable Legend" defining every symbol used.
- **Step-by-Step Solutions**: 
    - Include the COMPLETE problem statement in the "front" field - do NOT truncate with "..."
    - Include every numbered step from the text in the "back" field.
    - **Logic Guardrail**: If the source text suggests a formula that does not match the variables given (e.g., using F=ma when only velocity/time are provided), you must correct the logic to use the mathematically sound formula.
- **Accuracy Check**: Ensure every opened LaTeX bracket `{{` or `$` or `\\[` is properly closed. Use double backslashes in JSON for LaTeX (e.g. `\\\\frac`, `\\\\text`) so formulas parse correctly.

## 2. FORMATTING & JSON SAFETY (CRITICAL)
- **JSON Structure**: Output a RAW JSON ARRAY only. 
  - **MUST start with `[` and end with `]`** - This is an array, not a single object.
  - **Do NOT return a single card object** - Always return an array of at least 10 cards (5–8 definitions + 5–8 formulas + 3–5 procedural). You have enough token budget to output all of them; do not stop after one or two cards.
  - Do NOT wrap the array in a "cards" key. 
  - Do NOT include markdown code blocks (```json).
- **LaTeX in JSON**: In JSON string values, backslashes must be escaped. Write `\\\\frac`, `\\\\text`, `\\\\vec`, `\\\\Delta` (double backslash) so that after JSON parsing the card text contains single backslashes (e.g. \\frac). Never use \\t, \\n, or \\f in the JSON string for formatting—they become control characters (tab, newline, form feed) and break formulas. Use literal spaces and actual newlines only where intended.
- **KaTeX compatibility**: Use \\Delta and \\delta for Greek letters (not \\textDelta or \\textdelta). Use \\text{{...}} for units inside math (e.g. \\text{{ m/s}}). Close every $ with $ and every \\[ with \\. Always wrap formulas in $...$ or $$...$$ (e.g. $v_f = v_i + a t$); never leave subscripted math as plain v_f or v_i (underscores break rendering).
- **Newlines**: Use actual newline characters `\\n` in the JSON string to separate steps in the "back" field.
- **Step Formatting**: For step-by-step solutions, use DOUBLE newlines between each numbered step (Step 1, Step 2, etc.) for clear visual separation.
- **Clean Output**: Remove any [LaTeX] markers or placeholder text - include only actual LaTeX formulas.

## 3. CONTENT DENSITY
- **Front**: Concise question or prompt (keep it readable, but no strict length limit).
- **Back**: Comprehensive and detailed - include all necessary information, formulas, steps, and explanations. No length limit - be thorough.
"""

        try:
            response = await self.llm_service.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=REVISION_CARDS_MAX_TOKENS,
            )
            
            logger.info(f"LLM response type for revision cards: {type(response)}")
            logger.debug(f"LLM response for revision cards (first 500 chars): {str(response)[:500]}")
            
            # Parse response
            cards = []
            if isinstance(response, dict):
                logger.debug(f"Response is dict with keys: {list(response.keys())}")
                if 'cards' in response:
                    cards = response['cards']
                    logger.debug(f"Found 'cards' key with {len(cards) if isinstance(cards, list) else 'non-list'} items")
                elif 'revision_cards' in response:
                    cards = response['revision_cards']
                    logger.debug(f"Found 'revision_cards' key with {len(cards) if isinstance(cards, list) else 'non-list'} items")
                elif 'front' in response and 'back' in response:
                    # LLM returned a single card object instead of an array - wrap it
                    logger.debug("LLM returned a single card object, wrapping in array")
                    cards = [response]
                else:
                    # Try to extract cards from any array field
                    for key, value in response.items():
                        if isinstance(value, list):
                            cards = value
                            logger.debug(f"Found array in key '{key}' with {len(cards)} items")
                            break
            elif isinstance(response, list):
                cards = response
                logger.debug(f"Response is list with {len(cards)} items")
            elif isinstance(response, str):
                import json
                try:
                    parsed = json.loads(response)
                    logger.debug(f"Parsed string response, type: {type(parsed)}")
                    if isinstance(parsed, list):
                        cards = parsed
                    elif isinstance(parsed, dict):
                        if 'cards' in parsed:
                            cards = parsed['cards']
                        elif 'front' in parsed and 'back' in parsed:
                            # Single card object - wrap it
                            logger.debug("Parsed string contains single card object, wrapping in array")
                            cards = [parsed]
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse revision cards JSON: {e}")
                    logger.warning(f"Response content (first 500 chars): {response[:500]}")
                    cards = []
            else:
                logger.warning(f"Unexpected response type: {type(response)}")
            
            logger.info(f"Extracted {len(cards)} cards from LLM response")
            
            # Validate and clean cards (LaTeX: single pipeline in normalize_revision_card_latex)
            valid_cards = []
            for idx, card in enumerate(cards):
                if isinstance(card, dict) and 'front' in card and 'back' in card:
                    front_raw = card.get('front', '')
                    back_raw = card.get('back', '')
                    front = front_raw if isinstance(front_raw, str) else str(front_raw)
                    back = back_raw if isinstance(back_raw, str) else str(back_raw)

                    front = normalize_revision_card_latex(front)
                    back = normalize_revision_card_latex(back)

                    # Replace literal \n strings with actual newlines (if they're escaped as \\n)
                    back = back.replace('\\n', '\n')
                    front = front.replace('\\n', '\n')
                    
                    # Remove [LaTeX] markers that LLM sometimes adds
                    back = re.sub(r'\[LaTeX\]', '', back, flags=re.IGNORECASE)
                    back = re.sub(r'\[latex\]', '', back, flags=re.IGNORECASE)
                    front = re.sub(r'\[LaTeX\]', '', front, flags=re.IGNORECASE)
                    front = re.sub(r'\[latex\]', '', front, flags=re.IGNORECASE)
                    
                    # Clean up multiple consecutive newlines (more than 2)
                    back = re.sub(r'\n{3,}', '\n\n', back)
                    front = re.sub(r'\n{3,}', '\n\n', front)
                    
                    # Strip whitespace
                    front = front.strip()
                    back = back.strip()
                    
                    if front and back:
                        valid_cards.append({
                            'front': front,
                            'back': back
                        })
                    else:
                        logger.debug(f"Card {idx} filtered out: front empty or back empty")
                else:
                    logger.debug(f"Card {idx} invalid: type={type(card)}, has_front={'front' in card if isinstance(card, dict) else False}, has_back={'back' in card if isinstance(card, dict) else False}")
            
            logger.info(f"Generated {len(valid_cards)} valid revision cards for {concept_name} (from {len(cards)} total cards)")
            if valid_cards:
                logger.debug(f"First card example: front='{valid_cards[0]['front'][:50]}...', back='{valid_cards[0]['back'][:50]}...'")
            return valid_cards
            
        except Exception as e:
            logger.warning(f"Failed to generate revision cards using LLM: {e}", exc_info=True)
            return []
    
    async def _save_study_guide(
        self,
        child_id: str,
        concept_name: str,
        focus_area: str,
        content: str,
        grade_level: Optional[str],
        subject: Optional[str],
        key_points: List[str],
        practice_recommendations: List[str],
        common_errors: List[str],
        related_concepts: List[str],
        test_id: Optional[str],
        replace_existing: bool = False,
        revision_cards: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """Save study guide to database.
        
        Args:
            replace_existing: If True, update existing guide instead of creating new one
        """
        # Check if guide already exists and we should replace it
        existing_id = None
        if replace_existing:
            existing = await self.db.fetchrow(
                """
                SELECT id FROM study_guides
                WHERE child_id = $1 
                    AND concept_name = $2 
                    AND focus_area = $3
                ORDER BY generated_at DESC
                LIMIT 1
                """,
                child_id, concept_name, focus_area
            )
            if existing:
                existing_id = str(existing['id'])
                logger.info(f"Found existing guide {existing_id}, will update instead of creating new one")
        
        guide_id = existing_id if existing_id else str(uuid.uuid4())
        
        try:
            logger.info(f"Saving study guide to database: concept={concept_name}, focus_area={focus_area}, replace_existing={replace_existing}")
            
            # Normalize all array parameters to ensure they are lists of strings
            def ensure_string_array(arr, param_name):
                if not isinstance(arr, list):
                    logger.warning(f"{param_name} is not a list, converting: {type(arr)}")
                    return []
                normalized = []
                for item in arr:
                    if isinstance(item, str):
                        normalized.append(item)
                    elif isinstance(item, dict):
                        # Extract text from dict
                        text = item.get('title') or item.get('text') or item.get('description') or item.get('point') or str(item)
                        normalized.append(str(text))
                        logger.warning(f"{param_name} contains dict, extracted: {text[:50]}")
                    else:
                        normalized.append(str(item))
                return normalized
            
            normalized_key_points = ensure_string_array(key_points, 'key_points')
            normalized_practice = ensure_string_array(practice_recommendations, 'practice_recommendations')
            normalized_errors = ensure_string_array(common_errors, 'common_errors')
            normalized_concepts = ensure_string_array(related_concepts, 'related_concepts')
            
            logger.info(f"Normalized arrays - key_points: {len(normalized_key_points)}, practice: {len(normalized_practice)}, errors: {len(normalized_errors)}, concepts: {len(normalized_concepts)}")
            
            # Prepare metadata with revision cards
            metadata = {}
            if revision_cards:
                metadata['revision_cards'] = revision_cards
                logger.info(f"Including {len(revision_cards)} revision cards in metadata")
            metadata_json = json.dumps(metadata) if metadata else None
            
            if existing_id:
                # Update existing guide
                await self.db.execute(
                    """
                    UPDATE study_guides 
                    SET content = $1,
                        key_points = $2,
                        practice_recommendations = $3,
                        common_errors = $4,
                        related_concepts = $5,
                        grade_level = $6,
                        subject = $7,
                        generated_from_test_id = $8,
                        metadata = $9,
                        generated_at = CURRENT_TIMESTAMP
                    WHERE id = $10
                    """,
                    content,
                    normalized_key_points,
                    normalized_practice,
                    normalized_errors,
                    normalized_concepts,
                    grade_level,
                    subject,
                    test_id,
                    metadata_json,
                    guide_id
                )
                logger.info(f"Updated existing study guide with ID: {guide_id}")
            else:
                # Insert new guide
                await self.db.execute(
                    """
                    INSERT INTO study_guides 
                    (id, child_id, concept_name, focus_area, grade_level, subject, content,
                     key_points, practice_recommendations, common_errors, related_concepts,
                     generated_from_test_id, metadata)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    """,
                    guide_id,
                    child_id,
                    concept_name,
                    focus_area,
                    grade_level,
                    subject,
                    content,
                    normalized_key_points,
                    normalized_practice,
                    normalized_errors,
                    normalized_concepts,
                    test_id,
                    metadata_json  # metadata with revision cards
                )
                logger.info(f"Created new study guide with ID: {guide_id}")
            logger.info(f"Study guide saved successfully with ID: {guide_id}")
        except Exception as e:
            logger.error(f"Failed to save study guide to database: {e}", exc_info=True)
            # Check if table exists
            try:
                table_check = await self.db.fetchrow(
                    "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'study_guides')"
                )
                if not table_check or not table_check['exists']:
                    logger.error("study_guides table does not exist! Please run migration 017_study_guides_table.sql")
                    raise Exception("study_guides table does not exist. Please run the database migration.")
            except Exception as check_error:
                logger.error(f"Error checking for study_guides table: {check_error}")
            raise
        
        return guide_id
    
    async def get_study_guide(
        self,
        guide_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get study guide by ID.
        
        Args:
            guide_id: Study guide UUID
            
        Returns:
            Study guide dictionary or None
        """
        guide = await self.db.fetchrow(
            """
            SELECT * FROM study_guides WHERE id = $1
            """,
            guide_id
        )
        
        if guide:
            guide_dict = dict(guide)
            # Parse metadata if it's a string
            if guide_dict.get('metadata'):
                if isinstance(guide_dict['metadata'], str):
                    try:
                        guide_dict['metadata'] = json.loads(guide_dict['metadata'])
                        logger.debug(f"Parsed metadata string, revision_cards present: {'revision_cards' in guide_dict['metadata']}")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse metadata JSON: {e}")
                        guide_dict['metadata'] = {}
                if isinstance(guide_dict.get('metadata'), dict) and 'revision_cards' in guide_dict['metadata']:
                    raw_cards = guide_dict['metadata']['revision_cards']
                    logger.info(f"Found {len(raw_cards)} revision cards in metadata; normalizing LaTeX for display")
                    normalized_cards = []
                    for c in raw_cards:
                        if isinstance(c, dict) and 'front' in c and 'back' in c:
                            normalized_cards.append({
                                'front': normalize_revision_card_latex(c.get('front') or ''),
                                'back': normalize_revision_card_latex(c.get('back') or ''),
                            })
                        else:
                            normalized_cards.append(dict(c) if isinstance(c, dict) else c)
                    guide_dict['metadata'] = {**guide_dict['metadata'], 'revision_cards': normalized_cards}
            else:
                logger.debug("No metadata found in guide")
            return guide_dict
        return None
    
    async def get_study_guides_for_child(
        self,
        child_id: str,
        concept_name: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get all study guides for a child.
        Returns only the most recent guide per subject/topic (one per concept_name).
        
        Args:
            child_id: Child UUID
            concept_name: Optional concept name filter
            
        Returns:
            List of study guide dictionaries (one per concept)
        """
        logger.info(f"Fetching study guides for child_id: {child_id}, concept_name: {concept_name}")
        
        # First check if table exists
        try:
            table_check = await self.db.fetchrow(
                "SELECT EXISTS (SELECT FROM information_schema.tables WHERE table_name = 'study_guides')"
            )
            if not table_check or not table_check['exists']:
                logger.error("study_guides table does not exist!")
                return []
        except Exception as e:
            logger.error(f"Error checking for study_guides table: {e}")
            return []
        
        try:
            # One guide per subject/topic: most recent per concept_name
            if concept_name:
                guides = await self.db.fetch(
                    """
                    SELECT DISTINCT ON (concept_name) *
                    FROM study_guides
                    WHERE child_id = $1 AND concept_name = $2
                    ORDER BY concept_name, generated_at DESC
                    """,
                    child_id, concept_name
                )
            else:
                guides = await self.db.fetch(
                    """
                    SELECT DISTINCT ON (concept_name) *
                    FROM study_guides
                    WHERE child_id = $1
                    ORDER BY concept_name, generated_at DESC
                    """,
                    child_id
                )
            
            logger.info(f"Found {len(guides)} study guides for child {child_id} (one per subject/topic)")
            # Parse metadata for each guide and normalize revision card LaTeX (same as get_study_guide)
            result = []
            for g in guides:
                guide_dict = dict(g)
                # Parse metadata if it's a string
                if guide_dict.get('metadata'):
                    if isinstance(guide_dict['metadata'], str):
                        try:
                            guide_dict['metadata'] = json.loads(guide_dict['metadata'])
                        except (json.JSONDecodeError, TypeError):
                            guide_dict['metadata'] = {}
                    if isinstance(guide_dict.get('metadata'), dict) and 'revision_cards' in guide_dict['metadata']:
                        raw_cards = guide_dict['metadata']['revision_cards']
                        normalized_cards = []
                        for c in raw_cards:
                            if isinstance(c, dict) and 'front' in c and 'back' in c:
                                normalized_cards.append({
                                    'front': normalize_revision_card_latex(c.get('front') or ''),
                                    'back': normalize_revision_card_latex(c.get('back') or ''),
                                })
                            else:
                                normalized_cards.append(dict(c) if isinstance(c, dict) else c)
                        guide_dict['metadata'] = {**guide_dict['metadata'], 'revision_cards': normalized_cards}
                result.append(guide_dict)
            return result
        except Exception as e:
            logger.error(f"Error fetching study guides: {e}", exc_info=True)
            return []
