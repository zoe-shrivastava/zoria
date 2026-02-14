"""Document repository for database operations."""

import uuid
import os
import logging
from typing import Optional, List, Dict, Any
from datetime import datetime

from core.database import get_db, Database

logger = logging.getLogger(__name__)


class DocumentRepository:
    """Repository for document database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    async def create_document(
        self,
        filename: str,
        file_path: str,
        file_size: int,
        mime_type: str,
        child_id: Optional[str] = None,
        parent_id: Optional[str] = None
    ) -> str:
        """Create a new document record.
        
        Args:
            filename: Original filename
            file_path: Path to stored file
            file_size: File size in bytes
            mime_type: MIME type
            child_id: Child UUID (optional)
            parent_id: Parent UUID (optional)
            
        Returns:
            Document UUID
        """
        document_id = str(uuid.uuid4())
        await self.db.execute(
            """
            INSERT INTO documents 
            (id, child_id, parent_id, filename, file_path, file_size, mime_type, uploaded_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            """,
            document_id, child_id, parent_id, filename, file_path, file_size, 
            mime_type, datetime.utcnow()
        )
        return document_id
    
    async def update_document_processing(
        self,
        document_id: str,
        markdown_content: Optional[str] = None,
        concepts: Optional[Dict[str, Any]] = None,
        subject: Optional[str] = None
    ) -> None:
        """Update document with processed content.
        
        Args:
            document_id: Document UUID
            markdown_content: Extracted markdown content
            concepts: Extracted concepts (JSON)
            subject: Extracted subject name
        """
        import json
        
        # Convert concepts to JSON string for JSONB storage
        concepts_json = json.dumps(concepts) if concepts else None
        
        # Build update query dynamically
        updates = []
        params = []
        param_index = 1
        
        if markdown_content is not None:
            updates.append(f"markdown_content = ${param_index}")
            params.append(markdown_content)
            param_index += 1
        
        if concepts_json is not None:
            updates.append(f"concepts = ${param_index}")
            params.append(concepts_json)
            param_index += 1
        
        if subject is not None:
            updates.append(f"subject = ${param_index}")
            params.append(subject)
            param_index += 1
        
        if updates:
            updates.append(f"processed_at = ${param_index}")
            params.append(datetime.utcnow())
            param_index += 1
            
            params.append(document_id)
            
            query = f"""
                UPDATE documents 
                SET {', '.join(updates)}
                WHERE id = ${param_index}
            """
            
            await self.db.execute(query, *params)
    
    async def get_document_by_id(self, document_id: str) -> Optional[dict]:
        """Get document by ID.
        
        Args:
            document_id: Document UUID
            
        Returns:
            Document record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM documents WHERE id = $1 AND is_active = TRUE",
            document_id
        )
    
    async def get_documents_by_child(self, child_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all documents for a child.
        
        Args:
            child_id: Child UUID
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of document records
        """
        return await self.db.fetch(
            """
            SELECT * FROM documents
            WHERE child_id = $1 AND is_active = TRUE
            ORDER BY uploaded_at DESC
            LIMIT $2 OFFSET $3
            """,
            child_id, limit, offset
        )
    
    async def get_documents_by_parent(self, parent_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all documents uploaded by a parent.
        
        Args:
            parent_id: Parent UUID
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of document records
        """
        return await self.db.fetch(
            """
            SELECT * FROM documents
            WHERE parent_id = $1 AND is_active = TRUE
            ORDER BY uploaded_at DESC
            LIMIT $2 OFFSET $3
            """,
            parent_id, limit, offset
        )
    
    async def delete_document(self, document_id: str) -> None:
        """Delete a document and all related content (hard delete).
        
        This performs a hard delete which will trigger CASCADE constraints
        to automatically delete:
        - concepts (and their questions, visuals, relationships)
        - content_chunks (with embeddings)
        - document_concepts links
        - document_children links
        - chunks (legacy table)
        - student_concept_mastery records for those concepts
        
        Note: Tests are completely preserved when documents are deleted:
        - tests.concept_id will be set to NULL (ON DELETE SET NULL)
        - test_questions contain independent copies of question data
        - test_questions.question_id will be set to NULL (ON DELETE SET NULL)
        - Tests remain fully functional with all question data intact
        - No test data is lost when documents are deleted
        
        Args:
            document_id: Document UUID
        """
        # First, get the document to retrieve file_path before deletion
        # Don't filter by is_active - we want to delete even if already soft-deleted
        document = await self.db.fetchrow(
            "SELECT file_path FROM documents WHERE id = $1",
            document_id
        )
        
        if not document:
            logger.warning(f"Document {document_id} not found for deletion")
            return
        
        # Delete the physical file if it exists
        file_path = document.get("file_path")
        if file_path:
            try:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    logger.info(f"Deleted physical file: {file_path}")
                else:
                    logger.warning(f"File not found at path: {file_path}")
            except Exception as e:
                logger.warning(f"Failed to delete physical file {file_path}: {e}")
        
        # Hard delete the document (CASCADE will handle related data)
        # This will automatically delete:
        # - concepts (ON DELETE CASCADE) -> which cascades to questions, visuals, relationships
        # - content_chunks (ON DELETE CASCADE)
        # - document_concepts (ON DELETE CASCADE)
        # - document_children (ON DELETE CASCADE)
        # - chunks (ON DELETE CASCADE)
        result = await self.db.execute(
            "DELETE FROM documents WHERE id = $1",
            document_id
        )
        
        # Log the deletion
        deleted_count = int(result.split()[-1]) if result else 0
        if deleted_count > 0:
            logger.info(f"Deleted document {document_id} and all related content via CASCADE")
        else:
            logger.warning(f"No document deleted for ID {document_id}")
    
    async def count_documents_by_child(self, child_id: str) -> int:
        """Count documents for a child.
        
        Args:
            child_id: Child UUID
            
        Returns:
            Document count
        """
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM documents WHERE child_id = $1 AND is_active = TRUE",
            child_id
        )
    
    async def update_status(
        self,
        document_id: str,
        status: str,
        processing_started_at: Optional[datetime] = None,
        processing_completed_at: Optional[datetime] = None,
        failure_stage: Optional[str] = None,
        error_message: Optional[str] = None
    ) -> None:
        """Update document processing status.
        
        Args:
            document_id: Document UUID
            status: New status (uploaded, parsed, processing, ready, failed)
            processing_started_at: Optional processing start timestamp
            processing_completed_at: Optional processing completion timestamp
            failure_stage: Optional failure stage (if status is failed)
            error_message: Optional error message (if status is failed)
        """
        # Build update query dynamically
        updates = [f"status = $1"]
        params = [status]
        param_index = 2
        
        if processing_started_at:
            updates.append(f"processing_started_at = ${param_index}")
            params.append(processing_started_at)
            param_index += 1
        
        if processing_completed_at:
            updates.append(f"processing_completed_at = ${param_index}")
            params.append(processing_completed_at)
            param_index += 1
        
        if failure_stage:
            updates.append(f"failure_stage = ${param_index}")
            params.append(failure_stage)
            param_index += 1
        
        if error_message:
            updates.append(f"error_message = ${param_index}")
            params.append(error_message)
            param_index += 1
        
        params.append(document_id)
        
        query = f"""
            UPDATE documents 
            SET {', '.join(updates)}
            WHERE id = ${param_index}
        """
        
        await self.db.execute(query, *params)
    
    async def get_all_documents(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all documents (admin access).
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of document records
        """
        return await self.db.fetch(
            """
            SELECT * FROM documents
            WHERE is_active = TRUE
            ORDER BY uploaded_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def count_all_documents(self) -> int:
        """Count all active documents (admin access).
        
        Returns:
            Total document count
        """
        return await self.db.fetchval(
            "SELECT COUNT(*) FROM documents WHERE is_active = TRUE"
        )
    
    # Document-Children junction table methods
    
    async def attach_document_to_children(
        self,
        document_id: str,
        child_ids: List[str],
        attached_by: Optional[str] = None
    ) -> None:
        """Attach a document to multiple children.
        
        Args:
            document_id: Document UUID
            child_ids: List of child UUIDs
            attached_by: Parent UUID who attached it (optional)
        """
        if not child_ids:
            return
        
        # Insert all relationships
        for child_id in child_ids:
            await self.db.execute(
                """
                INSERT INTO document_children (document_id, child_id, attached_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (document_id, child_id) DO NOTHING
                """,
                document_id, child_id, attached_by
            )
    
    async def detach_document_from_child(
        self,
        document_id: str,
        child_id: str
    ) -> None:
        """Detach a document from a child.
        
        Args:
            document_id: Document UUID
            child_id: Child UUID
        """
        await self.db.execute(
            "DELETE FROM document_children WHERE document_id = $1 AND child_id = $2",
            document_id, child_id
        )
    
    async def get_document_children(self, document_id: str) -> List[str]:
        """Get all child IDs attached to a document.
        
        Args:
            document_id: Document UUID
            
        Returns:
            List of child UUIDs
        """
        rows = await self.db.fetch(
            "SELECT child_id FROM document_children WHERE document_id = $1",
            document_id
        )
        return [str(row["child_id"]) for row in rows]
    
    async def get_documents_by_child_via_junction(self, child_id: str, limit: int = 100, offset: int = 0) -> List[dict]:
        """Get all documents for a child via junction table.
        
        Args:
            child_id: Child UUID
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of document records
        """
        return await self.db.fetch(
            """
            SELECT d.* FROM documents d
            INNER JOIN document_children dc ON d.id = dc.document_id
            WHERE dc.child_id = $1 AND d.is_active = TRUE
            ORDER BY d.uploaded_at DESC
            LIMIT $2 OFFSET $3
            """,
            child_id, limit, offset
        )
    
    async def count_documents_by_child_via_junction(self, child_id: str) -> int:
        """Count documents for a child via junction table.
        
        Args:
            child_id: Child UUID
            
        Returns:
            Document count
        """
        return await self.db.fetchval(
            """
            SELECT COUNT(*) FROM documents d
            INNER JOIN document_children dc ON d.id = dc.document_id
            WHERE dc.child_id = $1 AND d.is_active = TRUE
            """,
            child_id
        )