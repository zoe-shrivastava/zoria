"""Test repository for database operations."""

import uuid
import json
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import Database

logger = logging.getLogger(__name__)


def json_serialize(obj):
    """Custom JSON serializer for objects not serializable by default json code.
    
    Handles UUID objects and recursively processes lists and dicts.
    """
    if isinstance(obj, uuid.UUID):
        return str(obj)
    # Let json.dumps handle lists and dicts recursively with this default function
    raise TypeError(f"Type {type(obj)} not serializable")


class TestRepository:
    """Repository for test/quiz database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    async def create_test(
        self,
        child_id: str,
        concept_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        title: str = "Test",
        time_limit_minutes: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new test.
        
        Args:
            child_id: Child UUID
            concept_id: Concept UUID (optional)
            parent_id: Parent UUID (optional)
            title: Test title
            time_limit_minutes: Time limit in minutes (optional)
            metadata: Additional metadata
            
        Returns:
            Test UUID
        """
        test_id = str(uuid.uuid4())
        # Serialize metadata, converting UUIDs to strings
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata, default=json_serialize)
        
        await self.db.execute(
            """
            INSERT INTO tests 
            (id, child_id, parent_id, concept_id, title, time_limit_minutes, metadata, status, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, 'draft', $8)
            """,
            test_id,
            child_id,
            parent_id,
            concept_id,
            title,
            time_limit_minutes,
            metadata_json,
            datetime.utcnow()
        )
        return test_id
    
    async def get_test_by_id(self, test_id: str) -> Optional[dict]:
        """Get test by ID.
        
        Args:
            test_id: Test UUID
            
        Returns:
            Test record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM tests WHERE id = $1",
            test_id
        )
    
    async def get_test_with_questions(self, test_id: str) -> Optional[dict]:
        """Get test with all questions and responses.
        
        Uses independent question data stored in test_questions table.
        Questions remain available even if original questions are deleted.
        
        Args:
            test_id: Test UUID
            
        Returns:
            Test record with questions and responses, or None
        """
        test = await self.get_test_by_id(test_id)
        if not test:
            return None
        
        # Get questions from test_questions (independent copies)
        # Use stored question data, fallback to original question if available
        questions = await self.db.fetch(
            """
            SELECT 
                tq.id as test_question_id,
                tq.order_index,
                tq.section_title,
                tq.max_score,
                COALESCE(tq.question_text, q.text) as text,
                COALESCE(tq.question_type, q.type) as type,
                COALESCE(tq.question_difficulty, q.difficulty) as difficulty,
                COALESCE(tq.question_metadata, q.metadata) as metadata,
                COALESCE(tq.original_question_id, tq.question_id, q.id) as question_id,
                tr.id as response_id,
                tr.answer,
                tr.score,
                tr.is_correct,
                tr.time_spent_seconds,
                tr.submitted_at,
                tr.metadata as response_metadata
            FROM test_questions tq
            LEFT JOIN questions q ON tq.question_id = q.id OR tq.original_question_id = q.id
            LEFT JOIN test_responses tr ON tr.test_id = tq.test_id 
                AND tr.question_id = COALESCE(tq.question_id, tq.original_question_id)
            WHERE tq.test_id = $1
            ORDER BY tq.order_index
            """,
            test_id
        )
        
        # Convert to dict and parse JSON fields
        test_dict = dict(test)
        if test_dict.get('metadata'):
            test_dict['metadata'] = json.loads(test_dict['metadata'])
        
        questions_list = []
        for q in questions:
            q_dict = dict(q)
            # Parse metadata if it's a string
            if q_dict.get('metadata'):
                if isinstance(q_dict['metadata'], str):
                    q_dict['metadata'] = json.loads(q_dict['metadata'])
            # Parse response_metadata if it exists and is a string
            if q_dict.get('response_metadata'):
                if isinstance(q_dict['response_metadata'], str):
                    q_dict['response_metadata'] = json.loads(q_dict['response_metadata'])
                # Merge response_metadata fields into question dict for easier access
                if isinstance(q_dict['response_metadata'], dict):
                    q_dict['detailed_feedback'] = q_dict['response_metadata'].get('detailed_feedback')
                    q_dict['error_type'] = q_dict['response_metadata'].get('error_type')
                    q_dict['misconception'] = q_dict['response_metadata'].get('misconception')
                    q_dict['method_detected'] = q_dict['response_metadata'].get('method_detected')
            questions_list.append(q_dict)
        
        test_dict['questions'] = questions_list
        return test_dict
    
    async def get_tests_for_child(
        self,
        child_id: str,
        status: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """Get all tests for a child.
        
        Args:
            child_id: Child UUID
            status: Filter by status (optional)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of test records
        """
        if status:
            tests = await self.db.fetch(
                """
                SELECT * FROM tests
                WHERE child_id = $1 AND status = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
                """,
                child_id, status, limit, offset
            )
        else:
            tests = await self.db.fetch(
                """
                SELECT * FROM tests
                WHERE child_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                child_id, limit, offset
            )
        
        # Parse JSON fields
        result = []
        for test in tests:
            test_dict = dict(test)
            if test_dict.get('metadata'):
                test_dict['metadata'] = json.loads(test_dict['metadata'])
            result.append(test_dict)
        
        return result
    
    async def get_all_tests_grouped_by_child(
        self,
        status: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0
    ) -> Dict[str, List[dict]]:
        """Get all tests grouped by child (for admin view).
        
        Args:
            status: Filter by status (optional)
            limit: Maximum number of results per child
            offset: Offset for pagination
            
        Returns:
            Dictionary mapping child_id to list of test records
        """
        if status:
            tests = await self.db.fetch(
                """
                SELECT t.*, c.name as child_name, c.grade as child_grade
                FROM tests t
                LEFT JOIN children c ON t.child_id = c.id
                WHERE t.status = $1
                ORDER BY c.name, t.created_at DESC
                LIMIT $2 OFFSET $3
                """,
                status, limit, offset
            )
        else:
            tests = await self.db.fetch(
                """
                SELECT t.*, c.name as child_name, c.grade as child_grade
                FROM tests t
                LEFT JOIN children c ON t.child_id = c.id
                ORDER BY c.name, t.created_at DESC
                LIMIT $1 OFFSET $2
                """,
                limit, offset
            )
        
        # Parse JSON fields and group by child
        grouped = {}
        for test in tests:
            test_dict = dict(test)
            if test_dict.get('metadata'):
                test_dict['metadata'] = json.loads(test_dict['metadata'])
            
            child_id = str(test_dict.get('child_id', ''))
            if child_id not in grouped:
                grouped[child_id] = {
                    'child_id': child_id,
                    'child_name': test_dict.get('child_name', 'Unknown'),
                    'child_grade': test_dict.get('child_grade'),
                    'tests': []
                }
            
            # Remove child fields from test dict (they're in the group)
            test_dict.pop('child_name', None)
            test_dict.pop('child_grade', None)
            grouped[child_id]['tests'].append(test_dict)
        
        return grouped
    
    async def get_tests_for_parent(
        self,
        parent_id: str,
        child_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> List[dict]:
        """Get all tests for a parent (read-only view).
        
        Args:
            parent_id: Parent UUID
            child_id: Optional child UUID filter
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of test records
        """
        if child_id:
            tests = await self.db.fetch(
                """
                SELECT * FROM tests
                WHERE parent_id = $1 AND child_id = $2
                ORDER BY created_at DESC
                LIMIT $3 OFFSET $4
                """,
                parent_id, child_id, limit, offset
            )
        else:
            tests = await self.db.fetch(
                """
                SELECT * FROM tests
                WHERE parent_id = $1
                ORDER BY created_at DESC
                LIMIT $2 OFFSET $3
                """,
                parent_id, limit, offset
            )
        
        # Parse JSON fields
        result = []
        for test in tests:
            test_dict = dict(test)
            if test_dict.get('metadata'):
                test_dict['metadata'] = json.loads(test_dict['metadata'])
            result.append(test_dict)
        
        return result
    
    async def update_test_status(
        self,
        test_id: str,
        status: str,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None
    ) -> None:
        """Update test status.
        
        Args:
            test_id: Test UUID
            status: New status (draft, active, completed, expired)
            started_at: Start timestamp (optional)
            completed_at: Completion timestamp (optional)
        """
        if started_at and completed_at:
            await self.db.execute(
                """
                UPDATE tests 
                SET status = $1, started_at = $2, completed_at = $3, updated_at = $4
                WHERE id = $5
                """,
                status, started_at, completed_at, datetime.utcnow(), test_id
            )
        elif started_at:
            await self.db.execute(
                """
                UPDATE tests 
                SET status = $1, started_at = $2, updated_at = $3
                WHERE id = $4
                """,
                status, started_at, datetime.utcnow(), test_id
            )
        elif completed_at:
            await self.db.execute(
                """
                UPDATE tests 
                SET status = $1, completed_at = $2, updated_at = $3
                WHERE id = $4
                """,
                status, completed_at, datetime.utcnow(), test_id
            )
        else:
            await self.db.execute(
                """
                UPDATE tests 
                SET status = $1, updated_at = $2
                WHERE id = $3
                """,
                status, datetime.utcnow(), test_id
            )
    
    async def update_test_metadata(
        self,
        test_id: str,
        metadata: Optional[Dict[str, Any]]
    ) -> None:
        """Update test metadata JSON.
        
        Args:
            test_id: Test UUID
            metadata: Metadata dictionary to store (will replace existing)
        """
        metadata_json = None
        if metadata:
            metadata_json = json.dumps(metadata, default=json_serialize)
        
        await self.db.execute(
            """
            UPDATE tests
            SET metadata = $1, updated_at = $2
            WHERE id = $3
            """,
            metadata_json, datetime.utcnow(), test_id
        )
    
    async def add_question_to_test(
        self,
        test_id: str,
        question_id: str,
        order_index: int,
        section_title: Optional[str] = None,
        max_score: float = 1.0
    ) -> str:
        """Add a question to a test (creates an independent copy).
        
        Args:
            test_id: Test UUID
            question_id: Question UUID (to copy data from)
            order_index: Order of question in test
            section_title: Section name (optional)
            max_score: Maximum score for this question
            
        Returns:
            Test-question junction ID
        """
        # Get question data to store as independent copy
        question = await self.db.fetchrow(
            """
            SELECT id, text, type, difficulty, metadata
            FROM questions
            WHERE id = $1
            """,
            question_id
        )
        
        if not question:
            raise ValueError(f"Question {question_id} not found")
        
        # Parse metadata if it's a string
        question_metadata = question.get("metadata")
        if isinstance(question_metadata, str):
            question_metadata = json.loads(question_metadata)
        
        junction_id = str(uuid.uuid4())
        await self.db.execute(
            """
            INSERT INTO test_questions 
            (id, test_id, question_id, original_question_id, order_index, section_title, max_score,
             question_text, question_type, question_difficulty, question_metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            ON CONFLICT (test_id, order_index) DO UPDATE
            SET question_id = $3, original_question_id = $4, section_title = $6, max_score = $7,
                question_text = $8, question_type = $9, question_difficulty = $10, question_metadata = $11
            """,
            junction_id, test_id, question_id, question_id, order_index, section_title, max_score,
            question.get("text", ""),
            question.get("type", "multiple_choice"),
            question.get("difficulty"),
            json.dumps(question_metadata) if question_metadata else None
        )
        return junction_id
    
    async def save_response(
        self,
        test_id: str,
        question_id: str,
        answer: str,
        time_spent_seconds: Optional[int] = None,
        behavioral_data: Optional[Dict[str, Any]] = None
    ) -> str:
        """Save or update a test response.
        
        Args:
            test_id: Test UUID
            question_id: Question UUID
            answer: Student answer
            time_spent_seconds: Time spent on question (optional)
            behavioral_data: Behavioral tracking data (optional)
            
        Returns:
            Response ID
        """
        import json
        response_id = str(uuid.uuid4())
        
        # Store behavioral data in metadata JSONB field if available
        behavioral_json = json.dumps(behavioral_data) if behavioral_data else None
        
        # Check if metadata column exists, if not, insert without it
        try:
            # Try to insert with metadata column
            await self.db.execute(
                """
                INSERT INTO test_responses 
                (id, test_id, question_id, answer, time_spent_seconds, submitted_at, metadata)
                VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
                ON CONFLICT (test_id, question_id) DO UPDATE
                SET answer = $4, time_spent_seconds = $5, submitted_at = $6, metadata = $7::jsonb
                """,
                response_id, test_id, question_id, answer, time_spent_seconds, datetime.utcnow(), behavioral_json
            )
        except Exception as e:
            error_str = str(e).lower()
            # If metadata column doesn't exist, insert without it
            if "metadata" in error_str and ("does not exist" in error_str or "column" in error_str):
                logger.warning(f"Metadata column not found in test_responses, inserting without behavioral data. Run migration 016 to enable behavioral tracking.")
                await self.db.execute(
                    """
                    INSERT INTO test_responses 
                    (id, test_id, question_id, answer, time_spent_seconds, submitted_at)
                    VALUES ($1, $2, $3, $4, $5, $6)
                    ON CONFLICT (test_id, question_id) DO UPDATE
                    SET answer = $4, time_spent_seconds = $5, submitted_at = $6
                    """,
                    response_id, test_id, question_id, answer, time_spent_seconds, datetime.utcnow()
                )
            else:
                raise
        return response_id
    
    async def update_response_score(
        self,
        test_id: str,
        question_id: str,
        score: float,
        is_correct: bool,
        error_type: Optional[str] = None,
        misconception: Optional[str] = None,
        method_detected: Optional[str] = None,
        detailed_feedback: Optional[str] = None
    ) -> None:
        """Update the score for a response.
        
        Args:
            test_id: Test UUID
            question_id: Question UUID
            score: Score for this answer
            is_correct: Whether answer is correct
            error_type: Type of error if incorrect
            misconception: Description of misconception if applicable
            method_detected: Evaluation method used
            detailed_feedback: Detailed feedback about what is wrong or correct
        """
        # Try to update with metadata, fallback if column doesn't exist
        try:
            # Update metadata with evaluation results
            existing_metadata = await self.db.fetchval(
                """
                SELECT metadata FROM test_responses
                WHERE test_id = $1 AND question_id = $2
                """,
                test_id, question_id
            )
            
            # Parse existing metadata or create new dict
            if existing_metadata:
                if isinstance(existing_metadata, str):
                    try:
                        metadata = json.loads(existing_metadata)
                    except (json.JSONDecodeError, TypeError):
                        metadata = {}
                else:
                    metadata = existing_metadata.copy() if existing_metadata else {}
            else:
                metadata = {}
            
            # Add evaluation results to metadata
            if error_type:
                metadata['error_type'] = error_type
            if misconception:
                metadata['misconception'] = misconception
            if method_detected:
                metadata['method_detected'] = method_detected
            if detailed_feedback:
                # Ensure detailed_feedback is stored as a string
                if isinstance(detailed_feedback, dict):
                    # If it's a dict, convert to JSON string
                    metadata['detailed_feedback'] = json.dumps(detailed_feedback)
                elif isinstance(detailed_feedback, str):
                    metadata['detailed_feedback'] = detailed_feedback
                else:
                    # Convert other types to string
                    metadata['detailed_feedback'] = str(detailed_feedback)
            
            metadata_json = json.dumps(metadata) if metadata else None
            
            await self.db.execute(
                """
                UPDATE test_responses
                SET score = $1, is_correct = $2, metadata = $3::jsonb
                WHERE test_id = $4 AND question_id = $5
                """,
                score, is_correct, metadata_json, test_id, question_id
            )
        except Exception as e:
            error_str = str(e).lower()
            # If metadata column doesn't exist, update without it
            if "metadata" in error_str and ("does not exist" in error_str or "column" in error_str):
                logger.warning(f"Metadata column not found in test_responses, updating without evaluation metadata. Run migration 016 to enable full tracking.")
                await self.db.execute(
                    """
                    UPDATE test_responses
                    SET score = $1, is_correct = $2
                    WHERE test_id = $3 AND question_id = $4
                    """,
                    score, is_correct, test_id, question_id
                )
            else:
                raise
    
    async def clear_evaluation_data(self, test_id: str) -> None:
        """Clear evaluation data (scores, is_correct, evaluation metadata) for a test.
        
        This is used when reevaluating a test - keeps answers but clears scores.
        
        Args:
            test_id: Test UUID
        """
        # Clear scores, is_correct, and evaluation metadata but keep answers
        try:
            # Try to clear metadata evaluation fields if metadata column exists
            await self.db.execute(
                """
                UPDATE test_responses
                SET score = NULL,
                    is_correct = NULL,
                    metadata = metadata - 'error_type' - 'misconception' - 'method_detected'
                WHERE test_id = $1
                """,
                test_id
            )
        except Exception as e:
            error_str = str(e).lower()
            # If metadata column doesn't exist, just clear scores
            if "metadata" in error_str and ("does not exist" in error_str or "column" in error_str):
                await self.db.execute(
                    """
                    UPDATE test_responses
                    SET score = NULL, is_correct = NULL
                    WHERE test_id = $1
                    """,
                    test_id
                )
            else:
                raise
    
    async def clear_all_responses(self, test_id: str) -> None:
        """Clear all response data (answers, scores, evaluations) for a test.
        
        This is used when reopening a test - removes all student answers.
        
        Args:
            test_id: Test UUID
        """
        # Delete all responses for this test
        await self.db.execute(
            """
            DELETE FROM test_responses
            WHERE test_id = $1
            """,
            test_id
        )
    
    async def reset_test_for_reopen(self, test_id: str) -> None:
        """Reset test status and clear completion data for reopening.
        
        Args:
            test_id: Test UUID
        """
        await self.db.execute(
            """
            UPDATE tests
            SET status = 'active',
                started_at = NULL,
                completed_at = NULL,
                total_score = NULL,
                updated_at = $1
            WHERE id = $2
            """,
            datetime.utcnow(), test_id
        )
    
    async def calculate_test_score(self, test_id: str) -> Dict[str, Any]:
        """Calculate total score for a test.
        
        Args:
            test_id: Test UUID
            
        Returns:
            Dictionary with total_score, max_score, percentage
        """
        result = await self.db.fetchrow(
            """
            SELECT 
                COALESCE(SUM(tr.score), 0) as total_score,
                COALESCE(SUM(tq.max_score), 0) as max_score
            FROM test_questions tq
            LEFT JOIN test_responses tr ON tr.test_id = tq.test_id 
                AND tr.question_id = COALESCE(tq.question_id, tq.original_question_id)
            WHERE tq.test_id = $1
            """,
            test_id
        )
        
        total_score = float(result['total_score']) if result['total_score'] else 0.0
        max_score = float(result['max_score']) if result['max_score'] else 0.0
        percentage = (total_score / max_score * 100) if max_score > 0 else 0.0
        
        # Update test record
        await self.db.execute(
            """
            UPDATE tests
            SET total_score = $1, max_score = $2, updated_at = $3
            WHERE id = $4
            """,
            total_score, max_score, datetime.utcnow(), test_id
        )
        
        return {
            'total_score': total_score,
            'max_score': max_score,
            'percentage': percentage
        }
