"""Admin API endpoints."""

import json
import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, HTTPException, status, Depends, Query

from schemas.user import ParentCreate, ParentResponse, ChildResponse
from schemas.document import DocumentListResponse, DocumentResponse
from schemas.llm_log import LLMLogListResponse, LLMUsageStatsResponse
from schemas.admin_settings import TimestampSettings
from services.user_service import UserService
from services.document_service import DocumentService
from services.llm_logging_service import LLMLoggingService
from services.concept_evaluation_service import (
    evaluate_markdown_concepts,
    summarize_concepts_for_kg_expected,
)
from core.dependencies import get_current_admin
from core.database import get_db, Database
from database.repositories.test_repository import TestRepository
from core.background_tasks import enqueue_document_processing

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
    logger = logging.getLogger(__name__)
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
        logger.error(f"Error reprocessing document {document_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}"
        )


@router.get("/documents/{document_id}/knowledge-graph")
async def get_document_knowledge_graph(
    document_id: str,
    ingestion_only: bool = Query(False, description="If true, return only data from document ingestion (concepts, relationships, questions from Concept JSON). Excludes later-generated questions."),
    admin: dict = Depends(get_current_admin)
):
    """Get knowledge graph data for a document (admin only).
    
    GET /api/v1/admin/documents/{document_id}/knowledge-graph
    GET /api/v1/admin/documents/{document_id}/knowledge-graph?ingestion_only=true
    
    Returns concepts, relationships, skills, and questions for the document.
    Use ingestion_only=true to see the raw KG at ingestion time (only questions created from Concept JSON).
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
        # When ingestion_only=True: only questions with metadata.source = 'concept_extraction' (created at ingestion).
        # Otherwise: all questions for this document (including later-generated ones).
        questions = []
        if concept_ids:
            concept_uuids = [uuid_module.UUID(cid) for cid in concept_ids]
            document_uuid = uuid_module.UUID(document_id)
            document_id_str = str(document_id)
            if ingestion_only:
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
                    WHERE q.concept_id = ANY($1::uuid[])
                      AND q.metadata->>'source' = 'concept_extraction'
                    ORDER BY c.name, q.difficulty
                    """,
                    concept_uuids
                )
            else:
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
                        q.metadata->>'document_id' = $3
                        OR
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
            "ingestion_only": ingestion_only,
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


@router.post("/documents/{document_id}/rebuild-knowledge-graph")
async def rebuild_document_knowledge_graph(
    document_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Rebuild knowledge graph and downstream data from existing markdown/concepts (admin only).

    POST /api/v1/admin/documents/{document_id}/rebuild-knowledge-graph

    This endpoint:
    - Requires that the document already has markdown_content and concepts JSON
    - Cleans up existing Phase 2/3 data (chunks, questions, visuals, relationships, document_concepts, concepts)
    - Re-runs the background processing pipeline (knowledge graph, questions, chunks, embeddings)
      using the existing markdown/concepts JSON without re-parsing the original PDF.
    """
    try:
        document_service = DocumentService()

        # Ensure document exists and admin has access
        document = await document_service.get_document(
            document_id=document_id,
            user_id=None,
            user_role="admin",
        )
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found",
            )

        # Validate that we have the data needed for Phase 2
        if not document.get("markdown_content") or not document.get("concepts"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Document is missing markdown or concepts JSON; run full reprocess first.",
            )

        # Set status to processing and enqueue background KG rebuild with cleanup
        await document_service.document_repo.update_status(document_id, "processing")
        await enqueue_document_processing(document_id, cleanup_first=True, run_type="rebuild")

        return {
            "document_id": document_id,
            "filename": document.get("filename"),
            "status": "processing",
            "message": "Knowledge graph rebuild started from existing markdown/concepts JSON",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to rebuild knowledge graph: {str(e)}",
        )


async def _get_document_markdown_concepts_for_eval(document_id: str) -> dict:
    document_service = DocumentService()
    document = await document_service.get_document(
        document_id=document_id,
        user_id=None,
        user_role="admin",
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    markdown = document.get("markdown_content") or ""
    concepts = document.get("concepts")
    if not markdown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document markdown is missing. Reprocess Phase 1 first.",
        )
    if not concepts:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document concepts JSON is missing. Reprocess Phase 1 first.",
        )
    if isinstance(concepts, str):
        concepts = json.loads(concepts)
    if not isinstance(concepts, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Document concepts JSON is invalid.",
        )
    return {"document": document, "markdown": markdown, "concepts": concepts}


async def _build_concepts_to_kg_actual(document_id: str, document: dict, ingestion_only: bool = True) -> dict:
    kg_actual = {
        "available": False,
        "reason": "Document is not ready. Knowledge graph summary becomes available after Phase 2 completes.",
        "all_nodes": 0,
        "all_edges": 0,
        "difficulty_distribution": {},
        "prerequisites": {
            "total_prerequisite_edges": 0,
            "concepts_with_prerequisites": 0,
        },
    }
    if document.get("status") != "ready":
        return kg_actual

    import uuid as uuid_module

    db = get_db()
    if db.pool is None:
        await db.connect()

    # ingestion_only=True means evaluate only KG entities associated to this
    # document's ingestion output:
    # - concepts created for this document (concepts.document_id)
    # - deduplicated concepts linked to this document (document_concepts)
    #
    # Relying only on concepts.document_id can produce false "0 actual nodes"
    # for docs where ingestion reused existing concepts.
    if ingestion_only:
        db_concepts = await db.fetch(
            """
            SELECT DISTINCT c.*
            FROM concepts c
            LEFT JOIN document_concepts dc ON dc.concept_id = c.id
            WHERE c.document_id = $1::uuid
               OR dc.document_id = $1::uuid
            ORDER BY c.created_at
            """,
            document_id,
        )
    else:
        from database.repositories.concept_repository import ConceptRepository
        concept_repo = ConceptRepository(db)
        db_concepts = await concept_repo.get_concepts_by_document(document_id)
    concept_ids = [str(c["id"]) for c in db_concepts] if db_concepts else []
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
                c_from.name AS from_concept_name,
                c_to.name AS to_concept_name
            FROM concept_relationships cr
            LEFT JOIN concepts c_from ON c_from.id = cr.from_concept_id
            LEFT JOIN concepts c_to ON c_to.id = cr.to_concept_id
            WHERE cr.from_concept_id = ANY($1::uuid[])
              AND cr.to_concept_id = ANY($1::uuid[])
            """,
            concept_uuids
        )

    difficulty_distribution = {}
    for c in db_concepts:
        difficulty = str(c.get("difficulty") or "unknown").strip().lower() or "unknown"
        difficulty_distribution[difficulty] = difficulty_distribution.get(difficulty, 0) + 1

    prereq_edges = [
        r for r in relationships
        if str(r.get("relationship_type") or "").strip().lower() == "prerequisite_of"
    ]
    concepts_with_prereqs = {str(r["to_concept_id"]) for r in prereq_edges if r.get("to_concept_id")}
    nodes = [
        {
            "concept_id": str(c["id"]),
            "concept_name": str(c.get("name") or "").strip(),
            "subtopic": c.get("subtopic"),
            "difficulty": str(c.get("difficulty") or "unknown").strip().lower() or "unknown",
        }
        for c in db_concepts
    ]
    edges = [
        {
            "from_concept_id": str(r["from_concept_id"]) if r.get("from_concept_id") else None,
            "to_concept_id": str(r["to_concept_id"]) if r.get("to_concept_id") else None,
            "from_concept_name": str(r.get("from_concept_name") or "").strip(),
            "to_concept_name": str(r.get("to_concept_name") or "").strip(),
            "relationship_type": str(r.get("relationship_type") or "").strip().lower(),
        }
        for r in prereq_edges
    ]
    return {
        "available": True,
        "reason": None,
        "all_nodes": len(db_concepts),
        "all_edges": len(relationships),
        "difficulty_distribution": difficulty_distribution,
        "prerequisites": {
            "total_prerequisite_edges": len(prereq_edges),
            "concepts_with_prerequisites": len(concepts_with_prereqs),
        },
        "nodes": nodes,
        "edges": edges,
    }


async def _load_kg_snapshot_actual(document_id: str, snapshot_id: Optional[str] = None) -> dict:
    """Load frozen KG payload from snapshots table."""
    db = get_db()
    if db.pool is None:
        await db.connect()

    if snapshot_id:
        row = await db.fetchrow(
            """
            SELECT id, document_id, run_type, snapshot_source, concepts_json_hash, kg_payload, created_at
            FROM kg_run_snapshots
            WHERE id = $1::uuid AND document_id = $2::uuid
            """,
            snapshot_id,
            document_id,
        )
    else:
        row = await db.fetchrow(
            """
            SELECT id, document_id, run_type, snapshot_source, concepts_json_hash, kg_payload, created_at
            FROM kg_run_snapshots
            WHERE document_id = $1::uuid
            ORDER BY created_at DESC
            LIMIT 1
            """,
            document_id,
        )

    if not row:
        return {
            "available": False,
            "reason": "No KG snapshot found for this document.",
            "all_nodes": 0,
            "all_edges": 0,
            "difficulty_distribution": {},
            "prerequisites": {
                "total_prerequisite_edges": 0,
                "concepts_with_prerequisites": 0,
            },
            "nodes": [],
            "edges": [],
        }

    payload = row.get("kg_payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload) if payload.strip() else {}
    if not isinstance(payload, dict):
        payload = {}
    payload["snapshot"] = {
        "id": str(row["id"]),
        "document_id": str(row["document_id"]),
        "run_type": row.get("run_type"),
        "snapshot_source": row.get("snapshot_source"),
        "concepts_json_hash": row.get("concepts_json_hash"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
    }
    payload.setdefault("available", True)
    payload.setdefault("reason", None)
    payload.setdefault("all_nodes", len(payload.get("nodes", [])))
    payload.setdefault("all_edges", len(payload.get("edges", [])))
    payload.setdefault("difficulty_distribution", {})
    payload.setdefault("prerequisites", {
        "total_prerequisite_edges": 0,
        "concepts_with_prerequisites": 0,
    })
    payload.setdefault("nodes", [])
    payload.setdefault("edges", [])
    return payload


@router.get("/documents/{document_id}/evaluate-md-concepts")
async def evaluate_md_to_concepts(
    document_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Evaluate MD -> Concepts report (admin only)."""
    try:
        eval_input = await _get_document_markdown_concepts_for_eval(document_id)
        document = eval_input["document"]
        markdown = eval_input["markdown"]
        concepts = eval_input["concepts"]
        m2c_report = evaluate_markdown_concepts(markdown, concepts)
        return {
            "document_id": document_id,
            "filename": document.get("filename"),
            "report": m2c_report,
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse stored concepts JSON.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate MD -> Concepts: {str(e)}",
        )


@router.get("/documents/{document_id}/evaluate-concepts-kg")
async def evaluate_concepts_to_kg(
    document_id: str,
    ingestion_only: bool = Query(
        True,
        description="If true, evaluate Concepts -> KG against ingestion-scoped KG only.",
    ),
    snapshot_id: Optional[str] = Query(
        None,
        description="Optional KG snapshot ID. If provided, evaluates against frozen snapshot payload.",
    ),
    admin: dict = Depends(get_current_admin),
):
    """Evaluate Concepts -> KG report (admin only)."""
    try:
        eval_input = await _get_document_markdown_concepts_for_eval(document_id)
        document = eval_input["document"]
        concepts = eval_input["concepts"]
        kg_expected = summarize_concepts_for_kg_expected(concepts)
        if snapshot_id:
            kg_actual = await _load_kg_snapshot_actual(document_id, snapshot_id=snapshot_id)
        else:
            kg_actual = await _build_concepts_to_kg_actual(document_id, document, ingestion_only=ingestion_only)
        expected_node_map = {
            str(n.get("concept_key") or "").lower(): n
            for n in (kg_expected.get("nodes") or [])
            if n.get("concept_key")
        }
        actual_node_map = {
            f"{str(n.get('subtopic') or '').strip().lower()}::{str(n.get('concept_name') or '').strip().lower()}": n
            for n in (kg_actual.get("nodes") or [])
            if n.get("concept_name")
        }

        expected_edge_map = {
            f"{str(e.get('from_key') or '').lower()}=>{str(e.get('to_key') or '').lower()}": e
            for e in (kg_expected.get("edges") or [])
            if e.get("from_key") and e.get("to_key")
        }
        actual_edge_map = {
            f"{str(e.get('from_concept_name') or '').strip().lower()}=>{str(e.get('to_concept_name') or '').strip().lower()}": e
            for e in (kg_actual.get("edges") or [])
            if e.get("from_concept_name") and e.get("to_concept_name")
        }

        node_rows = []
        for key, exp in expected_node_map.items():
            act = actual_node_map.get(key)
            node_rows.append({
                "type": "node",
                "concept_name": exp.get("concept_name"),
                "node_created": bool(act),
                "subtopic_correct": bool(act),
                "difficulty_expected": exp.get("difficulty"),
                "difficulty_actual": act.get("difficulty") if act else None,
                "difficulty_correct": bool(act) and (str(exp.get("difficulty") or "").strip().lower() == str(act.get("difficulty") or "").strip().lower()),
                "prerequisites_expected": exp.get("prerequisites", []),
                "correct": bool(act),
            })

        edge_rows = []
        for key, exp in expected_edge_map.items():
            act = actual_edge_map.get(key)
            edge_rows.append({
                "type": "edge",
                "prerequisite": (exp.get("from_key") or "").split("::", 1)[-1],
                "target_concept": (exp.get("to_key") or "").split("::", 1)[-1],
                "edge_created": bool(act),
                "correct": bool(act),
            })

        return {
            "document_id": document_id,
            "filename": document.get("filename"),
            "report": {
                "attributes": {
                    "all_nodes": {"expected": kg_expected["all_nodes"], "actual": kg_actual["all_nodes"]},
                    "all_edges": {"expected": kg_expected["all_edges"], "actual": kg_actual["all_edges"]},
                    "difficulty": {
                        "expected": kg_expected["difficulty_distribution"],
                        "actual": kg_actual["difficulty_distribution"],
                    },
                    "prerequisites": {
                        "expected": kg_expected["prerequisites"],
                        "actual": kg_actual["prerequisites"],
                    },
                },
                "availability": {
                    "available": kg_actual["available"],
                    "reason": kg_actual["reason"],
                    "ingestion_only": ingestion_only,
                    "snapshot_id": snapshot_id,
                },
                "entities": {
                    "expected_nodes": kg_expected.get("nodes", []),
                    "actual_nodes": kg_actual.get("nodes", []),
                    "expected_edges": kg_expected.get("edges", []),
                    "actual_edges": kg_actual.get("edges", []),
                },
                "rows": {
                    "node_rows": node_rows,
                    "edge_rows": edge_rows,
                },
                "snapshot": kg_actual.get("snapshot"),
            },
        }
    except HTTPException:
        raise
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to parse stored concepts JSON.",
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to evaluate Concepts -> KG: {str(e)}",
        )


@router.get("/documents/{document_id}/kg-snapshots")
async def list_document_kg_snapshots(
    document_id: str,
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    admin: dict = Depends(get_current_admin),
):
    """List immutable KG snapshots for a document (admin only)."""
    document_service = DocumentService()
    document = await document_service.get_document(
        document_id=document_id,
        user_id=None,
        user_role="admin",
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    db = get_db()
    if db.pool is None:
        await db.connect()

    rows = await db.fetch(
        """
        SELECT id, document_id, run_type, snapshot_source, concepts_json_hash, metadata, created_at
        FROM kg_run_snapshots
        WHERE document_id = $1::uuid
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        document_id,
        limit,
        offset,
    )

    total = await db.fetchval(
        "SELECT COUNT(*) FROM kg_run_snapshots WHERE document_id = $1::uuid",
        document_id,
    )

    return {
        "document_id": document_id,
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
        "snapshots": [
            {
                "id": str(r["id"]),
                "document_id": str(r["document_id"]),
                "run_type": r.get("run_type"),
                "snapshot_source": r.get("snapshot_source"),
                "concepts_json_hash": r.get("concepts_json_hash"),
                "metadata": r.get("metadata"),
                "created_at": r.get("created_at").isoformat() if r.get("created_at") else None,
            }
            for r in rows
        ],
    }


@router.get("/documents/{document_id}/kg-snapshots/{snapshot_id}")
async def get_document_kg_snapshot(
    document_id: str,
    snapshot_id: str,
    admin: dict = Depends(get_current_admin),
):
    """Get a single immutable KG snapshot with full payload (admin only)."""
    document_service = DocumentService()
    document = await document_service.get_document(
        document_id=document_id,
        user_id=None,
        user_role="admin",
    )
    if not document:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Document not found",
        )

    db = get_db()
    if db.pool is None:
        await db.connect()

    row = await db.fetchrow(
        """
        SELECT id, document_id, run_type, snapshot_source, concepts_json_hash, metadata, kg_payload, created_at
        FROM kg_run_snapshots
        WHERE id = $1::uuid AND document_id = $2::uuid
        """,
        snapshot_id,
        document_id,
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="KG snapshot not found",
        )

    kg_payload = row.get("kg_payload")
    if isinstance(kg_payload, str):
        kg_payload = json.loads(kg_payload) if kg_payload.strip() else {}
    if not isinstance(kg_payload, dict):
        kg_payload = {}

    return {
        "id": str(row["id"]),
        "document_id": str(row["document_id"]),
        "run_type": row.get("run_type"),
        "snapshot_source": row.get("snapshot_source"),
        "concepts_json_hash": row.get("concepts_json_hash"),
        "metadata": row.get("metadata"),
        "created_at": row.get("created_at").isoformat() if row.get("created_at") else None,
        "kg_payload": kg_payload,
    }


def _is_undefined_table_error(exc: Exception) -> bool:
    """True if the exception is asyncpg 'relation does not exist'."""
    return getattr(exc, "__class__", None).__name__ == "UndefinedTableError" or (
        "admin_settings" in str(exc) and "does not exist" in str(exc).lower()
    )


@router.get("/settings/timestamps", response_model=TimestampSettings)
async def get_timestamp_settings(
    admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    """Get admin-configurable timestamp display settings.

    GET /api/v1/admin/settings/timestamps
    If admin_settings table is missing, returns defaults (run migration 013_admin_settings.sql).
    """
    if db.pool is None:
        await db.connect()

    try:
        row = await db.fetchrow(
            "SELECT value FROM admin_settings WHERE key = 'timestamp_settings'"
        )
    except Exception as e:
        if _is_undefined_table_error(e):
            return TimestampSettings()
        raise

    if not row or row.get("value") is None:
        return TimestampSettings()

    value = row["value"]
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else {}
    if not isinstance(value, dict):
        value = {}
    return TimestampSettings(**value)


@router.put("/settings/timestamps", response_model=TimestampSettings)
async def update_timestamp_settings(
    settings: TimestampSettings,
    admin: dict = Depends(get_current_admin),
    db: Database = Depends(get_db),
):
    """Update admin-configurable timestamp display settings.

    PUT /api/v1/admin/settings/timestamps
    Requires admin_settings table (run migration 013_admin_settings.sql).
    """
    if db.pool is None:
        await db.connect()

    try:
        await db.execute(
            """
            INSERT INTO admin_settings (key, value)
            VALUES ('timestamp_settings', $1::jsonb)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            json.dumps(settings.dict()),
        )
    except Exception as e:
        if _is_undefined_table_error(e):
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Database migration required for display settings. "
                    "Run: backend/database/migrations/013_admin_settings.sql"
                ),
            ) from e
        raise

    return settings


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
        from api.v1.tests import get_evaluation_llm_service
        
        test_repo = TestRepository(db)
        
        # Get LLM service for evaluation (uses Ollama)
        llm_service = get_evaluation_llm_service()
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
