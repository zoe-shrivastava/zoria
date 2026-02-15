"""Deterministic validation for generated question blueprints.

This service performs structural and basic semantic checks on
GeneratedQuestionBlueprint instances before they are stored.
"""

from typing import Set
import re

from schemas.question_blueprint import GeneratedQuestionBlueprint


class QuestionValidatorService:
  """Service for validating generated questions deterministically."""

  def validate(self, blueprint: GeneratedQuestionBlueprint) -> None:
    """Validate a generated question blueprint.

    Raises:
        ValueError: If any validation rule fails.
    """
    self._validate_basic_structure(blueprint)
    
    if blueprint.question_type == "multiple_choice":
      self._validate_mcq_consistency(blueprint)
    else:
      self._validate_non_mcq_consistency(blueprint)
    
    # Numeric/unit sanity checks are currently disabled to avoid
    # over-rejecting valid conceptual questions. Re-enable and
    # refine when a more robust numeric validator is in place.
    # self._validate_numeric_sanity(blueprint)

  def _validate_basic_structure(self, blueprint: GeneratedQuestionBlueprint) -> None:
    """Validate basic required fields and relationships."""
    if not blueprint.question_text or not blueprint.question_text.strip():
      raise ValueError("Question text cannot be empty")

    # Support multiple question types
    valid_types = {"multiple_choice", "short_answer", "problem_solving"}
    if blueprint.question_type not in valid_types:
      raise ValueError(f"Unsupported question_type: {blueprint.question_type}. Must be one of: {valid_types}")

    if blueprint.question_type == "multiple_choice":
      if not blueprint.options or len(blueprint.options) != 4:
        raise ValueError("MCQ must have exactly 4 options (A, B, C, D)")
      self._validate_mcq_consistency(blueprint)

    # Validate hint is present and meaningful
    if not blueprint.hint or not str(blueprint.hint).strip():
      raise ValueError("hint is REQUIRED for all questions")
    
    hint_str = str(blueprint.hint).strip()
    if len(hint_str) < 10:
      raise ValueError("hint must be at least 10 characters long")
    
    # Check for placeholder patterns
    placeholder_patterns = ["n/a", "tbd", "to be determined", "see solution", "see above"]
    if any(pattern in hint_str.lower() for pattern in placeholder_patterns):
      raise ValueError("hint cannot be a placeholder - must provide actual helpful guidance")

  def _validate_non_mcq_consistency(self, blueprint: GeneratedQuestionBlueprint) -> None:
    """Validate non-MCQ question invariants."""
    if not blueprint.expected_answer or not str(blueprint.expected_answer).strip():
      raise ValueError(f"expected_answer is REQUIRED for {blueprint.question_type} questions")
    
    # Ensure expected_answer is meaningful (not just whitespace or placeholder)
    expected_answer_str = str(blueprint.expected_answer).strip()
    if len(expected_answer_str) < 1:
      raise ValueError("expected_answer cannot be empty")
    
    # Warn if expected_answer looks like a placeholder
    placeholder_patterns = ["see solution", "see above", "n/a", "tbd", "to be determined"]
    if expected_answer_str.lower() in placeholder_patterns:
      raise ValueError(f"expected_answer appears to be a placeholder: '{expected_answer_str}'")

  def _validate_mcq_consistency(self, blueprint: GeneratedQuestionBlueprint) -> None:
    """Validate MCQ-specific invariants."""
    labels: Set[str] = {opt.label for opt in blueprint.options}
    if labels != {"A", "B", "C", "D"}:
      raise ValueError("MCQ options must include labels A, B, C, and D exactly once")

    if blueprint.correct_answer not in labels:
      raise ValueError(
        f"correct_answer '{blueprint.correct_answer}' is not one of the option labels"
      )

    # Ensure option texts are non-empty and not all identical
    texts = [opt.text.strip() for opt in blueprint.options]
    if any(not t for t in texts):
      raise ValueError("All option texts must be non-empty")

    if len(set(texts)) == 1:
      raise ValueError("All options have identical text; question is invalid")

  def _validate_numeric_sanity(self, blueprint: GeneratedQuestionBlueprint) -> None:
    """Lightweight numeric / units sanity checks for math/physics MCQs.

    This is not a full symbolic math verifier, but enforces:
      - correct option contains at least one digit (for numeric-style questions)
      - if metadata.requires_units is true, correct option includes some letters
        (very rough unit presence check)
    """
    subject = (blueprint.subject or "").lower()
    if subject not in {"mathematics", "physics"}:
      return

    if blueprint.question_type != "multiple_choice":
      return

    requires_units = bool(blueprint.metadata.get("requires_units"))

    # Find correct option text
    correct_text = ""
    for opt in blueprint.options:
      if opt.label == blueprint.correct_answer:
        correct_text = opt.text or ""
        break

    if not correct_text:
      # Structural validator would already have failed if no matching label,
      # but double-check here.
      raise ValueError("No option text found for correct_answer label")

    # Determine if the question stem itself looks numeric (contains any digits)
    stem_has_digit = re.search(r"\d", blueprint.question_text or "") is not None

    # If the stem is numeric and this is not a units-only answer, require at least one digit
    if stem_has_digit and not requires_units:
      if re.search(r"\d", correct_text) is None:
        # For numeric-style questions in math/physics, we expect at least some numeric content
        raise ValueError("Correct answer for math/physics appears to contain no numeric content")

    if requires_units:
      # Very rough: require at least one alphabetic character somewhere in the correct answer
      if re.search(r"[A-Za-z]", correct_text) is None:
        raise ValueError("Correct answer is missing units but metadata.requires_units is true")
