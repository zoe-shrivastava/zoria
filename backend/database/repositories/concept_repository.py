"""Concept repository for database operations."""

import uuid
import json
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import Database


class ConceptRepository:
    """Repository for concept database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    async def create_concept(
        self,
        document_id: str,
        name: str,
        subtopic: Optional[str] = None,
        difficulty: Optional[str] = None,
        grade: Optional[List[int]] = None,
        prerequisites: Optional[List[str]] = None,
        keywords: Optional[List[str]] = None,
        source_markdown: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new concept.
        
        Args:
            document_id: Document UUID
            name: Concept name
            subtopic: Subtopic name
            difficulty: Difficulty level (easy, medium, hard)
            grade: List of grade levels
            prerequisites: List of prerequisite concept names
            keywords: List of keywords
            source_markdown: Source markdown text
            metadata: Additional metadata
            
        Returns:
            Concept UUID
        """
        concept_id = str(uuid.uuid4())
        await self.db.execute(
            """
            INSERT INTO concepts 
            (id, document_id, name, subtopic, difficulty, grade, prerequisites, keywords, source_markdown, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            """,
            concept_id,
            document_id,
            name,
            subtopic,
            difficulty,
            grade or [],
            prerequisites or [],
            keywords or [],
            source_markdown,
            json.dumps(metadata) if metadata else None
        )
        return concept_id
    
    async def get_concept_by_id(self, concept_id: str) -> Optional[dict]:
        """Get concept by ID.
        
        Args:
            concept_id: Concept UUID
            
        Returns:
            Concept record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM concepts WHERE id = $1",
            concept_id
        )
    
    async def get_concepts_by_document(self, document_id: str) -> List[dict]:
        """Get all concepts for a document.
        
        Uses both direct document_id link and document_concepts junction table
        to handle both new concepts and deduplicated existing concepts.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of concept records
        """
        return await self.db.fetch(
            """
            SELECT DISTINCT c.* 
            FROM concepts c
            LEFT JOIN document_concepts dc ON c.id = dc.concept_id
            WHERE c.document_id = $1 OR dc.document_id = $1
            ORDER BY c.created_at
            """,
            document_id
        )
    
    async def get_all_concepts(self) -> List[dict]:
        """Get all concepts (for deduplication).
        
        Returns:
            List of all concept records
        """
        return await self.db.fetch(
            "SELECT * FROM concepts ORDER BY name"
        )
    
    async def find_similar_concept(
        self,
        name: str,
        subtopic: Optional[str] = None,
        threshold: float = 0.85
    ) -> Optional[dict]:
        """Find similar concept by name (simple text matching for now).
        
        Note: Full semantic similarity would require embedding comparison.
        This is a placeholder that does simple name matching.
        
        Args:
            name: Concept name to search for
            subtopic: Optional subtopic
            threshold: Similarity threshold (not used in simple matching)
            
        Returns:
            Similar concept or None
        """
        # Simple name-based matching (can be enhanced with embeddings later)
        concepts = await self.db.fetch(
            """
            SELECT * FROM concepts 
            WHERE LOWER(name) = LOWER($1)
            LIMIT 1
            """,
            name
        )
        return concepts[0] if concepts else None
    
    async def link_to_document(self, concept_id: str, document_id: str) -> None:
        """Link an existing concept to a document.
        
        Args:
            concept_id: Concept UUID
            document_id: Document UUID
        """
        # Insert link (ON CONFLICT handles duplicates since it's a composite primary key)
        await self.db.execute(
            """
            INSERT INTO document_concepts (document_id, concept_id)
            VALUES ($1, $2)
            ON CONFLICT (document_id, concept_id) DO NOTHING
            """,
            document_id, concept_id
        )
    
    async def update_concept(
        self,
        concept_id: str,
        **kwargs
    ) -> None:
        """Update concept fields.
        
        Args:
            concept_id: Concept UUID
            **kwargs: Fields to update
        """
        if not kwargs:
            return
        
        # Build update query dynamically
        set_clauses = []
        values = []
        param_index = 1
        
        for key, value in kwargs.items():
            if key in ['grade', 'prerequisites', 'keywords']:
                set_clauses.append(f"{key} = ${param_index}")
                values.append(value or [])
            elif key == 'metadata':
                set_clauses.append(f"{key} = ${param_index}")
                values.append(json.dumps(value) if value else None)
            else:
                set_clauses.append(f"{key} = ${param_index}")
                values.append(value)
            param_index += 1
        
        set_clauses.append(f"updated_at = ${param_index}")
        values.append(datetime.utcnow())
        values.append(concept_id)
        
        query = f"""
            UPDATE concepts 
            SET {', '.join(set_clauses)}
            WHERE id = ${param_index + 1}
        """
        
        await self.db.execute(query, *values)
