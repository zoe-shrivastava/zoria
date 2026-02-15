"""Question router for routing questions to appropriate evaluators."""

import logging
from typing import Dict, Any, Tuple, Optional

from .deterministic_evaluator import DeterministicEvaluator
from .heuristic_evaluator import HeuristicEvaluator
from .llm_evaluator import LLMEvaluator
from .error_library import ErrorType

logger = logging.getLogger(__name__)


class QuestionRouter:
    """Router for directing questions to appropriate evaluators."""
    
    def __init__(self, llm_service=None, tolerance_percent: float = 2.0):
        """Initialize question router.
        
        Args:
            llm_service: Optional LLM service for LLM evaluator
            tolerance_percent: Tolerance percentage for heuristic evaluator
        """
        self.deterministic_evaluator = DeterministicEvaluator()
        self.heuristic_evaluator = HeuristicEvaluator(tolerance_percent=tolerance_percent)
        self.llm_evaluator = LLMEvaluator(llm_service) if llm_service else None
        
        # Routing map: question_type -> evaluator_type
        self.routing_map = {
            'multiple_choice': 'deterministic',
            'matching': 'deterministic',
            'fill_in_the_blank': 'deterministic',
            'short_answer': 'heuristic',  # Can be numerical or text
            'problem_solving': 'llm',  # Complex FRQ
            'conceptual_question': 'llm',  # Requires understanding assessment
        }
    
    async def evaluate(
        self,
        student_answer: str,
        question_type: str,
        correct_answer: Any,
        expected_answer: Optional[str],
        metadata: Dict[str, Any],
        max_score: float,
        question_text: Optional[str] = None,
        concept_tags: Optional[list] = None,
        solution_steps: Optional[list] = None
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str], Optional[str]]:
        """Route question to appropriate evaluator and return result.
        
        Args:
            student_answer: Student's answer
            question_type: Type of question
            correct_answer: Correct answer (for MCQ/Matching)
            expected_answer: Expected answer (for FRQ)
            metadata: Question metadata
            max_score: Maximum score
            question_text: Question text (for LLM evaluator)
            concept_tags: Concept tags (for LLM evaluator)
            solution_steps: Optional list of expected solution steps (for LLM evaluator)
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception, detailed_feedback)
        """
        # Determine evaluator type
        evaluator_type = self.routing_map.get(question_type, 'deterministic')
        
        logger.debug(
            f"Routing question type '{question_type}' to '{evaluator_type}' evaluator"
        )
        
        try:
            if evaluator_type == 'deterministic':
                result = self.deterministic_evaluator.evaluate(
                    student_answer=student_answer,
                    correct_answer=correct_answer,
                    question_type=question_type,
                    metadata=metadata,
                    max_score=max_score
                )
                # Add None for detailed_feedback (deterministic evaluators don't provide it)
                return (*result, None)
            
            elif evaluator_type == 'heuristic':
                # For short_answer, check if it's numerical
                # If it has numbers, use heuristic; otherwise fallback to deterministic
                if self._is_numerical_answer(student_answer):
                    # Use expected_answer if available, otherwise correct_answer
                    answer_to_check = expected_answer or str(correct_answer) or ""
                    result = self.heuristic_evaluator.evaluate(
                        student_answer=student_answer,
                        correct_answer=answer_to_check,
                        metadata=metadata,
                        max_score=max_score
                    )
                    # Add None for detailed_feedback (heuristic evaluators don't provide it)
                    return (*result, None)
                else:
                    # Text-based short answer, use deterministic
                    result = self.deterministic_evaluator._evaluate_exact_match(
                        student_answer=student_answer,
                        correct_answer=expected_answer or str(correct_answer) or "",
                        max_score=max_score
                    )
                    return (*result, None)
            
            elif evaluator_type == 'llm':
                if not self.llm_evaluator:
                    logger.warning(
                        f"LLM evaluator not available for {question_type}, "
                        "falling back to deterministic"
                    )
                    result = self.deterministic_evaluator._evaluate_exact_match(
                        student_answer=student_answer,
                        correct_answer=expected_answer or str(correct_answer) or "",
                        max_score=max_score
                    )
                    return (*result, None)
                
                # Use expected_answer for LLM evaluation
                if not expected_answer:
                    logger.warning(
                        f"No expected_answer provided for {question_type}, "
                        "using correct_answer as fallback"
                    )
                    expected_answer = str(correct_answer) if correct_answer else ""
                
                return await self.llm_evaluator.evaluate(
                    student_answer=student_answer,
                    expected_answer=expected_answer,
                    question_text=question_text or "",
                    metadata=metadata,
                    max_score=max_score,
                    concept_tags=concept_tags,
                    solution_steps=solution_steps
                )
            
            else:
                # Unknown evaluator type, fallback to deterministic
                logger.warning(f"Unknown evaluator type '{evaluator_type}', using deterministic")
                result = self.deterministic_evaluator._evaluate_exact_match(
                    student_answer=student_answer,
                    correct_answer=expected_answer or str(correct_answer) or "",
                    max_score=max_score
                )
                return (*result, None)
                
        except Exception as e:
            logger.error(f"Error in question routing: {e}", exc_info=True)
            # Fallback to basic evaluation
            return False, 0.0, "routing_error", ErrorType.NONE, None, None
    
    def _is_numerical_answer(self, answer: str) -> bool:
        """Check if answer appears to be numerical.
        
        Args:
            answer: Student answer
            
        Returns:
            True if answer contains numbers
        """
        import re
        # Check if answer contains numeric patterns
        numeric_pattern = r'-?\d+\.?\d*'
        return bool(re.search(numeric_pattern, str(answer)))
