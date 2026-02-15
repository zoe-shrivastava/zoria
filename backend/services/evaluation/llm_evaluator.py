"""LLM evaluator for FRQ and conceptual questions using rubric-based grading."""

import logging
import json
from typing import Dict, Any, Tuple, Optional

from .error_library import ErrorType, ErrorLibrary

logger = logging.getLogger(__name__)


class LLMEvaluator:
    """Evaluator for free-response and conceptual questions using LLM."""
    
    # System prompt template for rubric-based evaluation
    SYSTEM_PROMPT_TEMPLATE = """You are an expert educational evaluator. Your task is to grade student responses using a strict 4-point rubric.

RUBRIC:
- Correct (4.0/4.0): Answer is fully correct and demonstrates complete understanding
- Partially Correct (2.0/4.0): Answer shows partial understanding with minor errors or omissions
- Incorrect (1.0/4.0): Answer is wrong but shows some relevant knowledge or attempt
- Irrelevant (0.0/4.0): Answer is completely off-topic, nonsensical, or shows no understanding

OUTPUT FORMAT (JSON only, no markdown):
{{
  "score": float (0.0-4.0),
  "method_detected": "string (brief description of approach used)",
  "error_type": "Arithmetic|Conceptual|Procedural|None",
  "misconception": "string (if applicable, describe the misconception)"
}}

CONSTRAINTS:
- Output ONLY valid JSON, no markdown code fences, no explanations
- Score must be between 0.0 and 4.0
- error_type must be exactly one of: Arithmetic, Conceptual, Procedural, None
- If error_type is not None, misconception must describe the specific error
- method_detected should briefly describe the approach (e.g., "used correct formula", "applied wrong method")"""

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
        concept_tags: Optional[list] = None
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate student answer using LLM with rubric.
        
        Args:
            student_answer: Student's answer
            expected_answer: Expected correct answer
            question_text: Original question text
            metadata: Question metadata
            max_score: Maximum score for this question
            concept_tags: Optional concept tags for context
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception)
        """
        if not self.llm_service:
            logger.warning("LLM service not available, falling back to basic evaluation")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        
        try:
            # Build user prompt with rubric context
            user_prompt = self._build_evaluation_prompt(
                question_text, student_answer, expected_answer, concept_tags
            )
            
            # Call LLM with strict JSON output
            response = await self.llm_service.generate_json(
                prompt=user_prompt,
                system_prompt=self.SYSTEM_PROMPT_TEMPLATE,
                temperature=self.temperature,
                max_tokens=500,  # Short response for JSON
            )
            
            # Parse and validate response
            evaluation_result = self._parse_llm_response(response, max_score)
            
            # Extract components
            score = evaluation_result['score']
            method_detected = evaluation_result.get('method_detected', 'llm_evaluation')
            error_type_str = evaluation_result.get('error_type', 'None')
            misconception = evaluation_result.get('misconception')
            
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
            
            return is_correct, normalized_score, method_detected, error_type, misconception
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM JSON response: {e}")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        except Exception as e:
            logger.error(f"Error in LLM evaluation: {e}", exc_info=True)
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
    
    def _build_evaluation_prompt(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
        concept_tags: Optional[list] = None
    ) -> str:
        """Build evaluation prompt for LLM.
        
        Args:
            question_text: Original question
            student_answer: Student's response
            expected_answer: Expected answer
            concept_tags: Optional concept tags
            
        Returns:
            Formatted prompt string
        """
        prompt_parts = [
            "EVALUATE THE FOLLOWING STUDENT RESPONSE:",
            "",
            "QUESTION:",
            question_text,
            "",
            "STUDENT ANSWER:",
            student_answer,
            "",
            "EXPECTED ANSWER:",
            expected_answer,
        ]
        
        if concept_tags:
            prompt_parts.extend([
                "",
                "RELEVANT CONCEPTS:",
                ", ".join(concept_tags),
            ])
        
        prompt_parts.extend([
            "",
            "INSTRUCTIONS:",
            "1. Compare the student answer to the expected answer",
            "2. Assess understanding using the 4-point rubric",
            "3. Identify any errors and classify the error type",
            "4. Output ONLY valid JSON in the specified format",
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
        }
    
    def _default_result(self, max_score: float) -> Dict[str, Any]:
        """Return default evaluation result when parsing fails."""
        return {
            'score': 0.0,
            'method_detected': 'evaluation_error',
            'error_type': 'None',
            'misconception': 'Could not evaluate response',
        }
    
    def _fallback_evaluation(
        self,
        student_answer: str,
        expected_answer: str,
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Fallback evaluation when LLM is unavailable.
        
        Args:
            student_answer: Student's answer
            expected_answer: Expected answer
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception)
        """
        # Simple text similarity check
        student_lower = student_answer.strip().lower()
        expected_lower = expected_answer.strip().lower()
        
        if student_lower == expected_lower:
            return True, max_score, "text_match", ErrorType.NONE, None
        elif expected_lower in student_lower or student_lower in expected_lower:
            # Partial match
            return False, max_score * 0.5, "partial_match", ErrorType.CONCEPTUAL, "Incomplete answer"
        else:
            return False, 0.0, "no_match", ErrorType.CONCEPTUAL, "Answer does not match expected"
