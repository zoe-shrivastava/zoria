"""LLM evaluator with strict scoring and optional separate feedback model."""

import logging
import re
from fractions import Fraction
from typing import Dict, Any, Tuple, Optional, List

from .error_library import ErrorType, ErrorLibrary
from services.llm_service import LLMService
from core.config import settings

logger = logging.getLogger(__name__)


class LLMEvaluator:
    """Evaluator for free-response and conceptual questions using strict JSON scoring."""

    # Leniency calibration knobs for FRQ scoring
    WRONG_FORMULA_CAP = 0.4
    FINAL_ANSWER_CAP = 0.75
    CRITICAL_MISMATCH_CAP = 0.75
    CONTRADICTION_CAP = 0.4
    IS_CORRECT_THRESHOLD = 0.90
    MULTIPART_ATTEMPT_FLOOR = 0.4
    MULTIPART_ATTEMPT_BONUS_SCALE = 0.15
    WORKED_SOLUTION_FLOOR = 0.5

    STRICT_SCORER_SYSTEM_PROMPT = """
You are a strict, subject-agnostic grader for middle/high school STEM questions.
You may grade questions from:
- Math (algebra, geometry, calculus)
- Physics (kinematics, forces, energy)
- Chemistry (reactions, concentrations, stoichiometry)
- Biology (conceptual numeric or key outputs)
- Any STEM discipline with numeric or key conceptual answers

Rules:

1. Relevance check (highest priority):
   - If the student answer does not address the question at all, assign:
     - score = 0
     - errors = ["irrelevant answer"]
   - Skip further scoring if the answer is irrelevant.

2. Primary focus: numeric or key conceptual outputs
   - If all key outputs/concepts match the expected answer, award full credit (1.0), regardless of method notation.
   - Minor arithmetic, transcription, or alternative valid methods do not reduce full credit.

3. Partial credit is applied only when:
   - Final answer is incorrect -> score <= 0.75
   - Critical expected outputs/concepts are missing -> score < 1.0
   - Contradictions exist between steps and final answer -> score < 1.0
   - Invalid formulas/frameworks lead to wrong outputs -> score <= 0.4

4. Formula differences:
   - Accept alternative but valid formulas/methods if they produce the correct final answer.
   - Only penalize if formula is incorrect or logically invalid, or produces a wrong output.

5. Contradictions and critical output mismatches:
   - Always flag contradictions or mismatches.
   - Example: student writes correct numeric output but steps claim a different value -> partial credit.
   - Variable/Label Sensitivity: In any STEM context, the identifier (variable, unit, or label) is as critical as the numeric value. x=2 is not y=2, and 10 m/s is not 10 m/s^2. Any mismatch between expected variable/unit/label and student variable/unit/label must be flagged as "critical output mismatch".

6. Scoring priority:
   - Check relevance first.
   - Then check numeric/conceptual outputs.
   - Correct numeric/conceptual outputs override minor step mistakes.
   - Then check formula/method correctness.
   - Steps only reduce score if they invalidate the answer, produce contradictions, or critical output mismatches.
   - Always enforce the lowest applicable cap if multiple critical errors exist.
   - If the question asks for multiple outputs, all requested outputs must be present for full credit.

7. Errors to flag in JSON:
   - "irrelevant answer" -> answer does not address the question
   - "contradiction" -> steps contradict final answer or each other
   - "critical output mismatch" -> key expected outputs/concepts differ from student answer
   - "wrong formula" -> formula/method is invalid and produces wrong results
   - "final answer incorrect" -> numeric/conceptual output is wrong

8. JSON Output Format (strictly enforce):
{
  "score": float,
  "errors": [string],
  "reasoning": "string"
}

Evaluation Task:

- First, check if the answer is relevant to the question.
- Evaluate the student answer against the expected answer.
- Grade numeric/conceptual outputs first.
- Completeness Check: if multiple outputs are requested, verify all required outputs are present (not just one correct part).
- Variable Check: before comparing numbers, identify the exact entity being solved for and verify variable/label alignment with expected output. If expected is x=h and student gives y=k (or unit/label mismatch), treat as critical output mismatch.
- Validate each required output component exactly by meaning:
  - For coordinate outputs, both x and y values must match expected.
  - For equation outputs, both variable and value must match expected (e.g., x=2 is not equivalent to y=2).
  - For comparison outputs, direction/relationship must match expected (e.g., wider vs narrower, increase vs decrease).
  - A numerically equivalent representation is acceptable (e.g., 9/8 and 1.125), but changing the required variable/concept is not.
- Review step validity and formula correctness.
- Detect contradictions and critical output mismatches.
- Apply scoring rules as above.
- Return only valid JSON, no extra text.
"""

    FEEDBACK_SYSTEM_PROMPT = """
You are writing evaluation-report feedback (not a live chat).
Tone: professional, concise, neutral-supportive.
Do NOT use greetings, questions, or conversational fillers.
Do NOT say "let's", "we'll", "sound good", or ask the student to reply.
Write 3 short parts:
1) What was correct
2) What was incorrect and why
3) One concrete next step
Keep it under 90 words.
"""

    def __init__(self, llm_service, temperature: float = 0.1):
        self.llm_service = llm_service
        self.temperature = temperature
        self.feedback_llm_service: Optional[LLMService] = None

        if settings.EVALUATION_USE_SEPARATE_FEEDBACK:
            try:
                self.feedback_llm_service = LLMService(
                    model_name=settings.EVALUATION_FEEDBACK_MODEL,
                    enable_logging=True,
                    context_source="evaluation_feedback",
                )
            except Exception as e:
                logger.warning(f"Failed to initialize separate feedback model: {e}")

    async def evaluate(
        self,
        student_answer: str,
        expected_answer: str,
        question_text: str,
        metadata: Dict[str, Any],
        max_score: float,
        concept_tags: Optional[list] = None,
        solution_steps: Optional[list] = None,
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str], Optional[str]]:
        """Evaluate student answer with strict scoring + optional separate feedback model."""
        if not self.llm_service:
            logger.warning("LLM service not available, falling back to basic evaluation")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)

        try:
            prompt = self._build_strict_scoring_prompt(
                question_text, student_answer, expected_answer, concept_tags, solution_steps
            )
            response = await self.llm_service.generate_json(
                prompt=prompt,
                system_prompt=self.STRICT_SCORER_SYSTEM_PROMPT,
                temperature=self.temperature,
                max_tokens=700,
            )

            scoring_result = self._parse_strict_scoring_response(response)
            raw_score = scoring_result.get("score", 0.0)
            errors = scoring_result.get("errors", [])
            errors = self._apply_numeric_validation_overrides(
                question_text=question_text,
                student_answer=student_answer,
                expected_answer=expected_answer,
                errors=errors,
            )
            reasoning = scoring_result.get("reasoning", "")

            multipart_override = self._compute_multipart_partial_score(
                question_text=question_text,
                student_answer=student_answer,
                expected_answer=expected_answer,
            )
            if multipart_override is not None:
                score = multipart_override["score"]
                # Preserve severe error signals but avoid over-penalizing with
                # a global wrong-formula cap when part-wise scoring is available.
                errors = self._merge_errors_preserving_order(
                    errors,
                    multipart_override.get("errors", []),
                )
            else:
                score = self._apply_hard_caps(raw_score, errors)

            # Additional leniency for single-output questions where the student
            # shows substantive work (multiple computed intermediate values)
            # but misses the final combine step.
            score = self._apply_worked_solution_floor(
                score=score,
                question_text=question_text,
                student_answer=student_answer,
                errors=errors,
            )
            normalized_score = score * max_score

            method_detected = "strict_llm_scoring"
            error_type_str, misconception = self._map_errors_to_error_type_and_misconception(errors)
            error_type = ErrorLibrary.classify_error(
                error_type_str, method_detected, student_answer, expected_answer
            )

            has_explicit_error = error_type_str in ["Arithmetic", "Conceptual", "Procedural"]
            has_contradiction = any("contradiction" in e.lower() for e in errors)
            is_correct = (
                (normalized_score >= (max_score * self.IS_CORRECT_THRESHOLD))
                and (not has_explicit_error)
                and (not has_contradiction)
            )

            detailed_feedback = await self._generate_feedback(
                question_text=question_text,
                student_answer=student_answer,
                expected_answer=expected_answer,
                score=score,
                errors=errors,
                reasoning=reasoning,
            )

            logger.info(
                "Strict LLM evaluation: raw_score=%.2f normalized=%.2f/%.2f error_type=%s is_correct=%s",
                score,
                normalized_score,
                max_score,
                error_type.value,
                is_correct,
            )
            return is_correct, normalized_score, method_detected, error_type, misconception, detailed_feedback
        except ValueError as e:
            if "empty response" in str(e).lower():
                logger.warning(
                    "LLM returned empty response for evaluation, using fallback. Question type: %s",
                    metadata.get("question_type", "unknown"),
                )
            else:
                logger.warning(f"LLM evaluation error, using fallback: {e}")
            return self._fallback_evaluation(student_answer, expected_answer, max_score)
        except Exception as e:
            logger.warning(f"Unexpected error in LLM evaluation, using fallback: {e}", exc_info=True)
            return self._fallback_evaluation(student_answer, expected_answer, max_score)

    def _build_strict_scoring_prompt(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
        concept_tags: Optional[list] = None,
        solution_steps: Optional[list] = None,
    ) -> str:
        """Build strict scoring prompt for the scoring model."""
        parts = [
            "Evaluate this student response strictly.",
            "",
            "QUESTION:",
            question_text,
            "",
            "STUDENT ANSWER:",
            student_answer,
            "",
            "EXPECTED ANSWER:",
            expected_answer,
        ]

        if solution_steps:
            parts.extend(["", "EXPECTED SOLUTION STEPS:"])
            for i, step in enumerate(solution_steps, 1):
                parts.append(f"{i}. {step}")

        if concept_tags:
            parts.extend(["", "RELEVANT CONCEPTS:", ", ".join(concept_tags)])

        parts.extend(
            [
                "",
                "SCORING INSTRUCTIONS:",
                "- Score in [0.0, 1.0].",
                "- Prioritize numeric/conceptual correctness over literal formula syntax.",
                "- Wrong formula/framework that causes incorrect results -> score <= 0.4 and include 'wrong formula' in errors.",
                "- Final answer incorrect or key output mismatch -> score <= 0.75 and include 'final answer incorrect' in errors.",
                "- If any critical expected output/value/relation does not match, include 'critical output mismatch' and score <= 0.75.",
                "- If contradiction exists, include 'contradiction' in errors.",
                "- Minor formula variations that still produce correct outputs should NOT reduce score.",
                "- Always enforce the lowest applicable cap when multiple critical errors exist.",
                "- Return JSON only.",
            ]
        )
        return "\n".join(parts)

    def _parse_strict_scoring_response(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """Parse strict scorer response schema: score/errors/reasoning."""
        result = response or {}
        if isinstance(result, dict) and "result" in result and isinstance(result["result"], dict):
            result = result["result"]

        try:
            score = float(result.get("score", 0.0))
        except (TypeError, ValueError):
            score = 0.0
        score = max(0.0, min(1.0, score))

        errors = result.get("errors", [])
        if not isinstance(errors, list):
            errors = [str(errors)] if errors is not None else []
        normalized_errors = [str(e).strip() for e in errors if str(e).strip()]

        reasoning = result.get("reasoning", "")
        if not isinstance(reasoning, str):
            reasoning = str(reasoning)

        return {"score": score, "errors": normalized_errors, "reasoning": reasoning}

    def _apply_hard_caps(self, score: float, errors: List[str]) -> float:
        """Apply deterministic hard caps to reduce scorer leniency."""
        lowered = [e.lower() for e in errors]
        adjusted = score

        # Formula cap is applied conservatively; exact keypoint matches are
        # already handled upstream and clear spurious model-side formula errors.
        if any("wrong formula" in e or ("formula" in e and "wrong" in e) for e in lowered):
            adjusted = min(adjusted, self.WRONG_FORMULA_CAP)
        if any("final answer incorrect" in e or "wrong final answer" in e for e in lowered):
            adjusted = min(adjusted, self.FINAL_ANSWER_CAP)
        if any("critical output mismatch" in e for e in lowered):
            adjusted = min(adjusted, self.CRITICAL_MISMATCH_CAP)
        if any("contradiction" in e for e in lowered):
            adjusted = min(adjusted, self.CONTRADICTION_CAP)

        return max(0.0, min(1.0, adjusted))

    def _compute_multipart_partial_score(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
    ) -> Optional[Dict[str, Any]]:
        """Compute deterministic partial score for multi-part numeric outputs.

        This is designed for questions asking multiple requested outputs such as
        (a), (b), (c): final velocity, displacement, average velocity, etc.
        If we can reliably extract labeled values from expected + student answers,
        we score part-wise and return a proportional score in [0,1].
        """
        expected_parts = self._extract_named_numeric_parts(expected_answer)
        student_parts = self._extract_named_numeric_parts(student_answer)

        matched = 0
        missing_or_mismatch = 0
        keys_evaluated = 0
        attempted_ratio = 0.0

        if len(expected_parts) >= 2 and student_parts:
            for key, expected_val in expected_parts.items():
                student_val = student_parts.get(key)
                if student_val is None:
                    missing_or_mismatch += 1
                    keys_evaluated += 1
                    continue
                keys_evaluated += 1
                if self._numeric_close(expected_val, student_val):
                    matched += 1
                else:
                    missing_or_mismatch += 1
            attempted_ratio = (
                sum(1 for key in expected_parts.keys() if key in student_parts) / float(len(expected_parts))
                if expected_parts else 0.0
            )
        else:
            # Fallback for messy label formatting:
            # For clear multi-part prompts (a/b/c), compare expected/student numbers by order.
            if not self._looks_like_multipart_prompt(question_text):
                return None
            expected_values = self._extract_ordered_numeric_values(expected_answer)
            student_values = self._extract_ordered_numeric_values(student_answer)
            if len(expected_values) < 2 or not student_values:
                return None
            keys_evaluated = len(expected_values)
            attempts = min(len(student_values), len(expected_values))
            attempted_ratio = attempts / float(keys_evaluated)
            for i in range(keys_evaluated):
                if i >= len(student_values):
                    missing_or_mismatch += 1
                    continue
                if self._numeric_close(expected_values[i], student_values[i]):
                    matched += 1
                else:
                    missing_or_mismatch += 1

        if keys_evaluated < 2:
            return None

        score = matched / float(keys_evaluated)
        # Method-attempt floor for multi-part responses:
        # if student attempts most requested parts but gets results wrong, avoid over-harsh collapse.
        if matched == 0 and attempted_ratio >= 0.66:
            score = max(score, self.MULTIPART_ATTEMPT_FLOOR)
        elif matched > 0 and attempted_ratio > 0:
            score = max(score, min(1.0, score + self.MULTIPART_ATTEMPT_BONUS_SCALE * attempted_ratio))

        errors: List[str] = []
        if missing_or_mismatch > 0:
            errors.append("final answer incorrect")
        if len(expected_parts) >= 2:
            if any(k not in student_parts for k in expected_parts.keys()):
                errors.append("critical output mismatch")
        elif attempted_ratio < 1.0:
            errors.append("critical output mismatch")

        return {
            "score": max(0.0, min(1.0, score)),
            "errors": errors,
        }

    def _extract_named_numeric_parts(self, text: str) -> Dict[str, float]:
        """Extract labeled numeric outputs from free text."""
        if not text:
            return {}

        normalized = self._normalize_symbols_for_scoring(text.lower())
        lines = [ln.strip() for ln in re.split(r"[;\n]+", normalized) if ln.strip()]
        out: Dict[str, float] = {}

        label_patterns = {
            "vf": [r"\bv_f\b", r"\bvf\b", r"final velocity"],
            "dx": [r"\bdx\b", r"displacement"],
            "vavg": [r"\bvavg\b", r"average velocity", r"\bavg v\b", r"\bv average\b"],
        }

        for line in lines:
            nums = re.findall(r"[-+]?\d+(?:\.\d+)?", line)
            if not nums:
                continue
            # For equation-like lines, the right-most number usually represents final output.
            line_value = float(nums[-1])
            for key, patterns in label_patterns.items():
                if key in out:
                    continue
                if any(re.search(p, line) for p in patterns):
                    out[key] = line_value

        return out

    def _normalize_symbols_for_scoring(self, text: str) -> str:
        """Normalize common math symbols to help parsing labels."""
        return (
            text.replace("Δ", "d")
            .replace("δ", "d")
            .replace("−", "-")
            .replace("—", "-")
            .replace("v̄", "vavg")
        )

    def _numeric_close(self, expected_val: float, student_val: float) -> bool:
        """Numerical comparison with tolerance for scoring robustness."""
        abs_tol = 1e-6
        rel_tol = 0.02  # 2%
        if abs(expected_val - student_val) <= abs_tol:
            return True
        denom = max(abs(expected_val), 1.0)
        return abs(expected_val - student_val) / denom <= rel_tol

    def _merge_errors_preserving_order(self, base: List[str], extra: List[str]) -> List[str]:
        merged: List[str] = []
        seen = set()
        for e in list(base or []) + list(extra or []):
            e_clean = str(e).strip()
            if not e_clean:
                continue
            key = e_clean.lower()
            if key in seen:
                continue
            seen.add(key)
            merged.append(e_clean)
        return merged

    def _apply_worked_solution_floor(
        self,
        score: float,
        question_text: str,
        student_answer: str,
        errors: List[str],
    ) -> float:
        """Raise score floor for substantial worked attempts.

        Intended for cases where student clearly computes meaningful
        intermediate values but final synthesis is incorrect.
        """
        lowered_errors = [str(e).lower() for e in (errors or [])]
        if any("irrelevant answer" in e for e in lowered_errors):
            return score

        # Prefer multipart scorer when applicable; this floor is mostly for
        # single-output derived problems.
        if self._looks_like_multipart_prompt(question_text):
            return score

        text = (student_answer or "").lower()
        number_count = len(re.findall(r"[-+]?\d+(?:\.\d+)?", text))
        has_equations = text.count("=") >= 2 or text.count("*") >= 2 or text.count("+") >= 2
        has_step_markers = any(marker in text for marker in ("car a", "car b", "step", "therefore", "so"))

        # If there is clear worked attempt and score is very low, use floor.
        if number_count >= 4 and has_equations and has_step_markers and score < self.WORKED_SOLUTION_FLOOR:
            return self.WORKED_SOLUTION_FLOOR
        return score

    def _looks_like_multipart_prompt(self, question_text: str) -> bool:
        q = (question_text or "").lower()
        return ("(a)" in q and "(b)" in q) or ("part (a)" in q and "part (b)" in q)

    def _extract_ordered_numeric_values(self, text: str) -> List[float]:
        if not text:
            return []
        normalized = self._normalize_symbols_for_scoring(text)
        nums = re.findall(r"[-+]?\d+(?:\.\d+)?", normalized)
        return [float(n) for n in nums]

    def _apply_numeric_validation_overrides(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
        errors: List[str],
    ) -> List[str]:
        """Generic label/value integrity checks (subject/topic agnostic)."""
        normalized_errors = [str(e).strip() for e in errors if str(e).strip()]
        lowered_set = {e.lower() for e in normalized_errors}

        # Generic symbolic integrity check:
        # If expected answer contains explicit variable=value outputs, require
        # student to provide matching variable/value pairs (numeric equivalents allowed).
        expected_pairs = self._extract_var_value_pairs(expected_answer)
        student_pairs = self._extract_var_value_pairs(student_answer)
        if expected_pairs:
            for exp_var, exp_val in expected_pairs:
                matched = any(
                    stu_var == exp_var and self._is_numeric_equivalent(exp_val, stu_val)
                    for stu_var, stu_val in student_pairs
                )
                if not matched:
                    if "critical output mismatch" not in lowered_set:
                        normalized_errors.append("critical output mismatch")
                        lowered_set.add("critical output mismatch")
                    break

        # Generic completeness check for comparative/relation outputs:
        # if expected answer includes explicit relation terms and the question
        # asks for comparison, student must include the same relation terms.
        if self._is_comparison_question(question_text, expected_answer):
            required_terms = self._extract_relation_terms(expected_answer)
            if required_terms:
                student_lower = (student_answer or "").lower()
                missing_term = any(term not in student_lower for term in required_terms)
                if missing_term and "critical output mismatch" not in lowered_set:
                    normalized_errors.append("critical output mismatch")
                    lowered_set.add("critical output mismatch")

        # Generic contradiction check for opposite inequality claims against
        # question givens (e.g., question says a>0, student states a<0).
        if self._has_inequality_contradiction(question_text, student_answer):
            if "contradiction" not in lowered_set:
                normalized_errors.append("contradiction")
                lowered_set.add("contradiction")

        return normalized_errors

    def _extract_var_value_pairs(self, text: str) -> List[Tuple[str, str]]:
        """Extract simple variable=value pairs like x=2, y=-3, p=1/8."""
        if not text:
            return []
        pairs: List[Tuple[str, str]] = []
        pattern = r"\b([a-zA-Z])\s*=\s*([\-]?\d+(?:\.\d+)?(?:/\d+(?:\.\d+)?)?)"
        for var, val in re.findall(pattern, text):
            pairs.append((var.lower(), re.sub(r"\s+", "", val)))
        return pairs

    def _is_numeric_equivalent(self, expected_val: str, student_val: str) -> bool:
        """Compare two numeric strings with fraction/decimal equivalence."""
        if expected_val == student_val:
            return True
        try:
            e = float(Fraction(expected_val))
            s = float(Fraction(student_val))
            return abs(e - s) <= 1e-9
        except Exception:
            return False

    def _extract_relation_terms(self, text: str) -> List[str]:
        """Extract relation/comparison terms required by expected answer."""
        lowered = (text or "").lower()
        terms = [
            "wider",
            "narrower",
            "upward",
            "downward",
            "increase",
            "decrease",
            "greater",
            "less",
        ]
        return [t for t in terms if t in lowered]

    def _is_comparison_question(self, question_text: str, expected_answer: str) -> bool:
        """Detect whether question requires comparison/relationship output."""
        q = (question_text or "").lower()
        e = (expected_answer or "").lower()
        triggers = ["compare", "comparison", "relative", "relationship", "which is", "width", "wider", "narrower"]
        return any(t in q for t in triggers) or any(t in e for t in ["wider", "narrower", "upward", "downward"])

    def _has_inequality_contradiction(self, question_text: str, student_answer: str) -> bool:
        """Detect contradictions where student asserts opposite inequality for same variable."""
        q_pairs = self._extract_simple_inequalities(question_text)
        s_pairs = self._extract_simple_inequalities(student_answer)
        if not q_pairs or not s_pairs:
            return False

        student_map = {(var, val): op for var, op, val in s_pairs}
        opposite = {">": "<", "<": ">", ">=": "<=", "<=": ">="}
        for var, op, val in q_pairs:
            s_op = student_map.get((var, val))
            if s_op and opposite.get(op) == s_op:
                return True
        return False

    def _extract_simple_inequalities(self, text: str) -> List[Tuple[str, str, str]]:
        """Extract simple inequalities like a>0, x<=2 into (var, op, value)."""
        if not text:
            return []
        cleaned = (
            text.replace("≥", ">=")
                .replace("≤", "<=")
                .replace("−", "-")
        )
        pattern = r"\b([a-zA-Z])\s*(<=|>=|<|>)\s*([\-]?\d+(?:\.\d+)?)"
        return [(var.lower(), op, val) for var, op, val in re.findall(pattern, cleaned)]

    def _extract_first_coordinate_pair(self, text: str) -> Optional[Tuple[str, str]]:
        """Extract first coordinate pair as canonical strings for exact comparison."""
        if not text:
            return None
        match = re.search(r"\(\s*([^,\)]+)\s*,\s*([^\)]+)\s*\)", text)
        if not match:
            return None
        x_raw = re.sub(r"\s+", "", match.group(1))
        y_raw = re.sub(r"\s+", "", match.group(2))
        return x_raw, y_raw

    def _evaluate_keypoint_alignment(self, student_answer: str, expected_answer: str) -> str:
        """Return 'match', 'mismatch', or 'unknown' for key expected outputs."""
        student = (student_answer or "").lower()
        expected = (expected_answer or "")

        if not expected.strip():
            return "unknown"

        saw_confident_keypoint = False

        # Coordinate pairs present in expected should appear in student.
        expected_coords = re.findall(r"\(\s*([^,\)]+)\s*,\s*([^\)]+)\s*\)", expected)
        if expected_coords:
            saw_confident_keypoint = True
            student_coords = set(
                (re.sub(r"\s+", "", a), re.sub(r"\s+", "", b))
                for a, b in re.findall(r"\(\s*([^,\)]+)\s*,\s*([^\)]+)\s*\)", student_answer or "")
            )
            for a, b in expected_coords:
                if (re.sub(r"\s+", "", a), re.sub(r"\s+", "", b)) not in student_coords:
                    return "mismatch"

        # Directional relational keywords should be consistent when used by expected.
        for keyword in ("wider", "narrower", "upward", "downward"):
            if keyword in expected.lower():
                saw_confident_keypoint = True
                if keyword not in student:
                    return "mismatch"

        # Axis statements (x = value / y = value) in expected should appear in student.
        expected_axes = re.findall(r"\b([xy])\s*=\s*([\-]?\d+(?:\.\d+)?)", expected, flags=re.IGNORECASE)
        if expected_axes:
            saw_confident_keypoint = True
            student_axes = {
                (var.lower(), val)
                for var, val in re.findall(r"\b([xy])\s*=\s*([\-]?\d+(?:\.\d+)?)", student_answer or "", flags=re.IGNORECASE)
            }
            for var, val in expected_axes:
                if (var.lower(), val) not in student_axes:
                    return "mismatch"

        if saw_confident_keypoint:
            return "match"
        return "unknown"

    def _map_errors_to_error_type_and_misconception(self, errors: List[str]) -> Tuple[str, Optional[str]]:
        """Map strict scorer errors to the existing evaluator contract."""
        if not errors:
            return "None", None

        lowered = [e.lower() for e in errors]
        joined = "; ".join(errors)

        if any("formula" in e or "concept" in e for e in lowered):
            return "Conceptual", joined
        if any("procedure" in e or "step" in e for e in lowered):
            return "Procedural", joined
        if any("arithmetic" in e or "calculation" in e or "sign" in e for e in lowered):
            return "Arithmetic", joined
        return "Conceptual", joined

    async def _generate_feedback(
        self,
        question_text: str,
        student_answer: str,
        expected_answer: str,
        score: float,
        errors: List[str],
        reasoning: str,
    ) -> str:
        """Generate student-facing explanation with optional separate model."""
        errors_text = ", ".join(errors) if errors else "None"
        prompt = (
            f"Question: {question_text}\n"
            f"Student answer: {student_answer}\n"
            f"Expected answer: {expected_answer}\n"
            f"Score: {score:.2f}\n"
            f"Errors: {errors_text}\n"
            f"Reasoning: {reasoning}\n\n"
            "Task: Write report-style feedback for this evaluation. "
            "Non-interactive tone. No greeting. No questions. "
            "State what was correct, what was incorrect, and one next step."
        )

        feedback_service = self.feedback_llm_service or self.llm_service
        try:
            response = await feedback_service.generate(
                prompt=prompt,
                system_prompt=self.FEEDBACK_SYSTEM_PROMPT,
                temperature=0.3,
                max_tokens=350,
            )
            text = (response.get("text") or "").strip()
            if text:
                return self._normalize_report_feedback(text)
        except Exception as e:
            logger.warning(f"Feedback generation failed, falling back to reasoning: {e}")

        return reasoning or "Review the method setup and verify the final answer."

    def _normalize_report_feedback(self, text: str) -> str:
        """Normalize generated feedback into report-style tone."""
        cleaned = (text or "").strip()
        if not cleaned:
            return cleaned

        # Remove common greeting openers.
        cleaned = re.sub(r"^\s*(hi|hello|hey)[^.!?\n]*[.!?]\s*", "", cleaned, flags=re.IGNORECASE)

        # Replace conversational phrasing with report-style wording.
        replacements = {
            r"\blet['’]?s\b": "the next step is to",
            r"\bwe['’]?ll\b": "you should",
            r"\bsound good\??": "",
        }
        for pattern, repl in replacements.items():
            cleaned = re.sub(pattern, repl, cleaned, flags=re.IGNORECASE)

        # Avoid ending in a question for non-interactive reports.
        if cleaned.endswith("?"):
            cleaned = cleaned[:-1].rstrip() + "."

        return re.sub(r"\s{2,}", " ", cleaned).strip()

    def _fallback_evaluation(
        self,
        student_answer: str,
        expected_answer: str,
        max_score: float,
    ) -> Tuple[bool, float, Optional[str], ErrorType, Optional[str], Optional[str]]:
        """Fallback evaluation when LLM is unavailable."""
        student_lower = student_answer.strip().lower()
        expected_lower = expected_answer.strip().lower()

        if student_lower == expected_lower:
            return True, max_score, "text_match", ErrorType.NONE, None, "Answer matches expected response"
        if expected_lower in student_lower or student_lower in expected_lower:
            feedback = f"Your answer is partially correct but incomplete. Expected: {expected_answer}"
            return False, max_score * 0.6, "partial_match", ErrorType.CONCEPTUAL, "Incomplete answer", feedback

        feedback = f"Your answer does not match the expected response. Expected: {expected_answer}"
        return False, 0.0, "no_match", ErrorType.CONCEPTUAL, "Answer does not match expected", feedback
