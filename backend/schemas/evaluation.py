"""Schemas for evaluation and behavioral tracking."""

from typing import Optional, Dict, Any
from pydantic import BaseModel, Field


class BehavioralPayload(BaseModel):
    """Behavioral data collected during question answering."""
    
    latency_ms: Optional[int] = Field(
        None,
        description="Time taken to answer in milliseconds (detects automaticity vs struggle)"
    )
    idle_time_ms: Optional[int] = Field(
        None,
        description="Time spent idle/not typing in milliseconds (detects distraction or freezing)"
    )
    edit_count: Optional[int] = Field(
        None,
        description="Number of times answer was edited (detects self-correction or trial & error)"
    )
    hints_accessed: Optional[int] = Field(
        None,
        description="Number of times hints were accessed (applies mastery penalty)"
    )
    confidence_score: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Self-reported confidence score 1-5 (measures self-awareness/calibration)"
    )


class EvaluationResult(BaseModel):
    """Result of question evaluation."""
    
    is_correct: bool = Field(..., description="Whether the answer is correct")
    score: float = Field(..., ge=0.0, description="Score awarded (0 to max_score)")
    method_detected: Optional[str] = Field(None, description="Method used for evaluation")
    error_type: Optional[str] = Field(None, description="Type of error if incorrect")
    misconception: Optional[str] = Field(None, description="Description of misconception if applicable")
    behavioral_data: Optional[BehavioralPayload] = Field(None, description="Behavioral metrics")
