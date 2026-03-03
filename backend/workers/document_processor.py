"""Background worker for document processing pipeline."""

import logging
import asyncio
import json
from datetime import datetime
from typing import Dict, Any, Optional

from core.database import init_db, get_db
from database.repositories.document_repository import DocumentRepository
from database.repositories.concept_repository import ConceptRepository
from database.repositories.question_repository import QuestionRepository
from database.repositories.chunk_repository import ChunkRepository
from services.chunking_service import ChunkingService
from services.embedding_service import EmbeddingService
from services.knowledge_graph_service import KnowledgeGraphService

logger = logging.getLogger(__name__)


def normalize_question_type(question_type: Any) -> str:
    """Normalize question type to a valid value.
    
    Handles cases where LLM returns invalid or multiple values.
    Maps common variations to valid types. Defaults to "short_answer" if ambiguous.
    
    Valid types: multiple_choice, short_answer, problem_solving, 
                 conceptual_question, matching, fill_in_the_blank
    
    Args:
        question_type: Question type value (can be string or other)
        
    Returns:
        Normalized question type
    """
    if question_type is None:
        return "short_answer"
    
    # Convert to string and clean
    type_str = str(question_type).strip().lower()
    
    # Handle pipe-separated values like "multiple_choice | short_answer"
    if "|" in type_str:
        # Split and take the first valid value
        parts = [p.strip() for p in type_str.split("|")]
        for part in parts:
            normalized = _map_question_type(part)
            if normalized:
                return normalized
        # If none found, default to short_answer
        return "short_answer"
    
    # Map to valid type
    normalized = _map_question_type(type_str)
    if normalized:
        return normalized
    
    # Default to short_answer for any invalid value
    logger.warning(f"Invalid question type '{question_type}', defaulting to 'short_answer'")
    return "short_answer"


def _map_question_type(type_str: str) -> Optional[str]:
    """Map question type string to valid database value.
    
    Args:
        type_str: Question type string (lowercase, cleaned)
        
    Returns:
        Valid question type or None
    """
    # Direct matches
    valid_types = {
        "multiple_choice", "short_answer", "problem_solving",
        "conceptual_question", "matching", "fill_in_the_blank"
    }
    if type_str in valid_types:
        return type_str
    
    # Common variations and aliases
    type_mapping = {
        "mcq": "multiple_choice",
        "multiple choice": "multiple_choice",
        "choice": "multiple_choice",
        "sa": "short_answer",
        "short answer": "short_answer",
        "text": "short_answer",
        "problem": "problem_solving",
        "problem solving": "problem_solving",
        "ps": "problem_solving",
        "conceptual": "conceptual_question",
        "concept": "conceptual_question",
        "match": "matching",
        "fill": "fill_in_the_blank",
        "fill in": "fill_in_the_blank",
        "blank": "fill_in_the_blank"
    }
    
    return type_mapping.get(type_str)


class DocumentProcessor:
    """Background worker for document processing pipeline."""
    
    def __init__(self):
        """Initialize document processor."""
        self.db = init_db()
        self.document_repo = DocumentRepository(self.db)
        self.concept_repo = ConceptRepository(self.db)
        self.question_repo = QuestionRepository(self.db)
        self.chunk_repo = ChunkRepository(self.db)
        self.chunking_service = ChunkingService()
        self.embedding_service = EmbeddingService()
        self.kg_service = KnowledgeGraphService(self.db, self.embedding_service)
    
    async def cleanup_document_data(self, document_id: str) -> None:
        """Clean up existing processing data for a document before reprocessing.
        
        This cleans up all Phase 2/3 data:
        - content_chunks (with embeddings/indexes)
        - questions and question_skills links
        - visuals
        - concept_relationships (for concepts from this document)
        - document_concepts links
        - concepts (only if not used by other documents)
        
        Note: Skills are shared across documents and are NOT deleted.
        
        Args:
            document_id: Document UUID
        """
        logger.info(f"Cleaning up existing Phase 2/3 data for document {document_id}")
        
        async with self.db.pool.acquire() as conn:
            async with conn.transaction():
                # Step 1: Delete content_chunks (includes embeddings/indexes)
                # This is the main data from Phase 2/3
                chunks_result = await conn.execute(
                    "DELETE FROM content_chunks WHERE document_id = $1",
                    document_id
                )
                chunks_deleted = int(chunks_result.split()[-1]) if chunks_result else 0
                logger.info(f"Deleted {chunks_deleted} content chunks")
                
                # Step 2: Get concept IDs for this document before deletion
                concept_ids = await conn.fetch(
                    "SELECT id FROM concepts WHERE document_id = $1",
                    document_id
                )
                concept_id_list = [str(row["id"]) for row in concept_ids] if concept_ids else []
                
                if concept_id_list:
                    # Step 3: Delete question-skill links for questions from this document
                    question_skills_result = await conn.execute(
                        """
                        DELETE FROM question_skills 
                        WHERE question_id IN (
                            SELECT q.id FROM questions q
                            JOIN concepts c ON q.concept_id = c.id
                            WHERE c.document_id = $1
                        )
                        """,
                        document_id
                    )
                    question_skills_deleted = int(question_skills_result.split()[-1]) if question_skills_result else 0
                    logger.info(f"Deleted {question_skills_deleted} question-skill links")
                    
                    # Step 4: Delete questions (via concepts linked to this document)
                    questions_result = await conn.execute(
                        """
                        DELETE FROM questions 
                        WHERE concept_id IN (
                            SELECT id FROM concepts WHERE document_id = $1
                        )
                        """,
                        document_id
                    )
                    questions_deleted = int(questions_result.split()[-1]) if questions_result else 0
                    logger.info(f"Deleted {questions_deleted} questions")
                    
                    # Step 5: Delete visuals (via concepts linked to this document)
                    visuals_result = await conn.execute(
                        """
                        DELETE FROM visuals 
                        WHERE concept_id IN (
                            SELECT id FROM concepts WHERE document_id = $1
                        )
                        """,
                        document_id
                    )
                    visuals_deleted = int(visuals_result.split()[-1]) if visuals_result else 0
                    logger.info(f"Deleted {visuals_deleted} visuals")
                    
                    # Step 6: Delete concept_relationships where concepts are from this document
                    # Delete relationships where either from_concept or to_concept is from this document
                    relationships_result = await conn.execute(
                        """
                        DELETE FROM concept_relationships 
                        WHERE from_concept_id = ANY($1::uuid[]) 
                           OR to_concept_id = ANY($1::uuid[])
                        """,
                        concept_id_list
                    )
                    relationships_deleted = int(relationships_result.split()[-1]) if relationships_result else 0
                    logger.info(f"Deleted {relationships_deleted} concept relationships")
                else:
                    question_skills_deleted = 0
                    questions_deleted = 0
                    visuals_deleted = 0
                    relationships_deleted = 0
                    logger.info("No concepts found for this document, skipping related cleanup")
                
                # Step 7: Delete concept-document links (but keep concepts if used by other documents)
                doc_concepts_result = await conn.execute(
                    "DELETE FROM document_concepts WHERE document_id = $1",
                    document_id
                )
                doc_concepts_deleted = int(doc_concepts_result.split()[-1]) if doc_concepts_result else 0
                logger.info(f"Deleted {doc_concepts_deleted} document-concept links")
                
                # Step 8: Delete concepts that are ONLY linked to this document
                # (Keep concepts that are linked to other documents)
                concepts_result = await conn.execute(
                    """
                    DELETE FROM concepts 
                    WHERE document_id = $1
                    AND id NOT IN (
                        SELECT DISTINCT concept_id FROM document_concepts 
                        WHERE concept_id IN (
                            SELECT id FROM concepts WHERE document_id = $1
                        )
                        AND document_id != $1
                    )
                    """,
                    document_id
                )
                concepts_deleted = int(concepts_result.split()[-1]) if concepts_result else 0
                logger.info(f"Deleted {concepts_deleted} concepts (kept shared concepts)")
                
                logger.info(
                    f"Cleanup complete for document {document_id}: "
                    f"{chunks_deleted} chunks, {questions_deleted} questions, "
                    f"{visuals_deleted} visuals, {relationships_deleted} relationships, "
                    f"{concepts_deleted} concepts"
                )
    
    async def process_document(
        self, 
        document_id: str, 
        cleanup_first: bool = False
    ) -> Dict[str, Any]:
        """Process document in background (Phase 2).
        
        This method:
        1. Processes concepts and builds knowledge graph
        2. Creates questions and visuals
        3. Generates chunks
        4. Generates embeddings
        5. Stores chunks with embeddings
        6. Updates document status to 'ready'
        
        Args:
            document_id: Document UUID
            cleanup_first: If True, delete existing processing data first
            
        Returns:
            Processing result dictionary
        """
        await self.db.connect()
        
        try:
            # Ensure status is set to "processing" at the start of background task
            # This prevents the document from showing as "ready" while processing
            current_doc = await self.document_repo.get_document_by_id(document_id)
            if current_doc and current_doc.get("status") != "processing":
                logger.info(f"Setting document {document_id} status to 'processing' at start of background task")
                await self.document_repo.update_status(document_id, "processing")
            
            # Cleanup existing data if requested
            if cleanup_first:
                await self.cleanup_document_data(document_id)
            # Get document
            document = await self.document_repo.get_document_by_id(document_id)
            if not document:
                raise ValueError(f"Document {document_id} not found")
            
            markdown = document.get("markdown_content")
            concepts_json = document.get("concepts")
            document_subject = document.get("subject")  # Get subject from document
            
            if not markdown or not concepts_json:
                raise ValueError("Document missing markdown or concepts")
            
            # Parse concepts JSON if it's a string
            if isinstance(concepts_json, str):
                concepts_json = json.loads(concepts_json)
            
            concepts_list = concepts_json.get("concepts", [])
            
            if not concepts_list:
                await self.document_repo.update_status(
                    document_id,
                    "failed",
                    processing_completed_at=datetime.utcnow(),
                    failure_stage="concept_extraction",
                    error_message="Document has no concepts to process"
                )
                raise ValueError("Document has no concepts to process. Ensure the document contains extractable concepts.")
            
            def _normalize_concept(concept: Dict[str, Any]) -> Dict[str, Any]:
                """Normalize workflow concept schema to the internal expected shape."""
                if not isinstance(concept, dict):
                    return {}
                normalized = dict(concept)
                if not normalized.get("name"):
                    # New workflow schema provides topic_name + subtopic (no explicit concept name).
                    # Treat the subtopic as the concept name and store topic_name in legacy "subtopic".
                    if normalized.get("subtopic") and normalized.get("topic_name"):
                        normalized["name"] = normalized.get("subtopic") or ""
                        normalized["subtopic"] = normalized.get("topic_name")
                    else:
                        normalized["name"] = (
                            normalized.get("subtopic")
                            or normalized.get("topic_name")
                            or normalized.get("concept_name")
                            or normalized.get("title")
                            or ""
                        )
                if not normalized.get("subtopic") and normalized.get("topic_name"):
                    normalized["subtopic"] = normalized.get("topic_name")
                if normalized.get("subtopic") is None and normalized.get("sub_topic") is not None:
                    normalized["subtopic"] = normalized.get("sub_topic")
                for key in ("grade", "prerequisites", "keywords", "questions", "associated_visuals"):
                    if normalized.get(key) is None:
                        normalized[key] = []
                return normalized

            normalized_concepts_list = [_normalize_concept(c) for c in concepts_list]
            normalized_concepts_list = [c for c in normalized_concepts_list if c.get("name")]

            logger.info(f"Processing document {document_id} with {len(normalized_concepts_list)} concepts")
            
            # Start transaction-like processing
            # Note: We'll use explicit transaction management
            async with self.db.pool.acquire() as conn:
                async with conn.transaction():
                    # Step 1: Process concepts and build knowledge graph
                    logger.info("Step 1: Processing concepts and building knowledge graph...")
                    concept_ids = await self.kg_service.process_concepts(
                        document_id,
                        normalized_concepts_list,
                        subject=document_subject  # Pass subject to knowledge graph service
                    )
                    
                    # Step 2: Create questions and visuals
                    logger.info("Step 2: Creating questions and visuals...")
                    question_ids = []
                    visual_ids = []
                    
                    for i, concept_data in enumerate(normalized_concepts_list):
                        concept_id = concept_ids[i]
                        
                        # Create questions
                        for question_data in concept_data.get("questions", []):
                            # Normalize question type and difficulty
                            raw_question_type = question_data.get("type")
                            normalized_question_type = normalize_question_type(raw_question_type)
                            
                            raw_difficulty = concept_data.get("difficulty", "medium")
                            from services.knowledge_graph_service import KnowledgeGraphService
                            normalized_difficulty = KnowledgeGraphService._normalize_difficulty(raw_difficulty)
                            
                            # Include subject and document_id in question metadata
                            # source: "concept_extraction" marks this question as from ingestion (Concept JSON)
                            question_metadata = {
                                "associated_visuals": question_data.get("associated_visuals", []),
                                "visual_metadata": question_data.get("visual_metadata"),
                                "answer": question_data.get("answer"),  # Store extracted answer
                                "subject": document_subject,  # Store subject with question
                                "document_id": document_id,  # Store document_id to track question origin
                                "source": "concept_extraction",  # Raw KG: question from document ingestion
                            }
                            question_id = await self.question_repo.create_question(
                                concept_id=concept_id,
                                text=question_data.get("text", ""),
                                question_type=normalized_question_type,
                                difficulty=normalized_difficulty,
                                metadata=question_metadata
                            )
                            question_ids.append(question_id)
                            
                            # Link question to skill (if applicable)
                            skill_id = await self.kg_service.create_skill_from_question(
                                question_data.get("text", ""),
                                question_data.get("type", "")
                            )
                            if skill_id:
                                await self.question_repo.link_question_to_skill(
                                    question_id, skill_id
                                )
                        
                        # Create visuals
                        for visual_data in concept_data.get("associated_visuals", []):
                            # Handle different visual data formats
                            if isinstance(visual_data, str):
                                # If it's just a string (visual ID or key), create minimal visual
                                logger.warning(f"Visual data is a string, not dict: {visual_data}")
                                visual_id = await conn.fetchval(
                                    """
                                    INSERT INTO visuals 
                                    (concept_id, visual_key, visual_type, description)
                                    VALUES ($1, $2, $3, $4)
                                    RETURNING id
                                    """,
                                    concept_id,
                                    visual_data,
                                    "unknown",
                                    f"Visual reference: {visual_data}"
                                )
                                visual_ids.append(visual_id)
                            elif isinstance(visual_data, dict):
                                # Normal dictionary format
                                visual_id = await conn.fetchval(
                                    """
                                    INSERT INTO visuals 
                                    (concept_id, visual_key, visual_type, description, json_representation, metadata)
                                    VALUES ($1, $2, $3, $4, $5, $6)
                                    RETURNING id
                                    """,
                                    concept_id,
                                    visual_data.get("visual_key"),
                                    visual_data.get("visual_type"),
                                    visual_data.get("description"),
                                    json.dumps(visual_data.get("json_representation")) if visual_data.get("json_representation") else None,
                                    json.dumps(visual_data.get("metadata")) if visual_data.get("metadata") else None
                                )
                                visual_ids.append(visual_id)
                            else:
                                logger.warning(f"Unexpected visual data type: {type(visual_data)}, skipping")
                                continue
                    
                    logger.info(f"Created {len(question_ids)} questions and {len(visual_ids)} visuals")
                    
                    # Step 3: Generate chunks
                    logger.info("Step 3: Generating chunks...")
                    # Use normalized concepts for chunking so metadata contains stable concept_name
                    concepts_json_for_chunking = dict(concepts_json)
                    concepts_json_for_chunking["concepts"] = normalized_concepts_list
                    chunks = self.chunking_service.chunk_document(
                        document_id,
                        markdown,
                        concepts_json_for_chunking,
                        subject=document_subject  # Pass subject to chunking service
                    )
                    
                    # Update chunks with concept_ids and question_ids
                    concept_idx = 0
                    question_idx = 0
                    
                    for chunk in chunks:
                        # Find matching concept
                        chunk_concept_name = chunk.get("metadata", {}).get("concept_name")
                        if chunk_concept_name:
                            for i, concept_data in enumerate(normalized_concepts_list):
                                if concept_data.get("name") == chunk_concept_name:
                                    chunk["concept_id"] = concept_ids[i]
                                    break
                        
                        # Find matching question
                        chunk_question_id = chunk.get("metadata", {}).get("question_id")
                        if chunk_question_id and question_idx < len(question_ids):
                            # Simple mapping - can be improved
                            chunk["question_id"] = question_ids[question_idx]
                            question_idx += 1
                    
                    logger.info(f"Generated {len(chunks)} chunks")
                    
                    # Step 4: Generate embeddings
                    logger.info("Step 4: Generating embeddings...")
                    embedded_chunks = await self.embedding_service.embed_chunks(
                        chunks,
                        batch_size=10
                    )
                    
                    # Step 5: Store chunks with embeddings
                    logger.info("Step 5: Storing chunks with embeddings...")
                    chunk_ids = await self.chunk_repo.create_chunks_batch(embedded_chunks)
                    
                    logger.info(f"Stored {len(chunk_ids)} chunks with embeddings")
            
            # Step 6: Update document status
            await self.document_repo.update_status(
                document_id,
                "ready",
                processing_completed_at=datetime.utcnow()
            )
            
            logger.info(f"Document {document_id} processing completed successfully")
            
            return {
                "status": "ready",
                "document_id": document_id,
                "concepts_processed": len(concept_ids),
                "questions_created": len(question_ids),
                "chunks_created": len(chunk_ids)
            }
        
        except Exception as e:
            logger.error(f"Error processing document {document_id}: {e}", exc_info=True)
            
            # Mark as failed
            await self.document_repo.update_status(
                document_id,
                "failed",
                failure_stage="background_processing",
                error_message=str(e)
            )
            raise
        
        finally:
            # Don't close the global database pool - it's shared across the application
            # The pool will be closed when the application shuts down via lifespan
            # Closing it here breaks other concurrent requests
            pass


async def process_document_async(document_id: str, cleanup_first: bool = False) -> Dict[str, Any]:
    """Async wrapper for document processing (for background tasks).
    
    Args:
        document_id: Document UUID
        cleanup_first: If True, cleanup existing data first
        
    Returns:
        Processing result
    """
    processor = DocumentProcessor()
    return await processor.process_document(document_id, cleanup_first=cleanup_first)
