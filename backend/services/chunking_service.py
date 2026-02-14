"""Chunking service for intelligent text chunking of educational content."""

import logging
import re
from typing import List, Dict, Any, Optional
import tiktoken

from database.repositories.concept_repository import ConceptRepository

logger = logging.getLogger(__name__)


class ChunkingService:
    """Intelligent chunking service for educational content."""
    
    def __init__(self, target_tokens: int = 400, max_tokens: int = 800, min_tokens: int = 200):
        """Initialize chunking service.
        
        Args:
            target_tokens: Target number of tokens per chunk
            max_tokens: Maximum tokens per chunk
            min_tokens: Minimum tokens per chunk
        """
        self.target_tokens = target_tokens
        self.max_tokens = max_tokens
        self.min_tokens = min_tokens
        
        # Initialize tokenizer (cl100k_base is used by GPT models)
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception as e:
            logger.warning(f"Failed to load tiktoken, using simple token estimation: {e}")
            self.tokenizer = None
    
    def _count_tokens(self, text: str) -> int:
        """Count tokens in text.
        
        Args:
            text: Text to count
            
        Returns:
            Number of tokens
        """
        if self.tokenizer:
            return len(self.tokenizer.encode(text))
        else:
            # Fallback: approximate 1 token = 4 characters
            return len(text) // 4
    
    def _create_metadata(
        self,
        concept: Dict[str, Any],
        chunk_type: str,
        question: Optional[Dict[str, Any]] = None,
        section: Optional[str] = None,
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create metadata for adaptive filtering.
        
        Args:
            concept: Concept dictionary
            chunk_type: Type of chunk
            question: Optional question dictionary
            section: Optional section identifier
            subject: Optional subject name (from document level)
            
        Returns:
            Metadata dictionary
        """
        # Prefer the most specific label available:
        # - legacy: concept.name
        # - new workflow: concept.subtopic (granular) + concept.topic_name (broad)
        concept_name = (
            concept.get("name")
            or concept.get("subtopic")
            or concept.get("topic_name")
            or concept.get("concept_name")
            or ""
        )
        # Category/subtopic for filtering:
        # - legacy: concept.subtopic
        # - new workflow: concept.topic_name
        subtopic_category = concept.get("subtopic") or concept.get("sub_topic")
        if concept.get("topic_name") and not concept.get("name"):
            subtopic_category = concept.get("topic_name")
        metadata = {
            "concept_name": concept_name,
            "subtopic": subtopic_category,
            "grade": concept.get("grade", []),
            "difficulty": concept.get("difficulty", "medium"),
            "keywords": concept.get("keywords", []),
            "prerequisites": concept.get("prerequisites", []),
            "chunk_type": chunk_type
        }
        
        # Add subject if provided (document-level)
        if subject:
            metadata["subject"] = subject
        
        if question:
            metadata["question_type"] = question.get("type")
            metadata["question_id"] = question.get("id")
        
        if section:
            metadata["section"] = section
        
        return metadata
    
    def create_concept_overview_chunk(
        self,
        document_id: str,
        concept: Dict[str, Any],
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create concept overview chunk.
        
        Args:
            document_id: Document UUID
            concept: Concept dictionary
            subject: Optional subject name (from document level)
            
        Returns:
            Chunk dictionary
        """
        concept_name = (
            concept.get("name")
            or concept.get("subtopic")
            or concept.get("topic_name")
            or concept.get("concept_name")
            or "Unknown"
        )
        text_parts = [
            f"Concept: {concept_name}",
            f"Subtopic: {(concept.get('topic_name') if concept.get('topic_name') and not concept.get('name') else concept.get('subtopic')) or 'N/A'}",
            f"Grade Levels: {', '.join(map(str, concept.get('grade', [])))}",
            f"Difficulty: {concept.get('difficulty', 'medium')}",
        ]
        
        if concept.get('keywords'):
            text_parts.append(f"Keywords: {', '.join(concept.get('keywords', []))}")
        
        if concept.get('prerequisites'):
            text_parts.append(f"Prerequisites: {', '.join(concept.get('prerequisites', []))}")
        
        chunk_text = "\n".join(text_parts)
        
        return {
            "document_id": document_id,
            "concept_id": None,  # Will be set after concept creation
            "chunk_type": "concept_overview",
            "chunk_text": chunk_text,
            "metadata": self._create_metadata(concept, "concept_overview", subject=subject)
        }
    
    def create_explanation_chunks(
        self,
        document_id: str,
        concept: Dict[str, Any],
        markdown: str,
        subject: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Split markdown into explanation chunks.
        
        Each conceptual explanation = separate chunk
        Chunk size: 200-800 tokens
        
        Args:
            document_id: Document UUID
            concept: Concept dictionary
            markdown: Full markdown text
            
        Returns:
            List of chunk dictionaries
        """
        chunks = []
        
        # Find sections related to this concept using keywords
        concept_name = (
            concept.get("name")
            or concept.get("subtopic")
            or concept.get("topic_name")
            or concept.get("concept_name")
            or ""
        ).lower()
        keywords = [k.lower() for k in concept.get("keywords", [])]
        
        # Split markdown by sections (headers, paragraphs)
        # Look for sections that mention the concept or keywords
        sections = self._extract_relevant_sections(markdown, concept_name, keywords)
        
        for section_idx, section_text in enumerate(sections):
            section_id = f"section_{section_idx + 1}"
            
            # Split section into chunks if too long
            section_chunks = self._split_text_by_tokens(
                section_text,
                self.target_tokens,
                self.max_tokens
            )
            
            for chunk_idx, chunk_text in enumerate(section_chunks):
                chunk_text = chunk_text.strip()
                token_count = self._count_tokens(chunk_text)
                
                # Enforce 200-800 token rule
                if token_count < self.min_tokens:
                    # If chunk is too small, try to merge with next chunk or skip
                    logger.warning(
                        f"Chunk too small ({token_count} tokens < {self.min_tokens}), "
                        f"skipping or merging: {chunk_text[:50]}..."
                    )
                    continue
                
                if token_count > self.max_tokens:
                    # If chunk is too large, split further
                    logger.warning(
                        f"Chunk too large ({token_count} tokens > {self.max_tokens}), "
                        f"splitting further: {chunk_text[:50]}..."
                    )
                    # Recursively split
                    sub_chunks = self._split_text_by_tokens(
                        chunk_text,
                        self.target_tokens,
                        self.max_tokens
                    )
                    for sub_chunk_text in sub_chunks:
                        sub_chunk_text = sub_chunk_text.strip()
                        sub_token_count = self._count_tokens(sub_chunk_text)
                        if sub_token_count >= self.min_tokens:
                            chunks.append({
                                "document_id": document_id,
                                "concept_id": None,  # Will be set after concept creation
                                "chunk_type": "explanation",
                                "chunk_text": sub_chunk_text,
                                "metadata": self._create_metadata(
                                    concept, 
                                    "explanation",
                                    section=f"{section_id}_sub{chunk_idx + 1}",
                                    subject=subject
                                )
                            })
                else:
                    # Chunk is within valid range
                    chunks.append({
                        "document_id": document_id,
                        "concept_id": None,  # Will be set after concept creation
                        "chunk_type": "explanation",
                        "chunk_text": chunk_text,
                                "metadata": self._create_metadata(
                                    concept, 
                                    "explanation",
                                    section=section_id,
                                    subject=subject
                                )
                    })
        
        return chunks
    
    def create_question_chunk(
        self,
        document_id: str,
        concept: Dict[str, Any],
        question: Dict[str, Any],
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a question chunk (each question is a separate chunk).
        
        Args:
            document_id: Document UUID
            concept: Concept dictionary
            question: Question dictionary
            subject: Optional subject name (from document level)
            
        Returns:
            Chunk dictionary
        """
        question_text = question.get("text", "")
        token_count = self._count_tokens(question_text)
        
        # Validate token count (warn if outside range, but still create chunk)
        if token_count < self.min_tokens:
            logger.warning(
                f"Question chunk has {token_count} tokens (< {self.min_tokens}): "
                f"{question_text[:50]}..."
            )
        elif token_count > self.max_tokens:
            logger.warning(
                f"Question chunk has {token_count} tokens (> {self.max_tokens}): "
                f"{question_text[:50]}..."
            )
        
        return {
            "document_id": document_id,
            "concept_id": None,  # Will be set after concept creation
            "question_id": None,  # Will be set after question creation
            "chunk_type": "question",
            "chunk_text": question_text,
            "metadata": self._create_metadata(concept, "question", question, subject=subject)
        }
    
    def create_visual_description_chunk(
        self,
        document_id: str,
        concept: Dict[str, Any],
        visual: Dict[str, Any],
        subject: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a visual description chunk (each visual is a separate chunk).
        
        Args:
            document_id: Document UUID
            concept: Concept dictionary
            visual: Visual dictionary or string (visual ID/key)
            subject: Optional subject name (from document level)
            
        Returns:
            Chunk dictionary
        """
        # Handle different visual data formats
        if isinstance(visual, str):
            # If it's just a string (visual ID or key), create minimal chunk
            description = f"Visual reference: {visual}"
            visual_type = "unknown"
            visual_key = visual
        elif isinstance(visual, dict):
            # Normal dictionary format
            description = visual.get("description", "")
            visual_type = visual.get("visual_type", "visual")
            visual_key = visual.get("visual_key")
        else:
            # Fallback for unexpected types
            logger.warning(f"Unexpected visual type: {type(visual)}, using defaults")
            description = "Visual description not available"
            visual_type = "unknown"
            visual_key = None
        
        chunk_text = f"{visual_type.capitalize()}: {description}"
        token_count = self._count_tokens(chunk_text)
        
        # Validate token count (warn if outside range, but still create chunk)
        if token_count < self.min_tokens:
            logger.warning(
                f"Visual chunk has {token_count} tokens (< {self.min_tokens}): "
                f"{chunk_text[:50]}..."
            )
        elif token_count > self.max_tokens:
            logger.warning(
                f"Visual chunk has {token_count} tokens (> {self.max_tokens}): "
                f"{chunk_text[:50]}..."
            )
        
        metadata = self._create_metadata(concept, "visual_description", subject=subject)
        metadata["visual_type"] = visual_type
        if visual_key:
            metadata["visual_key"] = visual_key
        
        return {
            "document_id": document_id,
            "concept_id": None,  # Will be set after concept creation
            "chunk_type": "visual_description",
            "chunk_text": chunk_text,
            "metadata": metadata
        }
    
    def chunk_document(
        self,
        document_id: str,
        markdown: str,
        concepts: Dict[str, Any],
        subject: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Generate all chunks for a document.
        
        Chunking Rules:
        - Each question = separate chunk
        - Each visual = separate chunk
        - Each conceptual explanation = separate chunk
        - Keep chunk size between 200-800 tokens
        - Preserve: document_id, section, question_id, concept_id (nullable initially)
        
        Args:
            document_id: Document UUID
            markdown: Full markdown content
            concepts: Concepts dictionary from workflow output
            subject: Optional subject name (from document level)
            
        Returns:
            List of chunk dictionaries
        """
        all_chunks = []
        concepts_list = concepts.get("concepts", [])
        
        for concept in concepts_list:
            # 1. Concept overview chunk (may be small, but keep for completeness)
            overview_chunk = self.create_concept_overview_chunk(document_id, concept, subject=subject)
            all_chunks.append(overview_chunk)
            
            # 2. Explanation chunks (from markdown)
            # Each conceptual explanation = separate chunk, 200-800 tokens
            explanation_chunks = self.create_explanation_chunks(
                document_id, concept, markdown, subject=subject
            )
            all_chunks.extend(explanation_chunks)
            
            # 3. Question chunks
            # Each question = separate chunk
            for question in concept.get("questions", []):
                question_chunk = self.create_question_chunk(document_id, concept, question, subject=subject)
                all_chunks.append(question_chunk)
            
            # 4. Visual description chunks
            # Each visual = separate chunk
            for visual in concept.get("associated_visuals", []):
                visual_chunk = self.create_visual_description_chunk(document_id, concept, visual, subject=subject)
                all_chunks.append(visual_chunk)
        
        # Validate all chunks meet token requirements
        valid_chunks = []
        for chunk in all_chunks:
            token_count = self._count_tokens(chunk.get("chunk_text", ""))
            if token_count >= self.min_tokens and token_count <= self.max_tokens:
                valid_chunks.append(chunk)
            else:
                logger.warning(
                    f"Chunk {chunk.get('chunk_type')} has {token_count} tokens "
                    f"(outside {self.min_tokens}-{self.max_tokens} range), "
                    f"but keeping it: {chunk.get('chunk_text', '')[:50]}..."
                )
                # Still keep it, but log warning
                valid_chunks.append(chunk)
        
        logger.info(
            f"Generated {len(valid_chunks)} chunks for document {document_id} "
            f"(target: {self.min_tokens}-{self.max_tokens} tokens per chunk)"
        )
        return valid_chunks
    
    def _extract_relevant_sections(
        self,
        markdown: str,
        concept_name: str,
        keywords: List[str]
    ) -> List[str]:
        """Extract sections relevant to a concept.
        
        Args:
            markdown: Full markdown text
            concept_name: Concept name (lowercase)
            keywords: List of keywords (lowercase)
            
        Returns:
            List of relevant section texts
        """
        # Simple approach: split by headers and filter by keyword presence
        # Split by markdown headers (# ## ###)
        sections = re.split(r'\n#{1,3}\s+', markdown)
        
        relevant_sections = []
        for section in sections:
            section_lower = section.lower()
            # Check if section mentions concept or keywords
            if concept_name in section_lower or any(kw in section_lower for kw in keywords):
                # Clean up section
                section = section.strip()
                if len(section) > 50:  # Minimum section length
                    relevant_sections.append(section)
        
        # If no relevant sections found, return the whole markdown
        if not relevant_sections:
            return [markdown]
        
        return relevant_sections
    
    def _split_text_by_tokens(
        self,
        text: str,
        target_tokens: int,
        max_tokens: int
    ) -> List[str]:
        """Split text into chunks based on token count.
        
        Args:
            text: Text to split
            target_tokens: Target tokens per chunk
            max_tokens: Maximum tokens per chunk
            
        Returns:
            List of text chunks
        """
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        # Split by sentences (simple approach)
        sentences = re.split(r'([.!?]\s+)', text)
        
        for i in range(0, len(sentences), 2):
            sentence = sentences[i]
            if i + 1 < len(sentences):
                sentence += sentences[i + 1]
            
            sentence_tokens = self._count_tokens(sentence)
            
            if current_tokens + sentence_tokens > max_tokens and current_chunk:
                # Save current chunk and start new one
                chunks.append("".join(current_chunk))
                current_chunk = [sentence]
                current_tokens = sentence_tokens
            else:
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
                
                # If we've reached target, consider splitting
                if current_tokens >= target_tokens:
                    chunks.append("".join(current_chunk))
                    current_chunk = []
                    current_tokens = 0
        
        # Add remaining chunk
        if current_chunk:
            chunks.append("".join(current_chunk))
        
        return chunks
