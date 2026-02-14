"""Question repository for database operations."""

import uuid
import json
import numpy as np
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import Database


class QuestionRepository:
    """Repository for question database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    async def create_question(
        self,
        concept_id: str,
        text: str,
        question_type: Optional[str] = None,
        difficulty: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        status: str = "verified",
        embedding: Optional[np.ndarray] = None
    ) -> str:
        """Create a new question.
        
        Args:
            concept_id: Concept UUID
            text: Question text
            question_type: Type of question (multiple_choice, short_answer, etc.)
            difficulty: Difficulty level (easy, medium, hard)
            metadata: Additional metadata (options, correct_answer, etc.)
            status: Question status (generated, verified, rejected)
            embedding: Optional embedding vector
            
        Returns:
            Question UUID
        """
        question_id = str(uuid.uuid4())
        
        # Convert embedding to PostgreSQL vector format if provided
        embedding_str = None
        if embedding is not None:
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        await self.db.execute(
            """
            INSERT INTO questions 
            (id, concept_id, text, type, difficulty, metadata, status, embedding)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8::vector)
            """,
            question_id,
            concept_id,
            text,
            question_type,
            difficulty,
            json.dumps(metadata) if metadata else None,
            status,
            embedding_str
        )
        return question_id
    
    async def get_question_by_id(self, question_id: str) -> Optional[dict]:
        """Get question by ID.
        
        Args:
            question_id: Question UUID
            
        Returns:
            Question record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM questions WHERE id = $1",
            question_id
        )
    
    async def get_questions_by_concept(self, concept_id: str) -> List[dict]:
        """Get all questions for a concept.
        
        Args:
            concept_id: Concept UUID
            
        Returns:
            List of question records
        """
        return await self.db.fetch(
            "SELECT * FROM questions WHERE concept_id = $1 ORDER BY created_at",
            concept_id
        )
    
    async def get_questions_by_document(self, document_id: str) -> List[dict]:
        """Get all questions for a document (via concepts).
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of question records
        """
        return await self.db.fetch(
            """
            SELECT q.* FROM questions q
            JOIN concepts c ON q.concept_id = c.id
            WHERE c.document_id = $1
            ORDER BY q.created_at
            """,
            document_id
        )
    
    async def link_question_to_skill(
        self,
        question_id: str,
        skill_id: str
    ) -> None:
        """Link a question to a skill.
        
        Args:
            question_id: Question UUID
            skill_id: Skill UUID
        """
        await self.db.execute(
            """
            INSERT INTO question_skills (question_id, skill_id)
            VALUES ($1, $2)
            ON CONFLICT DO NOTHING
            """,
            question_id, skill_id
        )
    
    async def update_question_embedding(
        self,
        question_id: str,
        embedding: np.ndarray
    ) -> None:
        """Update question embedding.
        
        Args:
            question_id: Question UUID
            embedding: Embedding vector
        """
        if isinstance(embedding, np.ndarray):
            embedding = embedding.tolist()
        embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        await self.db.execute(
            """
            UPDATE questions 
            SET embedding = $1::vector
            WHERE id = $2
            """,
            embedding_str, question_id
        )
    
    async def update_question_status(
        self,
        question_id: str,
        status: str
    ) -> None:
        """Update question status.
        
        Args:
            question_id: Question UUID
            status: New status (generated, verified, rejected)
        """
        await self.db.execute(
            """
            UPDATE questions 
            SET status = $1
            WHERE id = $2
            """,
            status, question_id
        )
    
    async def count_questions_by_concept(
        self,
        concept_id: str,
        difficulty: Optional[str] = None,
        question_type: Optional[str] = None,
        exclude_rejected: bool = True
    ) -> int:
        """Count questions for a concept with optional filters.
        
        Args:
            concept_id: Concept UUID
            difficulty: Filter by difficulty (optional)
            question_type: Filter by question type (optional)
            exclude_rejected: Exclude rejected questions
            
        Returns:
            Count of questions
        """
        query = "SELECT COUNT(*) FROM questions WHERE concept_id = $1"
        params = [concept_id]
        param_index = 2
        
        if exclude_rejected:
            query += " AND status != 'rejected'"
        
        if difficulty:
            query += f" AND difficulty = ${param_index}"
            params.append(difficulty)
            param_index += 1
        
        if question_type:
            query += f" AND type = ${param_index}"
            params.append(question_type)
            param_index += 1
        
        return await self.db.fetchval(query, *params)
    
    async def find_similar_questions(
        self,
        query_embedding: np.ndarray,
        concept_id: str,
        limit: int = 5,
        similarity_threshold: float = 0.0
    ) -> List[Dict[str, Any]]:
        """Find similar questions using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            concept_id: Concept UUID to search within
            limit: Maximum number of results
            similarity_threshold: Minimum similarity score (0.0-1.0)
            
        Returns:
            List of similar questions with similarity scores
        """
        if isinstance(query_embedding, np.ndarray):
            query_embedding = query_embedding.tolist()
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        results = await self.db.fetch(
            """
            SELECT 
                id,
                text,
                type,
                difficulty,
                status,
                1 - (embedding <=> $1::vector) as similarity
            FROM questions
            WHERE concept_id = $2 
            AND embedding IS NOT NULL
            AND status != 'rejected'
            AND (1 - (embedding <=> $1::vector)) >= $3
            ORDER BY embedding <=> $1::vector
            LIMIT $4
            """,
            embedding_str, concept_id, similarity_threshold, limit
        )
        
        return [dict(r) for r in results]