"""Question generation service using LLM and semantic deduplication."""

import logging
import json
from typing import Dict, Any, Optional, List

from database.repositories.question_repository import QuestionRepository
from database.repositories.concept_repository import ConceptRepository
from database.repositories.chunk_repository import ChunkRepository
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService
from services.question_validator_service import QuestionValidatorService
from schemas.question_blueprint import GeneratedQuestionBlueprint, QuestionOption
from subject_config import (
    get_question_generation_config,
    get_validation_rules,
    get_subject_profile,
    normalize_subject_name
)
from core.database import Database

logger = logging.getLogger(__name__)


class QuestionGenerationService:
    """Service for generating questions using local LLM with semantic deduplication."""
    
    def __init__(
        self,
        db: Database,
        embedding_service: EmbeddingService,
        llm_service: Optional[LLMService] = None
    ):
        """Initialize question generation service.
        
        Args:
            db: Database instance
            embedding_service: Embedding service for semantic deduplication
            llm_service: LLM service for text generation (optional, will create if not provided)
        """
        self.db = db
        self.question_repo = QuestionRepository(db)
        self.concept_repo = ConceptRepository(db)
        self.chunk_repo = ChunkRepository(db)
        self.embedding_service = embedding_service
        # Initialize LLM service with logging enabled and context
        if llm_service is None:
            self.llm_service = LLMService(
                enable_logging=True,
                context_source="question_generation",
                db=db
            )
        else:
            self.llm_service = llm_service
        self.validator = QuestionValidatorService()
        logger.info("QuestionGenerationService initialized")
    
    async def check_question_pool(
        self,
        concept_id: str,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        required_count: int = 10
    ) -> Dict[str, Any]:
        """Check if sufficient questions exist in the pool.
        
        Args:
            concept_id: Concept UUID
            difficulty: Difficulty filter (optional)
            question_type: Question type filter (optional)
            required_count: Minimum number of questions needed
            
        Returns:
            Dictionary with pool status and existing questions
        """
        count = await self.question_repo.count_questions_by_concept(
            concept_id=concept_id,
            difficulty=difficulty,
            question_type=question_type,
            exclude_rejected=True
        )
        
        # Get existing questions if count is sufficient
        existing_questions = []
        if count >= required_count:
            # Fetch a sample of existing questions
            all_questions = await self.question_repo.get_questions_by_concept(concept_id)
            # Filter by difficulty and type if specified
            filtered = all_questions
            if difficulty:
                filtered = [q for q in filtered if q.get('difficulty') == difficulty]
            if question_type:
                filtered = [q for q in filtered if q.get('type') == question_type]
            # Exclude rejected
            filtered = [q for q in filtered if q.get('status') != 'rejected']
            existing_questions = filtered[:required_count]
        
        return {
            'sufficient': count >= required_count,
            'count': count,
            'required': required_count,
            'existing_questions': [dict(q) for q in existing_questions]
        }
    
    async def get_concept_metadata(
        self,
        concept_id: str
    ) -> Dict[str, Any]:
        """Get concept metadata for question generation.
        
        Args:
            concept_id: Concept UUID
            
        Returns:
            Concept metadata dictionary
        """
        concept = await self.concept_repo.get_concept_by_id(concept_id)
        if not concept:
            raise ValueError(f"Concept not found: {concept_id}")
        
        # Get existing questions for this concept (sample)
        existing_questions = await self.question_repo.get_questions_by_concept(concept_id)
        existing_question_texts = [
            q.get('text', '')[:100] 
            for q in existing_questions[:5] 
            if q.get('status') != 'rejected'
        ]
        
        return {
            'concept_id': concept_id,
            'concept_name': concept.get('name', ''),
            'subtopic': concept.get('subtopic', ''),
            'keywords': concept.get('keywords', []),
            'difficulty': concept.get('difficulty', 'medium'),
            'source_markdown': (concept.get('source_markdown') or '')[:500],  # Truncate
            'existing_questions': existing_question_texts
        }
    
    # Build dynamic JSON schema that supports all question types
        json_schema = """{{
  "questions": [
    {{
      "question_text": "Question text here",
      "question_type": "multiple_choice | short_answer | problem_solving",
      "difficulty": "{difficulty}",
      "cognitive_level": "application",
      "hint": "A helpful hint that guides students toward the solution without giving away the answer",
      // For multiple_choice questions:
      "options": [
        {{"label": "A", "text": "Option A text"}},
        {{"label": "B", "text": "Option B text"}},
        {{"label": "C", "text": "Option C text"}},
        {{"label": "D", "text": "Option D text"}}
      ],
      "correct_answer": "A",
      "error_pattern_map": {{
        "B": "name_of_common_mistakes_pattern_used",
        "C": "name_of_common_mistakes_pattern_used",
        "D": "name_of_common_mistakes_pattern_used"
      }},
      // For short_answer or problem_solving questions:
      "expected_answer": "Expected answer text or numeric value",
      // For FRQ questions: indicate if graph/diagram input is needed
      "needs_graph": false,  // Set to true if question requires graph drawing
      "needs_diagram": false,  // Set to true if question requires diagram drawing
      // Common fields:
      "solution_steps": [
        "Step 1...",
        "Step 2..."
      ],
      "metadata": {{
        "estimated_time_seconds": 90
      }}
    }}
  ]
}}"""
    async def generate_all_questions_via_llm(
        self,
        concept_metadata: Dict[str, Any],
        num_questions: int = 10,
        question_type: str = "multiple_choice",
        difficulty: Optional[str] = None,
        grade_level: Optional[int] = 8,
        subject_id: Optional[str] = None,
        selected_topics: Optional[List[str]] = None,
        subject_profile: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Generate all questions in a single LLM request.
        
        Args:
            concept_metadata: Concept metadata dictionary
            num_questions: Number of questions to generate (default 10)
            question_type: Type of question to generate
            difficulty: Difficulty level (overrides concept difficulty if provided)
            grade_level: Grade level for age-appropriate language
            subject_id: Subject ID for subject-specific generation rules
            selected_topics: List of selected topics
            subject_profile: Subject profile JSON dictionary
            
        Returns:
            List of generated question dictionaries (blueprint + raw)
        """
        concept_id = concept_metadata.get('concept_id')
        concept_name = concept_metadata.get('concept_name', '')
        difficulty = difficulty or concept_metadata.get('difficulty', 'medium')
        concept_subtopic = concept_metadata.get('subtopic', '') or ''

        # Retrieve contextual chunks for this concept to ground generation (trimmed)
        context_chunks = []
        if concept_id:
            try:
                chunks = await self.chunk_repo.get_chunks_by_concept(concept_id)
                # Prioritize concept_overview and explanation chunks
                for chunk in chunks:
                    chunk_type = chunk.get("chunk_type", "")
                    text = chunk.get("chunk_text", "")
                    if not text:
                        continue
                    # Trim each chunk to avoid very long prompts
                    snippet = text[:800]
                    context_chunks.append(f"[{chunk_type}] {snippet}")
                    if len(context_chunks) >= 5:
                        break
            except Exception as e:
                logger.warning(f"Failed to load context chunks for concept {concept_id}: {e}")

        context_text = "\n\n".join(context_chunks) if context_chunks else "None"
        selected_topics_str = ", ".join(selected_topics or []) or "None"
        subtopic_str = concept_subtopic or "None"
        
        # Get subject profile JSON if not provided
        if subject_id and not subject_profile:
            subject_id = normalize_subject_name(subject_id)
            subject_profile = get_subject_profile(subject_id)
        
        # Extract llm_prompt_template from subject profile
        llm_template = {}
        if subject_profile:
            llm_template = subject_profile.get("llm_prompt_template", {})
        
        system_instructions = llm_template.get("system_instructions", "")
        format_rules = llm_template.get("format_rules", "")
        
        # Format subject profile as JSON string for prompt (excluding llm_prompt_template to avoid duplication)
        relevant_profile = {}
        if subject_profile:
            relevant_profile = {
                "subject_id": subject_profile.get("subject_id"),
                "display_name": subject_profile.get("display_name"),
                "question_generation": subject_profile.get("question_generation", {}),
                "validation_rules": subject_profile.get("validation_rules", {}),
                "common_mistakes_patterns": subject_profile.get("common_mistakes_patterns", [])
            }
        subject_profile_json = json.dumps(relevant_profile, indent=2) if relevant_profile else "{}"

        # Ensure variables used in prompts are defined before the f-strings are built
        target_subject = (
            (subject_profile.get("display_name") if subject_profile else None)
            or subject_id
            or "unknown"
        )
        

        # Build system prompt (keep this concise; put profile/context/schema into the user prompt)
        system_prompt = f"""## System Instruction
You are a high-fidelity Assessment Engine. Your goal is to transform provided Study Context into {num_questions} unique, application-level test questions.

### Execution Rules:
1. **Transformation:** Do not repeat the study guide questions verbatim. If the context provides an equation, create a question where the student must identify its properties (intercepts, vertex, growth) or apply it to a scenario.
2. **Cognitive Level (Application):** Questions must require the user to perform a calculation or apply a rule. Avoid "Recall" questions (e.g., "What is the formula for...").
3. **LaTeX Standard:** Use $...$ for all mathematical expressions and technical notation.
4. **Visual Aids:** For any question involving geometry, functions, or data sets, include a [Image of X] tag within the question_text to provide a visual reference for the user.
5. **Question Type Selection:** Choose the most appropriate question type for each question:
   - **multiple_choice**: Use for questions with clear correct answers that can have plausible distractors. Include exactly 4 options (A, B, C, D) and use error_pattern_map to explain distractor design. REQUIRED: options, correct_answer, error_pattern_map.
   - **short_answer**: Use for questions requiring brief text or numeric responses (1-2 sentences or a number). REQUIRED: expected_answer (must be a specific answer, not a placeholder).
   - **problem_solving**: Use for multi-step problems requiring detailed solutions or explanations. REQUIRED: expected_answer (must be a specific answer or final result, not a placeholder).
6. **Plausible Distractors (MCQ only):** For multiple_choice questions, analyze the "common_mistakes_patterns" in the subject profile. Every incorrect option must be reachable through a specific, identified error (e.g., a sign error or wrong order of operations).
7. **CRITICAL - Correct Answers:** 
   - For multiple_choice: Always provide correct_answer (A, B, C, or D).
   - For short_answer and problem_solving: Always provide expected_answer with a specific, concrete answer. Do NOT use placeholders like "see solution" or "varies". The expected_answer must be the actual correct answer.
8. **REQUIRED - Hints:** Every question MUST include a helpful hint that:
   - Guides students toward the solution without giving away the answer
   - Provides a nudge in the right direction (e.g., "Think about the key formula", "Consider what happens when x = 0", "Remember the order of operations")
   - Is specific to the question (not generic)
   - Is at least 10 characters long
   - Does NOT reveal the answer directly
   - Helps students understand the approach or key concept needed

9. **Graph and Diagram Requirements (FRQ only):** For non-MCQ questions (short_answer, problem_solving), indicate if the question requires student input:
   - **needs_graph**: Set to true if the question asks students to plot, graph, or visualize data (e.g., "Graph the function f(x) = 2x + 3", "Plot the data points", "Sketch the coordinate plane", "Draw a graph showing...")
   - **needs_diagram**: Set to true if the question asks students to draw geometric shapes, diagrams, or visual representations (e.g., "Draw a triangle", "Sketch a free-body diagram", "Illustrate the molecular structure", "Draw a diagram showing...")
   - Both should be false for text-only questions or questions that only require calculations
   - These flags control which drawing tools are available to students in the UI

**Target Subject:** {target_subject}
**Target Grade:** {grade_level}
**Difficulty Selection (Inclusive):** {difficulty}
   - If "easy" is selected: Generate only easy questions
   - If "medium" is selected: Generate easy and medium questions (inclusive)
   - If "hard" is selected: Generate easy, medium, and hard questions (inclusive)
   - When generating, vary the difficulty levels appropriately within the selected range

**Subject Profile:**
{subject_profile_json}

**Context & Sample Questions:**
{context_text}

OUTPUT RULES:
- Return JSON strictly matching the schema below. Do not include any extra fields.
- Do NOT include any markdown or code fences. JSON only.
- Vary question types appropriately based on the content - use multiple_choice, short_answer, and problem_solving as appropriate.
- For multiple_choice: include options, correct_answer, and error_pattern_map.
- For short_answer and problem_solving: include expected_answer with a specific, concrete answer (REQUIRED).
- EVERY question must include a hint (REQUIRED).

JSON SCHEMA:
{json_schema.format(difficulty=difficulty)}

"""

        # Append subject-specific instructions/rules (if present) without duplicating the core system instruction.
        if system_instructions:
            system_prompt += f"\n\nSubject-specific instructions:\n{system_instructions}"
        if format_rules:
            system_prompt += f"\n\nFormat requirements:\n{format_rules}"

        # Build user prompt (your template + strict JSON schema for reliable parsing)
        prompt = f"""## User Input

**Concept:** {concept_name}
**Topics (selected):** {selected_topics_str}
**Subtopics for this concept:** {subtopic_str}

**Instruction for AI:**
Using the Context provided, generate {num_questions} questions. Choose the most appropriate question type for each question based on the content:
- Use **multiple_choice** for questions with clear correct answers and plausible distractors
- Use **short_answer** for brief responses (text or numbers)
- Use **problem_solving** for multi-step problems requiring detailed work

IMPORTANT: Generate exactly {num_questions} questions. The "questions" array must contain exactly {num_questions} question objects. Return ONLY the JSON object with no additional text.
"""

        try:
            # Calculate appropriate max_tokens: ~1000 tokens per question (includes JSON structure, options, solution steps, metadata)
            # Each question has: question_text, 4 options, 2 solution steps, error_pattern_map, metadata
            # For GPT-5 models with reasoning: need to account for reasoning_tokens + output_tokens
            # Allocate 2.5x the estimated output to account for reasoning (reasoning can use up to ~1.5x output size)
            estimated_output_tokens = (num_questions * 1000) + 3000  # 1000 per question + 3000 for JSON structure overhead
            estimated_reasoning_tokens = int(estimated_output_tokens * 1.5)  # Reasoning can use up to 1.5x output
            max_tokens = max(20000, estimated_output_tokens + estimated_reasoning_tokens)  # Minimum 20000, account for reasoning + output
            
            logger.info(f"Generating {num_questions} questions with max_tokens={max_tokens} (estimated {estimated_output_tokens} output + {estimated_reasoning_tokens} reasoning tokens needed)")
            
            response = await self.llm_service.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=max_tokens,
                concept_id=str(concept_id) if concept_id else None,
                metadata={
                    "concept_name": concept_name,
                    "difficulty": difficulty,
                    "question_type": question_type,
                    "subject_id": subject_id,
                    "selected_topics": selected_topics,
                    "num_questions": num_questions
                }
            )
            
            # Log full response for debugging
            logger.debug(f"Full LLM response: {json.dumps(response, indent=2)[:2000]}")
            
            # Extract questions from response
            questions_list = response.get("questions", [])
            if not questions_list:
                # Fallback: if response is a single question, wrap it
                if "question_text" in response:
                    questions_list = [response]
                else:
                    logger.error(f"No questions found in LLM response. Response keys: {list(response.keys())}")
                    logger.error(f"Full response structure: {json.dumps(response, indent=2)[:2000]}")
                    raise ValueError("No questions found in LLM response")
            
            logger.info(f"LLM generated {len(questions_list)} questions (requested {num_questions})")
            
            if len(questions_list) < num_questions:
                logger.warning(f"LLM generated only {len(questions_list)} questions instead of {num_questions}")
            
            # Process each question into blueprint format
            processed_questions = []
            for q_data in questions_list:
                # Ensure options are in correct format
                if "options" in q_data and isinstance(q_data["options"], list):
                    option_objs = []
                    for opt in q_data["options"]:
                        if isinstance(opt, dict):
                            if "label" in opt and "text" in opt:
                                option_objs.append(opt)
                            elif "text" in opt:
                                # Generate label if missing
                                label = chr(ord("A") + len(option_objs))
                                option_objs.append({"label": label, "text": opt["text"]})
                            else:
                                # Legacy format: just text
                                label = chr(ord("A") + len(option_objs))
                                option_objs.append({"label": label, "text": str(opt)})
                        else:
                            # Legacy format: list of strings
                            label = chr(ord("A") + len(option_objs))
                            option_objs.append({"label": label, "text": str(opt)})
                    q_data["options"] = option_objs[:4]  # Ensure exactly 4 options
                
                # Ensure correct_answer is valid
                correct_answer = str(q_data.get("correct_answer", "A")).strip().upper()
                if correct_answer not in ["A", "B", "C", "D"]:
                    correct_answer = "A"
                q_data["correct_answer"] = correct_answer
                
                # Ensure solution_steps exists and has 2 steps
                if "solution_steps" not in q_data or not q_data["solution_steps"]:
                    q_data["solution_steps"] = ["Step 1", "Step 2"]
                elif len(q_data["solution_steps"]) < 2:
                    # Pad with placeholder steps if needed
                    while len(q_data["solution_steps"]) < 2:
                        q_data["solution_steps"].append(f"Step {len(q_data['solution_steps']) + 1}")
                
                # Attach concept/subject metadata
                q_data.setdefault("metadata", {})
                q_data["metadata"].update({
                    "concept_name": concept_name,
                    "keywords": concept_metadata.get('keywords', []),
                })
                
                # Store diagram_code in metadata if present (for rendering in frontend)
                diagram_code = q_data.pop("diagram_code", None)
                if diagram_code:
                    q_data["metadata"]["diagram_code"] = diagram_code
                
                # Store needs_graph and needs_diagram flags for FRQ questions
                if q_data.get("question_type") != "multiple_choice":
                    needs_graph = q_data.pop("needs_graph", False)
                    needs_diagram = q_data.pop("needs_diagram", False)
                    if needs_graph:
                        q_data["metadata"]["needs_graph"] = True
                    if needs_diagram:
                        q_data["metadata"]["needs_diagram"] = True
                
                # Seed requires_units from subject validation rules when applicable
                if subject_id:
                    try:
                        rules = get_validation_rules(subject_id)
                        if rules.get("must_include_units_when_numerical"):
                            q_data["metadata"].setdefault("requires_units", True)
                    except Exception as e:
                        logger.warning(f"Failed to load validation rules for subject {subject_id}: {e}")
                
                # Build blueprint model (diagram_code is now in metadata, not top-level)
                try:
                    blueprint = GeneratedQuestionBlueprint(
                        subject=subject_id,
                        concept_id=str(concept_id) if concept_id else "",
                        **q_data,
                    )
                    
                    # Validate blueprint
                    self.validator.validate(blueprint)
                    
                    processed_questions.append({
                        "blueprint": blueprint,
                        "raw": q_data,
                    })
                    logger.debug(f"Successfully processed question: {blueprint.question_text[:100]}... for concept {concept_id}")
                except Exception as e:
                    logger.error(f"Failed to process question for concept {concept_id}: {e}")
                    logger.error(f"Question data keys: {list(q_data.keys())}")
                    logger.error(f"Question text preview: {q_data.get('question_text', 'N/A')[:200]}")
                    # Continue processing other questions instead of failing completely
                    continue
            
            return processed_questions
                    
        except Exception as e:
            logger.error(f"Error generating all questions via LLM: {e}")
            raise
    
    async def generate_all_questions_for_concepts(
        self,
        concept_ids: List[str],
        num_questions: int = 10,
        question_type: str = "multiple_choice",
        difficulty: Optional[str] = None,
        grade_level: Optional[int] = 8,
        subject_id: Optional[str] = None,
        selected_topics: Optional[List[str]] = None,
        subject_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Generate all questions for multiple concepts in a single LLM request.
        
        Args:
            concept_ids: List of concept UUIDs
            num_questions: Total number of questions to generate
            question_type: Type of question to generate
            difficulty: Difficulty level
            grade_level: Grade level for age-appropriate language
            subject_id: Subject ID for subject-specific generation rules
            selected_topics: List of selected topics
            subject_profile: Subject profile JSON dictionary
            
        Returns:
            Dictionary mapping concept_id to list of generated question dictionaries (blueprint + raw)
        """
        if not concept_ids:
            return {}
        
        # Get metadata for all concepts
        all_concept_metadata = []
        all_context_chunks = []
        concept_names = []
        
        for cid in concept_ids:
            try:
                concept_metadata = await self.get_concept_metadata(cid)
                all_concept_metadata.append(concept_metadata)
                concept_names.append(concept_metadata.get('concept_name', ''))
                
                # Retrieve contextual chunks for this concept
                if cid:
                    try:
                        chunks = await self.chunk_repo.get_chunks_by_concept(cid)
                        for chunk in chunks:
                            chunk_type = chunk.get("chunk_type", "")
                            text = chunk.get("chunk_text", "")
                            if not text:
                                continue
                            snippet = text[:600]  # Slightly smaller per chunk since we have multiple concepts
                            all_context_chunks.append(f"[Concept: {concept_metadata.get('concept_name', '')}] [{chunk_type}] {snippet}")
                            if len([c for c in all_context_chunks if c.startswith(f"[Concept: {concept_metadata.get('concept_name', '')}]")]) >= 3:
                                break  # Limit to 3 chunks per concept
                    except Exception as e:
                        logger.warning(f"Failed to load context chunks for concept {cid}: {e}")
            except Exception as e:
                logger.warning(f"Failed to get metadata for concept {cid}: {e}")
                continue
        
        if not all_concept_metadata:
            raise ValueError("No valid concept metadata found")
        
        # Aggregate context
        context_text = "\n\n".join(all_context_chunks) if all_context_chunks else "None"
        selected_topics_str = ", ".join(selected_topics or []) or "None"
        concepts_list_str = ", ".join(concept_names) or "None"
        subtopics_set = {m.get('subtopic') for m in all_concept_metadata if m.get('subtopic')}
        subtopics_str = ", ".join(sorted(subtopics_set)) or "None"
        
        # Get subject profile JSON if not provided
        if subject_id and not subject_profile:
            subject_id = normalize_subject_name(subject_id)
            subject_profile = get_subject_profile(subject_id)
        
        # Extract llm_prompt_template from subject profile
        llm_template = {}
        if subject_profile:
            llm_template = subject_profile.get("llm_prompt_template", {})
        
        system_instructions = llm_template.get("system_instructions", "")
        format_rules = llm_template.get("format_rules", "")
        
        # Format subject profile as JSON string for prompt (excluding llm_prompt_template to avoid duplication)
        relevant_profile = {}
        if subject_profile:
            relevant_profile = {
                "subject_id": subject_profile.get("subject_id"),
                "display_name": subject_profile.get("display_name"),
                "question_generation": subject_profile.get("question_generation", {}),
                "validation_rules": subject_profile.get("validation_rules", {}),
                "common_mistakes_patterns": subject_profile.get("common_mistakes_patterns", [])
            }
        subject_profile_json = json.dumps(relevant_profile, indent=2) if relevant_profile else "{}"
        
        # Match the single-concept instruction format for multi-concept generation (same core content)
        target_subject = (
            (subject_profile.get("display_name") if subject_profile else None)
            or subject_id
            or "unknown"
        )
        
        # Build dynamic JSON schema that supports all question types (same as single-concept method)
        json_schema = """{{
  "questions": [
    {{
      "question_text": "Question text here",
      "question_type": "multiple_choice | short_answer | problem_solving",
      "difficulty": "{difficulty}",
      "cognitive_level": "application",
      "hint": "A helpful hint that guides students toward the solution without giving away the answer",
      // For multiple_choice questions:
      "options": [
        {{"label": "A", "text": "Option A text"}},
        {{"label": "B", "text": "Option B text"}},
        {{"label": "C", "text": "Option C text"}},
        {{"label": "D", "text": "Option D text"}}
      ],
      "correct_answer": "A",
      "error_pattern_map": {{
        "B": "name_of_common_mistakes_pattern_used",
        "C": "name_of_common_mistakes_pattern_used",
        "D": "name_of_common_mistakes_pattern_used"
      }},
      // For short_answer or problem_solving questions:
      "expected_answer": "Expected answer text or numeric value",
      // For FRQ questions: indicate if graph/diagram input is needed
      "needs_graph": false,  // Set to true if question requires graph drawing
      "needs_diagram": false,  // Set to true if question requires diagram drawing
      // Common fields:
      "solution_steps": [
        "Step 1...",
        "Step 2..."
      ],
      "metadata": {{
        "estimated_time_seconds": 90
      }}
    }}
  ]
}}"""

        system_prompt = f"""## System Instruction
You are a high-fidelity Assessment Engine. Your goal is to transform provided Study Context into {num_questions} unique, application-level test questions.

### Execution Rules:
1. **Transformation:** Do not repeat the study guide questions verbatim. If the context provides an equation, create a question where the student must identify its properties (intercepts, vertex, growth) or apply it to a scenario.
2. **Cognitive Level (Application):** Questions must require the user to perform a calculation or apply a rule. Avoid "Recall" questions (e.g., "What is the formula for...").
3. **LaTeX Standard:** Use $...$ for all mathematical expressions and technical notation.
4. **Visual Aids:** For any question involving geometry, functions, or data sets, include a [Image of X] tag within the question_text to provide a visual reference for the user.
5. **Question Type Selection:** Choose the most appropriate question type for each question:
   - **multiple_choice**: Use for questions with clear correct answers that can have plausible distractors. Include exactly 4 options (A, B, C, D) and use error_pattern_map to explain distractor design. REQUIRED: options, correct_answer, error_pattern_map.
   - **short_answer**: Use for questions requiring brief text or numeric responses (1-2 sentences or a number). REQUIRED: expected_answer (must be a specific answer, not a placeholder).
   - **problem_solving**: Use for multi-step problems requiring detailed solutions or explanations. REQUIRED: expected_answer (must be a specific answer or final result, not a placeholder).
6. **Plausible Distractors (MCQ only):** For multiple_choice questions, analyze the "common_mistakes_patterns" in the subject profile. Every incorrect option must be reachable through a specific, identified error (e.g., a sign error or wrong order of operations).
7. **CRITICAL - Correct Answers:** 
   - For multiple_choice: Always provide correct_answer (A, B, C, or D).
   - For short_answer and problem_solving: Always provide expected_answer with a specific, concrete answer. Do NOT use placeholders like "see solution" or "varies". The expected_answer must be the actual correct answer.
8. **REQUIRED - Hints:** Every question MUST include a helpful hint that:
   - Guides students toward the solution without giving away the answer
   - Provides a nudge in the right direction (e.g., "Think about the key formula", "Consider what happens when x = 0", "Remember the order of operations")
   - Is specific to the question (not generic)
   - Is at least 10 characters long
   - Does NOT reveal the answer directly
   - Helps students understand the approach or key concept needed

9. **Graph and Diagram Requirements (FRQ only):** For non-MCQ questions (short_answer, problem_solving), indicate if the question requires student input:
   - **needs_graph**: Set to true if the question asks students to plot, graph, or visualize data (e.g., "Graph the function f(x) = 2x + 3", "Plot the data points", "Sketch the coordinate plane", "Draw a graph showing...")
   - **needs_diagram**: Set to true if the question asks students to draw geometric shapes, diagrams, or visual representations (e.g., "Draw a triangle", "Sketch a free-body diagram", "Illustrate the molecular structure", "Draw a diagram showing...")
   - Both should be false for text-only questions or questions that only require calculations
   - These flags control which drawing tools are available to students in the UI

**Target Subject:** {target_subject}
**Target Grade:** {grade_level}
**Difficulty Selection (Inclusive):** {difficulty}
   - If "easy" is selected: Generate only easy questions
   - If "medium" is selected: Generate easy and medium questions (inclusive)
   - If "hard" is selected: Generate easy, medium, and hard questions (inclusive)
   - When generating, vary the difficulty levels appropriately within the selected range

**Subject Profile:**
{subject_profile_json}

**Context & Sample Questions:**
{context_text}

OUTPUT RULES:
- Return JSON strictly matching the schema below. Do not include any extra fields.
- Do NOT include any markdown or code fences. JSON only.
- Vary question types appropriately based on the content - use multiple_choice, short_answer, and problem_solving as appropriate.
- For multiple_choice: include options, correct_answer, and error_pattern_map.
- For short_answer and problem_solving: include expected_answer with a specific, concrete answer (REQUIRED).
- EVERY question must include a hint (REQUIRED).

JSON SCHEMA:
{json_schema.format(difficulty=difficulty)}

"""

        if system_instructions:
            system_prompt += f"\n\nSubject-specific instructions:\n{system_instructions}"
        if format_rules:
            system_prompt += f"\n\nFormat requirements:\n{format_rules}"

        # Build user prompt to match the single-concept instruction block format
        prompt = f"""## User Input

**Concepts:** {concepts_list_str}
**Topics (selected):** {selected_topics_str}
**Subtopics for these concepts:** {subtopics_str}

**Instruction for AI:**
Using the Context provided, generate {num_questions} questions.
- If the Context includes Absolute Value equations, generate questions identifying the graph's vertex or direction.
- If the Context includes Sequences, generate word problems (e.g., money saved over weeks) rather than raw number lists.
- Ensure the 'error_pattern_map' specifically names which "common_mistakes_pattern" from the profile was used to create each distractor.

IMPORTANT: Generate exactly {num_questions} questions. The "questions" array must contain exactly {num_questions} question objects. Return ONLY the JSON object with no additional text.
"""

        try:
            # Calculate appropriate max_tokens: ~1000 tokens per question (includes JSON structure, options, solution steps, metadata)
            # Each question has: question_text, 4 options, 2 solution steps, error_pattern_map, metadata
            # For GPT-5 models with reasoning: need to account for reasoning_tokens + output_tokens
            # Allocate 2.5x the estimated output to account for reasoning (reasoning can use up to ~1.5x output size)
            estimated_output_tokens = (num_questions * 1000) + 3000  # 1000 per question + 3000 for JSON structure overhead
            estimated_reasoning_tokens = int(estimated_output_tokens * 1.5)  # Reasoning can use up to 1.5x output
            max_tokens = max(30000, estimated_output_tokens + estimated_reasoning_tokens)  # Minimum 30000 for multi-concept, account for reasoning + output
            
            logger.info(f"Generating {num_questions} questions for {len(concept_ids)} concepts with max_tokens={max_tokens} (estimated {estimated_output_tokens} output + {estimated_reasoning_tokens} reasoning tokens needed)")
            
            response = await self.llm_service.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.7,
                max_tokens=max_tokens,
                concept_id=str(concept_ids[0]) if concept_ids else None,
                metadata={
                    "concept_names": concept_names,
                    "difficulty": difficulty,
                    "question_type": question_type,
                    "subject_id": subject_id,
                    "selected_topics": selected_topics,
                    "num_questions": num_questions,
                    "num_concepts": len(concept_ids)
                }
            )
            
            # Log full response for debugging
            logger.debug(f"Full LLM response: {json.dumps(response, indent=2)[:2000]}")
            
            # Extract questions from response
            questions_list = response.get("questions", [])
            if not questions_list:
                logger.error(f"No questions found in LLM response. Response keys: {list(response.keys())}")
                logger.error(f"Full response structure: {json.dumps(response, indent=2)[:2000]}")
                raise ValueError("No questions found in LLM response")
            
            logger.info(f"LLM generated {len(questions_list)} questions (requested {num_questions})")
            
            if len(questions_list) < num_questions:
                logger.warning(f"LLM generated only {len(questions_list)} questions instead of {num_questions}")
                logger.warning(f"This may indicate the response was truncated due to max_tokens limit ({max_tokens})")
                logger.warning(f"Consider increasing max_tokens or reducing num_questions")
            
            # Log all question texts for debugging
            for idx, q in enumerate(questions_list):
                logger.debug(f"LLM Question {idx + 1}: {q.get('question_text', 'N/A')[:150]}... (concept: {q.get('concept_name', 'N/A')})")
            
            # Process each question and map to concepts
            result = {cid: [] for cid in concept_ids}
            total_processed = 0
            total_failed_validation = 0
            
            for q_data in questions_list:
                # Try to match question to concept by concept_name in response
                question_concept_name = q_data.get("concept_name", "").lower()
                matched_concept_id = None
                
                # Find best matching concept
                for i, concept_meta in enumerate(all_concept_metadata):
                    concept_name = concept_meta.get('concept_name', '').lower()
                    if question_concept_name in concept_name or concept_name in question_concept_name:
                        matched_concept_id = concept_ids[i]
                        break
                
                # If no match found, distribute evenly
                if not matched_concept_id:
                    # Distribute questions evenly across concepts
                    question_idx = len([q for questions in result.values() for q in questions])
                    matched_concept_id = concept_ids[question_idx % len(concept_ids)]
                
                # Process question based on type
                question_type = q_data.get("question_type", "multiple_choice")
                
                # Ensure hint is present and valid
                hint = q_data.get("hint", "").strip()
                if not hint or len(hint) < 10:
                    # Generate a basic hint if missing
                    if question_type == "multiple_choice":
                        hint = "Consider each option carefully and identify the key concept being tested."
                    elif question_type == "short_answer":
                        hint = "Think about the key formula or concept needed to solve this problem."
                    elif question_type == "problem_solving":
                        hint = "Break down the problem into steps and identify what information you need."
                    else:
                        hint = "Review the key concepts related to this question."
                    logger.warning(f"Question missing valid hint, generated default: {hint[:50]}...")
                
                # Validate hint is not a placeholder
                placeholder_patterns = ["n/a", "tbd", "to be determined", "see solution", "see above", "varies"]
                hint_lower = hint.lower()
                if any(pattern in hint_lower for pattern in placeholder_patterns):
                    # Replace placeholder with a meaningful hint
                    if question_type == "multiple_choice":
                        hint = "Consider each option carefully and identify the key concept being tested."
                    elif question_type == "short_answer":
                        hint = "Think about the key formula or concept needed to solve this problem."
                    elif question_type == "problem_solving":
                        hint = "Break down the problem into steps and identify what information you need."
                    logger.warning(f"Question had placeholder hint, replaced with: {hint[:50]}...")
                
                q_data["hint"] = hint
                
                if question_type == "multiple_choice":
                    # Ensure options are in correct format
                    if "options" in q_data and isinstance(q_data["options"], list):
                        option_objs = []
                        for opt in q_data["options"]:
                            if isinstance(opt, dict):
                                if "label" in opt and "text" in opt:
                                    option_objs.append(opt)
                                elif "text" in opt:
                                    label = chr(ord("A") + len(option_objs))
                                    option_objs.append({"label": label, "text": opt["text"]})
                                else:
                                    label = chr(ord("A") + len(option_objs))
                                    option_objs.append({"label": label, "text": str(opt)})
                            else:
                                label = chr(ord("A") + len(option_objs))
                                option_objs.append({"label": label, "text": str(opt)})
                        q_data["options"] = option_objs[:4]  # Ensure exactly 4 options
                    
                    # Ensure correct_answer is valid
                    correct_answer = str(q_data.get("correct_answer", "A")).strip().upper()
                    if correct_answer not in ["A", "B", "C", "D"]:
                        correct_answer = "A"
                    q_data["correct_answer"] = correct_answer
                else:
                    # For non-MCQ, ensure expected_answer exists and is valid
                    expected_answer = q_data.get("expected_answer")
                    
                    if not expected_answer or not str(expected_answer).strip():
                        # Try to extract from solution_steps if available
                        if q_data.get("solution_steps") and len(q_data["solution_steps"]) > 0:
                            # Use the last step as expected_answer if it looks like a final answer
                            last_step = q_data["solution_steps"][-1]
                            # Check if last step looks like an answer (contains numbers or key result words)
                            import re
                            if any(keyword in last_step.lower() for keyword in ["answer", "result", "equals", "=", "is"]) or re.search(r'\d', last_step):
                                expected_answer = last_step
                            else:
                                # If solution_steps don't have a clear answer, construct one
                                expected_answer = f"See solution steps: {last_step}"
                        else:
                            # If no solution_steps, we must have expected_answer - this is an error
                            logger.error(f"Question {q_data.get('question_text', 'N/A')[:100]}... has no expected_answer and no solution_steps")
                            raise ValueError(f"expected_answer is REQUIRED for {question_type} questions")
                    
                    # Validate that expected_answer is not a placeholder
                    import re
                    expected_answer_str = str(expected_answer).strip().lower()
                    placeholder_patterns = ["see solution", "see above", "n/a", "tbd", "to be determined", "varies"]
                    if any(pattern in expected_answer_str for pattern in placeholder_patterns):
                        logger.warning(f"Question has placeholder expected_answer: {expected_answer}. Attempting to extract from solution_steps.")
                        # Try to extract a real answer from solution_steps
                        if q_data.get("solution_steps"):
                            # Look for numeric values or final statements
                            for step in reversed(q_data["solution_steps"]):
                                # Check if step contains a clear answer
                                if re.search(r'\d+', step) or any(word in step.lower() for word in ["answer", "result", "equals"]):
                                    expected_answer = step
                                    break
                        
                        # If still a placeholder, this is an error
                        if any(pattern in str(expected_answer).strip().lower() for pattern in placeholder_patterns):
                            raise ValueError(f"expected_answer cannot be a placeholder for {question_type} questions. Must provide actual answer.")
                    
                    q_data["expected_answer"] = str(expected_answer).strip()
                
                # Ensure solution_steps exists and has at least 1 step
                if "solution_steps" not in q_data or not q_data["solution_steps"]:
                    q_data["solution_steps"] = ["Step 1"]
                elif len(q_data["solution_steps"]) < 1:
                    q_data["solution_steps"] = ["Step 1"]
                
                # Get concept metadata for this question
                concept_meta = next((m for i, m in enumerate(all_concept_metadata) if concept_ids[i] == matched_concept_id), all_concept_metadata[0])
                
                # Attach concept/subject metadata
                q_data.setdefault("metadata", {})
                q_data["metadata"].update({
                    "concept_name": concept_meta.get('concept_name', ''),
                    "keywords": concept_meta.get('keywords', []),
                })
                
                # Store diagram_code in metadata if present (for rendering in frontend)
                diagram_code = q_data.pop("diagram_code", None)
                if diagram_code:
                    q_data["metadata"]["diagram_code"] = diagram_code
                
                # Store needs_graph and needs_diagram flags for FRQ questions
                if q_data.get("question_type") != "multiple_choice":
                    needs_graph = q_data.pop("needs_graph", False)
                    needs_diagram = q_data.pop("needs_diagram", False)
                    if needs_graph:
                        q_data["metadata"]["needs_graph"] = True
                    if needs_diagram:
                        q_data["metadata"]["needs_diagram"] = True
                
                # Seed requires_units from subject validation rules when applicable
                if subject_id:
                    try:
                        rules = get_validation_rules(subject_id)
                        if rules.get("must_include_units_when_numerical"):
                            q_data["metadata"].setdefault("requires_units", True)
                    except Exception as e:
                        logger.warning(f"Failed to load validation rules for subject {subject_id}: {e}")
                
                # Build blueprint model (diagram_code is now in metadata, not top-level)
                try:
                    blueprint = GeneratedQuestionBlueprint(
                        subject=subject_id,
                        concept_id=str(matched_concept_id),
                        **q_data,
                    )
                    
                    # Validate blueprint
                    self.validator.validate(blueprint)
                    
                    result[matched_concept_id].append({
                        "blueprint": blueprint,
                        "raw": q_data,
                    })
                    total_processed += 1
                    logger.debug(f"✓ Successfully processed question {total_processed}: {blueprint.question_text[:100]}... for concept {matched_concept_id}")
                except Exception as e:
                    total_failed_validation += 1
                    logger.error(f"✗ Failed to process question for concept {matched_concept_id}: {e}")
                    logger.error(f"Question data keys: {list(q_data.keys())}")
                    logger.error(f"Question text preview: {q_data.get('question_text', 'N/A')[:200]}")
                    # Continue processing other questions instead of failing completely
                    continue
            
            logger.info(f"Question processing summary: {total_processed} processed successfully, {total_failed_validation} failed validation")
            logger.info(f"Questions per concept: {[(cid, len(questions)) for cid, questions in result.items()]}")
            return result
                    
        except Exception as e:
            logger.error(f"Error generating all questions for multiple concepts via LLM: {e}")
            raise
    
    async def check_semantic_duplicate(
        self,
        question_text: str,
        concept_id: str,
        similarity_threshold: float = 0.85
    ) -> Dict[str, Any]:
        """Check if question is a semantic duplicate using embeddings.
        
        Args:
            question_text: New question text
            concept_id: Concept UUID
            similarity_threshold: Minimum similarity to consider duplicate
            
        Returns:
            Dictionary with duplicate status and similar questions
        """
        # Generate embedding for new question
        question_embedding = await self.embedding_service.generate_embedding(question_text)
        
        # Search for similar questions
        similar_questions = await self.question_repo.find_similar_questions(
            query_embedding=question_embedding,
            concept_id=concept_id,
            limit=5,
            similarity_threshold=0.0  # Get all, filter by threshold below
        )
        
        max_similarity = 0.0
        similar_question = None
        
        if similar_questions:
            max_similarity = float(similar_questions[0].get('similarity', 0.0))
            if max_similarity >= similarity_threshold:
                similar_question = similar_questions[0]
        
        return {
            'is_duplicate': max_similarity >= similarity_threshold,
            'max_similarity': max_similarity,
            'similar_question': similar_question,
            'threshold': similarity_threshold
        }
    
    async def store_generated_question(
        self,
        concept_id: str,
        question_data: Dict[str, Any],
        question_text: str,
        embedding: Optional[Any] = None
    ) -> str:
        """Store generated question in database.
        
        Args:
            concept_id: Concept UUID
            question_data: Generated question data from LLM
            question_text: Question text (for embedding if not provided)
            embedding: Pre-computed embedding (optional)
            
        Returns:
            Question UUID
        """
        # Generate embedding if not provided
        if embedding is None:
            embedding = await self.embedding_service.generate_embedding(question_text)
        
        # Prepare metadata
        metadata = {
            'options': question_data.get('options', []),
            'correct_answer': question_data.get('answer', ''),
            'expected_answer': question_data.get('expected_answer', ''),
            'hint': question_data.get('hint', ''),
            'explanation': question_data.get('explanation', ''),
            'generated_by': 'llm',
            'model': self.llm_service.model_name,
        }
        # Include full blueprint if provided, so we preserve rich structure
        if 'blueprint' in question_data:
            metadata['blueprint'] = question_data['blueprint']
            # Extract diagram_code from blueprint metadata if present
            blueprint_metadata = question_data['blueprint'].get('metadata', {})
            if isinstance(blueprint_metadata, dict) and blueprint_metadata.get('diagram_code'):
                metadata['diagram_code'] = blueprint_metadata['diagram_code']
                logger.debug(f"Preserved diagram_code in question metadata: {metadata['diagram_code'][:100]}...")
        
        # Normalize difficulty to ensure it's valid (easy, medium, or hard)
        # Use the same normalization logic as KnowledgeGraphService
        from services.knowledge_graph_service import KnowledgeGraphService
        raw_difficulty = question_data.get('difficulty')
        difficulty = KnowledgeGraphService._normalize_difficulty(raw_difficulty)
        
        # Create question with embedding and status
        question_id = await self.question_repo.create_question(
            concept_id=concept_id,
            text=question_data['text'],
            question_type=question_data.get('type', 'multiple_choice'),
            difficulty=difficulty,
            metadata=metadata,
            status='generated',
            embedding=embedding
        )
        
        logger.info(f"Stored generated question {question_id} for concept {concept_id}")
        return question_id
    
    async def generate_questions_for_concept(
        self,
        concept_id: str,
        num_questions: int = 10,
        question_type: str = "multiple_choice",
        difficulty: Optional[str] = None,
        grade_level: int = 8,
        similarity_threshold: float = 0.85,
        max_attempts: int = 20,
        subject_id: Optional[str] = None,
        selected_topics: Optional[List[str]] = None,
        force_generate: bool = False,
        subject_profile: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate multiple questions for a concept with deduplication.
        
        Args:
            concept_id: Concept UUID
            num_questions: Number of questions to generate
            question_type: Type of questions to generate
            difficulty: Difficulty level (optional)
            grade_level: Grade level for age-appropriate language
            similarity_threshold: Similarity threshold for deduplication
            max_attempts: Maximum generation attempts (to handle duplicates)
            subject_id: Subject ID for subject-specific generation rules
            selected_topics: List of selected topics
            force_generate: Force generation even if pool is sufficient
            subject_profile: Subject profile JSON dictionary
            
        Returns:
            Dictionary with generation results
        """
        # Check existing pool unless we explicitly want to force new generation
        if not force_generate:
            pool_status = await self.check_question_pool(
                concept_id, difficulty, question_type, num_questions
            )
            
            if pool_status['sufficient']:
                logger.info(f"Sufficient questions in pool ({pool_status['count']}), skipping generation")
                return {
                    'generated': False,
                    'reason': 'sufficient_pool',
                    'existing_count': pool_status['count'],
                    'questions': pool_status['existing_questions']
                }
        
        # Get concept metadata
        concept_metadata = await self.get_concept_metadata(concept_id)
        
        # Get subject-specific question type if not specified
        if subject_id and not question_type:
            subject_id = normalize_subject_name(subject_id)
            gen_config = get_question_generation_config(subject_id)
            preferred_types = gen_config.get("preferred_question_types", ["multiple_choice"])
            question_type = preferred_types[0] if preferred_types else "multiple_choice"
        
        # Normalize subject_id
        if subject_id:
            subject_id = normalize_subject_name(subject_id)
        
        # Get subject profile if not provided
        if subject_id and not subject_profile:
            subject_profile = get_subject_profile(subject_id)
        
        # Generate all questions in one batch request
        generated_questions = []
        duplicates = 0
        attempts = 0
        
        try:
            attempts += 1
            # Generate all questions via LLM in one request
            gen_results = await self.generate_all_questions_via_llm(
                concept_metadata,
                num_questions=num_questions,
                question_type=question_type,
                difficulty=difficulty,
                grade_level=grade_level,
                subject_id=subject_id,
                selected_topics=selected_topics,
                subject_profile=subject_profile,
            )
            
            # Process each generated question: check duplicates and store
            for gen_result in gen_results:
                blueprint: GeneratedQuestionBlueprint = gen_result["blueprint"]
                raw = gen_result["raw"]
                
                question_text = blueprint.question_text
                
                # Check for semantic duplicates
                duplicate_check = await self.check_semantic_duplicate(
                    question_text,
                    concept_id,
                    similarity_threshold
                )
                
                if duplicate_check['is_duplicate']:
                    duplicates += 1
                    logger.debug(
                        f"Question duplicate detected (similarity: {duplicate_check['max_similarity']:.2f}), skipping"
                    )
                    continue
                
                # Map blueprint into storage-friendly question_data shape
                options_text = [opt.text for opt in blueprint.options]
                question_data_for_storage = {
                    "text": blueprint.question_text,
                    "type": blueprint.question_type,
                    "difficulty": blueprint.difficulty,
                    "options": options_text,
                    "answer": blueprint.correct_answer,
                    "explanation": blueprint.metadata.get("explanation") or raw.get("explanation", ""),
                    "blueprint": blueprint.dict(),
                }
                
                # Store question
                question_id = await self.store_generated_question(
                    concept_id,
                    question_data_for_storage,
                    question_text
                )
                
                generated_questions.append({
                    'question_id': question_id,
                    'text': question_text,
                    'type': blueprint.question_type,
                    'difficulty': blueprint.difficulty
                })
                
                logger.info(f"Generated and stored question {len(generated_questions)}/{num_questions}")
            
            logger.info(f"Batch generation completed: {len(generated_questions)}/{num_questions} questions stored (skipped {duplicates} duplicates)")
            
        except Exception as e:
            logger.error(f"Error generating questions in batch: {e}")
            # If batch generation fails, we could fall back to individual generation
            # but for now, we'll just return what we have
            pass
        
        return {
            'generated': True,
            'concept_id': concept_id,
            'requested': num_questions,
            'generated_count': len(generated_questions),
            'attempts': attempts,
            'duplicates': duplicates,
            'questions': generated_questions
        }
