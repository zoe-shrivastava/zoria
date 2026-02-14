"""Quiz-related request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class QuizQuestion(BaseModel):
    """Quiz question schema."""
    id: str
    question: str
    question_type: str  # 'multiple_choice', 'short_answer', 'problem_solving'
    options: Optional[List[str]] = None  # For multiple choice
    correct_answer: str
    difficulty: str  # 'easy', 'medium', 'hard'
    concept_name: Optional[str] = None


class QuizResponse(BaseModel):
    """Quiz response schema."""
    id: str
    child_id: str
    document_id: Optional[str] = None
    questions: List[QuizQuestion]
    created_at: datetime


class QuizSubmission(BaseModel):
    """Quiz submission schema."""
    answers: Dict[str, str] = Field(..., description="Question ID to answer mapping")
    time_taken: Optional[int] = Field(None, description="Time taken in seconds")


class QuizResultResponse(BaseModel):
    """Quiz result response schema."""
    id: str
    quiz_id: str
    child_id: str
    score: float
    total_questions: int
    correct_answers: int
    answers: Dict[str, str]
    completed_at: datetime
