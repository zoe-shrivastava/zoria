"""Admin API endpoints."""

from fastapi import APIRouter, HTTPException, status, Depends, Query
from typing import List, Optional
from datetime import datetime

from schemas.user import ParentCreate, ParentResponse, ChildResponse
from schemas.document import DocumentListResponse, DocumentResponse
from schemas.llm_log import LLMLogListResponse, LLMUsageStatsResponse
from services.user_service import UserService
from services.document_service import DocumentService
from services.llm_logging_service import LLMLoggingService
from core.dependencies import get_current_admin
from core.database import get_db, Database
from database.repositories.test_repository import TestRepository

router = APIRouter()


@router.post("/parents", response_model=ParentResponse, status_code=status.HTTP_201_CREATED)
async def create_parent(
    request: ParentCreate,
    admin: dict = Depends(get_current_admin)
):
    """Create a new parent user (admin only).
    
    POST /api/v1/admin/parents
    """
    try:
        user_service = UserService()
        result = await user_service.create_parent_user(
            email=request.email,
            password=request.password,
            role=request.role
        )
        return ParentResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create parent"
        )


@router.get("/parents", response_model=List[ParentResponse])
async def list_parents(
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """List all parents (admin only).
    
    GET /api/v1/admin/parents
    """
    try:
        user_service = UserService()
        parents = await user_service.list_parents(limit=limit, offset=offset)
        return [ParentResponse(**p) for p in parents]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list parents"
        )


@router.delete("/parents/{parent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_parent(
    parent_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Deactivate a parent account (admin only).
    
    DELETE /api/v1/admin/parents/{parent_id}
    """
    try:
        user_service = UserService()
        await user_service.deactivate_parent(parent_id)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to deactivate parent"
        )


# Children management endpoints for admin

@router.get("/children", response_model=List[ChildResponse])
async def list_children(
    limit: int = 1000,
    offset: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """List all children (admin only).
    
    GET /api/v1/admin/children
    
    - Admin can see all children across all parents
    """
    try:
        user_service = UserService()
        children = await user_service.list_children(parent_id=None, limit=limit, offset=offset)
        return [ChildResponse(**c) for c in children]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list children"
        )


# Document management endpoints for admin

@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    child_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    admin: dict = Depends(get_current_admin)
):
    """List all documents (admin only).
    
    GET /api/v1/admin/documents
    
    - Admin can see all documents across all children
    - Can filter by child_id if provided
    """
    try:
        document_service = DocumentService()
        result = await document_service.list_documents(
            child_id=child_id,
            parent_id=None,  # Admin sees all, not filtered by parent
            limit=limit,
            offset=offset
        )
        return DocumentListResponse(**result)
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing admin documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}"
        )


@router.get("/documents/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get a specific document (admin only).
    
    GET /api/v1/admin/documents/{document_id}
    """
    try:
        document_service = DocumentService()
        document = await document_service.get_document(
            document_id=document_id,
            user_id=None,  # Admin has access to all
            user_role="admin"
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return DocumentResponse(**document)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get document: {str(e)}"
        )


@router.post("/documents/{document_id}/reprocess", response_model=DocumentResponse)
async def reprocess_document(
    document_id: str,
    cleanup_existing: bool = True,
    skip_phase1: bool = False,
    admin: dict = Depends(get_current_admin)
):
    """Reprocess a document (admin only).
    
    POST /api/v1/admin/documents/{document_id}/reprocess
    """
    try:
        document_service = DocumentService()
        await document_service.reprocess_document(
            document_id=document_id,
            cleanup_existing=cleanup_existing,
            skip_phase1=skip_phase1
        )
        
        # Fetch the updated document to return proper DocumentResponse
        document = await document_service.get_document(
            document_id=document_id,
            user_id=None,  # Admin has access to all
            user_role="admin"
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return DocumentResponse(**document)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}"
        )


@router.get("/documents/{document_id}/knowledge-graph")
async def get_document_knowledge_graph(
    document_id: str,
    admin: dict = Depends(get_current_admin)
):
    """Get knowledge graph data for a document (admin only).
    
    GET /api/v1/admin/documents/{document_id}/knowledge-graph
    
    Returns concepts, relationships, skills, and questions for the document.
    """
    try:
        import uuid as uuid_module
        from database.repositories.concept_repository import ConceptRepository
        from database.repositories.question_repository import QuestionRepository
        from core.database import get_db
        
        db = get_db()
        if db.pool is None:
            await db.connect()
        
        # Get document
        document_service = DocumentService()
        document = await document_service.get_document(
            document_id=document_id,
            user_id=None,
            user_role="admin"
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        if document.get("status") != "ready":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document must be in 'ready' status to view knowledge graph"
            )
        
        concept_repo = ConceptRepository(db)
        question_repo = QuestionRepository(db)
        
        # Get concepts for this document
        concepts = await concept_repo.get_concepts_by_document(document_id)
        
        concept_ids = [str(c["id"]) for c in concepts] if concepts else []
        
        # Get relationships
        relationships = []
        if concept_ids:
            concept_uuids = [uuid_module.UUID(cid) for cid in concept_ids]
            relationships = await db.fetch(
                """
                SELECT 
                    cr.id,
                    cr.from_concept_id,
                    cr.to_concept_id,
                    cr.relationship_type,
                    cr.strength,
                    c1.name as from_concept_name,
                    c2.name as to_concept_name
                FROM concept_relationships cr
                JOIN concepts c1 ON cr.from_concept_id = c1.id
                JOIN concepts c2 ON cr.to_concept_id = c2.id
                WHERE cr.from_concept_id = ANY($1::uuid[]) 
                   OR cr.to_concept_id = ANY($1::uuid[])
                """,
                concept_uuids
            )
        
        # Get questions for concepts - ONLY from this document
        # Questions now store document_id in metadata, so we can filter by that.
        # For backward compatibility: if document_id is NULL in metadata, only show questions
        # if the concept was originally created for this document (c.document_id = $2).
        questions = []
        if concept_ids:
            concept_uuids = [uuid_module.UUID(cid) for cid in concept_ids]
            document_uuid = uuid_module.UUID(document_id)
            document_id_str = str(document_id)
            questions = await db.fetch(
                """
                SELECT DISTINCT
                    q.id,
                    q.concept_id,
                    q.text,
                    q.type,
                    q.difficulty,
                    c.name as concept_name
                FROM questions q
                JOIN concepts c ON q.concept_id = c.id
                LEFT JOIN document_concepts dc ON c.id = dc.concept_id
                WHERE q.concept_id = ANY($1::uuid[])
                  AND (
                    -- New questions: check metadata->>'document_id'
                    q.metadata->>'document_id' = $3
                    OR
                    -- Old questions (backward compatibility): only if concept was created for this document
                    (q.metadata->>'document_id' IS NULL AND c.document_id = $2)
                  )
                ORDER BY c.name, q.difficulty
                """,
                concept_uuids, document_uuid, document_id_str
            )
        
        # Get skills linked to questions
        skills = []
        if questions:
            question_ids = [uuid_module.UUID(str(q["id"])) for q in questions]
            skills = await db.fetch(
                """
                SELECT DISTINCT
                    s.id,
                    s.name,
                    s.description,
                    s.cognitive_level
                FROM skills s
                JOIN question_skills qs ON s.id = qs.skill_id
                WHERE qs.question_id = ANY($1::uuid[])
                ORDER BY s.name
                """,
                question_ids
            )
        
        # Get full document data including markdown and concepts JSON
        full_document = await document_service.get_document(
            document_id=document_id,
            user_id=None,
            user_role="admin"
        )
        
        return {
            "document_id": document_id,
            "document_name": document.get("filename"),
            "status": document.get("status"),
            "markdown_content": full_document.get("markdown_content") if full_document else None,
            "concepts_json": full_document.get("concepts") if full_document else None,
            "concepts": [
                {
                    "id": str(c["id"]),
                    "name": c.get("name"),
                    "subtopic": c.get("subtopic"),
                    "difficulty": c.get("difficulty"),
                    "grade": c.get("grade", []),
                    "keywords": c.get("keywords", []),
                    "prerequisites": c.get("prerequisites", [])
                }
                for c in concepts
            ],
            "relationships": [
                {
                    "id": str(r["id"]),
                    "from_concept_id": str(r["from_concept_id"]),
                    "to_concept_id": str(r["to_concept_id"]),
                    "from_concept_name": r.get("from_concept_name"),
                    "to_concept_name": r.get("to_concept_name"),
                    "relationship_type": r.get("relationship_type"),
                    "strength": float(r.get("strength", 1.0))
                }
                for r in relationships
            ],
            "questions": [
                {
                    "id": str(q["id"]),
                    "concept_id": str(q["concept_id"]),
                    "concept_name": q.get("concept_name"),
                    "text": q.get("text"),
                    "type": q.get("type"),
                    "difficulty": q.get("difficulty")
                }
                for q in questions
            ],
            "skills": [
                {
                    "id": str(s["id"]),
                    "name": s.get("name"),
                    "description": s.get("description"),
                    "cognitive_level": s.get("cognitive_level")
                }
                for s in skills
            ]
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting knowledge graph: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get knowledge graph: {str(e)}"
        )


# LLM Logs endpoints for admin

@router.get("/llm-logs", response_model=LLMLogListResponse)
async def list_llm_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    model: Optional[str] = None,
    call_type: Optional[str] = None,
    provider: Optional[str] = None,
    success: Optional[bool] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin: dict = Depends(get_current_admin)
):
    """List LLM logs with filtering (admin only).
    
    GET /api/v1/admin/llm-logs
    
    Query parameters:
    - limit: Number of logs to return (1-1000, default 100)
    - offset: Number of logs to skip (default 0)
    - model: Filter by model name
    - call_type: Filter by call type (llm_service, agent_sdk, workflow)
    - provider: Filter by provider (openai, ollama)
    - success: Filter by success status (true/false)
    - start_date: Filter logs from this date (ISO format)
    - end_date: Filter logs until this date (ISO format)
    """
    try:
        logging_service = LLMLoggingService(get_db())
        result = await logging_service.get_logs(
            limit=limit,
            offset=offset,
            model=model,
            call_type=call_type,
            provider=provider,
            success=success,
            start_date=start_date,
            end_date=end_date
        )
        
        from schemas.llm_log import LLMLogResponse
        logs = [LLMLogResponse(**log) for log in result["logs"]]
        
        return LLMLogListResponse(
            logs=logs,
            total=result["total"],
            limit=limit,
            offset=offset
        )
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing LLM logs: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list LLM logs: {str(e)}"
        )


@router.post("/tests/{test_id}/reevaluate")
async def reevaluate_test(
    test_id: str,
    admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db)
):
    """Reevaluate a completed test (admin only).
    
    This will:
    1. Clear old evaluation data (scores, is_correct, evaluation metadata)
    2. Re-run evaluation on all responses
    3. Update test scores
    
    POST /api/v1/admin/tests/{test_id}/reevaluate
    """
    try:
        from services.scoring_service import ScoringService
        from services.mastery_service import MasteryService
        from services.llm_service import LLMService
        
        test_repo = TestRepository(db)
        
        # Get LLM service for evaluation (uses Ollama)
        llm_service = LLMService(
            model_name="llama3.2:3b-instruct-fp16",
            enable_logging=True,
            context_source="evaluation"
        )
        scoring_service = ScoringService(db, embedding_service=None, llm_service=llm_service)
        mastery_service = MasteryService(db)
        
        # Get test to verify it exists and is completed
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        if test['status'] != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot reevaluate test with status: {test['status']}. Test must be completed."
            )
        
        # Clear old evaluation data (keeps answers, clears scores)
        await test_repo.clear_evaluation_data(test_id)
        
        # Re-run evaluation
        scoring_result = await scoring_service.grade_test(test_id)
        
        # Update mastery scores based on new evaluation
        # The method gets child_id from the test itself
        await mastery_service.update_mastery_from_test(test_id)
        
        return {
            "success": True,
            "test_id": test_id,
            "message": "Test reevaluated successfully",
            "scoring_result": scoring_result
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to reevaluate test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reevaluate test: {str(e)}"
        )


@router.post("/tests/{test_id}/reopen")
async def reopen_test(
    test_id: str,
    admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db)
):
    """Reopen a completed test for submission (admin only).
    
    This will:
    1. Delete all answers and evaluations
    2. Reset test status to 'active'
    3. Clear completion timestamps
    
    POST /api/v1/admin/tests/{test_id}/reopen
    """
    try:
        test_repo = TestRepository(db)
        
        # Get test to verify it exists
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Clear all responses (answers and evaluations)
        await test_repo.clear_all_responses(test_id)
        
        # Reset test status
        await test_repo.reset_test_for_reopen(test_id)
        
        return {
            "success": True,
            "test_id": test_id,
            "message": "Test reopened successfully. All answers and evaluations have been cleared."
        }
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Failed to reopen test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reopen test: {str(e)}"
        )


@router.get("/llm-logs/stats", response_model=LLMUsageStatsResponse)
async def get_llm_usage_stats(
    model: Optional[str] = None,
    call_type: Optional[str] = None,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    admin: dict = Depends(get_current_admin)
):
    """Get LLM usage statistics (admin only).
    
    GET /api/v1/admin/llm-logs/stats
    
    Query parameters:
    - model: Filter by model name
    - call_type: Filter by call type
    - start_date: Filter from this date (ISO format)
    - end_date: Filter until this date (ISO format)
    """
    try:
        db = get_db()
        # Check if database pool is available
        if db.pool is None or db.pool.is_closing():
            logger.error("Database pool is not available for LLM usage stats")
            raise HTTPException(
                status_code=503,
                detail="Database connection unavailable. Please try again later."
            )
        
        logging_service = LLMLoggingService(db)
        stats = await logging_service.get_usage_stats(
            model=model,
            call_type=call_type,
            start_date=start_date,
            end_date=end_date
        )
        
        return LLMUsageStatsResponse(**stats)
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error getting LLM usage stats: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get LLM usage stats: {str(e)}"
        )
