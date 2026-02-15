"""Test/Quiz API schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime

from schemas.evaluation import BehavioralPayload


class TestGenerateRequest(BaseModel):
    """Request to generate a test."""
    concept_id: Optional[str] = Field(None, description="Concept UUID to generate test from (legacy)")
    subject: Optional[str] = Field(None, description="Subject name (e.g., 'Mathematics', 'Physics')")
    topics: Optional[List[str]] = Field(None, description="List of topic names to generate test from")
    child_id: Optional[str] = Field(None, description="Child UUID (required for parent/admin, auto-set for child)")
    include_prerequisites: bool = Field(False, description="Include prerequisite concepts")
    difficulty: Optional[str] = Field(None, description="Filter by difficulty (easy, medium, hard)")
    num_questions: int = Field(10, ge=1, le=50, description="Number of questions")
    time_limit_minutes: Optional[int] = Field(None, ge=1, description="Time limit in minutes")


class QuestionGenerateRequest(BaseModel):
    """Request to generate questions for a concept."""
    concept_id: str = Field(..., description="Concept UUID to generate questions for")
    num_questions: int = Field(10, ge=1, le=50, description="Number of questions to generate")
    question_type: str = Field("multiple_choice", description="Type of questions to generate")
    difficulty: Optional[str] = Field(None, description="Difficulty level (easy, medium, hard)")
    grade_level: int = Field(8, ge=1, le=12, description="Grade level for age-appropriate language")
    similarity_threshold: float = Field(0.85, ge=0.0, le=1.0, description="Similarity threshold for deduplication")


class TestQuestionResponse(BaseModel):
    """Question in a test."""
    question_id: str
    text: str
    type: str
    difficulty: Optional[str]
    order_index: int
    section_title: Optional[str]
    max_score: float
    metadata: Optional[Dict[str, Any]]
    answer: Optional[str] = None
    score: Optional[float] = None
    is_correct: Optional[bool] = None


class TestResponse(BaseModel):
    """Test response."""
    id: str
    child_id: str
    parent_id: Optional[str]
    concept_id: Optional[str]
    title: str
    status: str
    total_score: Optional[float]
    max_score: Optional[float]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    time_limit_minutes: Optional[int]
    created_at: datetime
    questions: List[TestQuestionResponse] = []


class TestListResponse(BaseModel):
    """List of tests."""
    tests: List[TestResponse]
    total: int


class TestAnswerRequest(BaseModel):
    """Request to save an answer."""
    question_id: str
    answer: str
    time_spent_seconds: Optional[int] = None
    behavioral_data: Optional[BehavioralPayload] = Field(
        None,
        description="Behavioral tracking data (latency, edits, hints, confidence)"
    )


class TestSubmitResponse(BaseModel):
    """Response after submitting test."""
    test_id: str
    total_score: float
    max_score: float
    percentage: float
    correct_count: int
    graded_count: int
    mastery_updated: bool


class TestStartResponse(BaseModel):
    """Response after starting a test."""
    test_id: str
    title: str
    status: str
    time_limit_minutes: Optional[int]
    questions: List[TestQuestionResponse]
    started_at: datetime
