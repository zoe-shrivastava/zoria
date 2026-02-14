"""Content chunk repository for database operations."""

import uuid
import json
from typing import Optional, List, Dict, Any
import numpy as np

from core.database import Database


class ChunkRepository:
    """Repository for content chunk database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    async def create_chunk(
        self,
        document_id: str,
        chunk_type: str,
        chunk_text: str,
        embedding: Optional[List[float]] = None,
        concept_id: Optional[str] = None,
        question_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> str:
        """Create a new content chunk.
        
        Args:
            document_id: Document UUID
            chunk_type: Type of chunk (concept_overview, explanation, question, etc.)
            chunk_text: Chunk text content
            embedding: Embedding vector (list of floats)
            concept_id: Concept UUID (optional)
            question_id: Question UUID (optional)
            metadata: Metadata dictionary
            
        Returns:
            Chunk UUID
        """
        chunk_id = str(uuid.uuid4())
        
        # Convert embedding to PostgreSQL vector format
        embedding_str = None
        if embedding:
            if isinstance(embedding, np.ndarray):
                embedding = embedding.tolist()
            embedding_str = "[" + ",".join(map(str, embedding)) + "]"
        
        metadata_json = json.dumps(metadata) if metadata else "{}"
        
        await self.db.execute(
            """
            INSERT INTO content_chunks 
            (id, document_id, concept_id, question_id, chunk_type, chunk_text, embedding, metadata)
            VALUES ($1, $2, $3, $4, $5, $6, $7::vector, $8::jsonb)
            """,
            chunk_id,
            document_id,
            concept_id,
            question_id,
            chunk_type,
            chunk_text,
            embedding_str,
            metadata_json
        )
        return chunk_id
    
    async def create_chunks_batch(
        self,
        chunks: List[Dict[str, Any]]
    ) -> List[str]:
        """Create multiple chunks in a batch.
        
        Args:
            chunks: List of chunk dictionaries with required fields
            
        Returns:
            List of chunk UUIDs
        """
        chunk_ids = []
        
        for chunk in chunks:
            chunk_id = await self.create_chunk(
                document_id=chunk["document_id"],
                chunk_type=chunk["chunk_type"],
                chunk_text=chunk["chunk_text"],
                embedding=chunk.get("embedding"),
                concept_id=chunk.get("concept_id"),
                question_id=chunk.get("question_id"),
                metadata=chunk.get("metadata", {})
            )
            chunk_ids.append(chunk_id)
        
        return chunk_ids
    
    async def get_chunk_by_id(self, chunk_id: str) -> Optional[dict]:
        """Get chunk by ID.
        
        Args:
            chunk_id: Chunk UUID
            
        Returns:
            Chunk record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM content_chunks WHERE id = $1",
            chunk_id
        )
    
    async def get_chunks_by_document(
        self,
        document_id: str,
        chunk_type: Optional[str] = None
    ) -> List[dict]:
        """Get all chunks for a document.
        
        Args:
            document_id: Document UUID
            chunk_type: Optional filter by chunk type
            
        Returns:
            List of chunk records
        """
        if chunk_type:
            return await self.db.fetch(
                """
                SELECT * FROM content_chunks 
                WHERE document_id = $1 AND chunk_type = $2
                ORDER BY created_at
                """,
                document_id, chunk_type
            )
        else:
            return await self.db.fetch(
                """
                SELECT * FROM content_chunks 
                WHERE document_id = $1
                ORDER BY created_at
                """,
                document_id
            )
    
    async def get_chunks_by_concept(self, concept_id: str) -> List[dict]:
        """Get all chunks for a concept.
        
        Args:
            concept_id: Concept UUID
            
        Returns:
            List of chunk records
        """
        return await self.db.fetch(
            "SELECT * FROM content_chunks WHERE concept_id = $1 ORDER BY created_at",
            concept_id
        )
    
    async def search_similar_chunks(
        self,
        query_embedding: List[float],
        top_k: int = 5,
        document_id: Optional[str] = None,
        chunk_type: Optional[str] = None,
        metadata_filter: Optional[Dict[str, Any]] = None
    ) -> List[dict]:
        """Search for similar chunks using vector similarity.
        
        Args:
            query_embedding: Query embedding vector
            top_k: Number of results to return
            document_id: Optional filter by document
            chunk_type: Optional filter by chunk type
            metadata_filter: Optional metadata filters (e.g., {"grade": [6, 7], "difficulty": "easy"})
            
        Returns:
            List of similar chunk records with similarity scores
        """
        # Convert embedding to PostgreSQL vector format
        embedding_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Build query with filters
        where_clauses = []
        params = [embedding_str]
        param_index = 2
        
        if document_id:
            where_clauses.append(f"document_id = ${param_index}")
            params.append(document_id)
            param_index += 1
        
        if chunk_type:
            where_clauses.append(f"chunk_type = ${param_index}")
            params.append(chunk_type)
            param_index += 1
        
        # Add metadata filters if provided
        if metadata_filter:
            for key, value in metadata_filter.items():
                if isinstance(value, list):
                    # Array containment
                    where_clauses.append(f"metadata->'{key}' @> ${param_index}::jsonb")
                    params.append(json.dumps(value))
                else:
                    # Simple equality
                    where_clauses.append(f"metadata->>'{key}' = ${param_index}")
                    params.append(str(value))
                param_index += 1
        
        where_clause = " AND " + " AND ".join(where_clauses) if where_clauses else ""
        
        query = f"""
            SELECT 
                *,
                1 - (embedding <=> $1::vector) as similarity
            FROM content_chunks
            WHERE embedding IS NOT NULL {where_clause}
            ORDER BY similarity DESC
            LIMIT ${param_index}
        """
        params.append(top_k)
        
        return await self.db.fetch(query, *params)
