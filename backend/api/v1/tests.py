"""Test/Quiz API endpoints."""

import json
import logging
from typing import Optional
from fastapi import APIRouter, HTTPException, status, Depends, Query, BackgroundTasks
from fastapi.responses import JSONResponse
from datetime import datetime

from schemas.test import (
    TestGenerateRequest,
    TestResponse,
    TestListResponse,
    TestAnswerRequest,
    TestSubmitResponse,
    TestStartResponse,
    TestQuestionResponse,
    QuestionGenerateRequest
)
from services.test_generation_service import TestGenerationService
from services.scoring_service import ScoringService
from services.mastery_service import MasteryService
from services.question_generation_service import QuestionGenerationService
from services.embedding_service import EmbeddingService
from services.llm_service import LLMService
from subject_config import get_subject_profile, get_all_subject_ids, normalize_subject_name, get_subject_display_name
from core.dependencies import get_current_user, get_current_child, get_current_parent, get_database
from core.config import settings
from core.background_tasks import (
    enqueue_test_generation_from_concept,
    enqueue_test_generation_from_topics,
    enqueue_study_guide_regeneration,
)
from core.database import Database

logger = logging.getLogger(__name__)

router = APIRouter()


def uuid_to_str(value):
    """Convert UUID to string, handling None values."""
    if value is None:
        return None
    return str(value) if hasattr(value, '__str__') else value


def get_embedding_service() -> EmbeddingService:
    """Dependency to get embedding service."""
    return EmbeddingService()


def get_llm_service() -> LLMService:
    """Dependency to get LLM service for question generation (model via QUESTION_GENERATION_MODEL)."""
    model = settings.QUESTION_GENERATION_MODEL
    logger.info("Question generation using model: %s", model)
    try:
        from core.database import get_db
        return LLMService(
            model_name=model,
            enable_logging=True,
            context_source="question_generation"
        )
    except Exception:
        return LLMService(
            model_name=model,
            enable_logging=False,
            context_source="question_generation"
        )


def get_evaluation_llm_service() -> LLMService:
    """Dependency to get LLM service for evaluation (uses local Ollama)."""
    # Use local Ollama for evaluation
    try:
        from core.database import get_db
        return LLMService(
            model_name="llama3.1",
            enable_logging=True,
            context_source="evaluation"
        )
    except Exception:
        # Fallback if database not available
        return LLMService(
            model_name="llama3.1",
            enable_logging=False,
            context_source="evaluation"
        )


def get_question_generation_service(
    db: Database = Depends(get_database),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    llm_service: LLMService = Depends(get_llm_service)
) -> QuestionGenerationService:
    """Dependency to get question generation service."""
    return QuestionGenerationService(db, embedding_service, llm_service)


def get_test_generation_service(
    db: Database = Depends(get_database),
    question_gen_service: QuestionGenerationService = Depends(get_question_generation_service)
) -> TestGenerationService:
    """Dependency to get test generation service."""
    return TestGenerationService(db, question_gen_service)


def get_scoring_service(
    db: Database = Depends(get_database),
    llm_service: LLMService = Depends(get_evaluation_llm_service)
) -> ScoringService:
    """Dependency to get scoring service."""
    # Note: embedding_service is optional for scoring
    # LLM service is used for evaluation (uses Ollama)
    return ScoringService(db, embedding_service=None, llm_service=llm_service)


def get_mastery_service(db: Database = Depends(get_database)) -> MasteryService:
    """Dependency to get mastery service."""
    return MasteryService(db)


@router.get("/subjects-topics/{child_id}")
async def get_subjects_topics(
    child_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get available subjects and topics for a child based on their uploaded documents.
    
    GET /api/v1/tests/subjects-topics/{child_id}
    
    Returns subjects and topics that have content (concepts/questions) for this child.
    """
    try:
        # Check access
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        if user_role == "child":
            if child_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        elif user_role in ("parent", "admin"):
            # Verify parent owns this child (compare as strings for UUID/str mismatch)
            child = await db.fetchrow(
                "SELECT parent_id FROM children WHERE id = $1",
                child_id
            )
            if not child:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
            if user_role == "parent":
                child_parent_id = uuid_to_str(child['parent_id']) if child.get('parent_id') else None
                user_id_str = str(user_id) if user_id else None
                if child_parent_id != user_id_str:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied"
                    )
        
        # Get all document IDs for this child (check both direct child_id and junction table)
        # Use UNION to get documents from both sources
        all_document_ids_result = await db.fetch(
            """
            SELECT DISTINCT d.id::text as id
            FROM documents d
            WHERE (d.child_id = $1 OR d.id IN (
                SELECT document_id FROM document_children WHERE child_id = $1
            ))
            AND d.is_active = TRUE
            """,
            child_id
        )
        
        logger.info(f"Found {len(all_document_ids_result) if all_document_ids_result else 0} documents for child {child_id}")
        
        if not all_document_ids_result:
            # No documents found for this child
            logger.warning(f"No documents found for child {child_id}")
            return {
                'subjects': [],
                'total_subjects': 0,
                'message': 'No documents found. Upload documents first.'
            }
        
        all_document_ids = [row['id'] for row in all_document_ids_result]
        logger.info(f"Document IDs: {all_document_ids[:5]}...")  # Log first 5
        
        # Get unique subjects and their topics from concepts
        # Subject is at document level (one PDF = one subject)
        # Include concepts linked via both direct document_id and document_concepts junction table
        subject_topic_data = await db.fetch(
            """
            SELECT DISTINCT 
                COALESCE(NULLIF(d.subject, ''), 'Uncategorized') as subject,
                NULLIF(TRIM(c.subtopic), '') as topic
            FROM concepts c
            LEFT JOIN document_concepts dc ON c.id = dc.concept_id
            JOIN documents d ON (
                c.document_id = d.id 
                OR dc.document_id = d.id
            )
            WHERE d.id::text = ANY($1::text[])
            AND d.is_active = TRUE
            AND (d.status = 'ready' OR d.status IS NULL OR d.status = 'processing')
            AND c.subtopic IS NOT NULL
            AND TRIM(c.subtopic) != ''
            ORDER BY COALESCE(NULLIF(d.subject, ''), 'Uncategorized'), NULLIF(TRIM(c.subtopic), '')
            """,
            all_document_ids
        )
        
        logger.info(f"Found {len(subject_topic_data) if subject_topic_data else 0} subject-topic pairs from concepts")
        
        # Group by subject
        subjects_map = {}
        for row in subject_topic_data:
            subject = row['subject'] or 'Uncategorized'
            topic = row['topic']
            
            if subject not in subjects_map:
                subjects_map[subject] = set()
            
            if topic:
                subjects_map[subject].add(topic)
        
        # Also get subjects from documents that might not have concepts yet
        documents_with_subjects = await db.fetch(
            """
            SELECT DISTINCT COALESCE(NULLIF(subject, ''), 'Uncategorized') as subject
            FROM documents
            WHERE id::text = ANY($1::text[])
            AND is_active = TRUE
            AND (status = 'ready' OR status IS NULL OR status = 'processing')
            AND COALESCE(NULLIF(subject, ''), 'Uncategorized') NOT IN (
                SELECT DISTINCT COALESCE(NULLIF(d.subject, ''), 'Uncategorized')
                FROM documents d
                JOIN concepts c ON c.document_id = d.id
                WHERE d.id::text = ANY($1::text[])
                AND d.is_active = TRUE
            )
            """,
            all_document_ids
        )
        
        for doc in documents_with_subjects:
            subject = doc['subject'] or 'Uncategorized'
            if subject not in subjects_map:
                subjects_map[subject] = set()  # Empty topics for now
        
        # If still no subjects, check if there are any documents at all
        if not subjects_map:
            # Check if documents exist but don't have subjects/concepts
            any_docs = await db.fetchrow(
                """
                SELECT COUNT(*) as count
                FROM documents
                WHERE id::text = ANY($1::text[])
                AND is_active = TRUE
                """,
                all_document_ids
            )
            
            if any_docs and any_docs['count'] > 0:
                # Documents exist but no subjects/concepts - return empty with message
                logger.warning(f"Child {child_id} has {any_docs['count']} documents but no subjects/concepts extracted yet")
                return {
                    'subjects': [],
                    'total_subjects': 0,
                    'message': f'Found {any_docs["count"]} document(s) but no subjects/topics extracted yet. Documents may still be processing.'
                }
        
        # Convert to response format with profile enrichment
        result = []
        for subject_display_name, topics_set in subjects_map.items():
            # Normalize subject name to subject_id
            subject_id = normalize_subject_name(subject_display_name)
            
            # Get subject profile if available
            subject_profile = get_subject_profile(subject_id)
            
            # Use display_name from profile if available, otherwise use the original subject_display_name
            # This ensures "Mathematics" is shown instead of "mathematics"
            final_display_name = get_subject_display_name(subject_id) if subject_profile else subject_display_name
            
            # Build response with profile metadata
            subject_data = {
                'subject_id': subject_id,
                'subject': final_display_name,  # Use proper display name (e.g., "Mathematics" not "mathematics")
                'topics': sorted(list(topics_set)) if topics_set else []
            }
            
            # Enrich with profile metadata if available
            if subject_profile:
                subject_data['display_name'] = subject_profile.get("display_name", final_display_name)
                subject_data['description'] = subject_profile.get("description", "")
                subject_data['question_types'] = subject_profile.get("question_generation", {}).get("preferred_question_types", [])
                subject_data['supports_equations'] = subject_profile.get("answer_format_rules", {}).get("latex_required_for_equations", False)
                subject_data['supports_diagrams'] = subject_profile.get("question_generation", {}).get("supports_diagrams", False)
                subject_data['requires_units'] = subject_profile.get("answer_format_rules", {}).get("unit_required", False)
            else:
                # Default metadata if no profile
                subject_data['display_name'] = subject_display_name
                subject_data['description'] = ""
                subject_data['question_types'] = ["multiple_choice", "short_answer"]
                subject_data['supports_equations'] = False
                subject_data['supports_diagrams'] = False
                subject_data['requires_units'] = False
            
            result.append(subject_data)
        
        # Sort by display name
        result.sort(key=lambda x: x.get('display_name', x['subject']))
        
        logger.info(f"Returning {len(result)} subjects for child {child_id}: {[r.get('display_name', r['subject']) for r in result]}")
        
        return {
            'subjects': result,
            'total_subjects': len(result)
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting subjects/topics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get subjects/topics: {str(e)}"
        )


@router.post("/generate", response_model=TestResponse, status_code=status.HTTP_201_CREATED)
async def generate_test(
    request: TestGenerateRequest,
    current_user: dict = Depends(get_current_user),
    test_service: TestGenerationService = Depends(get_test_generation_service),
    db: Database = Depends(get_database)
):
    """Generate a test from a concept.
    
    POST /api/v1/tests/generate
    
    - Only children can generate tests (for themselves).
    - Parents and admins can view tests and reports but cannot generate or take tests.
    """
    try:
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        # Block admins from generating tests
        if user_role == "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Admins cannot generate tests. Only children can generate tests."
            )
        # Block parents from generating tests (they can view all tests and reports only)
        if user_role == "parent":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Parents can view all tests and evaluation reports but cannot generate new tests. Only children can generate and take tests."
            )
        
        # Only children can generate tests (parent_id is None when child generates for themselves)
        if user_role != "child":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only children can generate tests."
            )
        child_id = user_id
        parent_id = None
        
        # Generate test - support both concept_id (legacy) and subject/topics (new).
        # For both paths we now create a draft test and enqueue background generation.
        if request.concept_id:
            # Legacy: generate from single concept (async)
            pending_test = await test_service.create_pending_test_from_concept(
                child_id=child_id,
                concept_id=request.concept_id,
                parent_id=parent_id,
                include_prerequisites=request.include_prerequisites,
                difficulty=request.difficulty,
                num_questions=request.num_questions,
                time_limit_minutes=request.time_limit_minutes,
            )
            test_id = uuid_to_str(pending_test.get("id"))
            
            # Enqueue background generation (fire-and-forget)
            await enqueue_test_generation_from_concept(
                test_id=test_id,
                child_id=child_id,
                concept_id=request.concept_id,
                parent_id=parent_id,
                include_prerequisites=request.include_prerequisites,
                difficulty=request.difficulty,
                num_questions=request.num_questions,
                time_limit_minutes=request.time_limit_minutes,
                language=request.language,
            )
            test = pending_test
        elif request.subject and request.topics:
            # New: generate from subject and topics
            # Normalize subject to subject_id (but keep original for display)
            subject_id = normalize_subject_name(request.subject)
            pending_test = await test_service.create_pending_test_from_topics(
                child_id=child_id,
                subject=subject_id,  # Use normalized subject_id
                topics=request.topics,
                parent_id=parent_id,
                include_prerequisites=request.include_prerequisites,
                difficulty=request.difficulty,
                num_questions=request.num_questions,
                time_limit_minutes=request.time_limit_minutes,
            )
            test_id = uuid_to_str(pending_test.get("id"))
            
            # Enqueue background generation (fire-and-forget)
            await enqueue_test_generation_from_topics(
                test_id=test_id,
                child_id=child_id,
                subject=subject_id,
                topics=request.topics,
                parent_id=parent_id,
                include_prerequisites=request.include_prerequisites,
                difficulty=request.difficulty,
                num_questions=request.num_questions,
                time_limit_minutes=request.time_limit_minutes,
                language=request.language,
            )
            test = pending_test
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Either concept_id or both subject and topics must be provided"
            )
        
        # Convert to response model
        questions = [
            TestQuestionResponse(
                question_id=uuid_to_str(q.get('question_id', q.get('id'))),
                text=q.get('text', ''),
                type=q.get('type', 'short_answer'),
                difficulty=q.get('difficulty'),
                order_index=q.get('order_index', 0),
                section_title=q.get('section_title'),
                max_score=float(q.get('max_score', 1.0)),
                metadata=q.get('metadata'),
                answer=q.get('answer'),
                score=q.get('score'),
                is_correct=q.get('is_correct')
            )
            for q in test.get('questions', [])
        ]
        
        return TestResponse(
            id=uuid_to_str(test['id']),
            child_id=uuid_to_str(test['child_id']),
            parent_id=uuid_to_str(test.get('parent_id')),
            concept_id=uuid_to_str(test.get('concept_id')),
            title=test['title'],
            status=test['status'],
            total_score=float(test['total_score']) if test.get('total_score') is not None else None,
            max_score=float(test['max_score']) if test.get('max_score') is not None else None,
            started_at=test.get('started_at'),
            completed_at=test.get('completed_at'),
            time_limit_minutes=test.get('time_limit_minutes'),
            created_at=test['created_at'],
            questions=questions
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Error generating test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate test: {str(e)}"
        )


@router.post("/generate-questions", status_code=status.HTTP_201_CREATED)
async def generate_questions(
    request: QuestionGenerateRequest,
    current_user: dict = Depends(get_current_user),
    question_gen_service: QuestionGenerationService = Depends(get_question_generation_service),
    db: Database = Depends(get_database)
):
    """Generate questions for a concept (parent/admin only).
    
    POST /api/v1/tests/generate-questions
    
    Body: {
        "concept_id": "...",
        "num_questions": 10,
        "question_type": "multiple_choice",
        "difficulty": "medium",
        "grade_level": 8,
        "similarity_threshold": 0.85,
        "language": "hi"
    }
    Optional "language" (e.g. "en", "hi", "es" or "English", "Hindi", "Spanish") makes the LLM generate questions in that language.
    """
    try:
        # Access control - only parents and admins can generate questions
        role = current_user.get("role")
        if role not in ["parent", "admin"]:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only parents and admins can generate questions"
            )
        
        # Verify concept exists
        concept = await db.fetchrow(
            "SELECT id, name FROM concepts WHERE id = $1",
            request.concept_id
        )
        if not concept:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Concept not found: {request.concept_id}"
            )
        
        # Generate questions
        result = await question_gen_service.generate_questions_for_concept(
            concept_id=request.concept_id,
            num_questions=request.num_questions,
            question_type=request.question_type,
            difficulty=request.difficulty,
            grade_level=request.grade_level,
            similarity_threshold=request.similarity_threshold,
            language=request.language,
        )
        
        return {
            'success': True,
            'concept_id': request.concept_id,
            'concept_name': concept.get('name'),
            **result
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate questions: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate questions: {str(e)}"
        )


@router.get("/{test_id}", response_model=TestResponse)
async def get_test(
    test_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get a test by ID.
    
    GET /api/v1/tests/{test_id}
    
    - Child can view their own tests
    - Parent can view tests for their children (read-only)
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        # Get test
        test = await test_repo.get_test_with_questions(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Check access
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        # Convert UUIDs to strings for comparison
        test_child_id = uuid_to_str(test['child_id'])
        test_parent_id = uuid_to_str(test.get('parent_id'))
        user_id_str = str(user_id) if user_id else None
        
        logger.info(f"Access check - Role: {user_role}, User ID: {user_id_str}, Test Child ID: {test_child_id}, Test Parent ID: {test_parent_id}")
        
        if user_role == "child":
            if test_child_id != user_id_str:
                logger.warning(f"Child access denied - test child_id {test_child_id} != user_id {user_id_str}")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own tests"
                )
        elif user_role == "admin":
            # Admins can view any test - no additional check needed
            pass
        elif user_role == "parent":
            # Parent can view if they're linked to the test or are the parent of the child
            if test_parent_id != user_id_str:
                # Check if user is parent of the child
                child = await db.fetchrow(
                    "SELECT parent_id FROM children WHERE id = $1",
                    test['child_id']
                )
                if child:
                    child_parent_id = uuid_to_str(child['parent_id'])
                    if child_parent_id != user_id_str:
                        logger.warning(f"Parent access denied - child parent_id {child_parent_id} != user_id {user_id_str}")
                        raise HTTPException(
                            status_code=status.HTTP_403_FORBIDDEN,
                            detail="Access denied: You can only view tests for your children"
                        )
                else:
                    logger.warning(f"Parent access denied - child not found for test child_id {test_child_id}")
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="Access denied: Child not found"
                    )
        else:
            logger.warning(f"Access denied - invalid role: {user_role}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: Invalid user role"
            )
        
        # Convert to response model
        questions = []
        for q in test.get('questions', []):
            # Safely extract detailed_feedback - ensure it's a string or None
            detailed_feedback = None
            if test['status'] == 'completed':
                feedback_value = q.get('detailed_feedback')
                if feedback_value is not None and feedback_value != '':
                    # Convert to string if it's not already
                    if isinstance(feedback_value, str):
                        detailed_feedback = feedback_value
                    elif isinstance(feedback_value, (dict, list)):
                        # If it's a dict or list, convert to JSON string
                        try:
                            detailed_feedback = json.dumps(feedback_value)
                        except (TypeError, ValueError):
                            detailed_feedback = str(feedback_value)
                    else:
                        # Convert other types to string
                        detailed_feedback = str(feedback_value)
            
            questions.append(
                TestQuestionResponse(
                    question_id=uuid_to_str(q.get('question_id', q.get('id'))),
                    text=q.get('text', ''),
                    type=q.get('type', 'short_answer'),
                    difficulty=q.get('difficulty'),
                    order_index=q.get('order_index', 0),
                    section_title=q.get('section_title'),
                    max_score=float(q.get('max_score', 1.0)),
                    metadata=q.get('metadata'),
                    answer=q.get('answer') if user_role == "child" or test['status'] == 'completed' else None,
                    score=q.get('score') if test['status'] == 'completed' else None,
                    is_correct=q.get('is_correct') if test['status'] == 'completed' else None,
                    time_spent_seconds=int(q['time_spent_seconds']) if q.get('time_spent_seconds') is not None else None,
                    detailed_feedback=detailed_feedback,
                    response_metadata=q.get('response_metadata') if isinstance(q.get('response_metadata'), dict) else None
                )
            )
        
        return TestResponse(
            id=uuid_to_str(test['id']),
            child_id=uuid_to_str(test['child_id']),
            parent_id=uuid_to_str(test.get('parent_id')),
            concept_id=uuid_to_str(test.get('concept_id')),
            title=test['title'],
            status=test['status'],
            total_score=float(test['total_score']) if test.get('total_score') is not None else None,
            max_score=float(test['max_score']) if test.get('max_score') is not None else None,
            started_at=test.get('started_at'),
            completed_at=test.get('completed_at'),
            time_limit_minutes=test.get('time_limit_minutes'),
            created_at=test['created_at'],
            questions=questions
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get test: {str(e)}"
        )


@router.get("/child/{child_id}/list", response_model=TestListResponse)
async def list_tests_for_child(
    child_id: str,
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """List tests for a child.
    
    GET /api/v1/tests/child/{child_id}/list?status=active|completed
    
    - Child can list their own tests
    - Parent can list tests for their children
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        # Check access
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        if user_role == "child":
            if child_id != user_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        elif user_role == "admin":
            # Admins can access all children's tests - no additional check needed
            pass
        elif user_role == "parent":
            # Check if user is parent of the child (compare as strings for UUID/str mismatch)
            child = await db.fetchrow(
                "SELECT parent_id FROM children WHERE id = $1",
                child_id
            )
            child_parent_id = uuid_to_str(child['parent_id']) if child and child.get('parent_id') else None
            user_id_str = str(user_id) if user_id else None
            if not child or child_parent_id != user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied"
                )
        
        # Get tests
        tests = await test_repo.get_tests_for_child(child_id, status=status_filter)
        
        # Convert to response models
        test_responses = []
        for test in tests:
            test_responses.append(TestResponse(
                id=uuid_to_str(test['id']),
                child_id=uuid_to_str(test['child_id']),
                parent_id=uuid_to_str(test.get('parent_id')),
                concept_id=uuid_to_str(test.get('concept_id')),
                title=test['title'],
                status=test['status'],
                total_score=float(test['total_score']) if test.get('total_score') is not None else None,
                max_score=float(test['max_score']) if test.get('max_score') is not None else None,
                started_at=test.get('started_at'),
                completed_at=test.get('completed_at'),
                time_limit_minutes=test.get('time_limit_minutes'),
                created_at=test['created_at'],
                questions=[],  # Don't include questions in list view
                metadata=test.get('metadata', {})
            ))
        
        return TestListResponse(tests=test_responses, total=len(test_responses))
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing tests: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tests: {str(e)}"
        )


@router.get("/admin/all-grouped", response_model=dict)
async def list_all_tests_grouped_by_child(
    status_filter: Optional[str] = Query(None, alias="status"),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """List all tests grouped by child (admin only).
    
    GET /api/v1/tests/admin/all-grouped?status=active|completed
    
    Returns tests grouped by child for easy admin management.
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        # Check access - only admins
        user_role = current_user.get("role")
        if user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can access this endpoint"
            )
        
        # Get all tests grouped by child
        grouped_tests = await test_repo.get_all_tests_grouped_by_child(status=status_filter)
        
        # Convert to response format
        result = {}
        for child_id, group_data in grouped_tests.items():
            test_responses = []
            for test in group_data['tests']:
                # Skip tests without child_id (shouldn't happen, but be safe)
                if not test.get('child_id'):
                    continue
                    
                test_responses.append(TestResponse(
                    id=uuid_to_str(test['id']),
                    child_id=uuid_to_str(test['child_id']),  # Required field
                    parent_id=uuid_to_str(test.get('parent_id')) if test.get('parent_id') else None,
                    concept_id=uuid_to_str(test.get('concept_id')) if test.get('concept_id') else None,
                    title=test.get('title', 'Untitled Test'),
                    description=test.get('description'),
                    status=test.get('status', 'draft'),
                    created_at=test.get('created_at'),
                    started_at=test.get('started_at'),
                    completed_at=test.get('completed_at'),
                    time_limit_minutes=test.get('time_limit_minutes'),
                    total_score=float(test.get('total_score')) if test.get('total_score') is not None else None,
                    max_score=float(test.get('max_score')) if test.get('max_score') is not None else None,
                    metadata=test.get('metadata', {}),
                    questions=[]  # Don't include questions in list view
                ))
            
            result[child_id] = {
                'child_id': child_id,
                'child_name': group_data.get('child_name', 'Unknown'),
                'child_grade': group_data.get('child_grade'),
                'tests': test_responses,
                'total': len(test_responses)
            }
        
        return result
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing all tests grouped by child: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list tests: {str(e)}"
        )


@router.post("/{test_id}/start", response_model=TestStartResponse)
async def start_test(
    test_id: str,
    current_user: dict = Depends(get_current_child),
    db: Database = Depends(get_database)
):
    """Start a test (child only).
    
    POST /api/v1/tests/{test_id}/start
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        child_id = current_user.get("child_id")
        child_id_str = str(child_id) if child_id else None
        
        # Get test
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Check access - convert UUID to string for comparison
        test_child_id = uuid_to_str(test['child_id'])
        if test_child_id != child_id_str:
            logger.warning(f"Start test access denied - test child_id {test_child_id} != user child_id {child_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only start your own tests"
            )
        
        # Check status
        if test['status'] not in ('draft', 'active'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot start test with status: {test['status']}"
            )
        
        # Update status and start time
        started_at = datetime.utcnow()
        await test_repo.update_test_status(test_id, 'active', started_at=started_at)
        
        # Get test with questions
        test_with_questions = await test_repo.get_test_with_questions(test_id)
        
        questions = [
            TestQuestionResponse(
                question_id=uuid_to_str(q.get('question_id', q.get('id'))),
                text=q.get('text', ''),
                type=q.get('type', 'short_answer'),
                difficulty=q.get('difficulty'),
                order_index=q.get('order_index', 0),
                section_title=q.get('section_title'),
                max_score=float(q.get('max_score', 1.0)),
                metadata=q.get('metadata')
            )
            for q in test_with_questions.get('questions', [])
        ]
        
        return TestStartResponse(
            test_id=test_id,
            title=test['title'],
            status='active',
            time_limit_minutes=test.get('time_limit_minutes'),
            questions=questions,
            started_at=started_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error starting test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to start test: {str(e)}"
        )


@router.post("/{test_id}/answer")
async def save_answer(
    test_id: str,
    request: TestAnswerRequest,
    current_user: dict = Depends(get_current_child),
    db: Database = Depends(get_database)
):
    """Save an answer to a test question (child only).
    
    POST /api/v1/tests/{test_id}/answer
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        child_id = current_user.get("child_id")
        child_id_str = str(child_id) if child_id else None
        
        # Get test
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Check access - convert UUID to string for comparison
        test_child_id = uuid_to_str(test['child_id'])
        if test_child_id != child_id_str:
            logger.warning(f"Save answer access denied - test child_id {test_child_id} != user child_id {child_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only answer questions in your own tests"
            )
        
        # Check status
        if test['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot answer test with status: {test['status']}"
            )
        
        # Convert behavioral payload to dict if provided
        behavioral_data = None
        if request.behavioral_data:
            behavioral_data = request.behavioral_data.dict(exclude_none=True)
        
        # Save answer
        await test_repo.save_response(
            test_id=test_id,
            question_id=request.question_id,
            answer=request.answer,
            time_spent_seconds=request.time_spent_seconds,
            behavioral_data=behavioral_data
        )
        
        return {"saved": True, "test_id": test_id, "question_id": request.question_id}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error saving answer: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save answer: {str(e)}"
        )


@router.post("/{test_id}/submit", response_model=TestSubmitResponse)
async def submit_test(
    test_id: str,
    current_user: dict = Depends(get_current_child),
    scoring_service: ScoringService = Depends(get_scoring_service),
    mastery_service: MasteryService = Depends(get_mastery_service),
    db: Database = Depends(get_database)
):
    """Submit and grade a test (child only).
    
    POST /api/v1/tests/{test_id}/submit
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        child_id = current_user.get("child_id")
        child_id_str = str(child_id) if child_id else None
        
        # Get test
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Check access - convert UUID to string for comparison
        test_child_id = uuid_to_str(test['child_id'])
        if test_child_id != child_id_str:
            logger.warning(f"Save answer access denied - test child_id {test_child_id} != user child_id {child_id_str}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only answer questions in your own tests"
            )
        
        # Check status
        if test['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot submit test with status: {test['status']}"
            )
        
        # Grade test
        score_result = await scoring_service.grade_test(test_id)
        
        # Update test status
        completed_at = datetime.utcnow()
        await test_repo.update_test_status(test_id, 'completed', completed_at=completed_at)
        
        # Update mastery
        mastery_result = await mastery_service.update_mastery_from_test(test_id)
        
        # Infer session state from behavioral data and store on test
        try:
            from services.state_inference import infer_session_state
            test_with_questions = await test_repo.get_test_with_questions(test_id)
            if test_with_questions:
                inferred_state, state_confidence = infer_session_state(test_with_questions)
                logger.info(
                    "Session state for test %s: inferred_session_state=%s inferred_state_confidence=%.2f",
                    test_id, inferred_state, state_confidence
                )
                existing_meta = (test_with_questions.get("metadata") or {}).copy()
                if not isinstance(existing_meta, dict):
                    existing_meta = {}
                existing_meta["inferred_session_state"] = inferred_state
                existing_meta["inferred_state_confidence"] = round(state_confidence, 2)
                await test_repo.update_test_metadata(test_id, existing_meta)
        except Exception as e:
            logger.warning("Failed to infer or store session state for test %s: %s", test_id, e)
        
        return TestSubmitResponse(
            test_id=test_id,
            total_score=score_result['total_score'],
            max_score=score_result['max_score'],
            percentage=score_result['percentage'],
            correct_count=score_result['correct_count'],
            graded_count=score_result['graded_count'],
            mastery_updated=mastery_result.get('updated', False)
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error submitting test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to submit test: {str(e)}"
        )


@router.delete("/{test_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_test(
    test_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Delete a test (admin only).
    
    DELETE /api/v1/tests/{test_id}
    """
    try:
        from database.repositories.test_repository import TestRepository
        test_repo = TestRepository(db)
        
        # Check access - only admins can delete tests
        role = current_user.get("role")
        if role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only admins can delete tests"
            )
        
        # Get test to verify it exists
        test = await test_repo.get_test_by_id(test_id)
        if not test:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Test not found"
            )
        
        # Before deleting the test, delete any GENERATED questions that are used
        # only by this test (so document-parsed questions remain untouched).
        # This ensures that generated questions created specifically for this test
        # are cleaned up when the test is deleted.
        
        # First, get the question IDs referenced by this test
        test_question_refs = await db.fetch(
            """
            SELECT DISTINCT COALESCE(tq.question_id, tq.original_question_id) as question_id
            FROM test_questions tq
            WHERE tq.test_id = $1
              AND COALESCE(tq.question_id, tq.original_question_id) IS NOT NULL
            """,
            test_id
        )
        
        if test_question_refs:
            # Extract question IDs (handle both UUID objects and strings)
            question_ids_to_check = []
            for ref in test_question_refs:
                qid = ref['question_id']
                question_ids_to_check.append(str(qid) if qid else None)
            question_ids_to_check = [qid for qid in question_ids_to_check if qid]
            
            if question_ids_to_check:
                # Delete generated questions that are referenced by this test and not by any other test
                # Use a subquery approach that works with PostgreSQL UUID arrays
                delete_result = await db.execute(
                    """
                    DELETE FROM questions q
                    WHERE q.status = 'generated'
                      AND q.id IN (
                          SELECT DISTINCT COALESCE(tq.question_id, tq.original_question_id)
                          FROM test_questions tq
                          WHERE tq.test_id = $1
                            AND COALESCE(tq.question_id, tq.original_question_id) IS NOT NULL
                      )
                      AND NOT EXISTS (
                          SELECT 1
                          FROM test_questions tq2
                          WHERE tq2.test_id <> $1
                            AND COALESCE(tq2.question_id, tq2.original_question_id) = q.id
                      )
                    """,
                    test_id
                )
                
                # Log how many questions were deleted
                deleted_count = int(delete_result.split()[-1]) if delete_result else 0
                if deleted_count > 0:
                    logger.info(f"Deleted {deleted_count} generated question(s) associated with test {test_id}")
                else:
                    logger.debug(f"No generated questions to delete for test {test_id} (may be used by other tests or not generated)")

        # Delete test (cascade will delete test_questions and test_responses)
        await db.execute("DELETE FROM tests WHERE id = $1", test_id)
        
        logger.info(f"Admin {current_user.get('parent_id')} deleted test {test_id}")
        
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting test: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to delete test: {str(e)}"
        )


@router.get("/child/{child_id}/evaluation-report")
async def get_evaluation_report(
    background_tasks: BackgroundTasks,
    child_id: str,
    days_back: int = Query(30, ge=7, le=365),
    generate_guides: bool = Query(True),
    language: Optional[str] = Query(None, description="Language for study guides and cards (e.g. English, Hindi, Spanish)"),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database),
):
    """Get detailed evaluation report for a child.
    
    GET /api/v1/tests/child/{child_id}/evaluation-report?days_back=30&generate_guides=true&language=Hindi
    
    - When generate_guides=true, report returns immediately with study_guide_links as placeholders (generating: true);
      study guides are generated in parallel in the background.
    - Child can view own report; parent can view their children's reports; admin can view any.
    """
    try:
        from services.evaluation_report_service import EvaluationReportService
        
        # Check access
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        if user_role == "child":
            if str(user_id) != str(child_id):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own reports"
                )
        elif user_role == "parent":
            child = await db.fetchrow(
                "SELECT parent_id FROM children WHERE id = $1",
                child_id
            )
            child_parent_id = uuid_to_str(child['parent_id']) if child and child.get('parent_id') else None
            user_id_str = str(user_id) if user_id else None
            if not child or child_parent_id != user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view reports for your children"
                )
        elif user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        report_service = EvaluationReportService(db)
        report = await report_service.generate_report(
            child_id=child_id,
            days_back=days_back,
            generate_study_guides=generate_guides,
            language=language,
        )
        if generate_guides and report and not report.get("error") and report.get("areas_of_focus"):
            background_tasks.add_task(
                report_service.generate_study_guides_background,
                child_id,
                report["areas_of_focus"],
                language,
                days_back,
            )
        
        return report
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating evaluation report: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to generate report: {str(e)}"
        )


@router.get("/study-guides/{guide_id}")
async def get_study_guide(
    guide_id: str,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get a specific study guide.
    
    GET /api/v1/tests/study-guides/{guide_id}
    """
    try:
        from services.study_guide_service import StudyGuideService
        
        study_guide_service = StudyGuideService(db)
        guide = await study_guide_service.get_study_guide(guide_id)
        
        if not guide:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study guide not found"
            )
        
        # Check access: child (own), parent (their children's guides), admin (any)
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        guide_child_id = str(guide['child_id']) if guide.get('child_id') else None
        
        if user_role == "child":
            if str(user_id) != guide_child_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view your own study guides"
                )
        elif user_role == "parent":
            child = await db.fetchrow(
                "SELECT parent_id FROM children WHERE id = $1",
                guide['child_id']
            )
            child_parent_id = uuid_to_str(child['parent_id']) if child and child.get('parent_id') else None
            user_id_str = str(user_id) if user_id else None
            if not child or child_parent_id != user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only view study guides for your children"
                )
        elif user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        return guide
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting study guide: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to get study guide: {str(e)}"
        )


@router.post("/study-guides/{guide_id}/regenerate")
async def regenerate_study_guide(
    guide_id: str,
    days_back: int = Query(30, ge=7, le=365),
    language: Optional[str] = Query(None, description="Language for study guide and cards (e.g. English, Hindi, Spanish)"),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Regenerate a study guide with latest evaluation data.
    
    POST /api/v1/tests/study-guides/{guide_id}/regenerate?days_back=30&language=Hindi
    """
    try:
        from services.study_guide_service import StudyGuideService
        from services.evaluation_report_service import EvaluationReportService
        
        study_guide_service = StudyGuideService(db)
        
        # Get existing guide to extract parameters
        existing_guide = await study_guide_service.get_study_guide(guide_id)
        
        if not existing_guide:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study guide not found"
            )
        
        # Check access: child (own), parent (their children's guides), admin (any)
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        if user_role == "child":
            if str(user_id) != str(existing_guide['child_id']):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only regenerate your own study guides"
                )
        elif user_role == "parent":
            child = await db.fetchrow(
                "SELECT parent_id FROM children WHERE id = $1",
                existing_guide['child_id']
            )
            child_parent_id = uuid_to_str(child['parent_id']) if child and child.get('parent_id') else None
            user_id_str = str(user_id) if user_id else None
            if not child or child_parent_id != user_id_str:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Access denied: You can only regenerate study guides for your children"
                )
        elif user_role != "admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied"
            )
        
        # Get latest evaluation report data to regenerate with current errors/feedback
        evaluation_service = EvaluationReportService(db)
        report = await evaluation_service.generate_report(
            child_id=str(existing_guide['child_id']),
            days_back=days_back,
            min_tests=1,
            generate_study_guides=False  # We'll generate manually
        )
        
        # Find the matching focus area in the report
        concept_name = existing_guide['concept_name']
        matching_area = None
        for area in report.get('areas_of_focus', []):
            if area['concept'] == concept_name:
                matching_area = area
                break
        
        if not matching_area:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot regenerate: no matching focus area for this guide. Complete a test created with subject+topics and view the evaluation report to regenerate from focus areas."
            )
        
        subject = matching_area.get('subject')
        if not subject or not str(subject).strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Focus area has no subject; cannot regenerate study guide. Tests must be created with subject+topics."
            )
        has_topic = matching_area.get('topic') or (matching_area.get('topics_from_test') and len(matching_area.get('topics_from_test', [])) > 0)
        if not has_topic:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Focus area has no topic from test; cannot regenerate study guide. Tests must be created with subject+topics so metadata.topics is set."
            )
        
        # Regenerate with latest data from evaluation report (run in background to avoid blocking server)
        child = await db.fetchrow(
            "SELECT grade FROM children WHERE id = $1",
            existing_guide['child_id']
        )
        grade_level = child['grade'] if child else None
        
        # Extract common errors with explanations
        common_errors_list = []
        if matching_area.get('common_errors'):
            for e in matching_area['common_errors']:
                if isinstance(e, dict):
                    error_type = e.get('type', str(e))
                    explanations = e.get('explanations', [])
                    if explanations:
                        error_desc = f"{error_type}: {explanations[0]}"
                        if len(explanations) > 1:
                            error_desc += f" (Also seen: {', '.join(explanations[1:2])})"
                        common_errors_list.append(error_desc)
                    else:
                        error_desc = f"{error_type}: This error occurred {e.get('count', 1)} time(s). Review the concept and practice similar problems."
                        common_errors_list.append(error_desc)
                else:
                    common_errors_list.append(str(e))
        
        focus_area_str = f"Performance: {matching_area['score_percentage']}%"
        from services.study_guide_service import is_study_guide_generation_in_progress_async
        if await is_study_guide_generation_in_progress_async(
            str(existing_guide['child_id']), concept_name, focus_area_str
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Study guide generation is already in progress for this focus area. Wait for it to finish, then try again."
            )
        await enqueue_study_guide_regeneration(
            guide_id=guide_id,
            child_id=str(existing_guide['child_id']),
            concept_name=concept_name,
            focus_area=focus_area_str,
            grade_level=grade_level,
            subject=subject,
            common_errors=common_errors_list if common_errors_list else None,
            misconceptions=matching_area.get('misconceptions', []),
            sample_questions=matching_area.get('sample_questions', []),
            language=language,
            topic_from_test=matching_area.get('topic'),
            topics_from_test=matching_area.get('topics_from_test'),
        )
        return JSONResponse(
            status_code=status.HTTP_202_ACCEPTED,
            content={
                'message': 'Study guide regeneration started. This may take several minutes. Poll GET /api/v1/tests/study-guides/{guide_id} until metadata.regeneration_status is not "in_progress".',
                'guide_id': guide_id,
            },
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error regenerating study guide: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to regenerate study guide: {str(e)}"
        )


@router.get("/child/{child_id}/study-guides")
async def list_study_guides(
    child_id: str,
    concept_name: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """List study guides for a child.
    
    GET /api/v1/tests/child/{child_id}/study-guides?concept_name=optional
    """
    try:
        from services.study_guide_service import StudyGuideService
        
        # Check access
        user_role = current_user.get("role")
        user_child_id = current_user.get("child_id")
        
        if user_role == "child" and str(user_child_id) != child_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only view your own study guides"
            )
        
        study_guide_service = StudyGuideService(db)
        guides = await study_guide_service.get_study_guides_for_child(
            child_id=child_id,
            concept_name=concept_name
        )
        
        return {'guides': guides}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error listing study guides: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list study guides: {str(e)}"
        )


@router.post("/study-guide/coach/chat")
async def chat_with_coach(
    request: dict,
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Chat with AI Coach about a study guide.
    
    POST /api/v1/tests/study-guide/coach/chat
    Body: {
        "guide_id": "uuid",
        "message": "user message",
        "conversation_history": [...],
        "context": {...},
        "language": "English"  // optional: e.g. English, Hindi, Spanish
    }
    """
    try:
        from services.study_guide_service import StudyGuideService
        
        guide_id = request.get("guide_id")
        message = request.get("message")
        conversation_history = request.get("conversation_history", [])
        context = request.get("context", {})
        language = request.get("language")
        
        if not guide_id or not message:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="guide_id and message are required"
            )
        
        # Get study guide
        study_guide_service = StudyGuideService(db)
        guide = await study_guide_service.get_study_guide(guide_id)
        
        if not guide:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Study guide not found"
            )
        
        # Check access
        user_role = current_user.get("role")
        user_child_id = current_user.get("child_id")
        
        if user_role == "child" and str(user_child_id) != str(guide['child_id']):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Access denied: You can only chat about your own study guides"
            )
        
        # Load child context for cultural/context flexibility
        child_id_for_ctx = str(guide.get("child_id")) if guide.get("child_id") else None
        from core.child_context import get_child_context
        child_ctx = await get_child_context(child_id=child_id_for_ctx, language_override=language)
        cultural_block = child_ctx.get("prompt_block") or ""
        
        # Build system prompt for Socratic AI Coach
        system_prompt = _build_coach_system_prompt(guide, context, language=language, cultural_block=cultural_block)
        
        # Prepare messages
        messages = []
        for msg in conversation_history:
            messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
        
        messages.append({
            "role": "user",
            "content": message
        })
        
        # Call LLM
        llm_service = LLMService(
            model_name="llama3.1",
            enable_logging=True,
            context_source="ai_coach"
        )
        
        response = await llm_service.chat(
            messages=messages,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=1000,
            test_id=None,
            metadata={
                "guide_id": guide_id,
                "context": context
            }
        )
        
        content = response.get("text", "") or response.get("content", "")
        
        # Parse response for deep linking actions
        actions = _parse_coach_response(content)
        
        return {
            "success": True,
            "response": content,
            "actions": actions
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in AI Coach chat: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to chat with coach: {str(e)}"
        )


def _build_coach_system_prompt(
    guide: dict,
    context: dict,
    language: Optional[str] = None,
    cultural_block: Optional[str] = None
) -> str:
    """Build system prompt for Socratic AI Coach."""
    output_lang = (language or "English").strip() or "English"
    prompt = f"""# Role: Socratic AI Coach (Llama 3.1)
You are a brilliant, supportive tutor. Your goal is to guide students to mastery by using the provided **Study Guide** as a topical anchor while utilizing your own vast knowledge to provide analogies, explanations, and practice.

## 0. OUTPUT LANGUAGE AND SCRIPT
Respond in **{output_lang}** only. All your messages (explanations, questions, hints, navigation suggestions) must be in {output_lang}. Keep LaTeX and math notation unchanged. If the user writes in another language, you may acknowledge briefly but continue in {output_lang}.
**CRITICAL - Use the native script, not Roman/Latin transliteration:** For Hindi, write in **Devanagari script** (e.g. आपको, समस्या, मदद), NOT in Roman script (e.g. "Aapko", "samasya", "madad"). For Spanish or English, use standard Latin script. Never respond in Hindi using Romanized/English letters—always use Devanagari (हिंदी) when the language is Hindi.
{f'''

## 0b. CULTURAL / CONTEXT PREFERENCES
{cultural_block}
''' if cultural_block else ''}

## 1. THE KNOWLEDGE HIERARCHY
- **Scope Anchor**: Use the provided `[STUDY_GUIDE]` to identify which topics are "in-bounds." Do not teach advanced concepts (e.g., Relativity) if the guide only covers Classical Mechanics.
- **Explaining**: You are encouraged to use your own knowledge to explain concepts in simpler terms, use creative analogies, or provide real-world examples not found in the guide.
- **Practice Generation**: You may generate original practice questions on the fly to test a user's understanding of a specific section.

## 2. SOCRATIC PROTOCOL (The "Guide, Don't Tell" Rule)
- **Identify Confusion**: Ask the user what specifically they are finding difficult.
- **Avoid Direct Answers**: If a user asks "What is the formula for X?", respond with: "You'll find that in the [Fundamental Principles] section. It relates Force and Mass—do you remember how those two interact?"
- **Scaffolded Learning**: If a user is stuck on a calculation, provide the first step only, then ask them for the second.

## 3. UI NAVIGATION CONTROL
You act as the navigator for the Learning Drawer. Use these tags to trigger UI changes:
- `[NAV:GUIDE:#section_id]`: Automatically scroll the Study Guide to a specific section.
- `[NAV:CARDS]`: Switch the drawer view to the Revision Cards tab.
- **Markdown Links**: Use [View Guide](guide) or [Try Cards](cards) for manual navigation.

## 4. TECHNICAL & FORMATTING
- **LaTeX**: Always use double-backslashes for math: `\\vec{{F}} = ma`.
- **Brevity**: Keep responses under 3-4 sentences. The conversation should be a back-and-forth, not a lecture.

## 5. STUDY GUIDE CONTEXT
"""
    
    # Send as much of the full study guide as fits (so the coach can reference any section)
    AI_COACH_GUIDE_MAX_CHARS = 18000  # Full 8-section guide typically ~15–20k chars; leave room for system + chat
    if guide.get("content"):
        full_content = guide["content"]
        if len(full_content) <= AI_COACH_GUIDE_MAX_CHARS:
            prompt += f"\n[STUDY_GUIDE] (complete):\n{full_content}\n"
        else:
            prompt += f"\n[STUDY_GUIDE] (first {AI_COACH_GUIDE_MAX_CHARS} chars of {len(full_content)} total):\n{full_content[:AI_COACH_GUIDE_MAX_CHARS]}\n"
    
    # Add context about errors
    if context.get("relatedError"):
        error_info = context["relatedError"]
        prompt += f"""
## STUDENT ERROR CONTEXT
- Topic: {context.get('activeTopic', 'Unknown')}
- Error Type: {error_info.get('errorType', 'Unknown')}
- Misconceptions: {', '.join(error_info.get('misconceptions', []))}
"""
    
    prompt += """
Remember: Guide, don't tell. Ask questions that lead to understanding.
"""
    
    return prompt


def _parse_coach_response(content: str) -> dict:
    """Parse coach response for navigation actions."""
    actions = {}
    
    # Check for navigation suggestions
    if "[Revision Card]" in content or "[revision card]" in content.lower() or "(cards)" in content.lower():
        actions["navigateToTab"] = "CARDS"
    elif "[Guide]" in content or "(guide)" in content.lower():
        actions["navigateToTab"] = "GUIDE"
    
    return actions
