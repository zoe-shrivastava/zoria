"""Schemas for generated question blueprints used in the question pipeline."""

from typing import List, Dict, Any, Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field, validator


class QuestionOption(BaseModel):
  """Single answer option for a multiple-choice question."""

  label: Literal["A", "B", "C", "D"] = Field(..., description="Option label")
  text: str = Field(..., description="Option text (may include LaTeX)")


class GeneratedQuestionBlueprint(BaseModel):
  """Internal canonical schema for a generated question."""

  question_id: Optional[UUID] = Field(
    None,
    description="Optional UUID for the generated question (can be assigned by DB)",
  )
  subject: Optional[str] = Field(
    None,
    description="Subject identifier (e.g., 'mathematics', 'physics')",
  )
  concept_id: str = Field(
    ..., description="Concept UUID this question is linked to"
  )
  difficulty: str = Field(
    "medium",
    description="Difficulty level (e.g., easy, medium, hard)",
  )
  cognitive_level: Optional[str] = Field(
    None,
    description="Cognitive level (e.g., recall, application, analysis)",
  )

  question_text: str = Field(..., description="Full question stem text")
  question_type: str = Field(
    "multiple_choice",
    description="Question type: 'multiple_choice', 'short_answer', 'problem_solving', etc.",
  )

  # MCQ-specific fields (required only for multiple_choice)
  options: Optional[List[QuestionOption]] = Field(
    None, description="List of answer options (A–D) - required for multiple_choice"
  )

  correct_answer: Optional[Literal["A", "B", "C", "D"]] = Field(
    None, description="Label of the correct option - required for multiple_choice"
  )

  # For non-MCQ questions - REQUIRED
  expected_answer: Optional[str] = Field(
    None, description="Expected answer text or value - REQUIRED for short_answer and problem_solving"
  )

  # Hint field - REQUIRED for all question types
  hint: str = Field(
    ..., description="A helpful hint to guide students toward the solution without giving away the answer"
  )

  solution_steps: List[str] = Field(
    default_factory=list,
    description="Optional step-by-step solution explanation",
  )

  error_pattern_map: Optional[Dict[str, str]] = Field(
    default_factory=dict,
    description="Map from option label to error pattern identifier - used for multiple_choice",
  )

  metadata: Dict[str, Any] = Field(
    default_factory=dict,
    description="Additional metadata (estimated time, units, etc.)",
  )

  diagram_code: Optional[str] = Field(
    None,
    description="Optional LaTeX TikZ code for diagrams/visuals",
  )

  # For FRQ (non-MCQ) questions: indicate if student input requires graph or diagram
  needs_graph: Optional[bool] = Field(
    False,
    description="For FRQ questions: Set to true if the question requires the student to draw a graph (e.g., plotting functions, data visualization, coordinate geometry)"
  )
  
  needs_diagram: Optional[bool] = Field(
    False,
    description="For FRQ questions: Set to true if the question requires the student to draw a diagram (e.g., geometric shapes, free-body diagrams, molecular structures)"
  )

  @validator("options")
  def validate_options_for_mcq(cls, v: Optional[List[QuestionOption]], values: dict) -> Optional[List[QuestionOption]]:
    """Ensure options are provided for MCQ and have unique labels."""
    question_type = values.get('question_type', 'multiple_choice')
    if question_type == 'multiple_choice':
      if not v or len(v) == 0:
        raise ValueError("Options are required for multiple_choice questions")
      labels = [opt.label for opt in v]
      if len(labels) != len(set(labels)):
        raise ValueError("Option labels must be unique")
      if len(v) != 4:
        raise ValueError("Multiple choice questions must have exactly 4 options")
    return v

  @validator("correct_answer")
  def validate_correct_answer_for_mcq(cls, v: Optional[str], values: dict) -> Optional[str]:
    """Ensure correct_answer is provided for MCQ."""
    question_type = values.get('question_type', 'multiple_choice')
    if question_type == 'multiple_choice':
      if not v:
        raise ValueError("correct_answer is required for multiple_choice questions")
      if v not in ["A", "B", "C", "D"]:
        raise ValueError("correct_answer must be A, B, C, or D")
    return v

  @validator("expected_answer")
  def validate_expected_answer_for_non_mcq(cls, v: Optional[str], values: dict) -> Optional[str]:
    """Ensure expected_answer is REQUIRED for non-MCQ questions."""
    question_type = values.get('question_type', 'multiple_choice')
    if question_type != 'multiple_choice':
      if not v or not str(v).strip():
        raise ValueError(f"expected_answer is REQUIRED for {question_type} questions")
    return v

  @validator("hint")
  def validate_hint(cls, v: str) -> str:
    """Ensure hint is provided and meaningful."""
    if not v or not str(v).strip():
      raise ValueError("hint is REQUIRED for all questions")
    hint_str = str(v).strip()
    if len(hint_str) < 10:
      raise ValueError("hint must be at least 10 characters long")
    # Check for placeholder patterns
    placeholder_patterns = ["n/a", "tbd", "to be determined", "see solution", "see above"]
    if any(pattern in hint_str.lower() for pattern in placeholder_patterns):
      raise ValueError("hint cannot be a placeholder - must provide actual helpful guidance")
    return hint_str
