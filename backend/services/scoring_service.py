"""Scoring service for grading test responses."""

import logging
import json
import re
from typing import Dict, Any, Optional, Tuple, List

from database.repositories.test_repository import TestRepository
from database.repositories.question_repository import QuestionRepository
from core.database import Database
from services.graph_evaluation_service import GraphEvaluationService
from services.evaluation import QuestionRouter, ErrorType, ErrorLibrary
from schemas.evaluation import BehavioralPayload

logger = logging.getLogger(__name__)


class ScoringService:
    """Service for scoring test responses."""
    
    def __init__(self, db: Database, embedding_service=None, llm_service=None):
        """Initialize scoring service.
        
        Args:
            db: Database instance
            embedding_service: Optional embedding service for semantic similarity
            llm_service: Optional LLM service for graph evaluation and LLM evaluator
        """
        self.db = db
        self.test_repo = TestRepository(db)
        self.question_repo = QuestionRepository(db)
        self.embedding_service = embedding_service
        self.graph_eval_service = GraphEvaluationService(llm_service=llm_service)
        # Initialize question router with LLM service
        self.question_router = QuestionRouter(llm_service=llm_service, tolerance_percent=2.0)
    
    async def grade_response(
        self,
        test_id: str,
        question_id: str,
        answer: str,
        behavioral_data: Optional[BehavioralPayload] = None
    ) -> Tuple[bool, float, Optional[str], Optional[str], Optional[str]]:
        """Grade a single response using hybrid evaluation routing.
        
        Args:
            test_id: Test UUID
            question_id: Question UUID
            answer: Student answer
            behavioral_data: Optional behavioral tracking data
            
        Returns:
            Tuple of (is_correct, score, error_type, misconception, method_detected)
        """
        # Get question
        question = await self.question_repo.get_question_by_id(question_id)
        if not question:
            raise ValueError(f"Question not found: {question_id}")
        
        question_type = question.get('type', 'short_answer')
        metadata = question.get('metadata', {})
        if isinstance(metadata, str):
            metadata = json.loads(metadata)
        
        # Get max score for this question (check both question_id and original_question_id)
        test_question = await self.db.fetchrow(
            """
            SELECT max_score FROM test_questions 
            WHERE test_id = $1 
            AND (question_id = $2 OR original_question_id = $2)
            """,
            test_id, question_id
        )
        max_score = float(test_question['max_score']) if test_question else 1.0
        
        # Extract answer component from combined format if needed
        answer_to_grade = self._extract_answer_component(answer, question_type, metadata)
        
        # Check if answer is a drawing (graph/diagram)
        if self.graph_eval_service.is_drawing_answer(answer_to_grade):
            is_correct, score, feedback = await self._grade_drawing(
                answer_to_grade, question, metadata, max_score
            )
            logger.info(f"Graded drawing answer for question {question_id}: correct={is_correct}, score={score}")
            error_type = ErrorType.NONE
            misconception = None
            method_detected = "drawing_evaluation"
        else:
            # Use question router for hybrid evaluation
            correct_answer = metadata.get('correct_answer', '')
            expected_answer = metadata.get('expected_answer', '') or metadata.get('blueprint', {}).get('expected_answer', '')
            
            # Extract concept tags from metadata if available
            concept_tags = None
            if isinstance(metadata.get('blueprint'), dict):
                concept_tags = metadata['blueprint'].get('concept_tags', [])
            elif 'concept_name' in metadata:
                concept_tags = [metadata.get('concept_name')]
            
            # Route to appropriate evaluator
            is_correct, score, method_detected, error_type, misconception = await self.question_router.evaluate(
                student_answer=answer_to_grade,
                question_type=question_type,
                correct_answer=correct_answer,
                expected_answer=expected_answer,
                metadata=metadata,
                max_score=max_score,
                question_text=question.get('text', ''),
                concept_tags=concept_tags
            )
        
        # Apply behavioral penalties
        if behavioral_data:
            score = self._apply_behavioral_penalties(score, max_score, behavioral_data)
        
        # Update response score with error information
        await self.test_repo.update_response_score(
            test_id, question_id, score, is_correct,
            error_type=error_type.value if error_type else None,
            misconception=misconception,
            method_detected=method_detected
        )
        
        # Store error type and misconception in response metadata if available
        # (This would require extending the test_responses table or using metadata field)
        
        return is_correct, score, error_type.value if error_type else None, misconception, method_detected
    
    def _extract_answer_component(
        self,
        answer: str,
        question_type: str,
        metadata: Dict[str, Any]
    ) -> str:
        """Extract the relevant answer component from combined format.
        
        Combined format can be:
        - Plain string (backward compatible)
        - JSON string with 'objects' (drawing data)
        - JSON object with {text, graph, diagram} keys
        
        Args:
            answer: Student answer (may be combined format)
            question_type: Question type
            metadata: Question metadata
            
        Returns:
            Extracted answer component to grade
        """
        if not answer:
            return ''
        
        # Try to parse as JSON
        try:
            parsed = json.loads(answer) if isinstance(answer, str) else answer
            
            # Check if it's combined format (has text/graph/diagram keys)
            if isinstance(parsed, dict):
                # Combined format
                if 'text' in parsed or 'graph' in parsed or 'diagram' in parsed:
                    # For MCQ, prefer text (shouldn't have drawings anyway)
                    if question_type == 'multiple_choice':
                        return parsed.get('text', '')
                    
                    # For drawing questions, prefer graph, then diagram
                    if parsed.get('graph'):
                        return parsed['graph']
                    if parsed.get('diagram'):
                        return parsed['diagram']
                    
                    # Otherwise, use text
                    return parsed.get('text', '')
                
                # If it's a drawing (has 'objects' key), return as-is
                if 'objects' in parsed:
                    return answer if isinstance(answer, str) else json.dumps(parsed)
            
        except (json.JSONDecodeError, TypeError):
            # Not JSON, return as-is
            pass
        
        # Return original answer (plain string or already parsed drawing)
        return answer if isinstance(answer, str) else str(answer)
    
    def _grade_mcq(
        self,
        answer: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float]:
        """Grade multiple choice question.
        
        Args:
            answer: Student answer (option index as string "0", "1", "2", "3" or letter "A", "B", "C", "D")
            metadata: Question metadata with options and correct_answer
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score)
        """
        correct_answer = metadata.get('correct_answer', '')
        options = metadata.get('options', [])
        
        if not correct_answer or not options:
            return False, 0.0
        
        # Normalize answer
        answer = str(answer).strip()
        correct_answer = str(correct_answer).strip()
        
        # Convert answer to index
        answer_index = None
        if answer.isdigit():
            # Answer is already an index (0, 1, 2, 3)
            answer_index = int(answer)
        elif len(answer) == 1 and answer.upper() in ['A', 'B', 'C', 'D', 'E', 'F']:
            # Answer is a letter (A, B, C, D) - convert to index
            answer_index = ord(answer.upper()) - ord('A')
        else:
            # Try to find answer in options by text match
            answer_lower = answer.lower()
            for idx, option in enumerate(options):
                if answer_lower in str(option).lower():
                    answer_index = idx
                    break
        
        # Convert correct_answer to index
        correct_index = None
        if correct_answer.isdigit():
            correct_index = int(correct_answer)
        elif len(correct_answer) == 1 and correct_answer.upper() in ['A', 'B', 'C', 'D', 'E', 'F']:
            # Correct answer is a letter (A, B, C, D) - convert to index
            correct_index = ord(correct_answer.upper()) - ord('A')
        else:
            # Try to find correct answer in options by text match
            correct_lower = correct_answer.lower()
            for idx, option in enumerate(options):
                if correct_lower in str(option).lower():
                    correct_index = idx
                    break
        
        # Compare indices
        if answer_index is not None and correct_index is not None:
            is_correct = (0 <= answer_index < len(options) and 
                         0 <= correct_index < len(options) and
                         answer_index == correct_index)
        else:
            # Fallback: text comparison
            is_correct = answer.lower() == correct_answer.lower()
        
        score = max_score if is_correct else 0.0
        return is_correct, score
    
    async def _grade_short_answer(
        self,
        answer: str,
        metadata: Dict[str, Any],
        max_score: float,
        similarity_threshold: float = 0.85
    ) -> Tuple[bool, float]:
        """Grade short answer question using semantic similarity.
        
        Args:
            answer: Student answer
            metadata: Question metadata with correct_answer
            max_score: Maximum score
            similarity_threshold: Minimum similarity for full credit
            
        Returns:
            Tuple of (is_correct, score)
        """
        correct_answer = metadata.get('correct_answer', '')
        
        if not correct_answer:
            # No correct answer provided, can't grade
            return False, 0.0
        
        # Normalize answers
        answer = answer.strip().lower()
        correct_answer = str(correct_answer).strip().lower()
        
        # Try exact match first (fast)
        if answer == correct_answer:
            return True, max_score
        
        # Try fuzzy match (case-insensitive, whitespace-insensitive)
        answer_normalized = re.sub(r'\s+', ' ', answer)
        correct_normalized = re.sub(r'\s+', ' ', correct_answer)
        if answer_normalized == correct_normalized:
            return True, max_score
        
        # Use semantic similarity if embedding service available
        if self.embedding_service:
            try:
                similarity = await self._calculate_similarity(answer, correct_answer)
                if similarity >= similarity_threshold:
                    # Full credit for high similarity
                    return True, max_score
                elif similarity >= 0.7:
                    # Partial credit for medium similarity
                    partial_score = max_score * (similarity / similarity_threshold)
                    return False, partial_score
                else:
                    # No credit for low similarity
                    return False, 0.0
            except Exception as e:
                logger.warning(f"Error calculating similarity: {e}")
        
        # Fallback: no match
        return False, 0.0
    
    async def _calculate_similarity(
        self,
        answer: str,
        correct_answer: str
    ) -> float:
        """Calculate semantic similarity between two answers.
        
        Args:
            answer: Student answer
            correct_answer: Correct answer
            
        Returns:
            Similarity score (0.0 to 1.0)
        """
        if not self.embedding_service:
            return 0.0
        
        try:
            # Generate embeddings
            answer_embedding = await self.embedding_service.generate_embedding(answer)
            correct_embedding = await self.embedding_service.generate_embedding(correct_answer)
            
            # Calculate cosine similarity
            import numpy as np
            dot_product = np.dot(answer_embedding, correct_embedding)
            norm_a = np.linalg.norm(answer_embedding)
            norm_b = np.linalg.norm(correct_embedding)
            
            if norm_a == 0 or norm_b == 0:
                return 0.0
            
            similarity = dot_product / (norm_a * norm_b)
            return float(similarity)
        except Exception as e:
            logger.error(f"Error calculating similarity: {e}")
            return 0.0
    
    def _grade_problem_solving(
        self,
        answer: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float]:
        """Grade problem solving question.
        
        Args:
            answer: Student answer
            metadata: Question metadata with correct_answer
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score)
        """
        correct_answer = metadata.get('correct_answer', '')
        
        if not correct_answer:
            return False, 0.0
        
        # Extract numeric values
        answer_nums = self._extract_numbers(answer)
        correct_nums = self._extract_numbers(correct_answer)
        
        if answer_nums and correct_nums:
            # Check if numeric values match (within tolerance)
            if len(answer_nums) == len(correct_nums):
                all_match = all(
                    abs(a - c) < 0.01  # Tolerance for floating point
                    for a, c in zip(answer_nums, correct_nums)
                )
                if all_match:
                    return True, max_score
        
        # Fallback to text comparison
        answer_normalized = answer.strip().lower()
        correct_normalized = str(correct_answer).strip().lower()
        
        if answer_normalized == correct_normalized:
            return True, max_score
        
        # Partial credit for containing key terms
        key_terms = metadata.get('key_terms', [])
        if key_terms:
            matches = sum(1 for term in key_terms if term.lower() in answer_normalized)
            if matches > 0:
                partial_score = max_score * (matches / len(key_terms))
                return False, partial_score
        
        return False, 0.0
    
    def _extract_numbers(self, text: str) -> List[float]:
        """Extract numeric values from text.
        
        Args:
            text: Text to extract numbers from
            
        Returns:
            List of numeric values
        """
        # Match integers and floats
        pattern = r'-?\d+\.?\d*'
        matches = re.findall(pattern, text)
        return [float(m) for m in matches]
    
    async def _grade_drawing(
        self,
        answer: str,
        question: Dict[str, Any],
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float]:
        """Grade a drawing answer.
        
        Args:
            answer: Student answer (JSON string from Fabric.js)
            question: Question data
            metadata: Question metadata
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score)
        """
        try:
            drawing_data = json.loads(answer)
            question_text = question.get('text', '')
            expected_graph_info = metadata.get('expected_graph', None)
            
            is_correct, score, feedback = await self.graph_eval_service.evaluate_drawing(
                user_drawing_data=drawing_data,
                expected_graph_info=expected_graph_info,
                question_text=question_text,
                max_score=max_score
            )
            
            # Store feedback in metadata if needed
            if feedback:
                logger.info(f"Drawing evaluation feedback: {feedback}")
            
            return is_correct, score
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON in drawing answer: {answer[:100]}")
            return False, 0.0
        except Exception as e:
            logger.error(f"Error grading drawing: {e}", exc_info=True)
            return False, 0.0
    
    def _grade_exact_match(
        self,
        answer: str,
        metadata: Dict[str, Any],
        max_score: float
    ) -> Tuple[bool, float]:
        """Grade using exact match.
        
        Args:
            answer: Student answer
            metadata: Question metadata with correct_answer
            max_score: Maximum score
            
        Returns:
            Tuple of (is_correct, score)
        """
        correct_answer = metadata.get('correct_answer', '')
        
        if not correct_answer:
            return False, 0.0
        
        answer_normalized = answer.strip().lower()
        correct_normalized = str(correct_answer).strip().lower()
        
        is_correct = answer_normalized == correct_normalized
        score = max_score if is_correct else 0.0
        
        return is_correct, score
    
    def _apply_behavioral_penalties(
        self,
        score: float,
        max_score: float,
        behavioral_data: BehavioralPayload
    ) -> float:
        """Apply penalties based on behavioral data.
        
        Args:
            score: Current score
            max_score: Maximum possible score
            behavioral_data: Behavioral tracking data
            
        Returns:
            Adjusted score after penalties
        """
        adjusted_score = score
        
        # Hint penalty: -10% per hint accessed
        if behavioral_data.hints_accessed and behavioral_data.hints_accessed > 0:
            hint_penalty = max_score * 0.10 * behavioral_data.hints_accessed
            adjusted_score = max(0.0, adjusted_score - hint_penalty)
            logger.debug(
                f"Applied hint penalty: {hint_penalty:.2f} "
                f"(hints_accessed={behavioral_data.hints_accessed})"
            )
        
        # Confidence score weighting (for mastery updates, not score adjustment)
        # High confidence + wrong answer = deeper misconception
        # This is handled in mastery service, not here
        
        return adjusted_score
    
    async def grade_test(self, test_id: str) -> Dict[str, Any]:
        """Grade all responses in a test.
        
        Args:
            test_id: Test UUID
            
        Returns:
            Dictionary with scoring results
        """
        # Get test with questions and responses
        test = await self.test_repo.get_test_with_questions(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        
        questions = test.get('questions', [])
        
        graded_count = 0
        correct_count = 0
        
        for question in questions:
            response = question.get('answer')
            if not response:
                continue  # Skip unanswered questions
            
            question_id = question['question_id']
            try:
                # Extract behavioral data from response if available
                behavioral_data = None
                if isinstance(response, dict) and 'behavioral_data' in response:
                    behavioral_data = BehavioralPayload(**response['behavioral_data'])
                    # Extract actual answer
                    answer = response.get('answer', response.get('text', ''))
                else:
                    answer = response
                
                is_correct, score, error_type, misconception, method = await self.grade_response(
                    test_id, question_id, answer, behavioral_data
                )
                graded_count += 1
                if is_correct:
                    correct_count += 1
            except Exception as e:
                logger.error(f"Error grading question {question_id}: {e}")
        
        # Calculate total score
        score_result = await self.test_repo.calculate_test_score(test_id)
        
        return {
            'test_id': test_id,
            'graded_count': graded_count,
            'correct_count': correct_count,
            **score_result
        }
