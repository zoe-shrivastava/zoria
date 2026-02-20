"""Background task management for async document processing."""

import asyncio
import logging
from typing import Callable, Any, Optional
from functools import wraps
from datetime import datetime

from core.config import settings

logger = logging.getLogger(__name__)

# Global task registry
_background_tasks: set = set()


def run_in_background(coro: Callable) -> Callable:
    """Decorator to run a coroutine in the background.
    
    Usage:
        @run_in_background
        async def my_task():
            ...
    """
    @wraps(coro)
    def wrapper(*args, **kwargs):
        task = asyncio.create_task(coro(*args, **kwargs))
        _background_tasks.add(task)
        
        def remove_task(t):
            _background_tasks.discard(t)
        
        task.add_done_callback(remove_task)
        
        # Log task completion/failure
        def log_completion(t):
            try:
                if t.cancelled():
                    logger.warning(f"Background task {coro.__name__} was cancelled")
                elif t.exception():
                    logger.error(
                        f"Background task {coro.__name__} raised exception: {t.exception()}",
                        exc_info=t.exception()
                    )
                else:
                    logger.info(f"Background task {coro.__name__} completed successfully")
            except Exception as e:
                logger.error(f"Error in task completion callback: {e}")
        
        task.add_done_callback(log_completion)
        logger.info(f"Started background task: {coro.__name__}")
        
        return task
    
    return wrapper


async def enqueue_document_processing(document_id: str, cleanup_first: bool = False) -> None:
    """Enqueue document for background processing.
    
    Args:
        document_id: Document UUID
        cleanup_first: If True, cleanup existing data before processing
    """
    async def process_task():
        try:
            from workers.document_processor import DocumentProcessor
            processor = DocumentProcessor()
            await processor.process_document(document_id, cleanup_first=cleanup_first)
        except Exception as e:
            logger.error(f"Background processing failed for document {document_id}: {e}", exc_info=True)
            raise
    
    # Create and start background task
    task = asyncio.create_task(process_task())
    _background_tasks.add(task)
    
    def remove_task(t):
        _background_tasks.discard(t)
    
    task.add_done_callback(remove_task)
    
    # Log task completion/failure
    def log_completion(t):
        try:
            if t.cancelled():
                logger.warning(f"Background processing task for document {document_id} was cancelled")
            elif t.exception():
                logger.error(
                    f"Background processing task for document {document_id} raised exception: {t.exception()}",
                    exc_info=t.exception()
                )
            else:
                logger.info(f"Background processing task for document {document_id} completed successfully")
        except Exception as e:
            logger.error(f"Error in task completion callback: {e}")
    
    task.add_done_callback(log_completion)
    logger.info(f"Enqueued background processing for document {document_id}")


async def enqueue_document_phase1(document_id: str) -> None:
    """Enqueue document for Phase 1 processing (workflow + subject extraction).
    
    Phase 1 includes:
    - OpenAI Agents workflow (document parsing + concept extraction)
    - Subject extraction via local LLM
    - Storing markdown, concepts, and subject
    
    After Phase 1 completes, Phase 2 will be automatically enqueued.
    
    Args:
        document_id: Document UUID
    """
    async def process_phase1():
        try:
            from services.document_service import DocumentService
            from workflows.workflow import run_workflow, WorkflowInput
            from database.repositories.document_repository import DocumentRepository
            from core.database import get_db
            
            db = get_db()
            document_repo = DocumentRepository(db)
            
            # Get document to find file path
            document = await document_repo.db.fetchrow(
                "SELECT file_path FROM documents WHERE id = $1",
                document_id
            )
            
            if not document:
                logger.error(f"Document {document_id} not found for Phase 1 processing")
                await document_repo.update_status(document_id, "failed", error_message="Document not found")
                return
            
            file_path = document.get("file_path")
            if not file_path:
                logger.error(f"Document {document_id} has no file path")
                await document_repo.update_status(document_id, "failed", error_message="File path not found")
                return
            
            # Update status to 'processing'
            await document_repo.update_status(document_id, "processing", processing_started_at=datetime.utcnow())
            
            # Process with OpenAI Agents workflow (Phase 1)
            logger.info(f"Phase 1: Processing document {document_id} with OpenAI Agents...")
            workflow_input = WorkflowInput(pdf_path=file_path)
            result = await run_workflow(workflow_input)
            
            # Extract subject from workflow result
            extracted_subject = result.get("subject")
            
            # Update document with processed content and subject
            await document_repo.update_document_processing(
                document_id=document_id,
                markdown_content=result.get("markdown"),
                concepts=result.get("concepts"),
                subject=extracted_subject
            )
            
            if extracted_subject:
                logger.info(f"Document {document_id} classified as subject: {extracted_subject}")
            
            await document_repo.update_status(document_id, "parsed")
            logger.info(f"Phase 1 complete: Document {document_id} parsed successfully")
            
            # Phase 2: Trigger background processing
            logger.info(f"Phase 2: Enqueuing background processing for document {document_id}...")
            await enqueue_document_processing(document_id)
            
        except Exception as e:
            logger.error(f"Phase 1 processing failed for document {document_id}: {e}", exc_info=True)
            # Update document status to failed
            try:
                from database.repositories.document_repository import DocumentRepository
                from core.database import get_db
                
                db = get_db()
                document_repo = DocumentRepository(db)
                await document_repo.update_status(
                    document_id,
                    "failed",
                    failure_stage="phase1_workflow",
                    error_message=str(e)
                )
            except Exception as update_error:
                logger.error(f"Failed to update document status: {update_error}")
            raise
    
    # Create and start background task
    task = asyncio.create_task(process_phase1())
    _background_tasks.add(task)
    
    def remove_task(t):
        _background_tasks.discard(t)
    
    task.add_done_callback(remove_task)
    
    # Log task completion/failure
    def log_completion(t):
        try:
            if t.cancelled():
                logger.warning(f"Phase 1 task for document {document_id} was cancelled")
            elif t.exception():
                logger.error(
                    f"Phase 1 task for document {document_id} raised exception: {t.exception()}",
                    exc_info=t.exception()
                )
            else:
                logger.info(f"Phase 1 task for document {document_id} completed successfully")
        except Exception as e:
            logger.error(f"Error in Phase 1 task completion callback: {e}")
    
    task.add_done_callback(log_completion)
    logger.info(f"Enqueued Phase 1 processing for document {document_id}")


async def enqueue_test_generation_from_concept(
    test_id: str,
    child_id: str,
    concept_id: str,
    parent_id: Optional[str],
    include_prerequisites: bool,
    difficulty: Optional[str],
    num_questions: int,
    time_limit_minutes: Optional[int],
    language: Optional[str] = None,
) -> None:
    """Enqueue background test generation for a single concept."""
    async def process_test():
        try:
            from core.database import get_db
            from services.test_generation_service import TestGenerationService
            from services.question_generation_service import QuestionGenerationService
            from services.embedding_service import EmbeddingService
            from services.llm_service import LLMService
            
            db = get_db()
            embedding_service = EmbeddingService()
            llm_service = LLMService(
                model_name=settings.QUESTION_GENERATION_MODEL,
                enable_logging=True,
                context_source="question_generation"
            )
            question_gen_service = QuestionGenerationService(db, embedding_service, llm_service)
            test_service = TestGenerationService(db, question_gen_service)
            
            # Generate questions into the existing pending test
            await test_service.generate_questions_for_existing_test_from_concept(
                test_id=test_id,
                child_id=child_id,
                concept_id=concept_id,
                parent_id=parent_id,
                include_prerequisites=include_prerequisites,
                difficulty=difficulty,
                num_questions=num_questions,
                time_limit_minutes=time_limit_minutes,
                language=language,
            )
        except Exception as e:
            logger.error(f"Background test generation failed for test {test_id}: {e}", exc_info=True)
            try:
                from core.database import get_db
                from database.repositories.test_repository import TestRepository
                db = get_db()
                repo = TestRepository(db)
                await repo.update_test_status(test_id, "failed")
            except Exception as update_error:
                logger.error(f"Failed to update status for test {test_id}: {update_error}")
            raise
    
    task = asyncio.create_task(process_test())
    _background_tasks.add(task)
    
    def remove_task(t):
        _background_tasks.discard(t)
    
    task.add_done_callback(remove_task)
    
    def log_completion(t):
        try:
            if t.cancelled():
                logger.warning(f"Background test generation task for test {test_id} was cancelled")
            elif t.exception():
                logger.error(
                    f"Background test generation task for test {test_id} raised exception: {t.exception()}",
                    exc_info=t.exception()
                )
            else:
                logger.info(f"Background test generation task for test {test_id} completed successfully")
        except Exception as e:
            logger.error(f"Error in test generation task completion callback: {e}")
    
    task.add_done_callback(log_completion)
    logger.info(f"Enqueued background generation for test {test_id} (concept {concept_id})")


async def enqueue_test_generation_from_topics(
    test_id: str,
    child_id: str,
    subject: str,
    topics: list,
    parent_id: Optional[str],
    include_prerequisites: bool,
    difficulty: Optional[str],
    num_questions: int,
    time_limit_minutes: Optional[int],
    language: Optional[str] = None,
) -> None:
    """Enqueue background test generation for subject/topics."""
    async def process_test():
        try:
            from core.database import get_db
            from services.test_generation_service import TestGenerationService
            from services.question_generation_service import QuestionGenerationService
            from services.embedding_service import EmbeddingService
            from services.llm_service import LLMService
            
            db = get_db()
            embedding_service = EmbeddingService()
            llm_service = LLMService(
                model_name=settings.QUESTION_GENERATION_MODEL,
                enable_logging=True,
                context_source="question_generation"
            )
            question_gen_service = QuestionGenerationService(db, embedding_service, llm_service)
            test_service = TestGenerationService(db, question_gen_service)
            
            await test_service.generate_questions_for_existing_test_from_topics(
                test_id=test_id,
                child_id=child_id,
                subject=subject,
                topics=topics,
                parent_id=parent_id,
                include_prerequisites=include_prerequisites,
                difficulty=difficulty,
                num_questions=num_questions,
                time_limit_minutes=time_limit_minutes,
                language=language,
            )
        except Exception as e:
            logger.error(f"Background topic-based test generation failed for test {test_id}: {e}", exc_info=True)
            try:
                from core.database import get_db
                from database.repositories.test_repository import TestRepository
                db = get_db()
                repo = TestRepository(db)
                await repo.update_test_status(test_id, "failed")
            except Exception as update_error:
                logger.error(f"Failed to update status for test {test_id}: {update_error}")
            raise
    
    task = asyncio.create_task(process_test())
    _background_tasks.add(task)
    
    def remove_task(t):
        _background_tasks.discard(t)
    
    task.add_done_callback(remove_task)
    
    def log_completion(t):
        try:
            if t.cancelled():
                logger.warning(f"Background topic-based test generation task for test {test_id} was cancelled")
            elif t.exception():
                logger.error(
                    f"Background topic-based test generation task for test {test_id} raised exception: {t.exception()}",
                    exc_info=t.exception()
                )
            else:
                logger.info(f"Background topic-based test generation task for test {test_id} completed successfully")
        except Exception as e:
            logger.error(f"Error in topic-based test generation task completion callback: {e}")
    
    task.add_done_callback(log_completion)
    logger.info(f"Enqueued background generation for test {test_id} (subject {subject}, topics {topics})")


async def enqueue_study_guide_regeneration(
    guide_id: str,
    child_id: str,
    concept_name: str,
    focus_area: str,
    grade_level: Optional[str],
    subject: str,
    common_errors: Optional[list],
    misconceptions: list,
    sample_questions: list,
    language: Optional[str] = None,
    topic_from_test: Optional[str] = None,
    topics_from_test: Optional[list] = None,
) -> None:
    """Enqueue study guide regeneration so the HTTP request returns immediately.
    Long-running pipeline (outline + 8 sections + revision cards) runs in background.
    Client should poll GET /study-guides/{guide_id} until metadata.regeneration_status is not 'in_progress'.
    """
    async def process_regeneration():
        from core.database import get_db
        from services.study_guide_service import StudyGuideService

        db = get_db()
        try:
            await db.execute(
                """
                UPDATE study_guides
                SET metadata = jsonb_set(COALESCE(metadata, '{}'), '{regeneration_status}', to_jsonb('in_progress'::text))
                WHERE id = $1
                """,
                guide_id,
            )
            logger.info(f"Study guide regeneration started for {guide_id}")

            study_guide_service = StudyGuideService(db)
            try:
                await study_guide_service.generate_study_guide(
                    child_id=child_id,
                    concept_name=concept_name,
                    focus_area=focus_area,
                    grade_level=grade_level,
                    subject=subject,
                    common_errors=common_errors,
                    misconceptions=misconceptions or [],
                    sample_questions=sample_questions or [],
                    force_regenerate=True,
                    language=language,
                    topic_from_test=topic_from_test,
                    topics_from_test=topics_from_test,
                )
                logger.info(f"Study guide regeneration completed for {guide_id}")
            except Exception as in_progress_exc:
                from services.study_guide_service import StudyGuideGenerationInProgressError
                if isinstance(in_progress_exc, StudyGuideGenerationInProgressError):
                    logger.info(
                        "Study guide regeneration skipped for %s: generation already in progress for this focus area",
                        guide_id,
                    )
                    try:
                        await db.execute(
                            """
                            UPDATE study_guides
                            SET metadata = metadata #- '{regeneration_status}'
                            WHERE id = $1
                            """,
                            guide_id,
                        )
                    except Exception as clear_err:
                        logger.warning("Failed to clear regeneration_status for %s: %s", guide_id, clear_err)
                    return
                raise
        except Exception as e:
            logger.error(f"Background study guide regeneration failed for {guide_id}: {e}", exc_info=True)
            try:
                await db.execute(
                    """
                    UPDATE study_guides
                    SET metadata = metadata #- '{regeneration_status}'
                    WHERE id = $1
                    """,
                    guide_id,
                )
            except Exception as clear_err:
                logger.error(f"Failed to clear regeneration_status for {guide_id}: {clear_err}")
            raise

    task = asyncio.create_task(process_regeneration())
    _background_tasks.add(task)

    def remove_task(t):
        _background_tasks.discard(t)

    task.add_done_callback(remove_task)

    def log_completion(t):
        try:
            if t.cancelled():
                logger.warning(f"Study guide regeneration task for {guide_id} was cancelled")
            elif t.exception():
                logger.error(
                    f"Study guide regeneration task for {guide_id} raised: {t.exception()}",
                    exc_info=t.exception(),
                )
            else:
                logger.info(f"Study guide regeneration task for {guide_id} completed successfully")
        except Exception as e:
            logger.error(f"Error in study guide regeneration completion callback: {e}")

    task.add_done_callback(log_completion)
    logger.info(f"Enqueued study guide regeneration for {guide_id}")


def get_background_tasks() -> set:
    """Get set of active background tasks.
    
    Returns:
        Set of active tasks
    """
    return _background_tasks.copy()
