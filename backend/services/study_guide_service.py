"""Service for generating personalized study guides."""

import logging
import uuid
import json
from typing import Dict, Any, Optional, List

from services.llm_service import LLMService
from database.repositories.concept_repository import ConceptRepository
from core.database import Database

logger = logging.getLogger(__name__)


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
        force_regenerate: bool = False
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
            
        Returns:
            Dictionary with study guide data
        """
        logger.info(f"generate_study_guide called: child_id={child_id}, concept={concept_name}, focus_area={focus_area}, force_regenerate={force_regenerate}")
        
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
        
        # Get concept information if available
        concept_info = None
        concepts = await self.concept_repo.get_all_concepts()
        for concept in concepts:
            if concept['name'].lower() == concept_name.lower():
                concept_info = concept
                break
        
        # Build prompt for study guide generation
        prompt = self._build_study_guide_prompt(
            concept_name=concept_name,
            focus_area=focus_area,
            grade_level=grade_level,
            subject=subject,
            concept_info=concept_info,
            common_errors=common_errors or [],
            misconceptions=misconceptions or [],
            sample_questions=sample_questions or []
        )
        
        system_prompt = """
        You are an expert educational tutor. Your task is to generate a DETAILED, COMPREHENSIVE study guide in Markdown. 
Because this is for the Zoria Learning System, you must use specific structural patterns that our frontend will transform into interactive "Knowledge Blocks."

## 1. STRUCTURAL DIRECTIVES
- **Tone**: Professional, encouraging, and clear (Middle School level).
- **LaTeX**: Use double-backslashes for all math (e.g., `\\vec{F} = ma`).
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
            
            # Generate revision cards using LLM
            logger.info(f"Generating revision cards for {concept_name}")
            revision_cards = await self._generate_revision_cards(content, concept_name)
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
        sample_questions: List[Dict]
    ) -> str:
        """Build prompt for study guide generation."""
        prompt_parts = [
            f"Create a comprehensive study guide for: {concept_name}",
            f"",
            f"Focus Area: {focus_area}",
            ""
        ]
        
        if grade_level:
            prompt_parts.append(f"Grade Level: {grade_level}")
        if subject:
            prompt_parts.append(f"Subject: {subject}")
        
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
                "Misconceptions Identified:",
            ])
            for i, misc in enumerate(misconceptions, 1):
                prompt_parts.append(f"{i}. {misc}")
        
        if sample_questions:
            prompt_parts.extend([
                "",
                "Sample Questions (where errors occurred):",
            ])
            for i, q in enumerate(sample_questions[:3], 1):
                q_text = q.get('text', '')[:200] if isinstance(q.get('text'), str) else str(q.get('text', ''))[:200]
                prompt_parts.append(f"{i}. {q_text}")
        
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
        concept_name: str
    ) -> List[Dict[str, Any]]:
        """Generate revision cards from study guide content using LLM.
        
        Args:
            content: The study guide markdown content
            concept_name: Name of the concept
            
        Returns:
            List of revision card objects with 'front' and 'back' keys
        """
        prompt = f"""
Extract revision cards from this study guide for {concept_name}:

{content}

### TASK: Structural Content Extraction
Review the provided text and generate:
1. **5-8 Definitions**: Focus on fundamental terms found in Sections 1 and 2.
2. **5-8 Formulas**: Extract core equations. Use LaTeX.
3. **3-5 Procedural Examples**: Extract full problems and all steps from Sections 4 or 7.

### OUTPUT RULES:
- If a problem in the text has a calculation error or uses an incorrect formula for the given variables, correct it in the card output.
- Every card must be self-contained (no "as seen in example 1" references).
- Use proper LaTeX syntax with single backslashes in JSON: \vec{{F}} = ma, \frac{{1}}{{2}}, \text{{units}}
- Use actual newlines (\n) to separate steps, NOT escaped backslashes
- Remove any [LaTeX] markers - just include the actual LaTeX formulas
- CRITICAL: For sample problems, include the COMPLETE problem statement in the "front" field - do NOT truncate with "..." or ellipsis. Include all given values and what is being asked.
- CRITICAL: Return a JSON ARRAY of cards, starting with [ and ending with ]. Do NOT return a single object.

### OUTPUT JSON EXAMPLE:
[
  {{
    "front": "What is the formula for Kinetic Energy?",
    "back": "The formula is: $$KE = \\frac{{1}}{{2}}mv^2$$\n\nWhere:\n- $m$ is mass\n- $v$ is velocity"
  }},
  {{
    "front": "Sample Problem: A cart starts from rest and accelerates uniformly at 2.0 m/s² for 5 seconds. Find the final velocity and distance traveled.",
    "back": "Step 1: Identify given values\n\nInitial velocity $u = 0 \\text{{ m/s}}$\nAcceleration $a = 2.0 \\text{{ m/s}}^2$\nTime $t = 5 \\text{{ s}}$\n\n\nStep 2: Apply formula $v = u + at$\n\n\nStep 3: Calculate final velocity\n\n$$v = 0 + (2.0)(5) = 10.0 \\text{{ m/s}}$$\n\n\nStep 4: Calculate distance using $s = ut + \\frac{{1}}{{2}}at^2$\n\n$$s = (0)(5) + \\frac{{1}}{{2}}(2.0)(5)^2 = 25 \\text{{ m}}$$\n\n\nFinal Answer: The final velocity is 10.0 m/s and the distance traveled is 25 m."
  }}
]
"""

        system_prompt = """
# Role: Expert Educational Content Extractor (Llama 3.1)
You are a specialist in transforming long-form Study Guides into high-utility active recall Revision Cards.

## 1. EXTRACTION & AUDIT PROTOCOL
- **Definitions**: Identify core terms. Format: Front: "What is [Term]?"; Back: Scientific definition.
- **Formulas**: Extract LaTeX formulas. You MUST provide a "Variable Legend" defining every symbol used.
- **Step-by-Step Solutions**: 
    - Include the COMPLETE problem statement in the "front" field - do NOT truncate with "..."
    - Include every numbered step from the text in the "back" field.
    - **Logic Guardrail**: If the source text suggests a formula that does not match the variables given (e.g., using F=ma when only velocity/time are provided), you must correct the logic to use the mathematically sound formula.
- **Accuracy Check**: Ensure every opened LaTeX bracket `{{` or `$` is properly closed. Verify syntax like `\\text{m s}^{-1}`.

## 2. FORMATTING & JSON SAFETY (CRITICAL)
- **JSON Structure**: Output a RAW JSON ARRAY only. 
  - **MUST start with `[` and end with `]`** - This is an array, not a single object.
  - **Do NOT return a single card object** - Always return an array, even if it has only one card.
  - Do NOT wrap the array in a "cards" key. 
  - Do NOT include markdown code blocks (```json).
- **LaTeX Syntax**: Use single backslashes in JSON output (e.g., `\frac`, `\vec`, `\text`). The JSON parser will handle escaping.
- **Newlines**: Use actual newline characters `\n` (not escaped backslashes) to separate steps in the "back" field.
- **Step Formatting**: For step-by-step solutions, use DOUBLE newlines (`\n\n`) between each numbered step (Step 1, Step 2, etc.) to ensure clear visual separation.
- **Line Breaks**: Each step should be on its own line, with a blank line between steps for readability.
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
            
            # Validate and clean cards
            import re
            valid_cards = []
            for idx, card in enumerate(cards):
                if isinstance(card, dict) and 'front' in card and 'back' in card:
                    # Ensure front and back are strings
                    # Use repr to preserve escape sequences, then decode
                    front_raw = card.get('front', '')
                    back_raw = card.get('back', '')
                    
                    # Convert to string, handling both string and other types
                    if isinstance(front_raw, str):
                        front = front_raw
                    else:
                        front = str(front_raw)
                    
                    if isinstance(back_raw, str):
                        back = back_raw
                    else:
                        back = str(back_raw)
                    
                    # Fix LaTeX commands that lost their backslashes due to Python escape sequence interpretation
                    # When JSON contains "\frac", Python's json.loads interprets \f as form feed (\x0c)
                    # So "\frac" becomes form feed character + "rac"
                    
                    # First, fix form feed characters that should be \frac
                    # Pattern: form feed followed by "rac" -> "\frac"
                    front = re.sub(r'\x0crac', r'\\frac', front)
                    back = re.sub(r'\x0crac', r'\\frac', back)
                    
                    # Also fix form feed followed by any LaTeX-like pattern (in case of other commands)
                    # Pattern: form feed + letter sequence that looks like LaTeX command
                    # Match form feed followed by lowercase letters (LaTeX commands are lowercase)
                    front = re.sub(r'\x0c([a-z]+)', r'\\\1', front)  # form feed + command -> \command
                    back = re.sub(r'\x0c([a-z]+)', r'\\\1', back)
                    
                    # Fix any remaining form feed characters - they're likely from \f in JSON
                    # Remove standalone form feeds (not followed by a letter that could be a command)
                    front = re.sub(r'\x0c(?!\w)', '', front)  # Remove form feed if not followed by word char
                    back = re.sub(r'\x0c(?!\w)', '', back)
                    
                    # Also check for form feed in the middle of text (like "KE = \x0c\frac")
                    # Replace form feed + backslash + command with just backslash + command
                    front = re.sub(r'\x0c\\', r'\\', front)
                    back = re.sub(r'\x0c\\', r'\\', back)
                    
                    # Fix other common LaTeX commands that might have lost backslashes
                    # Pattern: "rac{" -> "\frac{" (when backslash was lost)
                    front = re.sub(r'([^\\])rac\{', r'\1\\frac{', front)
                    back = re.sub(r'([^\\])rac\{', r'\1\\frac{', back)
                    front = re.sub(r'^rac\{', r'\\frac{', front)
                    back = re.sub(r'^rac\{', r'\\frac{', back)
                    
                    # Fix "ext{" -> "\text{" (when backslash was lost)
                    front = re.sub(r'([^\\])ext\{', r'\1\\text{', front)
                    back = re.sub(r'([^\\])ext\{', r'\1\\text{', back)
                    front = re.sub(r'^ext\{', r'\\text{', front)
                    back = re.sub(r'^ext\{', r'\\text{', back)
                    
                    # Normalize LaTeX: fix double backslashes and escaped newlines
                    # Replace \\\\ with \\ (for over-escaped backslashes)
                    # But be careful - we want to preserve actual double backslashes that are needed
                    # Only normalize if we have 4+ consecutive backslashes
                    front = re.sub(r'\\\\{3,}', r'\\\\', front)
                    back = re.sub(r'\\\\{3,}', r'\\\\', back)
                    
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
                        if 'revision_cards' in guide_dict['metadata']:
                            logger.info(f"Found {len(guide_dict['metadata']['revision_cards'])} revision cards in metadata")
                    except (json.JSONDecodeError, TypeError) as e:
                        logger.warning(f"Failed to parse metadata JSON: {e}")
                        guide_dict['metadata'] = {}
                elif isinstance(guide_dict['metadata'], dict):
                    logger.debug(f"Metadata is already dict, revision_cards present: {'revision_cards' in guide_dict['metadata']}")
                    if 'revision_cards' in guide_dict['metadata']:
                        logger.info(f"Found {len(guide_dict['metadata']['revision_cards'])} revision cards in metadata")
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
