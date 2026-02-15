"""Deterministic evaluator for MCQ, Matching, and Fill-in-the-Blank questions."""

import logging
import json
from typing import Dict, Any, Tuple, Optional

from .error_library import ErrorType, ErrorLibrary

logger = logging.getLogger(__name__)


class DeterministicEvaluator:
    """Evaluator for questions with exact answer matching."""
    
    def evaluate(
        self,
        student_answer: str,
        correct_answer: Any,
        question_type: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate student answer using exact matching.
        
        Args:
            student_answer: Student's answer
            correct_answer: Correct answer (can be string, index, or dict for matching)
            question_type: Type of question
            metadata: Question metadata
            max_score: Maximum score for this question
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception)
        """
        try:
            if question_type == 'multiple_choice':
                return self._evaluate_mcq(student_answer, correct_answer, metadata, max_score)
            elif question_type == 'matching':
                return self._evaluate_matching(student_answer, correct_answer, metadata, max_score)
            elif question_type == 'fill_in_the_blank':
                return self._evaluate_fill_in_blank(student_answer, correct_answer, metadata, max_score)
            else:
                # Default: exact string match
                return self._evaluate_exact_match(student_answer, correct_answer, max_score)
        except Exception as e:
            logger.error(f"Error in deterministic evaluation: {e}", exc_info=True)
            return False, 0.0, "evaluation_error", ErrorType.NONE, None
    
    def _evaluate_mcq(
        self,
        student_answer: str,
        correct_answer: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate multiple choice question."""
        options = metadata.get('options', [])
        
        if not correct_answer or not options:
            return False, 0.0, "missing_correct_answer", ErrorType.NONE, None
        
        # Normalize answers
        student_ans = str(student_answer).strip()
        correct_ans = str(correct_answer).strip()
        
        # Convert to indices
        student_idx = self._answer_to_index(student_ans, options)
        correct_idx = self._answer_to_index(correct_ans, options)
        
        if student_idx is None or correct_idx is None:
            # Fallback: text comparison
            is_correct = student_ans.lower() == correct_ans.lower()
        else:
            is_correct = student_idx == correct_idx
        
        if is_correct:
            return True, max_score, "exact_match", ErrorType.NONE, None
        else:
            # Check error pattern map for misconception
            error_pattern_map = metadata.get('error_pattern_map', {})
            misconception = None
            error_type = ErrorType.NONE
            
            if student_idx is not None and student_idx < len(options):
                option_label = chr(ord('A') + student_idx)
                error_pattern = error_pattern_map.get(option_label)
                if error_pattern:
                    misconception = error_pattern
                    # Map error pattern to error type
                    error_type = ErrorLibrary.classify_error(error_pattern)
            
            return False, 0.0, "incorrect_selection", error_type, misconception
    
    def _evaluate_matching(
        self,
        student_answer: str,
        correct_answer: Any,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate matching question."""
        try:
            # Parse student answer (should be JSON object)
            student_matches = json.loads(student_answer) if isinstance(student_answer, str) else student_answer
            
            # Parse correct answer (should be JSON object)
            if isinstance(correct_answer, str):
                correct_matches = json.loads(correct_answer)
            else:
                correct_matches = correct_answer
            
            if not isinstance(student_matches, dict) or not isinstance(correct_matches, dict):
                return False, 0.0, "invalid_format", ErrorType.PROCEDURAL, "Invalid matching format"
            
            # Count correct matches
            total_pairs = len(correct_matches)
            if total_pairs == 0:
                return False, 0.0, "no_correct_answer", ErrorType.NONE, None
            
            correct_count = 0
            for key, value in correct_matches.items():
                if student_matches.get(key) == value:
                    correct_count += 1
            
            # Partial credit based on correct matches
            score = max_score * (correct_count / total_pairs)
            is_correct = correct_count == total_pairs
            
            method = f"matched_{correct_count}_of_{total_pairs}"
            error_type = ErrorType.NONE if is_correct else ErrorType.PROCEDURAL
            
            return is_correct, score, method, error_type, None
            
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"Error parsing matching answer: {e}")
            return False, 0.0, "parse_error", ErrorType.PROCEDURAL, "Could not parse matching pairs"
    
    def _evaluate_fill_in_blank(
        self,
        student_answer: str,
        correct_answer: Any,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate fill-in-the-blank question."""
        try:
            # Parse student answer (should be JSON array)
            student_answers = json.loads(student_answer) if isinstance(student_answer, str) else student_answer
            
            # Parse correct answer (should be JSON array)
            if isinstance(correct_answer, str):
                correct_answers = json.loads(correct_answer)
            else:
                correct_answers = correct_answer
            
            if not isinstance(student_answers, list) or not isinstance(correct_answers, list):
                return False, 0.0, "invalid_format", ErrorType.PROCEDURAL, "Invalid fill-in-the-blank format"
            
            # Count correct blanks
            total_blanks = len(correct_answers)
            if total_blanks == 0:
                return False, 0.0, "no_correct_answer", ErrorType.NONE, None
            
            correct_count = 0
            for i, correct in enumerate(correct_answers):
                if i < len(student_answers):
                    student_ans = str(student_answers[i]).strip().lower()
                    correct_ans = str(correct).strip().lower()
                    if student_ans == correct_ans:
                        correct_count += 1
            
            # Partial credit based on correct blanks
            score = max_score * (correct_count / total_blanks)
            is_correct = correct_count == total_blanks
            
            method = f"filled_{correct_count}_of_{total_blanks}_blanks"
            error_type = ErrorType.NONE if is_correct else ErrorType.PROCEDURAL
            
            return is_correct, score, method, error_type, None
            
        except (json.JSONDecodeError, TypeError, AttributeError) as e:
            logger.warning(f"Error parsing fill-in-the-blank answer: {e}")
            return False, 0.0, "parse_error", ErrorType.PROCEDURAL, "Could not parse fill-in-the-blank answers"
    
    def _evaluate_exact_match(
        self,
        student_answer: str,
        correct_answer: str,
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate using exact string match."""
        student_ans = str(student_answer).strip().lower()
        correct_ans = str(correct_answer).strip().lower()
        
        is_correct = student_ans == correct_ans
        score = max_score if is_correct else 0.0
        
        return is_correct, score, "exact_match", ErrorType.NONE, None
    
    def _answer_to_index(self, answer: str, options: list) -> Optional[int]:
        """Convert answer (letter or index) to option index."""
        answer = answer.strip()
        
        # If it's a digit, use directly
        if answer.isdigit():
            idx = int(answer)
            if 0 <= idx < len(options):
                return idx
        
        # If it's a single letter, convert to index
        if len(answer) == 1 and answer.upper() in ['A', 'B', 'C', 'D', 'E', 'F']:
            return ord(answer.upper()) - ord('A')
        
        # Try to find in options by text match
        answer_lower = answer.lower()
        for idx, option in enumerate(options):
            option_text = str(option).lower() if not isinstance(option, dict) else str(option.get('text', '')).lower()
            if answer_lower in option_text or option_text in answer_lower:
                return idx
        
        return None
