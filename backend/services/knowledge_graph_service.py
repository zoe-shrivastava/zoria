"""Knowledge graph service for concept deduplication and relationship management."""

import logging
from typing import List, Dict, Any, Optional
import numpy as np

from database.repositories.concept_repository import ConceptRepository
from services.embedding_service import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeGraphService:
    """Knowledge graph construction and relationship management."""
    
    def __init__(self, db, embedding_service: EmbeddingService):
        """Initialize knowledge graph service.
        
        Args:
            db: Database instance
            embedding_service: Embedding service for similarity calculation
        """
        self.db = db
        self.concept_repo = ConceptRepository(db)
        self.embedding_service = embedding_service
        self.similarity_threshold = 0.85

    @staticmethod
    def _normalize_difficulty(difficulty: Any) -> str:
        """Normalize difficulty value to a single valid value.
        
        Handles cases where LLM returns multiple values like "easy | medium | hard"
        or invalid values. Defaults to "medium" if ambiguous.
        
        Args:
            difficulty: Difficulty value (can be string, list, or other)
            
        Returns:
            Normalized difficulty: "easy", "medium", or "hard"
        """
        if difficulty is None:
            return "medium"
        
        # Convert to string and clean
        difficulty_str = str(difficulty).strip().lower()
        
        # Handle pipe-separated values like "easy | medium | hard"
        if "|" in difficulty_str:
            # Split and take the first valid value
            parts = [p.strip() for p in difficulty_str.split("|")]
            for part in parts:
                if part in ("easy", "medium", "hard"):
                    return part
            # If none found, default to medium
            return "medium"
        
        # Check for valid single value
        if difficulty_str in ("easy", "medium", "hard"):
            return difficulty_str
        
        # Default to medium for any invalid value
        logger.warning(f"Invalid difficulty value '{difficulty}', defaulting to 'medium'")
        return "medium"
    
    @staticmethod
    def _normalize_concept_dict(concept_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize concept dict coming from workflow into the expected internal shape.

        We historically expected:
          - name, subtopic, difficulty, grade, prerequisites, keywords, questions, associated_visuals

        Newer workflow schema may provide:
          - topic_name (instead of name)
          - subject_name (document-level subject is passed separately)
        """
        if not isinstance(concept_data, dict):
            return {}

        normalized = dict(concept_data)

        # Support new workflow field names:
        # - If workflow provides topic_name + subtopic (no "name"), treat the *subtopic* as the concept name
        #   and store the broader topic_name in "subtopic" (our legacy "category" field).
        if not normalized.get("name"):
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

        # If we still don't have a legacy "subtopic" category but do have topic_name, use it.
        if not normalized.get("subtopic") and normalized.get("topic_name"):
            normalized["subtopic"] = normalized.get("topic_name")

        # Keep subtopic as-is (already same key), but support alternates
        if normalized.get("subtopic") is None:
            if normalized.get("sub_topic") is not None:
                normalized["subtopic"] = normalized.get("sub_topic")

        # Ensure lists are always lists
        for key in ("grade", "prerequisites", "keywords", "questions", "associated_visuals"):
            val = normalized.get(key)
            if val is None:
                normalized[key] = []

        return normalized
    
    async def process_concepts(
        self,
        document_id: str,
        concepts: List[Dict[str, Any]],
        subject: Optional[str] = None
    ) -> List[str]:
        """Process concepts with deduplication and create relationships.
        
        Args:
            document_id: Document UUID
            concepts: List of concept dictionaries from workflow
            subject: Optional subject name (from document level)
            
        Returns:
            List of concept IDs (newly created or existing)
        """
        concept_ids = []
        
        for concept_data in concepts:
            concept_data = self._normalize_concept_dict(concept_data)
            if not concept_data.get("name"):
                logger.warning("Skipping concept with missing name/topic_name in workflow output")
                continue

            # Check for existing similar concept
            existing = await self._find_similar_concept(concept_data)
            
            # Prepare metadata with subject
            metadata = {}
            if subject:
                metadata["subject"] = subject
            
            if existing:
                concept_id = existing["id"]
                logger.info(f"Found existing concept: {concept_data.get('name')} -> {concept_id}")
                
                # Link to document
                await self.concept_repo.link_to_document(concept_id, document_id)
                
                # Update concept if new document has more information (including subject)
                concept_data_with_subject = {**concept_data}
                if subject:
                    concept_data_with_subject["subject"] = subject
                await self._update_concept_if_needed(concept_id, concept_data_with_subject)
            else:
                # Normalize difficulty - handle cases where LLM returns multiple values like "easy | medium | hard"
                raw_difficulty = concept_data.get("difficulty", "medium")
                difficulty = KnowledgeGraphService._normalize_difficulty(raw_difficulty)
                
                # Create new concept with subject in metadata
                concept_id = await self.concept_repo.create_concept(
                    document_id=document_id,
                    name=concept_data.get("name", ""),
                    subtopic=concept_data.get("subtopic"),
                    difficulty=difficulty,
                    grade=concept_data.get("grade", []),
                    prerequisites=concept_data.get("prerequisites", []),
                    keywords=concept_data.get("keywords", []),
                    source_markdown=concept_data.get("source_markdown"),
                    metadata=metadata if metadata else None
                )
                logger.info(f"Created new concept: {concept_data.get('name')} -> {concept_id}")
            
            concept_ids.append(concept_id)
            
            # Create prerequisite relationships
            await self._create_prerequisite_relationships(
                concept_id,
                concept_data.get("prerequisites", []),
                concepts
            )
        
        return concept_ids
    
    async def _find_similar_concept(
        self,
        concept_data: Dict[str, Any]
    ) -> Optional[dict]:
        """Find similar concept using embedding similarity.
        
        Args:
            concept_data: Concept data dictionary
            
        Returns:
            Similar concept or None
        """
        concept_name = (concept_data.get("name") or "").strip()
        if not concept_name:
            return None
        subtopic = concept_data.get("subtopic", "")
        
        # First try simple name matching (fast)
        existing = await self.concept_repo.find_similar_concept(
            name=concept_name,
            subtopic=subtopic
        )
        
        if existing:
            return existing
        
        # If no exact match, try semantic similarity with embeddings
        # Get all existing concepts
        all_concepts = await self.concept_repo.get_all_concepts()
        
        if not all_concepts:
            return None
        
        # Prepare query text
        query_text = f"{concept_name} {subtopic}".strip()
        query_embedding = await self.embedding_service.generate_embedding(query_text)
        
        # Compare with existing concepts
        for existing_concept in all_concepts:
            existing_name = existing_concept.get("name", "")
            existing_subtopic = existing_concept.get("subtopic", "")
            existing_text = f"{existing_name} {existing_subtopic}".strip()
            
            existing_embedding = await self.embedding_service.generate_embedding(existing_text)
            
            # Calculate cosine similarity using numpy
            similarity = np.dot(query_embedding, existing_embedding) / (
                np.linalg.norm(query_embedding) * np.linalg.norm(existing_embedding)
            )
            
            if similarity >= self.similarity_threshold:
                logger.info(
                    f"Found semantically similar concept: "
                    f"{concept_name} ~ {existing_name} (similarity: {similarity:.3f})"
                )
                return existing_concept
        
        return None
    
    async def _update_concept_if_needed(
        self,
        concept_id: str,
        new_concept_data: Dict[str, Any]
    ) -> None:
        """Update concept if new data provides more information.
        
        Args:
            concept_id: Concept UUID
            new_concept_data: New concept data
        """
        existing = await self.concept_repo.get_concept_by_id(concept_id)
        if not existing:
            return
        
        updates = {}
        
        # Merge keywords
        existing_keywords = set(existing.get("keywords", []) or [])
        new_keywords = set(new_concept_data.get("keywords", []) or [])
        if new_keywords - existing_keywords:
            updates["keywords"] = list(existing_keywords | new_keywords)
        
        # Merge grade ranges
        existing_grade = set(existing.get("grade", []) or [])
        new_grade = set(new_concept_data.get("grade", []) or [])
        if new_grade - existing_grade:
            updates["grade"] = list(existing_grade | new_grade)
        
        # Update subject in metadata if provided
        existing_metadata = existing.get("metadata") or {}
        # Handle cases where metadata is stored as JSON string
        if isinstance(existing_metadata, str):
            import json
            existing_metadata = json.loads(existing_metadata) if existing_metadata else {}

        # Ensure we have a dict before using .get / assigning
        if not isinstance(existing_metadata, dict):
            existing_metadata = {}
        
        if new_concept_data.get("subject"):
            # Only update if subject is missing or different
            if existing_metadata.get("subject") != new_concept_data.get("subject"):
                existing_metadata["subject"] = new_concept_data.get("subject")
                updates["metadata"] = existing_metadata
        
        # Update if there are changes
        if updates:
            await self.concept_repo.update_concept(concept_id, **updates)
            logger.info(f"Updated concept {concept_id} with additional information")
    
    async def _create_prerequisite_relationships(
        self,
        concept_id: str,
        prerequisites: List[str],
        all_concepts: List[Dict[str, Any]]
    ) -> None:
        """Create prerequisite relationships for a concept.
        
        Args:
            concept_id: Concept UUID
            prerequisites: List of prerequisite concept names
            all_concepts: All concepts from current document (for name resolution)
        """
        if not prerequisites:
            return
        
        # Find prerequisite concept IDs
        for prereq_name in prerequisites:
            # First, check in current document's concepts
            prereq_concept = None
            for concept in all_concepts:
                if concept.get("name") == prereq_name:
                    # This concept should already be processed
                    prereq_concept = await self.concept_repo.find_similar_concept(
                        name=prereq_name
                    )
                    break
            
            # If not found in current document, search all concepts
            if not prereq_concept:
                prereq_concept = await self.concept_repo.find_similar_concept(
                    name=prereq_name
                )
            
            if prereq_concept:
                prereq_id = prereq_concept["id"]
                
                # Create relationship
                await self.db.execute(
                    """
                    INSERT INTO concept_relationships 
                    (from_concept_id, to_concept_id, relationship_type)
                    VALUES ($1, $2, 'prerequisite_of')
                    ON CONFLICT (from_concept_id, to_concept_id, relationship_type) DO NOTHING
                    """,
                    prereq_id, concept_id
                )
                logger.debug(
                    f"Created prerequisite relationship: {prereq_name} -> {concept_id}"
                )
            else:
                logger.warning(
                    f"Prerequisite concept not found: {prereq_name} "
                    f"(for concept {concept_id})"
                )
    
    async def create_skill_from_question(
        self,
        question_text: str,
        question_type: str
    ) -> Optional[str]:
        """Extract or create skill from question.
        
        Args:
            question_text: Question text
            question_type: Type of question
            
        Returns:
            Skill ID or None
        """
        # Simple skill extraction based on question type and keywords
        # This is a placeholder - can be enhanced with LLM-based extraction
        
        skill_name = None
        cognitive_level = None
        
        # Map question types to cognitive levels
        if question_type in ["problem_solving", "conceptual_question"]:
            cognitive_level = "apply"
        elif question_type == "multiple_choice":
            cognitive_level = "understand"
        else:
            cognitive_level = "remember"
        
        # Extract action verbs from question text
        action_verbs = ["analyze", "apply", "evaluate", "compare", "explain", "describe"]
        question_lower = question_text.lower()
        
        for verb in action_verbs:
            if verb in question_lower:
                skill_name = f"{verb.capitalize()} {question_type.replace('_', ' ')}"
                break
        
        if not skill_name:
            skill_name = f"Answer {question_type.replace('_', ' ')}"
        
        # Check if skill exists
        existing_skill = await self.db.fetchrow(
            "SELECT id FROM skills WHERE name = $1",
            skill_name
        )
        
        if existing_skill:
            return existing_skill["id"]
        
        # Create new skill
        skill_id = await self.db.fetchval(
            """
            INSERT INTO skills (name, cognitive_level)
            VALUES ($1, $2)
            RETURNING id
            """,
            skill_name, cognitive_level
        )
        
        logger.info(f"Created new skill: {skill_name} -> {skill_id}")
        return skill_id
