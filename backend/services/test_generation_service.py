"""Test generation service for creating tests from knowledge graph concepts."""

import logging
import random
import re
from typing import List, Dict, Any, Optional

from database.repositories.test_repository import TestRepository
from database.repositories.concept_repository import ConceptRepository
from database.repositories.question_repository import QuestionRepository
from subject_config import normalize_subject_name, get_subject_profile
from services.user_service import UserService
from core.database import Database
import json

logger = logging.getLogger(__name__)


class TestGenerationService:
    """Service for generating tests from concepts."""
    
    def __init__(self, db: Database, question_generation_service=None):
        """Initialize test generation service.
        
        Args:
            db: Database instance
            question_generation_service: Optional QuestionGenerationService for auto-generating questions
        """
        self.db = db
        self.test_repo = TestRepository(db)
        self.concept_repo = ConceptRepository(db)
        self.question_repo = QuestionRepository(db)
        self.question_gen_service = question_generation_service
    
    def _get_inclusive_difficulty_levels(self, difficulty: Optional[str]) -> List[str]:
        """Get inclusive difficulty levels based on selected difficulty.
        
        - easy: only easy
        - medium: easy and medium
        - hard: all levels (easy, medium, hard)
        - None: all levels
        """
        if not difficulty:
            return ["easy", "medium", "hard"]
        
        difficulty = difficulty.lower().strip()
        if difficulty == "easy":
            return ["easy"]
        elif difficulty == "medium":
            return ["easy", "medium"]
        elif difficulty == "hard":
            return ["easy", "medium", "hard"]
        else:
            # Default to all if invalid
            return ["easy", "medium", "hard"]
    
    async def create_pending_test_from_concept(
        self,
        child_id: str,
        concept_id: str,
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a draft test record for async generation from a concept."""
        concept = await self.concept_repo.get_concept_by_id(concept_id)
        if not concept:
            raise ValueError(f"Concept not found: {concept_id}")
        
        concept_name = concept.get('name', 'Unknown Concept')
        test_title = f"Test: {concept_name}"
        if include_prerequisites:
            test_title += " (generating…)"
        
        test_id = await self.test_repo.create_test(
            child_id=child_id,
            concept_id=concept_id,
            parent_id=parent_id,
            title=test_title,
            time_limit_minutes=time_limit_minutes,
            metadata={
                'include_prerequisites': include_prerequisites,
                'difficulty_filter': difficulty,
                'num_questions': num_questions,
                'generation_status': 'pending',
                'mode': 'concept'
            }
        )
        
        test = await self.test_repo.get_test_by_id(test_id)
        return dict(test) if test else {'id': test_id}
    
    async def create_pending_test_from_topics(
        self,
        child_id: str,
        subject: str,
        topics: List[str],
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a draft test record for async generation from topics."""
        topics_str = ', '.join(topics)
        test_title = f"Test: {subject} - {topics_str}" if topics else f"Test: {subject}"
        
        test_id = await self.test_repo.create_test(
            child_id=child_id,
            concept_id=None,
            parent_id=parent_id,
            title=test_title,
            time_limit_minutes=time_limit_minutes,
            metadata={
                'subject': subject,
                'topics': topics,
                'include_prerequisites': include_prerequisites,
                'difficulty_filter': difficulty,
                'num_questions': num_questions,
                'generation_status': 'pending',
                'mode': 'topics'
            }
        )
        
        test = await self.test_repo.get_test_by_id(test_id)
        return dict(test) if test else {'id': test_id}
    
    async def generate_test_from_concept(
        self,
        child_id: str,
        concept_id: str,
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate a test from a concept.
        
        Args:
            child_id: Child UUID
            concept_id: Concept UUID
            parent_id: Parent UUID (optional)
            include_prerequisites: Whether to include prerequisite concepts
            difficulty: Filter by difficulty (easy, medium, hard)
            num_questions: Target number of questions
            time_limit_minutes: Time limit in minutes (optional)
            
        Returns:
            Test dictionary with questions
        """
        # Use shared section generation logic
        concept, concept_ids, sections = await self._generate_sections_for_concept(
            child_id=child_id,
            concept_id=concept_id,
            include_prerequisites=include_prerequisites,
            difficulty=difficulty,
            num_questions=num_questions
        )
        
        # Create test synchronously (legacy path)
        concept_name = concept.get('name', 'Unknown Concept')
        test_title = f"Test: {concept_name}"
        if include_prerequisites and len(concept_ids) > 1:
            test_title += f" (with prerequisites)"
        
        test_id = await self.test_repo.create_test(
            child_id=child_id,
            concept_id=concept_id,
            parent_id=parent_id,
            title=test_title,
            time_limit_minutes=time_limit_minutes,
            metadata={
                'sections': [s['title'] for s in sections],
                'include_prerequisites': include_prerequisites,
                'difficulty_filter': difficulty
            }
        )
        
        # Attach questions and activate test
        await self._populate_test_with_questions(
            test_id=test_id,
            sections=sections
        )
        
        # Fetch complete test with questions
        test = await self.test_repo.get_test_with_questions(test_id)
        
        logger.info(f"Generated test {test_id} with {len(selected_questions)} questions")
        
        return test

    async def generate_questions_for_existing_test_from_concept(
        self,
        test_id: str,
        child_id: str,
        concept_id: str,
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> None:
        """Generate questions and attach them to an existing draft test (concept mode)."""
        concept, concept_ids, sections = await self._generate_sections_for_concept(
            child_id=child_id,
            concept_id=concept_id,
            include_prerequisites=include_prerequisites,
            difficulty=difficulty,
            num_questions=num_questions
        )
        
        # Merge/update metadata on existing test
        existing = await self.test_repo.get_test_by_id(test_id)
        metadata = {}
        if existing and existing.get("metadata"):
            raw = existing["metadata"]
            if isinstance(raw, str):
                try:
                    metadata = json.loads(raw)
                except Exception:
                    metadata = {}
            elif isinstance(raw, dict):
                metadata = dict(raw)
        metadata.update({
            'sections': [s['title'] for s in sections],
            'include_prerequisites': include_prerequisites,
            'difficulty_filter': difficulty,
            'generation_status': 'completed',
        })
        await self.test_repo.update_test_metadata(test_id, metadata)
        
        # Attach questions and activate
        await self._populate_test_with_questions(test_id=test_id, sections=sections)

    async def _generate_sections_for_concept(
        self,
        child_id: str,
        concept_id: str,
        include_prerequisites: bool,
        difficulty: Optional[str],
        num_questions: int
    ):
        """Shared logic: generate sections for a concept (no test creation)."""
        # Fetch concept
        concept = await self.concept_repo.get_concept_by_id(concept_id)
        if not concept:
            raise ValueError(f"Concept not found: {concept_id}")
        
        # Get concept IDs to include (main + prerequisites if enabled)
        concept_ids = [concept_id]
        if include_prerequisites:
            prerequisite_ids = await self._get_prerequisite_concepts(concept_id)
            concept_ids.extend(prerequisite_ids)
            logger.info(f"Including {len(prerequisite_ids)} prerequisite concepts")
        
        # Get subject from concept metadata
        concept_metadata = concept.get('metadata') or {}
        if isinstance(concept_metadata, str):
            concept_metadata = json.loads(concept_metadata) if concept_metadata else {}
        subject_id = normalize_subject_name(concept_metadata.get('subject', '')) if concept_metadata else None
        
        # Get child profile to extract grade level
        grade_level = 8  # Default
        try:
            user_service = UserService()  # Fixed: UserService doesn't take db parameter
            child_profile = await user_service.get_child(child_id)
            if child_profile and child_profile.get('grade'):
                grade_str = str(child_profile.get('grade', ''))
                grade_match = re.search(r'\d+', grade_str)
                if grade_match:
                    grade_level = int(grade_match.group())
                else:
                    try:
                        grade_level = int(grade_str)
                    except ValueError:
                        pass
        except Exception as e:
            logger.warning(f"Failed to get child profile for grade level: {e}")
        
        # Get subject profile
        subject_profile = get_subject_profile(subject_id) if subject_id else None
        
        # Track IDs of questions generated in this run so the test uses only these
        generated_question_ids: set[str] = set()
        
        # Normalize difficulty before passing to LLM
        normalized_difficulty = difficulty or "medium"
        if normalized_difficulty not in ["easy", "medium", "hard"]:
            from services.knowledge_graph_service import KnowledgeGraphService
            normalized_difficulty = KnowledgeGraphService._normalize_difficulty(normalized_difficulty)
        
        # Auto-generate questions if service is available and pool is insufficient
        if self.question_gen_service and concept_ids:
            try:
                gen_results = await self.question_gen_service.generate_all_questions_for_concepts(
                    concept_ids=[str(cid) for cid in concept_ids],
                    num_questions=num_questions,
                    question_type="multiple_choice",
                    difficulty=normalized_difficulty,  # Use normalized value
                    grade_level=grade_level,
                    subject_id=subject_id,
                    selected_topics=None,
                    subject_profile=subject_profile,
                )
                
                # Add safety check
                if not gen_results:
                    logger.warning("generate_all_questions_for_concepts returned None or empty dict")
                    gen_results = {}
                
                total_generated = 0
                total_skipped_duplicate = 0
                total_failed = 0
                for concept_id_str, questions_list in gen_results.items():
                    # Safety check
                    if questions_list is None:
                        logger.warning(f"questions_list is None for concept {concept_id_str}, skipping")
                        continue
                        
                    concept_id_uuid = concept_id_str
                    logger.info(f"Processing {len(questions_list)} questions for concept {concept_id_uuid}")
                    for idx, gen_result in enumerate(questions_list):
                        # Safety check for gen_result structure
                        if not gen_result or "blueprint" not in gen_result:
                            logger.error(f"Invalid gen_result structure at index {idx} for concept {concept_id_uuid}")
                            total_failed += 1
                            continue
                            
                        blueprint = gen_result["blueprint"]
                        raw = gen_result.get("raw", {})
                        
                        logger.debug(f"Processing question {idx + 1}/{len(questions_list)} for concept {concept_id_uuid}: {blueprint.question_text[:100]}...")
                        
                        # Skip duplicate detection when generating questions for a test
                        # We want to use the LLM-generated questions even if similar ones exist
                        # The test will use these specific questions, so duplicates are acceptable
                        # duplicate_check = await self.question_gen_service.check_semantic_duplicate(
                        #     blueprint.question_text,
                        #     concept_id_uuid,
                        #     similarity_threshold=0.85
                        # )
                        # if duplicate_check['is_duplicate']:
                        #     logger.warning(f"Question duplicate detected for concept {concept_id_uuid}, skipping. Similarity: {duplicate_check.get('max_similarity', 0)}")
                        #     total_skipped_duplicate += 1
                        #     continue
                        
                        # Safer options handling
                        options_text = []
                        if blueprint.options:
                            try:
                                options_text = [opt.text for opt in blueprint.options if opt and hasattr(opt, 'text')]
                            except (TypeError, AttributeError) as e:
                                logger.error(f"Error processing options for question {idx + 1}: {e}")
                                options_text = []
                        # Preserve diagram_code from metadata if present
                        diagram_code = blueprint.metadata.get("diagram_code") or raw.get("metadata", {}).get("diagram_code")
                        question_data_for_storage = {
                            "text": blueprint.question_text,
                            "type": blueprint.question_type,
                            "difficulty": blueprint.difficulty,
                            "options": options_text,
                            "answer": blueprint.correct_answer if blueprint.question_type == "multiple_choice" else None,
                            "expected_answer": blueprint.expected_answer if blueprint.question_type != "multiple_choice" else None,
                            "hint": blueprint.hint,
                            "explanation": blueprint.metadata.get("explanation") or raw.get("explanation", ""),
                            "blueprint": blueprint.dict(),
                        }
                        # Ensure diagram_code is preserved in blueprint metadata
                        if diagram_code:
                            if "blueprint" not in question_data_for_storage:
                                question_data_for_storage["blueprint"] = {}
                            if isinstance(question_data_for_storage["blueprint"], dict):
                                if "metadata" not in question_data_for_storage["blueprint"]:
                                    question_data_for_storage["blueprint"]["metadata"] = {}
                                question_data_for_storage["blueprint"]["metadata"]["diagram_code"] = diagram_code
                        
                        # Preserve needs_graph and needs_diagram flags for FRQ questions
                        if blueprint.question_type != "multiple_choice":
                            needs_graph = blueprint.needs_graph or blueprint.metadata.get("needs_graph", False)
                            needs_diagram = blueprint.needs_diagram or blueprint.metadata.get("needs_diagram", False)
                            if needs_graph:
                                if "blueprint" not in question_data_for_storage:
                                    question_data_for_storage["blueprint"] = {}
                                if isinstance(question_data_for_storage["blueprint"], dict):
                                    if "metadata" not in question_data_for_storage["blueprint"]:
                                        question_data_for_storage["blueprint"]["metadata"] = {}
                                    question_data_for_storage["blueprint"]["metadata"]["needs_graph"] = True
                            if needs_diagram:
                                if "blueprint" not in question_data_for_storage:
                                    question_data_for_storage["blueprint"] = {}
                                if isinstance(question_data_for_storage["blueprint"], dict):
                                    if "metadata" not in question_data_for_storage["blueprint"]:
                                        question_data_for_storage["blueprint"]["metadata"] = {}
                                    question_data_for_storage["blueprint"]["metadata"]["needs_diagram"] = True
                        try:
                            question_id = await self.question_gen_service.store_generated_question(
                                concept_id_uuid,
                                question_data_for_storage,
                                blueprint.question_text
                            )
                            # Ensure question_id is stored as string for consistent comparison
                            question_id_str = str(question_id)
                            generated_question_ids.add(question_id_str)
                            total_generated += 1
                            logger.info(f"✓ Stored question {question_id_str} for concept {concept_id_uuid} (question {idx + 1}/{len(questions_list)}, diagram_code: {'yes' if diagram_code else 'no'})")
                        except Exception as e:
                            total_failed += 1
                            logger.error(f"✗ Failed to store question {idx + 1}/{len(questions_list)} for concept {concept_id_uuid}: {e}", exc_info=True)
                
                logger.info(f"Question storage summary: {total_generated} stored, {total_skipped_duplicate} skipped (duplicates), {total_failed} failed")
                
                if total_generated > 0:
                    logger.info(f"Generated and stored {total_generated} questions for {len(concept_ids)} concepts in a single LLM request")
            except Exception as e:
                logger.warning(f"Failed to auto-generate questions for concepts: {e}", exc_info=True)
        
        # Fetch questions for all concepts (but only keep ones generated in this run, if any)
        all_questions = []
        logger.info(f"Fetching questions for {len(concept_ids)} concepts. Generated question IDs: {list(generated_question_ids)}")
        for cid in concept_ids:
            questions = await self.question_repo.get_questions_by_concept(cid)
            questions = [q for q in questions if q.get('status') != 'rejected']
            logger.debug(f"Concept {cid}: Found {len(questions)} non-rejected questions")
            if generated_question_ids:
                # Convert question IDs to strings for comparison (database might return UUID objects)
                filtered_questions = [
                    q for q in questions 
                    if str(q.get('id')) in generated_question_ids or q.get('id') in generated_question_ids
                ]
                logger.info(f"Filtered questions for concept {cid}: {len(questions)} total, {len(filtered_questions)} from current LLM run (generated_question_ids count: {len(generated_question_ids)})")
                if filtered_questions:
                    logger.debug(f"  Matched question IDs: {[str(q.get('id')) for q in filtered_questions]}")
                else:
                    logger.warning(f"  No questions matched generated_question_ids for concept {cid}")
                    logger.debug(f"  Available question IDs: {[str(q.get('id')) for q in questions]}")
                questions = filtered_questions
            else:
                logger.warning(f"No generated_question_ids tracked for concept {cid}, using all available questions (this may include old questions)")
            all_questions.extend(questions)
        
        logger.info(f"Total questions collected from all concepts: {len(all_questions)}")
        
        # Get inclusive difficulty levels and apply filter
        if difficulty:
            inclusive_difficulties = self._get_inclusive_difficulty_levels(difficulty)
            before_filter = len(all_questions)
            all_questions = [q for q in all_questions if q.get('difficulty') in inclusive_difficulties]
            logger.info(f"After inclusive difficulty filter ({difficulty} -> {inclusive_difficulties}): {len(all_questions)} questions (was {before_filter})")
        
        if not all_questions:
            raise ValueError(f"No questions found for concept {concept_id}")
        
        if len(all_questions) > num_questions:
            selected_questions = random.sample(all_questions, num_questions)
            logger.info(f"Randomly selected {len(selected_questions)} questions from {len(all_questions)} available")
        else:
            selected_questions = all_questions
            logger.info(f"Using all {len(selected_questions)} available questions (requested {num_questions})")
        
        logger.debug(f"Selected question IDs: {[str(q.get('id')) for q in selected_questions]}")
        sections = self._organize_questions_into_sections(selected_questions)
        logger.info(f"Organized {len(selected_questions)} questions into {len(sections)} sections")
        return concept, concept_ids, sections

    async def _populate_test_with_questions(
        self,
        test_id: str,
        sections: List[Dict[str, Any]]
    ) -> None:
        """Attach questions to an existing test and activate it."""
        total_questions = sum(len(section['questions']) for section in sections)
        logger.info(f"Populating test {test_id} with {total_questions} questions from {len(sections)} sections")
        order_index = 0
        for section_idx, section in enumerate(sections):
            logger.debug(f"Section {section_idx + 1}/{len(sections)}: '{section.get('title', 'Unknown')}' with {len(section['questions'])} questions")
            for q_idx, question in enumerate(section['questions']):
                logger.debug(f"  Adding question {q_idx + 1}/{len(section['questions'])}: {question.get('text', 'N/A')[:100]}...")
                await self.test_repo.add_question_to_test(
                    test_id=test_id,
                    question_id=question['id'],
                    order_index=order_index,
                    section_title=section['title'],
                    max_score=1.0  # Default max score
                )
                order_index += 1
        
        # Activate test
        await self.test_repo.update_test_status(test_id, 'active')
    
    async def _get_prerequisite_concepts(self, concept_id: str) -> List[str]:
        """Get all prerequisite concept IDs for a concept.
        
        Args:
            concept_id: Concept UUID
            
        Returns:
            List of prerequisite concept IDs
        """
        # Get prerequisites via concept_relationships table
        relationships = await self.db.fetch(
            """
            SELECT to_concept_id 
            FROM concept_relationships
            WHERE from_concept_id = $1 
            AND relationship_type IN ('prerequisite_of', 'requires')
            """,
            concept_id
        )
        
        prerequisite_ids = [r['to_concept_id'] for r in relationships]
        
        # Also check reverse relationships (if concept is a prerequisite of others)
        reverse_relationships = await self.db.fetch(
            """
            SELECT from_concept_id 
            FROM concept_relationships
            WHERE to_concept_id = $1 
            AND relationship_type IN ('prerequisite_of', 'requires')
            """,
            concept_id
        )
        
        # For reverse, we want concepts that this concept is a prerequisite of
        # So we get concepts that have this as a prerequisite
        for rel in reverse_relationships:
            if rel['from_concept_id'] not in prerequisite_ids:
                prerequisite_ids.append(rel['from_concept_id'])
        
        return prerequisite_ids
    
    def _organize_questions_into_sections(
        self,
        questions: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Organize questions into sections by type.
        
        Args:
            questions: List of question dictionaries
            
        Returns:
            List of sections, each containing questions
        """
        # Group questions by type
        by_type = {}
        for q in questions:
            q_type = q.get('type', 'short_answer')
            if q_type not in by_type:
                by_type[q_type] = []
            by_type[q_type].append(q)
        
        # Create sections
        sections = []
        section_order = ['multiple_choice', 'short_answer', 'problem_solving', 'conceptual_question']
        
        for q_type in section_order:
            if q_type in by_type:
                section_title = self._get_section_title(q_type)
                sections.append({
                    'title': section_title,
                    'type': q_type,
                    'questions': by_type[q_type]
                })
        
        # Add any remaining question types
        for q_type, q_list in by_type.items():
            if q_type not in section_order:
                section_title = self._get_section_title(q_type)
                sections.append({
                    'title': section_title,
                    'type': q_type,
                    'questions': q_list
                })
        
        return sections
    
    async def generate_test_from_topics(
        self,
        child_id: str,
        subject: str,
        topics: List[str],
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> Dict[str, Any]:
        """Generate a test from topics.
        
        Args:
            child_id: Child UUID
            subject: Subject name (e.g., 'Mathematics', 'Physics')
            topics: List of topic names
            parent_id: Parent UUID (optional)
            include_prerequisites: Whether to include prerequisite concepts
            difficulty: Filter by difficulty (easy, medium, hard)
            num_questions: Target number of questions
            time_limit_minutes: Time limit in minutes (optional)
            
        Returns:
            Test dictionary with questions
        """
        matched_concept_ids, sections = await self._generate_sections_for_topics(
            child_id=child_id,
            subject=subject,
            topics=topics,
            include_prerequisites=include_prerequisites,
            difficulty=difficulty,
            num_questions=num_questions
        )
        
        # Create test title
        topics_str = ', '.join(topics)
        test_title = f"Test: {subject} - {topics_str}"
        if len(topics) > 1:
            test_title = f"Test: {subject} ({len(topics)} topics)"
        
        test_id = await self.test_repo.create_test(
            child_id=child_id,
            concept_id=None,  # No single concept for topic-based tests
            parent_id=parent_id,
            title=test_title,
            time_limit_minutes=time_limit_minutes,
            metadata={
                'subject': subject,
                'topics': topics,
                'sections': [s['title'] for s in sections],
                'include_prerequisites': include_prerequisites,
                'difficulty_filter': difficulty,
                'matched_concept_ids': matched_concept_ids
            }
        )
        
        # Attach questions and activate test
        await self._populate_test_with_questions(
            test_id=test_id,
            sections=sections
        )
        
        # Fetch complete test with questions
        test = await self.test_repo.get_test_with_questions(test_id)
        
        logger.info(f"Generated test {test_id} with {len(selected_questions)} questions from {len(topics)} topics")
        
        return test

    async def generate_questions_for_existing_test_from_topics(
        self,
        test_id: str,
        child_id: str,
        subject: str,
        topics: List[str],
        parent_id: Optional[str] = None,
        include_prerequisites: bool = False,
        difficulty: Optional[str] = None,
        num_questions: int = 10,
        time_limit_minutes: Optional[int] = None
    ) -> None:
        """Generate questions and attach them to an existing draft test (topics mode)."""
        matched_concept_ids, sections = await self._generate_sections_for_topics(
            child_id=child_id,
            subject=subject,
            topics=topics,
            include_prerequisites=include_prerequisites,
            difficulty=difficulty,
            num_questions=num_questions
        )
        
        # Merge/update metadata on existing test
        existing = await self.test_repo.get_test_by_id(test_id)
        metadata = {}
        if existing and existing.get("metadata"):
            raw = existing["metadata"]
            if isinstance(raw, str):
                try:
                    metadata = json.loads(raw)
                except Exception:
                    metadata = {}
            elif isinstance(raw, dict):
                metadata = dict(raw)
        metadata.update({
            'subject': subject,
            'topics': topics,
            'sections': [s['title'] for s in sections],
            'include_prerequisites': include_prerequisites,
            'difficulty_filter': difficulty,
            'matched_concept_ids': matched_concept_ids,
            'generation_status': 'completed',
        })
        await self.test_repo.update_test_metadata(test_id, metadata)
        
        # Attach questions and activate
        await self._populate_test_with_questions(test_id=test_id, sections=sections)

    async def _generate_sections_for_topics(
        self,
        child_id: str,
        subject: str,
        topics: List[str],
        include_prerequisites: bool,
        difficulty: Optional[str],
        num_questions: int
    ):
        """Shared logic: generate sections for a subject/topics combo (no test creation)."""
        # Find concepts that match the topics
        # We'll match by subtopic name or by checking if topic name appears in concept name/subtopic
        concept_ids: List[str] = []
        
        # Get all concepts for the child (from their documents)
        all_concepts = await self.db.fetch(
            """
            SELECT DISTINCT c.id, c.name, c.subtopic, c.keywords, d.subject
            FROM concepts c
            JOIN documents d ON c.document_id = d.id
            WHERE (
                d.child_id = $1 
                OR d.id IN (
                    SELECT document_id 
                    FROM document_children 
                    WHERE child_id = $1
                )
            )
            AND d.is_active = TRUE
            AND (
                d.subject = $2 
                OR d.subject IS NULL 
                OR LOWER(TRIM(d.subject)) = LOWER(TRIM($2))
            )
            """,
            child_id, subject
        )
        
        logger.info(f"Found {len(all_concepts) if all_concepts else 0} concepts for child {child_id}, subject {subject}")
        
        if all_concepts:
            sample_concepts = all_concepts[:5]
            for c in sample_concepts:
                logger.debug(f"Concept: {c.get('name')}, Subtopic: {c.get('subtopic')}, Subject: {c.get('subject')}")
        
        matched_concept_ids: List[str] = []
        for concept in all_concepts:
            concept_subtopic = (concept.get('subtopic') or '').lower().strip()
            concept_name = (concept.get('name') or '').lower().strip()
            concept_keywords = [k.lower().strip() for k in (concept.get('keywords') or []) if k]
            
            for topic in topics:
                topic_lower = topic.lower().strip()
                
                if concept_subtopic == topic_lower:
                    if concept['id'] not in matched_concept_ids:
                        matched_concept_ids.append(concept['id'])
                        logger.debug(f"Matched concept '{concept.get('name')}' by exact subtopic: '{concept_subtopic}' == '{topic_lower}'")
                    break
                
                if topic_lower in concept_subtopic or concept_subtopic in topic_lower:
                    if concept['id'] not in matched_concept_ids:
                        matched_concept_ids.append(concept['id'])
                        logger.debug(f"Matched concept '{concept.get('name')}' by subtopic contains: '{topic_lower}' in '{concept_subtopic}'")
                    break
                
                if topic_lower in concept_name:
                    if concept['id'] not in matched_concept_ids:
                        matched_concept_ids.append(concept['id'])
                        logger.debug(f"Matched concept '{concept.get('name')}' by name contains: '{topic_lower}' in '{concept_name}'")
                    break
                
                if any(topic_lower in kw or kw in topic_lower for kw in concept_keywords):
                    if concept['id'] not in matched_concept_ids:
                        matched_concept_ids.append(concept['id'])
                        logger.debug(f"Matched concept '{concept.get('name')}' by keyword: '{topic_lower}' in keywords")
                    break
        
        if not matched_concept_ids:
            available_subtopics = set()
            for concept in all_concepts:
                subtopic = concept.get('subtopic')
                if subtopic:
                    available_subtopics.add(subtopic)
            
            error_msg = f"No concepts found matching topics: {', '.join(topics)}"
            if available_subtopics:
                error_msg += f"\n\nAvailable topics for subject '{subject}': {', '.join(sorted(available_subtopics))}"
            else:
                error_msg += f"\n\nNo concepts found for child {child_id} with subject '{subject}'."
                error_msg += " Make sure documents are uploaded and processed for this subject."
            
            logger.warning(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Found {len(matched_concept_ids)} concepts matching topics: {topics}")
        
        if include_prerequisites:
            all_prerequisite_ids: List[str] = []
            for cid in matched_concept_ids:
                prereq_ids = await self._get_prerequisite_concepts(cid)
                all_prerequisite_ids.extend(prereq_ids)
            for pid in all_prerequisite_ids:
                if pid not in matched_concept_ids:
                    matched_concept_ids.append(pid)
            logger.info(f"Including {len(all_prerequisite_ids)} prerequisite concepts")
        
        subject_id = normalize_subject_name(subject)
        
        grade_level = 8  # Default
        try:
            user_service = UserService()  # Fixed: UserService doesn't take db parameter
            child_profile = await user_service.get_child(child_id)
            if child_profile and child_profile.get('grade'):
                grade_str = str(child_profile.get('grade', ''))
                grade_match = re.search(r'\d+', grade_str)
                if grade_match:
                    grade_level = int(grade_match.group())
                else:
                    try:
                        grade_level = int(grade_str)
                    except ValueError:
                        pass
        except Exception as e:
            logger.warning(f"Failed to get child profile for grade level: {e}")
        
        subject_profile = get_subject_profile(subject_id)
        
        # Track IDs of questions generated in this run so the test uses only these
        generated_question_ids: set[str] = set()
        
        # Normalize difficulty before passing to LLM
        normalized_difficulty = difficulty or "medium"
        if normalized_difficulty not in ["easy", "medium", "hard"]:
            from services.knowledge_graph_service import KnowledgeGraphService
            normalized_difficulty = KnowledgeGraphService._normalize_difficulty(normalized_difficulty)
        
        if self.question_gen_service and matched_concept_ids:
            try:
                gen_results = await self.question_gen_service.generate_all_questions_for_concepts(
                    concept_ids=[str(cid) for cid in matched_concept_ids],
                    num_questions=num_questions,
                    question_type="multiple_choice",
                    difficulty=normalized_difficulty,  # Use normalized value
                    grade_level=grade_level,
                    subject_id=subject_id,
                    selected_topics=topics,
                    subject_profile=subject_profile,
                )
                
                # Add safety check
                if not gen_results:
                    logger.warning("generate_all_questions_for_concepts returned None or empty dict")
                    gen_results = {}
                
                total_generated = 0
                total_skipped_duplicate = 0
                total_failed = 0
                for concept_id_str, questions_list in gen_results.items():
                    # Safety check
                    if questions_list is None:
                        logger.warning(f"questions_list is None for concept {concept_id_str}, skipping")
                        continue
                        
                    concept_id_uuid = concept_id_str
                    logger.info(f"Processing {len(questions_list)} questions for concept {concept_id_uuid}")
                    for idx, gen_result in enumerate(questions_list):
                        # Safety check for gen_result structure
                        if not gen_result or "blueprint" not in gen_result:
                            logger.error(f"Invalid gen_result structure at index {idx} for concept {concept_id_uuid}")
                            total_failed += 1
                            continue
                            
                        blueprint = gen_result["blueprint"]
                        raw = gen_result.get("raw", {})
                        
                        logger.debug(f"Processing question {idx + 1}/{len(questions_list)} for concept {concept_id_uuid}: {blueprint.question_text[:100]}...")
                        
                        # Skip duplicate detection when generating questions for a test
                        # We want to use the LLM-generated questions even if similar ones exist
                        # The test will use these specific questions, so duplicates are acceptable
                        # duplicate_check = await self.question_gen_service.check_semantic_duplicate(
                        #     blueprint.question_text,
                        #     concept_id_uuid,
                        #     similarity_threshold=0.85
                        # )
                        # if duplicate_check['is_duplicate']:
                        #     logger.warning(f"Question duplicate detected for concept {concept_id_uuid}, skipping. Similarity: {duplicate_check.get('max_similarity', 0)}")
                        #     total_skipped_duplicate += 1
                        #     continue
                        
                        # Safer options handling
                        options_text = []
                        if blueprint.options:
                            try:
                                options_text = [opt.text for opt in blueprint.options if opt and hasattr(opt, 'text')]
                            except (TypeError, AttributeError) as e:
                                logger.error(f"Error processing options for question {idx + 1}: {e}")
                                options_text = []
                        # Preserve diagram_code from metadata if present
                        diagram_code = blueprint.metadata.get("diagram_code") or raw.get("metadata", {}).get("diagram_code")
                        question_data_for_storage = {
                            "text": blueprint.question_text,
                            "type": blueprint.question_type,
                            "difficulty": blueprint.difficulty,
                            "options": options_text,
                            "answer": blueprint.correct_answer if blueprint.question_type == "multiple_choice" else None,
                            "expected_answer": blueprint.expected_answer if blueprint.question_type != "multiple_choice" else None,
                            "hint": blueprint.hint,
                            "explanation": blueprint.metadata.get("explanation") or raw.get("explanation", ""),
                            "blueprint": blueprint.dict(),
                        }
                        # Ensure diagram_code is preserved in blueprint metadata
                        if diagram_code:
                            if "blueprint" not in question_data_for_storage:
                                question_data_for_storage["blueprint"] = {}
                            if isinstance(question_data_for_storage["blueprint"], dict):
                                if "metadata" not in question_data_for_storage["blueprint"]:
                                    question_data_for_storage["blueprint"]["metadata"] = {}
                                question_data_for_storage["blueprint"]["metadata"]["diagram_code"] = diagram_code
                        
                        # Preserve needs_graph and needs_diagram flags for FRQ questions
                        if blueprint.question_type != "multiple_choice":
                            needs_graph = blueprint.needs_graph or blueprint.metadata.get("needs_graph", False)
                            needs_diagram = blueprint.needs_diagram or blueprint.metadata.get("needs_diagram", False)
                            if needs_graph:
                                if "blueprint" not in question_data_for_storage:
                                    question_data_for_storage["blueprint"] = {}
                                if isinstance(question_data_for_storage["blueprint"], dict):
                                    if "metadata" not in question_data_for_storage["blueprint"]:
                                        question_data_for_storage["blueprint"]["metadata"] = {}
                                    question_data_for_storage["blueprint"]["metadata"]["needs_graph"] = True
                            if needs_diagram:
                                if "blueprint" not in question_data_for_storage:
                                    question_data_for_storage["blueprint"] = {}
                                if isinstance(question_data_for_storage["blueprint"], dict):
                                    if "metadata" not in question_data_for_storage["blueprint"]:
                                        question_data_for_storage["blueprint"]["metadata"] = {}
                                    question_data_for_storage["blueprint"]["metadata"]["needs_diagram"] = True
                        
                        try:
                            question_id = await self.question_gen_service.store_generated_question(
                                concept_id_uuid,
                                question_data_for_storage,
                                blueprint.question_text
                            )
                            # Ensure question_id is stored as string for consistent comparison
                            question_id_str = str(question_id)
                            generated_question_ids.add(question_id_str)
                            total_generated += 1
                            logger.info(f"✓ Stored question {question_id_str} for concept {concept_id_uuid} (question {idx + 1}/{len(questions_list)}, diagram_code: {'yes' if diagram_code else 'no'})")
                        except Exception as e:
                            total_failed += 1
                            logger.error(f"✗ Failed to store question {idx + 1}/{len(questions_list)} for concept {concept_id_uuid}: {e}", exc_info=True)
                
                logger.info(f"Question storage summary: {total_generated} stored, {total_skipped_duplicate} skipped (duplicates), {total_failed} failed")
                
                if total_generated > 0:
                    logger.info(f"Generated and stored {total_generated} questions for {len(matched_concept_ids)} concepts in a single LLM request")
            except Exception as e:
                logger.warning(f"Failed to auto-generate questions for concepts: {e}", exc_info=True)
        
        # Fetch questions for all concepts (but only keep ones generated in this run, if any)
        all_questions: List[Dict[str, Any]] = []
        logger.info(f"Fetching questions for {len(matched_concept_ids)} concepts. Generated question IDs: {list(generated_question_ids)}")
        for cid in matched_concept_ids:
            questions = await self.question_repo.get_questions_by_concept(cid)
            questions = [q for q in questions if q.get('status') != 'rejected']
            logger.debug(f"Concept {cid}: Found {len(questions)} non-rejected questions")
            # If we generated new questions in this run, restrict to those IDs
            if generated_question_ids:
                # Convert question IDs to strings for comparison (database might return UUID objects)
                filtered_questions = [
                    q for q in questions 
                    if str(q.get('id')) in generated_question_ids or q.get('id') in generated_question_ids
                ]
                logger.info(f"Filtered questions for concept {cid}: {len(questions)} total, {len(filtered_questions)} from current LLM run (generated_question_ids count: {len(generated_question_ids)})")
                if filtered_questions:
                    logger.debug(f"  Matched question IDs: {[str(q.get('id')) for q in filtered_questions]}")
                else:
                    logger.warning(f"  No questions matched generated_question_ids for concept {cid}")
                    logger.debug(f"  Available question IDs: {[str(q.get('id')) for q in questions]}")
                questions = filtered_questions
            else:
                logger.warning(f"No generated_question_ids tracked for concept {cid}, using all available questions (this may include old questions)")
            all_questions.extend(questions)
        
        logger.info(f"Total questions collected from all concepts: {len(all_questions)}")
        
        # Get inclusive difficulty levels and apply filter
        if difficulty:
            inclusive_difficulties = self._get_inclusive_difficulty_levels(difficulty)
            before_filter = len(all_questions)
            all_questions = [q for q in all_questions if q.get('difficulty') in inclusive_difficulties]
            logger.info(f"After inclusive difficulty filter ({difficulty} -> {inclusive_difficulties}): {len(all_questions)} questions (was {before_filter})")
        
        if not all_questions:
            raise ValueError(f"No questions found for topics: {', '.join(topics)}")
        
        if len(all_questions) > num_questions:
            selected_questions = random.sample(all_questions, num_questions)
            logger.info(f"Randomly selected {len(selected_questions)} questions from {len(all_questions)} available")
        else:
            selected_questions = all_questions
            logger.info(f"Using all {len(selected_questions)} available questions (requested {num_questions})")
        
        logger.debug(f"Selected question IDs: {[str(q.get('id')) for q in selected_questions]}")
        sections = self._organize_questions_into_sections(selected_questions)
        logger.info(f"Organized {len(selected_questions)} questions into {len(sections)} sections")
        return matched_concept_ids, sections
    
    def _get_section_title(self, question_type: str) -> str:
        """Get section title for question type.
        
        Args:
            question_type: Question type string
            
        Returns:
            Section title
        """
        titles = {
            'multiple_choice': 'Multiple Choice',
            'short_answer': 'Short Answer',
            'problem_solving': 'Problem Solving',
            'conceptual_question': 'Conceptual Questions',
            'matching': 'Matching',
            'fill_in_the_blank': 'Fill in the Blank'
        }
        return titles.get(question_type, 'Questions')
