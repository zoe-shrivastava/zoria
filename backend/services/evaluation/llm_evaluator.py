"""LLM evaluator for FRQ and conceptual questions using rubric-based grading."""

import logging
import json
from typing import Dict, Any, Tuple, Optional

from .error_library import ErrorType, ErrorLibrary

logger = logging.getLogger(__name__)


class LLMEvaluator:
    """Evaluator for free-response and conceptual questions using LLM."""
    
    # System prompt template for rubric-based evaluation
    SYSTEM_PROMPT_TEMPLATE = """You are an expert educational evaluator. Your task is to grade student responses using a strict 4-point rubric that considers both semantic correctness and solution process.

EVALUATION PRINCIPLES:
1. **Semantic Equivalence**: Accept answers that are semantically correct even if wording differs. For example:
   - "25 meters" = "25 m" = "25.0 m" = "25.00 m"
   - "The object accelerates" = "Acceleration occurs" = "It speeds up"
   - "Distance is 25 m and speed is 10 m/s" = "25 m distance, 10 m/s final speed"
2. **Process Evaluation**: Evaluate the solution steps/work shown, not just the final answer:
   - If the student shows correct steps but makes a minor calculation error, award partial credit
   - If the student uses the correct method/formula but gets a slightly wrong answer, recognize the understanding
   - If the student shows work that demonstrates understanding, reward the process even if final answer is incomplete
3. **Multi-part Answers**: For questions with multiple parts, evaluate each part separately and provide feedback on each

RUBRIC:
- Correct (4.0/4.0): Answer is fully correct (semantically equivalent) and demonstrates complete understanding. All parts are correct.
- Partially Correct (2.0-3.5/4.0): Answer shows understanding but has minor issues:
  - Correct process/steps but minor calculation error
  - Correct method but incomplete answer (missing one part)
  - Semantically correct but missing units or formatting
  - One part correct, one part incorrect
- Incorrect but Attempted (1.0-1.5/4.0): Answer is wrong but shows some relevant knowledge:
  - Wrong method but demonstrates understanding of concepts
  - Correct approach but significant calculation error
  - Partially correct steps but wrong conclusion
- Irrelevant (0.0/4.0): Answer is completely off-topic, nonsensical, or shows no understanding

OUTPUT FORMAT (JSON only, no markdown):
{{
  "score": float (0.0-4.0),
  "method_detected": "string (brief description of approach used)",
  "error_type": "Arithmetic|Conceptual|Procedural|None",
  "misconception": "string (if applicable, describe the misconception)",
  "detailed_feedback": "string (detailed explanation of what is wrong, what is missing, or what needs correction. Be specific about which parts are correct and which are incorrect)"
}}

CONSTRAINTS:
- Output ONLY valid JSON, no markdown code fences, no explanations
- Score must be between 0.0 and 4.0
- error_type must be exactly one of: Arithmetic, Conceptual, Procedural, None
- If error_type is not None, misconception must describe the specific error
- method_detected should briefly describe the approach (e.g., "used correct formula", "applied wrong method")
- detailed_feedback must provide specific, actionable feedback about what is wrong, what is missing, or what is correct. For multi-part answers, identify which parts are correct/incorrect."""

    def __init__(self, llm_service, temperature: float = 0.1):
        """Initialize LLM evaluator.
        
        Args:
            llm_service: LLM service instance
            temperature: Temperature for LLM (default 0.1 for reproducibility)
        """
        self.llm_service = llm_service
        self.temperature = temperature
    
    async def evaluate(
        self,
        student_answer: str,
        expected_answer: str,
        question_text: str,
        metadata: Dict[str, Any],
        max_score: float,
        concept_tags: Optional[list] = None,
        solution_steps: Optional[list] = None
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str], Optional[str]]:
        """Evaluate student answer using LLM with rubric.
        
        Args:
            student_answer: Student's answer (may include solution steps/work shown)
            expected_answer: Expected correct answer
            question_text: Original question text
            metadata: Question metadata
            max_score: Maximum score for this question
            concept_tags: Optional concept tags for context
            solution_steps: Optional list of expected solution steps for process evaluation
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception, detailed_feedback)
        """
        if not self.llm_service:
            logger.warning("LLM service not available, falling back to basic evaluation")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        
        try:
            # Build user prompt with rubric context
            user_prompt = self._build_evaluation_prompt(
                question_text, student_answer, expected_answer, concept_tags, solution_steps
            )
            
            # Call LLM with strict JSON output
            response = await self.llm_service.generate_json(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT_TEMPLATE,
                temperature=self.temperature,
                max_tokens=800,  # Increased for detailed feedback
            )
            
            # Parse and validate response
            evaluation_result = self._parse_llm_response(response, max_score)
            
            # Extract components
            score = evaluation_result['score']
            method_detected = evaluation_result.get('method_detected', 'llm_evaluation')
            error_type_str = evaluation_result.get('error_type', 'None')
            misconception = evaluation_result.get('misconception')
            detailed_feedback = evaluation_result.get('detailed_feedback')
            
            # Classify error type
            error_type = ErrorLibrary.classify_error(
                error_type_str, method_detected, student_answer, expected_answer
            )
            
            # Convert score from 4-point scale to max_score scale
            normalized_score = (score / 4.0) * max_score
            
            # Determine if correct (score >= 3.0 on 4-point scale, or >= 75% of max)
            is_correct = normalized_score >= (max_score * 0.75)
            
            logger.info(
                f"LLM evaluation: score={normalized_score:.2f}/{max_score:.2f}, "
                f"error_type={error_type.value}, is_correct={is_correct}"
            )
            
            return is_correct, normalized_score, method_detected, error_type, misconception, detailed_feedback
            
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM JSON response, using fallback: {e}")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        except ValueError as e:
            if "empty response" in str(e).lower():
                logger.warning(
                    f"LLM returned empty response for evaluation (model may not support JSON format), "
                    f"using fallback evaluation. Question type: {metadata.get('question_type', 'unknown')}"
                )
            else:
                logger.warning(f"LLM evaluation error, using fallback: {e}")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        except Exception as e:
            logger.warning(f"Unexpected error in LLM evaluation, using fallback: {e}", exc_info=True)
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
    
    def _build_evaluation_prompt(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
        concept_tags: Optional[list] = None,
        solution_steps: Optional[list] = None
    ) -> str:
        """Build evaluation prompt for LLM.
        
        Args:
            question_text: Original question
            student_answer: Student's response (may include work/steps)
            expected_answer: Expected answer
            concept_tags: Optional concept tags
            solution_steps: Optional list of expected solution steps
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "EVALUATE THE FOLLOWING STUDENT RESPONSE:",
            "",
            "QUESTION:",
            question_text,
            "",
            "STUDENT ANSWER (including any work/steps shown):",
            student_answer,
            "",
            "EXPECTED ANSWER:",
            expected_answer,
        ]
        
        if solution_steps:
            prompt_parts.extend([
                "",
                "EXPECTED SOLUTION STEPS (for process evaluation):",
            ])
            for i, step in enumerate(solution_steps, 1):
                prompt_parts.append(f"{i}. {step}")
        
        if concept_tags:
            prompt_parts.extend([
                "",
                "RELEVANT CONCEPTS:",
                ", ".join(concept_tags),
            ])
        
        prompt_parts.extend([
            "",
            "EVALUATION INSTRUCTIONS:",
            "1. **LaTeX Normalization**: When comparing answers, normalize LaTeX formatting:",
            "   - Treat LaTeX commands and their plain text equivalents as equivalent",
            "   - Example: '$9000 \\text{ g/mol}$' = '9000 g/mol' = '9000 g/mol'",
            "   - Example: '$25 \\text{ m}$' = '25 m' = '25 meters' = '25.0 m'",
            "   - Extract the semantic meaning from LaTeX, not just the formatting",
            "   - If expected answer has LaTeX but student answer is plain text, compare the semantic content",
            "",
            "2. **Semantic Evaluation**: Check if the student's answer is semantically equivalent to the expected answer, even if wording differs.",
            "   - Accept variations in units (m, meters, m.), formatting (25, 25.0, 25.00), and phrasing",
            "   - For multi-part answers, check each part separately",
            "   - Ignore LaTeX formatting differences if the semantic content matches",
            "",
            "3. **Process Evaluation**: If the student shows work/steps, evaluate the solution process:",
            "   - Check if the student used the correct method/formula/approach",
            "   - Identify which steps are correct and which have errors",
            "   - Award credit for correct process even if final answer has minor errors",
            "   - If solution_steps are provided, compare student's approach to expected steps",
            "",
            "4. **Multi-part Answer Analysis**:",
            "   - Identify each distinct part of the answer (e.g., distance, speed, units)",
            "   - Evaluate each part separately",
            "   - Note which parts are correct, incorrect, or missing",
            "",
            "5. **Scoring Guidelines**:",
            "   - 4.0: All parts correct, semantically equivalent, correct process",
            "   - 3.0-3.5: Correct process, minor calculation/formatting error, or one part missing",
            "   - 2.0-2.5: Correct method but significant error, or partially correct answer",
            "   - 1.0-1.5: Wrong answer but shows some understanding or correct initial steps",
            "   - 0.0: Completely wrong or irrelevant",
            "",
            "6. **Detailed Feedback**: Provide specific, actionable feedback about:",
            "   - Which parts are correct (if any) and why",
            "   - Which parts are incorrect or missing and what should be there",
            "   - If work is shown, which steps are correct/incorrect",
            "   - Specific values, units, or concepts that need correction",
            "   - What the student should have done differently",
            "   - For incorrect answers, explain the mistake clearly and suggest how to correct it",
            "",
            "7. Output ONLY valid JSON in the specified format (no markdown, no explanations outside JSON)",
        ])
        
        return "\n".join(prompt_parts)
    
    def _parse_llm_response(self, response: Dict[str, Any], max_score: float) -> Dict[str, Any]:
        """Parse and validate LLM response.
        
        Args:
            response: LLM response (may be dict or contain nested data)
            max_score: Maximum score for normalization
            
        Returns:
            Parsed evaluation result
        """
        # Handle different response formats
        if isinstance(response, dict):
            # Check if response has nested structure
            if 'evaluation' in response:
                result = response['evaluation']
            elif 'result' in response:
                result = response['result']
            else:
                result = response
        else:
            # Try to parse as JSON string
            try:
                result = json.loads(str(response))
            except (json.JSONDecodeError, TypeError):
                logger.error(f"Invalid LLM response format: {response}")
                return self._default_result(max_score)
        
        # Validate and normalize
        score = result.get('score', 0.0)
        if not isinstance(score, (int, float)):
            try:
                score = float(score)
            except (ValueError, TypeError):
                score = 0.0
        
        # Clamp score to 0-4.0 range
        score = max(0.0, min(4.0, float(score)))
        
        # Validate error_type
        error_type = result.get('error_type', 'None')
        valid_error_types = ['Arithmetic', 'Conceptual', 'Procedural', 'None']
        if error_type not in valid_error_types:
            error_type = 'None'
        
        return {
            'score': score,
            'method_detected': result.get('method_detected', 'llm_evaluation'),
            'error_type': error_type,
            'misconception': result.get('misconception'),
            'detailed_feedback': result.get('detailed_feedback'),
        }
    
    def _default_result(self, max_score: float) -> Dict[str, Any]:
        """Return default evaluation result when parsing fails."""
        return {
            'score': 0.0,
            'method_detected': 'evaluation_error',
            'error_type': 'None',
            'misconception': 'Could not evaluate response',
            'detailed_feedback': 'Unable to evaluate response due to parsing error',
        }
    
    def _fallback_evaluation(
        self,
        student_answer: str,
        expected_answer: str,
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str], Optional[str]]:
        """Fallback evaluation when LLM is unavailable.
        
        Args:
            student_answer: Student's answer
            expected_answer: Expected answer
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception, detailed_feedback)
        """
        # Simple text similarity check
        student_lower = student_answer.strip().lower()
        expected_lower = expected_answer.strip().lower()
        
        if student_lower == expected_lower:
            return True, max_score, "text_match", ErrorType.NONE, None, "Answer matches expected response"
        elif expected_lower in student_lower or student_lower in expected_lower:
            # Partial match
            feedback = f"Your answer is partially correct but incomplete. Expected: {expected_answer}"
            return False, max_score * 0.5, "partial_match", ErrorType.CONCEPTUAL, "Incomplete answer", feedback
        else:
            feedback = f"Your answer does not match the expected response. Expected: {expected_answer}"
            return False, 0.0, "no_match", ErrorType.CONCEPTUAL, "Answer does not match expected", feedback
