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


def normalize_revision_card_latex(text: str) -> str:
    """Single pipeline for revision-card LaTeX only. Apply to card front/back when building or serving.
    Do not use on study guide body or quiz content.
    Steps: (1) control chars from JSON (\\b/\\t/\\f), (2) \\textDelta/\\textdelta,
    (3) unclosed \\[...], (4) collapse \\\\ -> \\, (5) rac{/ext{ lost backslash,
    (6) stray $1\\text, (7) \\frac/\\f/frac double-fix cleanup."""
    if not text or not isinstance(text, str):
        return text or ""
    out = text
    # 1) JSON escape damage: \boxed -> \b+oxed, \text -> \t+ext, \frac -> \f+rac
    out = re.sub(r"\x08oxed", r"\\boxed", out)
    out = re.sub(r"\x09ext", r"\\text", out)
    out = re.sub(r"\x0crac", r"\\frac", out)
    out = re.sub(r"\x0c([a-z]+)", r"\\\1", out)
    out = re.sub(r"\x0c(?!\w)", "", out)
    out = re.sub(r"\x0c\\", r"\\", out)
    # 2) KaTeX: \textDelta / \textdelta -> \Delta, \delta
    out = out.replace("\\textDelta", "\\Delta")
    out = out.replace("\\textdelta", "\\delta")
    # 3) Display math missing \]: \[...] at line/s end -> \[...\]
    out = re.sub(r"\\\[([\s\S]*?)\](?=\s*(\n|$))", r"\\[\1\\]", out)
    # 4) Over-escaped backslashes
    while "\\\\" in out:
        out = out.replace("\\\\", "\\")
    # 5) Lost backslash: rac{ -> \frac{, ext{ -> \text{
    out = re.sub(r"([^\\])rac\{", r"\1\\frac{", out)
    out = re.sub(r"^rac\{", r"\\frac{", out)
    out = re.sub(r"([^\\])ext\{", r"\1\\text{", out)
    out = re.sub(r"^ext\{", r"\\text{", out)
    # 6) Stray $1\text (e.g. from \b eating a char)
    out = re.sub(r"\$1\\text\{", r"$\\text{", out)
    # 7) Double-fix cleanup
    out = out.replace("\\frac\\frac", "\\frac")
    out = re.sub(r"\\f\\frac", "\\frac", out)
    out = re.sub(r"\\fracrac\{?", "\\frac{", out)
    out = re.sub(r"\\fracrac", "\\frac", out)
    return out


class StudyGuideService:
    """Service for generating study guides for focus areas."""
    
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
        
        # Build prompt for study guide generation
        prompt = self._build_study_guide_prompt(
            concept_name=concept_name,
            focus_area=focus_area,
            grade_level=grade_level,
            subject=subject,
            concept_info=concept_info,
            common_errors=common_errors or [],
            misconceptions=misconceptions or [],
            sample_questions=sample_questions or [],
            topic_from_test=topic_from_test,
            topics_from_test=topics_from_test or [],
        )
        
        system_prompt = f"""
        You are an expert educational tutor. Your task is to generate a DETAILED, COMPREHENSIVE study guide in Markdown. 
Because this is for the Zoria Learning System, you must use specific structural patterns that our frontend will transform into interactive "Knowledge Blocks."

## 0. OUTPUT LANGUAGE AND PREFERENCES
Generate the ENTIRE study guide in **{output_language}** only: all section titles, explanations, analogies, step-by-step content, examples, pitfall descriptions, cheat sheet text, and mastery check. Keep LaTeX and math notation unchanged. If the language is a code (e.g. en, hi, es), use the corresponding full language (English, Hindi, Spanish, etc.).
{f'''
## 0b. CULTURAL / CONTEXT PREFERENCES
{cultural_block}
''' if cultural_block else ''}

## 1. STRUCTURAL DIRECTIVES
- **Tone**: Professional, encouraging, and clear (Middle School level).
- **LaTeX**: Use double-backslashes for all math (e.g., `\\vec{{F}} = ma`). Write display math as $$...$$ and inline math as $...$ directly in the paragraph—do NOT wrap them in ```latex or ``` code blocks, or the UI will not render the math.
- **Formatting**: Use Bold for key terms and Blockquotes for "Missions."

## 2. ZORIA COMPONENT MAPPING
Please structure your Markdown using these exact section headers so the UI can style them:

### Concept Snapshot: [Topic Name]
- Provide a clear definition and why it matters. 
- Use a **"Zoria Analogy"** to explain the concept (e.g., "Imagine force like a push on a swing...").

### Your Quest Map (Step-by-Step)
- Use a numbered list to show the 1-2-3 approach to solving problems. 
- Include a "Why?" after each step.

### Zoria's Lab (Worked Examples)
- Start with a "Level 1: Basic" example.
- Move to a "Level 2: Complex" example.
- Include a "Variation" or "Edge Case" to challenge the student.

### Pitfall Patrol (Common Mistakes)
- Address the student's specific errors (e.g., "No Answer" or "Incorrect Formula").
- Explain the "Trap" and show the "Escape Route" (the correct way).

### The Cheat Sheet (Quick Reference)
- Provide a Markdown table of formulas, units, and constants.

### 🎯 Mastery Check
- List 3 signs that the student has mastered the concept.
"""
        
        # Generate study guide using LLM
        try:
            logger.info(f"Calling LLM to generate study guide for {concept_name}")
            response = await self.llm_service.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                max_tokens=4000,  # Increased significantly for comprehensive guides
                temperature=0.7
            )
            
            logger.info(f"LLM response received, type: {type(response)}")
            
            # Extract content from response (returns dict with 'text' key)
            if isinstance(response, dict):
                content = response.get('text', '') or response.get('content', '') or str(response)
            else:
                content = str(response)
            content = _normalize_study_guide_revision_latex(content) or content
            
            if not content or len(content.strip()) < 50:
                raise ValueError(f"LLM returned insufficient content: {len(content) if content else 0} characters")
            
            logger.info(f"Extracted content length: {len(content)} characters")
            
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
            # Filter out None, empty, or invalid common errors before saving
            valid_common_errors = []
            if common_errors:
                valid_common_errors = [e for e in common_errors if e and isinstance(e, str) and e.strip() and e.lower() not in ['none', 'null', '']]
            logger.info(f"Saving {len(valid_common_errors)} valid common errors (filtered from {len(common_errors) if common_errors else 0} total)")
            
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
                common_errors=valid_common_errors,
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
                'common_errors': valid_common_errors,
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
                    "Concept Information:",
                    f"Name: {concept_info.get('name', '')}",
                    f"Description: {source_markdown[:500]}",
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
    "- Define the concept using a relatable middle-school analogy (e.g., explaining 'Inertia' using a skateboard).",
    "- Explain the 'Why': How does this make the world work? (Real-world context).",
    "",
    "## Section 2: Core Principles & Formulas",
    "- Break down the theory into 'Bite-Sized' principles.",
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
        prompt = f"""
Extract revision cards from this study guide. Write ALL card "front" and "back" text in **{output_lang}** only. Keep LaTeX and math unchanged.

**Context (use this scope for definitions and formulas):**
Concept: {concept_name}
{scope_line}
**Study guide content:**

{content}

### TASK: Structural Content Extraction
Review the provided text and generate:
1. **5-8 Definitions**: Focus on fundamental terms found in Sections 1 and 2.
2. **5-8 Formulas**: Extract core equations. Use LaTeX.
3. **3-5 Procedural Examples**: Extract full problems and all steps from Sections 4 or 7.

### OUTPUT RULES:
- If a problem in the text has a calculation error or uses an incorrect formula for the given variables, correct it in the card output.
- Every card must be self-contained (no "as seen in example 1" references).
- Use actual newlines (\n) to separate steps, NOT escaped backslashes.
- Remove any [LaTeX] markers - just include the actual LaTeX formulas.
- CRITICAL: For sample problems, include the COMPLETE problem statement in the "front" field - do NOT truncate with "..." or ellipsis. Include all given values and what is being asked.
- CRITICAL: Return a JSON ARRAY of cards, starting with [ and ending with ]. Do NOT return a single object.

### LaTeX RULES (cards are rendered with KaTeX):
- In JSON string values use DOUBLE backslash before every LaTeX command: write \\\\frac, \\\\text, \\\\vec, \\\\Delta (so after JSON parsing the card gets one backslash: \\frac, \\text, etc.). A single backslash in JSON (e.g. \\f) becomes a control character and breaks the formula.
- KaTeX only supports \\Delta and \\delta for Greek letters; do NOT use \\textDelta or \\textdelta (they will not render).
- For units inside math use \\\\text{{...}}: e.g. $10 \\\\text{{ m/s}}$ or $v = 5 \\\\text{{ m/s}}$.
- Close every math block: each $ with $, each $$ with $$, and each \\\\[ with \\\\].
- Inline math: $...$. Display math: $$...$$ or \\\\[...\\\\].

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
  - **Do NOT return a single card object** - Always return an array, even if it has only one card.
  - Do NOT wrap the array in a "cards" key. 
  - Do NOT include markdown code blocks (```json).
- **LaTeX in JSON**: In JSON string values, backslashes must be escaped. Write `\\\\frac`, `\\\\text`, `\\\\vec`, `\\\\Delta` (double backslash) so that after JSON parsing the card text contains single backslashes (e.g. \\frac). Using a single backslash in JSON (e.g. \\f) can be interpreted as a control character and break the formula.
- **KaTeX compatibility**: Use \\Delta and \\delta for Greek letters (not \\textDelta or \\textdelta). Use \\text{{...}} for units inside math (e.g. \\text{{ m/s}}). Close every $ with $ and every \\[ with \\].
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
                max_tokens=4000  # Increased to allow longer, more detailed revision cards
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
                    cards = guide_dict['metadata']['revision_cards']
                    logger.info(f"Found {len(cards)} revision cards in metadata; normalizing LaTeX for display")
                    for c in cards:
                        if isinstance(c, dict) and 'front' in c and 'back' in c:
                            c['front'] = normalize_revision_card_latex(c.get('front') or '')
                            c['back'] = normalize_revision_card_latex(c.get('back') or '')
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
        Returns only the most recent guide for each concept/focus_area combination.
        
        Args:
            child_id: Child UUID
            concept_name: Optional concept name filter
            
        Returns:
            List of study guide dictionaries (deduplicated)
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
            # Get only the most recent guide for each concept/focus_area combination
            if concept_name:
                guides = await self.db.fetch(
                    """
                    SELECT DISTINCT ON (concept_name, focus_area) *
                    FROM study_guides
                    WHERE child_id = $1 AND concept_name = $2
                    ORDER BY concept_name, focus_area, generated_at DESC
                    """,
                    child_id, concept_name
                )
            else:
                guides = await self.db.fetch(
                    """
                    SELECT DISTINCT ON (concept_name, focus_area) *
                    FROM study_guides
                    WHERE child_id = $1
                    ORDER BY concept_name, focus_area, generated_at DESC
                    """,
                    child_id
                )
            
            logger.info(f"Found {len(guides)} unique study guides for child {child_id} (deduplicated by concept/focus_area)")
            # Parse metadata for each guide
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
                result.append(guide_dict)
            return result
        except Exception as e:
            logger.error(f"Error fetching study guides: {e}", exc_info=True)
            return []
