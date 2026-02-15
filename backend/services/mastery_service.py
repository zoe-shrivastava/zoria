"""Mastery service for tracking and updating concept mastery scores."""

import logging
import json
from typing import Dict, Any, Optional, List

from database.repositories.test_repository import TestRepository
from core.database import Database
from services.evaluation import ErrorLibrary, ErrorType

logger = logging.getLogger(__name__)


class MasteryService:
    """Service for managing concept mastery tracking."""
    
    def __init__(self, db: Database):
        """Initialize mastery service.
        
        Args:
            db: Database instance
        """
        self.db = db
        self.test_repo = TestRepository(db)
    
    async def update_mastery_from_test(self, test_id: str) -> Dict[str, Any]:
        """Update mastery scores based on test results.
        
        Args:
            test_id: Test UUID
            
        Returns:
            Dictionary with mastery update results
        """
        # Get test
        test = await self.test_repo.get_test_by_id(test_id)
        if not test:
            raise ValueError(f"Test not found: {test_id}")
        
        child_id = test['child_id']
        concept_id = test.get('concept_id')
        
        if not concept_id:
            logger.warning(f"Test {test_id} has no concept_id, skipping mastery update")
            return {'updated': False, 'reason': 'no_concept_id'}
        
        # Calculate performance from test
        score_result = await self.test_repo.calculate_test_score(test_id)
        total_score = score_result.get('total_score', 0.0)
        max_score = score_result.get('max_score', 1.0)
        
        if max_score == 0:
            logger.warning(f"Test {test_id} has max_score of 0, skipping mastery update")
            return {'updated': False, 'reason': 'zero_max_score'}
        
        # Calculate performance percentage (0-100)
        performance = (total_score / max_score) * 100.0
        
        # Get behavioral data and error types from responses for weighted calculation
        responses = await self.db.fetch(
            """
            SELECT metadata, score, is_correct
            FROM test_responses
            WHERE test_id = $1
            """,
            test_id
        )
        
        # Calculate weighted performance considering confidence and error types
        weighted_performance = self._calculate_weighted_performance(
            performance, responses
        )
        
        # Update mastery using the database function with weighted performance
        new_mastery = await self.db.fetchval(
            """
            SELECT update_mastery_score($1, $2, $3)
            """,
            child_id, concept_id, weighted_performance
        )
        
        logger.info(
            f"Updated mastery for child {child_id}, concept {concept_id}: "
            f"{performance:.1f}% -> {new_mastery:.1f}"
        )
        
        return {
            'updated': True,
            'child_id': child_id,
            'concept_id': concept_id,
            'performance': performance,
            'new_mastery_score': float(new_mastery) if new_mastery else 0.0
        }
    
    async def get_mastery_score(
        self,
        child_id: str,
        concept_id: str
    ) -> Optional[float]:
        """Get mastery score for a child and concept.
        
        Args:
            child_id: Child UUID
            concept_id: Concept UUID
            
        Returns:
            Mastery score (0-100) or None if not found
        """
        result = await self.db.fetchrow(
            """
            SELECT mastery_score 
            FROM student_concept_mastery
            WHERE student_id = $1 AND concept_id = $2
            """,
            child_id, concept_id
        )
        
        if result:
            return float(result['mastery_score'])
        return None
    
    async def get_mastery_level(
        self,
        child_id: str,
        concept_id: str
    ) -> str:
        """Get mastery level (beginner, intermediate, advanced) for a concept.
        
        Args:
            child_id: Child UUID
            concept_id: Concept UUID
            
        Returns:
            Mastery level string
        """
        mastery_score = await self.get_mastery_score(child_id, concept_id)
        
        if mastery_score is None:
            return 'beginner'
        elif mastery_score >= 80:
            return 'advanced'
        elif mastery_score >= 50:
            return 'intermediate'
        else:
            return 'beginner'
    
    async def get_all_mastery_for_child(
        self,
        child_id: str
    ) -> Dict[str, float]:
        """Get all mastery scores for a child.
        
        Args:
            child_id: Child UUID
            
        Returns:
            Dictionary mapping concept_id to mastery_score
        """
        results = await self.db.fetch(
            """
            SELECT concept_id, mastery_score
            FROM student_concept_mastery
            WHERE student_id = $1
            """,
            child_id
        )
        
        return {
            str(r['concept_id']): float(r['mastery_score'])
            for r in results
        }
    
    async def get_concepts_needing_review(
        self,
        child_id: str,
        threshold: float = 70.0
    ) -> List[Dict[str, Any]]:
        """Get concepts that need review (mastery below threshold).
        
        Args:
            child_id: Child UUID
            threshold: Mastery threshold (default 70)
            
        Returns:
            List of concept dictionaries with mastery scores
        """
        results = await self.db.fetch(
            """
            SELECT 
                c.id,
                c.name,
                c.subtopic,
                c.difficulty,
                scm.mastery_score,
                scm.last_updated
            FROM student_concept_mastery scm
            JOIN concepts c ON scm.concept_id = c.id
            WHERE scm.student_id = $1 
            AND scm.mastery_score < $2
            ORDER BY scm.mastery_score ASC, scm.last_updated ASC
            """,
            child_id, threshold
        )
        
        return [dict(r) for r in results]
    
    def _calculate_weighted_performance(
        self,
        base_performance: float,
        responses: List[Dict[str, Any]]
    ) -> float:
        """Calculate weighted performance considering confidence and error types.
        
        Args:
            base_performance: Base performance percentage (0-100)
            responses: List of response dictionaries with metadata
            
        Returns:
            Weighted performance percentage (0-100)
        """
        if not responses:
            return base_performance
        
        total_weight = 0.0
        weighted_sum = 0.0
        
        for response in responses:
            metadata = response.get('metadata', {})
            if isinstance(metadata, str):
                try:
                    metadata = json.loads(metadata)
                except (json.JSONDecodeError, TypeError):
                    metadata = {}
            
            is_correct = response.get('is_correct', False)
            score = float(response.get('score', 0.0))
            max_score = 1.0  # Default, could be retrieved from test_questions
            
            # Get confidence score (1-5)
            confidence_score = metadata.get('confidence_score')
            if confidence_score:
                confidence_score = max(1, min(5, int(confidence_score)))
            else:
                confidence_score = 3  # Default to neutral
            
            # Get error type
            error_type_str = metadata.get('error_type', 'None')
            error_type = ErrorLibrary.classify_error(error_type_str)
            
            # Calculate weight based on confidence and correctness
            # High confidence + wrong answer = deeper misconception (higher penalty)
            # Low confidence + correct answer = less certain mastery (lower weight)
            if is_correct:
                # Correct answer: weight by confidence (higher confidence = more weight)
                weight = confidence_score / 5.0
            else:
                # Wrong answer: weight by confidence (higher confidence = deeper misconception)
                # Apply error type penalty
                error_penalty = ErrorLibrary.get_mastery_penalty(error_type)
                # High confidence wrong = more serious (weight it more heavily for penalty)
                weight = (confidence_score / 5.0) * error_penalty
            
            # Question performance (0-1)
            question_perf = score / max_score if max_score > 0 else 0.0
            
            weighted_sum += question_perf * weight * 100.0  # Convert to percentage
            total_weight += weight
        
        if total_weight > 0:
            weighted_performance = weighted_sum / total_weight
            # Clamp to 0-100
            return max(0.0, min(100.0, weighted_performance))
        else:
            return base_performance