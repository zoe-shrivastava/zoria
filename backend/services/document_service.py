"""Document processing service using OpenAI Agents workflow."""

import logging
import os
import uuid
from pathlib import Path
from typing import Optional, Dict, Any, List
import aiofiles

from datetime import datetime
from core.config import settings
from core.database import get_db
from core.background_tasks import enqueue_document_processing, enqueue_document_phase1
from database.repositories.document_repository import DocumentRepository
from workflows.workflow import run_workflow, WorkflowInput, extract_concepts_from_markdown

logger = logging.getLogger(__name__)


class DocumentService:
    """Service for document processing operations."""
    
    def __init__(self):
        """Initialize document service."""
        self.db = get_db()
        self.document_repo = DocumentRepository(self.db)
        # Ensure upload directory exists
        settings.ensure_upload_dir()
    
    async def save_uploaded_file(
        self,
        file_content: bytes,
        filename: str
    ) -> tuple[str, str]:
        """Save uploaded file to disk.
        
        Args:
            file_content: File content bytes
            filename: Original filename
            
        Returns:
            Tuple of (file_path, unique_filename)
        """
        # Generate unique filename
        file_ext = Path(filename).suffix
        unique_filename = f"{uuid.uuid4()}{file_ext}"
        file_path = settings.UPLOAD_DIR / unique_filename
        
        # Save file
        async with aiofiles.open(file_path, 'wb') as f:
            await f.write(file_content)
        
        return str(file_path), unique_filename
    
    async def process_document(
        self,
        file_content: bytes,
        filename: str,
        child_ids: Optional[List[str]] = None,
        parent_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """Process a document: save, extract content, store in database.
        
        Args:
            file_content: File content bytes
            filename: Original filename
            child_ids: List of child UUIDs (optional, for many-to-many relationship)
            parent_id: Parent UUID (optional)
            
        Returns:
            Document processing result
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        try:
            # Save file
            file_path, unique_filename = await self.save_uploaded_file(file_content, filename)
            file_size = len(file_content)
            mime_type = "application/pdf"  # Default, could be detected
            
            # Use first child_id for backward compatibility (legacy child_id field)
            # But also use junction table for multiple children
            first_child_id = child_ids[0] if child_ids and len(child_ids) > 0 else None
            
            # Phase 1: Create document record with 'uploaded' status
            document_id = await self.document_repo.create_document(
                filename=filename,
                file_path=file_path,
                file_size=file_size,
                mime_type=mime_type,
                child_id=first_child_id,  # Legacy field for backward compatibility
                parent_id=parent_id
            )
            
            # Attach document to all specified children via junction table
            if child_ids:
                await self.document_repo.attach_document_to_children(
                    document_id,
                    child_ids,
                    attached_by=parent_id
                )
            
            # Update status to 'uploaded'
            await self.document_repo.update_status(
                document_id,
                "uploaded",
                processing_started_at=datetime.utcnow()
            )
            
            # Enqueue Phase 1 processing (workflow + subject extraction) as background task
            await enqueue_document_phase1(document_id)
            
            logger.info(f"Document {document_id} queued for Phase 1 processing (workflow + subject extraction)")
            
            return {
                "document_id": document_id,
                "filename": filename,
                "status": "uploaded",
                "message": "Document uploaded successfully. Processing in background."
            }
            
        except Exception as e:
            logger.error(f"Error processing document: {e}", exc_info=True)
            # If document was created, mark it as failed
            if 'document_id' in locals():
                await self.document_repo.update_status(
                    document_id,
                    "failed",
                    failure_stage="upload",
                    error_message=str(e)
                )
            raise
    
    async def get_document(
        self,
        document_id: str,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Get document by ID with access control.
        
        Args:
            document_id: Document UUID
            user_id: User UUID (for access control)
            user_role: User role (for access control)
            
        Returns:
            Document information or None
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        document = await self.document_repo.get_document_by_id(document_id)
        if not document:
            return None
        
        # Access control: child can only see their own documents
        # Parent can see documents for their children
        # Admin can see all documents
        if user_role == "admin":
            # Admin has access to all documents
            pass
        elif user_role == "child":
            if document.get("child_id") and str(document["child_id"]) != user_id:
                return None
        
        # Parse concepts if it's a string (JSONB might be returned as string)
        concepts_data = document.get("concepts")
        if concepts_data and isinstance(concepts_data, str):
            try:
                import json
                concepts_data = json.loads(concepts_data)
            except (json.JSONDecodeError, TypeError):
                logger.warning(f"Failed to parse concepts JSON for document {document_id}")
                concepts_data = None
        
        # Get child_ids for this document
        child_ids = await self.document_repo.get_document_children(str(document["id"]))
        
        return {
            "id": str(document["id"]),
            "child_ids": child_ids,
            "child_id": str(document["child_id"]) if document.get("child_id") else None,
            "parent_id": str(document["parent_id"]) if document.get("parent_id") else None,
            "filename": document["filename"],
            "file_size": document.get("file_size"),
            "mime_type": document.get("mime_type"),
            "markdown_content": document.get("markdown_content"),
            "concepts": concepts_data,
            "status": document.get("status", "uploaded"),
            "uploaded_at": document["uploaded_at"],
            "processed_at": document.get("processed_at"),
            "processing_started_at": document.get("processing_started_at"),
            "processing_completed_at": document.get("processing_completed_at"),
            "is_active": document["is_active"]
        }
    
    async def list_documents(
        self,
        child_id: Optional[str] = None,
        parent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0
    ) -> Dict[str, Any]:
        """List documents with access control.
        
        Args:
            child_id: Child UUID (optional)
            parent_id: Parent UUID (optional)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            Dictionary with documents list and total count
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        if child_id:
            documents = await self.document_repo.get_documents_by_child(child_id, limit, offset)
            total = await self.document_repo.count_documents_by_child(child_id)
        elif parent_id:
            documents = await self.document_repo.get_documents_by_parent(parent_id, limit, offset)
            total = len(documents)  # Could add count method for parents too
        else:
            # Admin access - get all documents
            documents = await self.document_repo.get_all_documents(limit, offset)
            total = await self.document_repo.count_all_documents()
        
        # Get all child_ids for documents in batch (more efficient)
        document_ids = [str(d["id"]) for d in documents]
        child_ids_map = {}
        if document_ids:
            # Fetch all document-child relationships in one query
            relationships = await self.db.fetch(
                """
                SELECT document_id, child_id 
                FROM document_children 
                WHERE document_id = ANY($1::uuid[])
                """,
                [uuid.UUID(did) for did in document_ids]
            )
            for rel in relationships:
                doc_id = str(rel["document_id"])
                child_id = str(rel["child_id"])
                if doc_id not in child_ids_map:
                    child_ids_map[doc_id] = []
                child_ids_map[doc_id].append(child_id)
        
        result_documents = []
        for d in documents:
            # Ensure uploaded_at is always present (required by schema)
            uploaded_at = d.get("uploaded_at")
            if uploaded_at is None:
                # Fallback to current time if missing (shouldn't happen, but be defensive)
                uploaded_at = datetime.utcnow()
            
            doc_id = str(d["id"])
            child_ids = child_ids_map.get(doc_id, [])
            
            result_documents.append({
                "id": doc_id,
                "child_ids": child_ids,
                "child_id": str(d["child_id"]) if d.get("child_id") else None,  # Keep for backward compatibility
                "parent_id": str(d["parent_id"]) if d.get("parent_id") else None,
                "filename": d.get("filename", "Unknown"),
                "file_size": d.get("file_size"),
                "mime_type": d.get("mime_type"),
                "status": d.get("status", "uploaded"),
                "uploaded_at": uploaded_at,
                "processed_at": d.get("processed_at"),
                "processing_started_at": d.get("processing_started_at"),
                "processing_completed_at": d.get("processing_completed_at"),
                "is_active": bool(d.get("is_active", True))
            })
        
        return {
            "documents": result_documents,
            "total": total
        }
    
    async def delete_document(
        self,
        document_id: str,
        user_id: str,
        user_role: str
    ) -> None:
        """Delete a document with access control.
        
        Args:
            document_id: Document UUID
            user_id: User UUID
            user_role: User role
            
        Raises:
            ValueError: If document not found or access denied
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        document = await self.document_repo.get_document_by_id(document_id)
        if not document:
            raise ValueError("Document not found")
        
        # Access control
        if user_role == "child":
            if not document.get("child_id") or str(document["child_id"]) != user_id:
                raise ValueError("Access denied")
        elif user_role in ("parent", "admin"):
            # Parent can delete documents for their children
            if document.get("parent_id") and str(document["parent_id"]) != user_id:
                # Check if it's for one of their children
                # This would require checking parent-child relationship
                pass
        
        await self.document_repo.delete_document(document_id)
    
    async def reprocess_document(
        self,
        document_id: str,
        cleanup_existing: bool = True,
        skip_phase1: bool = False
    ) -> Dict[str, Any]:
        """Reprocess a document that's stuck or needs reprocessing.
        
        Args:
            document_id: Document UUID
            cleanup_existing: If True, delete existing chunks/questions/visuals first
            skip_phase1: If True, skip Phase 1 and go straight to Phase 2.
                         If False, automatically skips Phase 1 if markdown/concepts exist.
            
        Returns:
            Processing result
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        document = await self.document_repo.get_document_by_id(document_id)
        if not document:
            raise ValueError(f"Document {document_id} not found")
        
        current_status = document.get("status", "uploaded")
        file_path = document.get("file_path")
        has_markdown = bool(document.get("markdown_content"))
        has_concepts = bool(document.get("concepts"))
        
        # Step 1: Cleanup existing concepts/data if requested (do this FIRST)
        if cleanup_existing:
            logger.info(f"Starting cleanup for document {document_id}...")
            from workers.document_processor import DocumentProcessor
            processor = DocumentProcessor()
            await processor.db.connect()
            try:
                await processor.cleanup_document_data(document_id)
                logger.info(f"Cleanup completed for document {document_id}")
            finally:
                await processor.db.close()
            # Re-read document after cleanup so Phase 1 decision uses current state
            document = await self.document_repo.get_document_by_id(document_id)
            has_markdown = bool(document.get("markdown_content"))
            has_concepts = bool(document.get("concepts"))
        else:
            logger.info(f"Cleanup skipped for document {document_id} (cleanup_existing=False)")
        
        # Step 2: Re-extract concepts from existing markdown when we have markdown.
        # Always run Phase 1 after cleanup when markdown exists so Phase 2 has concepts.
        if (not skip_phase1 and has_markdown) or (cleanup_existing and has_markdown):
            # Re-extract concepts from existing markdown (skip document parsing)
            logger.info(f"Re-extracting concepts from existing markdown for document {document_id}...")
            logger.info(f"  - Will re-run concept_extractor agent (concept extraction from markdown)")
            logger.info(f"  - Skipping document_parser agent (using existing markdown)")
            
            markdown_content = document.get("markdown_content")
            if not markdown_content:
                raise ValueError("Document has no markdown content for concept extraction")
            
            # Extract concepts from existing markdown
            result = await extract_concepts_from_markdown(markdown_content, document_id=document_id)
            
            # Extract subject from result
            extracted_subject = result.get("subject")
        
            # Update document with new concepts and subject
            await self.document_repo.update_document_processing(
                document_id=document_id,
                markdown_content=markdown_content,  # Keep existing markdown
                concepts=result.get("concepts"),
                subject=extracted_subject
            )
            
            if extracted_subject:
                logger.info(f"Document {document_id} reclassified as subject: {extracted_subject}")
            
            await self.document_repo.update_status(document_id, "parsed")
            logger.info(f"Concept re-extraction complete: Document {document_id} has new concepts")
        elif not skip_phase1 and not has_markdown:
            # No markdown exists, need to run full Phase 1 (document parsing + concept extraction)
            if not file_path:
                raise ValueError("Document file path not found")
            
            logger.info(f"Phase 1: Reprocessing document {document_id} with OpenAI Agents...")
            logger.info(f"  - Will re-run document_parser agent (markdown extraction)")
            logger.info(f"  - Will re-run concept_extractor agent (concept extraction)")
            
            # Create workflow input with document_id for logging
            workflow_input = WorkflowInput(pdf_path=file_path, document_id=document_id)
            result = await run_workflow(workflow_input)
            
            # Extract subject from workflow result
            extracted_subject = result.get("subject")
            
            # Update document with processed content and subject
            await self.document_repo.update_document_processing(
                document_id=document_id,
                markdown_content=result.get("markdown"),
                concepts=result.get("concepts"),
                subject=extracted_subject
            )
            
            if extracted_subject:
                logger.info(f"Document {document_id} reclassified as subject: {extracted_subject}")
            
            await self.document_repo.update_status(document_id, "parsed")
            logger.info(f"Phase 1 complete: Document {document_id} parsed with new markdown and concepts")
        else:
            # skip_phase1=True, so skip concept extraction
            if has_markdown and has_concepts:
                logger.info(
                    f"Skipping Phase 1 for document {document_id}: "
                    f"markdown and concepts already exist (skip_phase1=True)"
                )
            else:
                logger.warning(
                    f"Skipping Phase 1 for document {document_id} but markdown/concepts missing. "
                    f"Phase 2 may fail."
                )
        
        # Phase 2: Trigger background processing
        logger.info(f"Phase 2: Enqueuing background processing for document {document_id}...")
        
        # Set status to "processing" BEFORE enqueuing to ensure it's not "ready" while background task runs
        await self.document_repo.update_status(document_id, "processing")
        
        # Verify status was updated (for debugging)
        status_check = await self.document_repo.get_document_by_id(document_id)
        if status_check and status_check.get("status") != "processing":
            logger.warning(
                f"Document {document_id} status update may have failed. "
                f"Expected 'processing', got '{status_check.get('status')}'"
            )
        
        # Pass cleanup_first if we already cleaned up (to avoid double cleanup)
        await enqueue_document_processing(document_id, cleanup_first=False)
        
        phase1_skipped = skip_phase1 or ((has_markdown and has_concepts) and not cleanup_existing)
        logger.info(
            f"Reprocess complete for document {document_id}. "
            f"Phase 1: {'skipped (markdown/concepts exist)' if phase1_skipped else 'completed'}, "
            f"Cleanup: {'completed' if cleanup_existing else 'skipped'}, "
            f"Phase 2: enqueued (running in background)"
        )
        
        return {
            "document_id": document_id,
            "filename": document.get("filename", "Unknown"),
            "status": "processing",
            "message": "Document reprocessing started" + (" (cleaned existing data)" if cleanup_existing else "")
        }