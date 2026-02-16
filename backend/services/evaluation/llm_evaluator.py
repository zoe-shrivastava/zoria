"""LLM evaluator for FRQ and conceptual questions using rubric-based grading."""

import logging
import json
from typing import Dict, Any, Tuple, Optional

from .error_library import ErrorType, ErrorLibrary

logger = logging.getLogger(__name__)


class LLMEvaluator:
    """Evaluator for free-response and conceptual questions using LLM."""
    
    # System prompt template for rubric-based evaluation
    SYSTEM_PROMPT_TEMPLATE = """
  # Role: High-Fidelity Educational Evaluator
You are an expert evaluator. Your goal is to validate the student's **Conceptual Accuracy** and **Logical Consistency**.

## 1. CORE PRINCIPLES
- **Concept Over Keywords**: If a student describes a process correctly or uses correct bond names (e.g., "glycosidic"), do not penalize them for missing a secondary keyword (e.g., "dehydration synthesis") unless it is the primary subject of the question.
- **Math Over Formatting**: If a calculation is correct (e.g., 180 * 50 = 9000), it is correct. Never penalize for lack of LaTeX, missing bolding, or informal symbols like `*` or `x`.
- **Ignore "Missing Steps" if Logic is Clear**: If a one-step calculation is shown, do not claim "steps are missing." 
- **Review calculation for each step**: If the student's calculation is correct, do not penalize them for missing a step.There should be penalty for step calculation errors.
-**Final Answer**: Ensure that the student's final answer is correct and complete. There should be penalty for final answer errors.

## 1.1 NEW VALIDATION RULE:
- If the student's statement is scientifically accurate (e.g., "carbohydrates have glycosidic bonds"), DO NOT mark it as incorrect. 
- Do not penalize for missing keywords that were not explicitly requested in the prompt.
- If the logic is sound, the score must be 1.0/1.0 (or 4.0/4.0).

## 2. SCORING SCALE

Use the following criteria to ensure objective and granular grading. Scores must reflect the presence of relevant scientific/mathematical reasoning.

| Score | Rating | Primary Criteria |
| :--- | :--- | :--- |
| **4.0** | **Correct** | **Flawless.** Sound logic, correct methodology, and accurate final answer (including units). |
| **3.5** | **Minor Slip** | **Mechanical Error.** Correct conceptual path and logic, but includes a non-conceptual typo (e.g., arithmetic error or missing units). |
| **2.5** | **Partial Mastery** | **Procedural Error.** Correct identification of principles/formulas, but the execution breaks down significantly or is incomplete. |
| **1.0** | **Conceptual Pivot** | **Fundamental Misunderstanding.** The student attempts to answer using relevant terminology but applies the wrong logic, formula, or framework. |
| **0.0** | **No Merit** | **Non-Responsive.** The answer is blank, contains gibberish (e.g., "abcd"), or is entirely irrelevant to the question. |

---

### EVALUATION PROTOCOL
1. **Detect Substance:** Before grading, determine if the response contains actual subject-matter content. 
2. **Zero-Tolerance for Gibberish:** If the student's answer consists of random characters, placeholder text, or unrelated "noise," it **must** be scored a **0.0**.
3. **Keyword Check:** For a score of 1.0 or higher, the student must demonstrate a baseline attempt to engage with the specific keywords (e.g., "bonds," "heat," "denaturation").
4. **Logic Over Layout:** Ignore LaTeX formatting or "steps" style; focus entirely on the scientific accuracy of the statements provided.

## 3. FEEDBACK RULES
- **Do not hallucinate errors**: If the student's statement is scientifically true (e.g., "Carbs have glycosidic bonds"), do not call it incorrect.
- **LaTeX Safety**: In your JSON output, use double-backslashes for all LaTeX: `\\text{g/mol}`.

## 4. CRITICAL: JSON-LaTeX ENCODING
- **Double Backslashes**: Every LaTeX command must use double backslashes. 
  - USE: `\\text{m/s}` | `\\frac{1}{2}` | `\\times`
- **Avoid Mixed Styles**: Do not use bold markdown (`**`) inside or around LaTeX.
- **Escape Newlines**: Use `\n` for line breaks in the feedback string.


## 5. OUTPUT FORMAT (Strict JSON Only)
{
  "score": float,
  "method_detected": "string",
  "error_type": "Arithmetic | Conceptual | Procedural | None",
  "misconception": "string | null",
  "detailed_feedback": "string"
}
    """

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
                max_tokens=1200,  # Increased for detailed step-by-step feedback
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
            "1. Identify the logical components in the student's answer.",
            "2. Compare the math and concepts against the Expected Solution.",
            "3. Apply the Penalty Scale: award 4.0 for correct logic/answer, 3.5 for minor slips, and 2.5-3.0 for procedural errors.",
            "4. Ignore all formatting and LaTeX differences.",
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
        
        # Handle detailed_feedback - ensure it's a string, not an object
        detailed_feedback = result.get('detailed_feedback')
        if detailed_feedback is not None:
            if isinstance(detailed_feedback, dict):
                # If it's a dict, convert to formatted string
                parts = []
                for key, value in detailed_feedback.items():
                    if isinstance(value, str):
                        parts.append(f"{key}: {value}")
                    else:
                        parts.append(f"{key}: {str(value)}")
                detailed_feedback = "\n".join(parts)
            elif not isinstance(detailed_feedback, str):
                # Convert other types to string
                detailed_feedback = str(detailed_feedback)
        
        return {
            'score': score,
            'method_detected': result.get('method_detected', 'llm_evaluation'),
            'error_type': error_type,
            'misconception': result.get('misconception'),
            'detailed_feedback': detailed_feedback,
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
