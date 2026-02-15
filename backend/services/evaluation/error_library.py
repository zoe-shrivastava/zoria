"""Error classification library for standardized error types."""

from enum import Enum
from typing import Optional


class ErrorType(str, Enum):
    """Standardized error types for student responses."""
    
    NONE = "None"
    ARITHMETIC = "Arithmetic"
    CONCEPTUAL = "Conceptual"
    PROCEDURAL = "Procedural"
    UNIT_MISMATCH = "Unit_Mismatch"
    SIGN_ERROR = "Sign_Error"
    ORDER_OF_OPERATIONS = "Order_Of_Operations"
    FORMULA_SELECTION = "Formula_Selection"
    IRRELEVANT = "Irrelevant"


class ErrorLibrary:
    """Library for error classification and mapping."""
    
    @staticmethod
    def classify_error(
        error_type: Optional[str],
        method_detected: Optional[str] = None,
        student_answer: Optional[str] = None,
        expected_answer: Optional[str] = None
    ) -> ErrorType:
        """Classify error type from evaluation result.
        
        Args:
            error_type: Error type string from evaluator
            method_detected: Method detected by evaluator
            student_answer: Student's answer
            expected_answer: Expected answer
            
        Returns:
            ErrorType enum value
        """
        if not error_type:
            return ErrorType.NONE
        
        error_upper = error_type.strip().upper()
        
        # Map common error patterns
        if error_upper in ["ARITHMETIC", "CALCULATION", "COMPUTATION"]:
            return ErrorType.ARITHMETIC
        elif error_upper in ["CONCEPTUAL", "CONCEPT", "MISCONCEPTION"]:
            return ErrorType.CONCEPTUAL
        elif error_upper in ["PROCEDURAL", "PROCEDURE", "PROCESS"]:
            return ErrorType.PROCEDURAL
        elif error_upper in ["UNIT", "UNIT_MISMATCH", "UNITS"]:
            return ErrorType.UNIT_MISMATCH
        elif error_upper in ["SIGN", "SIGN_ERROR", "DIRECTION"]:
            return ErrorType.SIGN_ERROR
        elif error_upper in ["ORDER", "ORDER_OF_OPERATIONS", "OPERATIONS"]:
            return ErrorType.ORDER_OF_OPERATIONS
        elif error_upper in ["FORMULA", "FORMULA_SELECTION", "METHOD"]:
            return ErrorType.FORMULA_SELECTION
        elif error_upper in ["IRRELEVANT", "OFF_TOPIC", "NONSENSICAL"]:
            return ErrorType.IRRELEVANT
        
        # Try to infer from method_detected or answer comparison
        if method_detected:
            method_lower = method_detected.lower()
            if "wrong formula" in method_lower or "incorrect method" in method_lower:
                return ErrorType.FORMULA_SELECTION
            if "calculation" in method_lower or "computation" in method_lower:
                return ErrorType.ARITHMETIC
        
        # Default to NONE if we can't classify
        return ErrorType.NONE
    
    @staticmethod
    def get_mastery_penalty(error_type: ErrorType) -> float:
        """Get mastery penalty multiplier based on error type.
        
        Args:
            error_type: Classified error type
            
        Returns:
            Penalty multiplier (0.0 to 1.0, where 1.0 = no penalty)
        """
        # Conceptual errors are more serious than arithmetic
        penalties = {
            ErrorType.NONE: 1.0,
            ErrorType.ARITHMETIC: 0.8,  # 20% penalty
            ErrorType.PROCEDURAL: 0.7,  # 30% penalty
            ErrorType.CONCEPTUAL: 0.5,  # 50% penalty (deep misconception)
            ErrorType.UNIT_MISMATCH: 0.9,  # 10% penalty
            ErrorType.SIGN_ERROR: 0.85,  # 15% penalty
            ErrorType.ORDER_OF_OPERATIONS: 0.75,  # 25% penalty
            ErrorType.FORMULA_SELECTION: 0.6,  # 40% penalty
            ErrorType.IRRELEVANT: 0.3,  # 70% penalty
        }
        return penalties.get(error_type, 1.0)
