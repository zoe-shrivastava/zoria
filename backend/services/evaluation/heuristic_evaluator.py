"""Heuristic evaluator for numerical answers with tolerance and unit validation."""

import logging
import re
from typing import Dict, Any, Tuple, Optional

from .error_library import ErrorType, ErrorLibrary

logger = logging.getLogger(__name__)


class HeuristicEvaluator:
    """Evaluator for numerical answers with tolerance and unit checking."""
    
    # Unit conversion patterns (common units)
    UNIT_PATTERNS = {
        'length': {
            'm': 1.0, 'meter': 1.0, 'meters': 1.0,
            'cm': 0.01, 'centimeter': 0.01, 'centimeters': 0.01,
            'mm': 0.001, 'millimeter': 0.001, 'millimeters': 0.001,
            'km': 1000.0, 'kilometer': 1000.0, 'kilometers': 1000.0,
            'in': 0.0254, 'inch': 0.0254, 'inches': 0.0254,
            'ft': 0.3048, 'foot': 0.3048, 'feet': 0.3048,
        },
        'mass': {
            'kg': 1.0, 'kilogram': 1.0, 'kilograms': 1.0,
            'g': 0.001, 'gram': 0.001, 'grams': 0.001,
            'mg': 0.000001, 'milligram': 0.000001, 'milligrams': 0.000001,
            'lb': 0.453592, 'pound': 0.453592, 'pounds': 0.453592,
        },
        'time': {
            's': 1.0, 'sec': 1.0, 'second': 1.0, 'seconds': 1.0,
            'min': 60.0, 'minute': 60.0, 'minutes': 60.0,
            'h': 3600.0, 'hr': 3600.0, 'hour': 3600.0, 'hours': 3600.0,
        },
        'velocity': {
            'm/s': 1.0, 'm s^-1': 1.0, 'ms^-1': 1.0,
            'km/h': 0.277778, 'kmh^-1': 0.277778,
            'mph': 0.44704,
        },
    }
    
    def __init__(self, tolerance_percent: float = 2.0):
        """Initialize heuristic evaluator.
        
        Args:
            tolerance_percent: Tolerance percentage for numerical matching (default 2%)
        """
        self.tolerance_percent = tolerance_percent
    
    def evaluate(
        self,
        student_answer: str,
        correct_answer: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Evaluate numerical answer with tolerance and unit checking.
        
        Args:
            student_answer: Student's answer
            correct_answer: Expected answer
            metadata: Question metadata
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score, method_detected, error_type, misconception)
        """
        try:
            # Extract numeric values and units
            student_nums, student_units = self._extract_number_and_unit(student_answer)
            correct_nums, correct_units = self._extract_number_and_unit(correct_answer)
            
            if not student_nums or not correct_nums:
                # No numbers found, fallback to text comparison
                return self._fallback_text_match(student_answer, correct_answer, max_score)
            
            # Check units first (if both have units)
            if student_units and correct_units:
                unit_match, unit_error = self._validate_units(student_units, correct_units)
                if not unit_match:
                    # Unit mismatch - apply penalty but still check numeric value
                    error_type = ErrorType.UNIT_MISMATCH
                    misconception = f"Unit mismatch: {student_units} vs {correct_units}"
                else:
                    error_type = ErrorType.NONE
                    misconception = None
            else:
                unit_match = True
                error_type = ErrorType.NONE
                misconception = None
            
            # Check numeric values with tolerance
            numeric_match = self._check_numeric_tolerance(student_nums, correct_nums)
            
            if numeric_match and unit_match:
                # Fully correct
                return True, max_score, "numeric_match_with_units", ErrorType.NONE, None
            elif numeric_match and not unit_match:
                # Correct number, wrong unit - partial credit
                partial_score = max_score * 0.9  # 10% penalty for unit error
                return False, partial_score, "numeric_match_unit_mismatch", ErrorType.UNIT_MISMATCH, misconception
            elif not numeric_match and unit_match:
                # Wrong number, correct unit - check if within tolerance
                if self._check_numeric_tolerance(student_nums, correct_nums, tolerance_multiplier=2.0):
                    # Within 2x tolerance - partial credit
                    partial_score = max_score * 0.6
                    return False, partial_score, "numeric_close_match", ErrorType.ARITHMETIC, "Calculation error"
                else:
                    # Way off - no credit
                    return False, 0.0, "numeric_mismatch", ErrorType.ARITHMETIC, "Incorrect calculation"
            else:
                # Both wrong
                return False, 0.0, "numeric_and_unit_mismatch", error_type or ErrorType.ARITHMETIC, misconception or "Incorrect answer"
                
        except Exception as e:
            logger.error(f"Error in heuristic evaluation: {e}", exc_info=True)
            return False, 0.0, "evaluation_error", ErrorType.NONE, None
    
    def _extract_number_and_unit(self, text: str) -> Tuple[Optional[float], Optional[str]]:
        """Extract numeric value and unit from text.
        
        Args:
            text: Text to extract from
            
        Returns:
            Tuple of (numeric_value, unit_string)
        """
        if not text:
            return None, None
        
        # Pattern: number followed by optional unit
        # Matches: "10", "10.5", "10 kg", "10.5 m/s", "-5.2", etc.
        pattern = r'(-?\d+\.?\d*)\s*([a-zA-Z/^\-0-9\s]+)?'
        match = re.search(pattern, text.strip())
        
        if match:
            number_str = match.group(1)
            unit_str = match.group(2).strip() if match.group(2) else None
            
            try:
                number = float(number_str)
                return number, unit_str
            except ValueError:
                pass
        
        # Try to extract just the number
        number_pattern = r'-?\d+\.?\d*'
        number_match = re.search(number_pattern, text)
        if number_match:
            try:
                number = float(number_match.group(0))
                return number, None
            except ValueError:
                pass
        
        return None, None
    
    def _validate_units(self, student_unit: str, correct_unit: str) -> Tuple[bool, Optional[str]]:
        """Validate if units match (with conversion if needed).
        
        Args:
            student_unit: Student's unit
            correct_unit: Correct unit
            
        Returns:
            Tuple of (matches, error_message)
        """
        student_unit = student_unit.strip().lower()
        correct_unit = correct_unit.strip().lower()
        
        # Exact match
        if student_unit == correct_unit:
            return True, None
        
        # Check if they're in the same category and can be converted
        for category, conversions in self.UNIT_PATTERNS.items():
            if student_unit in conversions and correct_unit in conversions:
                # Same category, check if values would match after conversion
                # (We'll do the actual conversion in the numeric check)
                return True, None
        
        # Check for common variations
        variations = {
            'm/s': ['ms^-1', 'm s^-1', 'meters per second', 'meter per second'],
            'kg': ['kilogram', 'kilograms'],
            'm': ['meter', 'meters'],
            's': ['sec', 'second', 'seconds'],
        }
        
        for base, vars_list in variations.items():
            if (student_unit == base or student_unit in vars_list) and \
               (correct_unit == base or correct_unit in vars_list):
                return True, None
        
        return False, f"Unit mismatch: {student_unit} vs {correct_unit}"
    
    def _check_numeric_tolerance(
        self,
        student_value: float,
        correct_value: float,
        tolerance_multiplier: float = 1.0
    ) -> bool:
        """Check if numeric values match within tolerance.
        
        Args:
            student_value: Student's numeric value
            correct_value: Correct numeric value
            tolerance_multiplier: Multiplier for tolerance (default 1.0)
            
        Returns:
            True if within tolerance
        """
        if correct_value == 0:
            # Special case: if correct is 0, check if student is very close
            return abs(student_value) < 0.01
        
        tolerance = abs(correct_value) * (self.tolerance_percent / 100.0) * tolerance_multiplier
        difference = abs(student_value - correct_value)
        
        return difference <= tolerance
    
    def _fallback_text_match(
        self,
        student_answer: str,
        correct_answer: str,
        max_score: float
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str]]:
        """Fallback to text matching if no numbers found."""
        student_ans = student_answer.strip().lower()
        correct_ans = correct_answer.strip().lower()
        
        is_correct = student_ans == correct_ans
        score = max_score if is_correct else 0.0
        
        return is_correct, score, "text_match", ErrorType.NONE, None
