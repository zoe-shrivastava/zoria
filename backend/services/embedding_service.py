"""Embedding service using Ollama for local embedding generation."""

import logging
import os
import aiohttp
from typing import List, Dict, Any, Optional
import numpy as np
import asyncio

logger = logging.getLogger(__name__)


class EmbeddingService:
    """Local embedding generation service using Ollama."""
    
    def __init__(
        self,
        model_name: str = "mxbai-embed-large",
        ollama_base_url: Optional[str] = None
    ):
        """Initialize embedding service.
        
        Args:
            model_name: Ollama model name (default: mxbai-embed-large)
            ollama_base_url: Ollama API base URL
        """
        self.model_name = model_name
        self.ollama_base_url = (
            ollama_base_url or 
            os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
        ).rstrip('/')
        self.dimension = 1024  # mxbai-embed-large dimension
        logger.info(f"EmbeddingService initialized with model: {self.model_name} (dimension: {self.dimension})")
    
    def get_embedding_dimension(self) -> int:
        """Get embedding dimension.
        
        Returns:
            Dimension of embeddings
        """
        return self.dimension
    
    async def generate_embedding(self, text: str) -> np.ndarray:
        """Generate embedding for a single text (async).
        
        Args:
            text: Text to embed (will be truncated if too long)
            
        Returns:
            Embedding vector as numpy array
        """
        # Truncate text if it's too long for the embedding model
        # mxbai-embed-large has a context length limit (typically 512 tokens)
        # Using character count as approximation (1 token ≈ 3-4 characters, conservative)
        # Limit: 512 tokens ≈ 1200 characters (very conservative to avoid API errors)
        MAX_TEXT_LENGTH = 1200
        
        original_length = len(text)
        if original_length > MAX_TEXT_LENGTH:
            logger.warning(
                f"Text too long ({original_length} chars), truncating to {MAX_TEXT_LENGTH} chars for embedding"
            )
            # Truncate at word boundary if possible
            truncated = text[:MAX_TEXT_LENGTH]
            last_space = truncated.rfind(' ')
            if last_space > MAX_TEXT_LENGTH * 0.8:  # Only use word boundary if it's not too far back
                text = truncated[:last_space] + "..."
            else:
                text = truncated
        
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "model": self.model_name,
                    "prompt": text
                }
                
                async with session.post(
                    f"{self.ollama_base_url}/api/embeddings",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=60)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama embedding API error {response.status}: {error_text}")
                        raise RuntimeError(f"Ollama embedding API error {response.status}: {error_text}")
                    
                    data = await response.json()
                    embedding = data.get('embedding', [])
                    
                    if not embedding:
                        raise RuntimeError("Empty embedding returned from Ollama")
                    
                    return np.array(embedding, dtype=np.float32)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            raise
    
    async def generate_embeddings_batch(
        self,
        texts: List[str],
        batch_size: int = 10
    ) -> List[np.ndarray]:
        """Generate embeddings for multiple texts (optimized with batching).
        
        Args:
            texts: List of texts to embed
            batch_size: Number of texts to process in parallel
            
        Returns:
            List of embedding vectors
        """
        embeddings = []
        
        # Process in batches
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Generating embeddings for batch {i//batch_size + 1} ({len(batch)} texts)")
            
            # Process batch in parallel
            batch_embeddings = await asyncio.gather(
                *[self.generate_embedding(text) for text in batch],
                return_exceptions=True
            )
            
            # Handle any errors
            for j, emb in enumerate(batch_embeddings):
                if isinstance(emb, Exception):
                    logger.error(f"Failed to generate embedding for text {i+j}: {emb}")
                    # Use zero vector as fallback (or raise)
                    embeddings.append(np.zeros(self.dimension, dtype=np.float32))
                else:
                    embeddings.append(emb)
        
        logger.info(f"Generated {len(embeddings)} embeddings")
        return embeddings
    
    def prepare_text_for_embedding(
        self,
        chunk: Dict[str, Any]
    ) -> str:
        """Prepare chunk text with metadata for better semantic search.
        
        Args:
            chunk: Chunk dictionary with metadata
            
        Returns:
            Enhanced text for embedding (will be truncated if too long)
        """
        metadata = chunk.get("metadata", {})
        concept_name = metadata.get("concept_name", "")
        keywords = metadata.get("keywords", [])
        chunk_text = chunk.get("chunk_text", "")
        
        # Limit keyword list to avoid making text too long
        max_keywords = 5
        keywords_list = keywords[:max_keywords] if isinstance(keywords, list) else []
        
        # Combine for better retrieval, but prioritize chunk_text
        # Reserve space for chunk_text (most important)
        MAX_TOTAL_LENGTH = 1200
        prefix_max = 150  # Max length for concept/keywords prefix
        
        parts = []
        prefix_parts = []
        if concept_name:
            prefix_parts.append(f"Concept: {concept_name}")
        if keywords_list:
            keywords_str = ', '.join(keywords_list)
            if len(keywords_str) > 100:  # Truncate keywords if too long
                keywords_str = keywords_str[:100] + "..."
            prefix_parts.append(f"Keywords: {keywords_str}")
        
        prefix = ". ".join(prefix_parts)
        if len(prefix) > prefix_max:
            prefix = prefix[:prefix_max] + "..."
        
        # Calculate available space for chunk_text
        available_for_chunk = MAX_TOTAL_LENGTH - len(prefix) - 10  # 10 for separators
        
        # Truncate chunk_text if needed
        if len(chunk_text) > available_for_chunk:
            chunk_text = chunk_text[:available_for_chunk].rsplit(' ', 1)[0] + "..."  # Truncate at word boundary
        
        if prefix:
            parts.append(prefix)
        if chunk_text:
            parts.append(chunk_text)
        
        result = ". ".join(parts)
        
        # Final safety check
        if len(result) > MAX_TOTAL_LENGTH:
            result = result[:MAX_TOTAL_LENGTH].rsplit(' ', 1)[0] + "..."
        
        return result
    
    async def embed_chunks(
        self,
        chunks: List[Dict[str, Any]],
        batch_size: int = 10
    ) -> List[Dict[str, Any]]:
        """Generate embeddings for chunks and add to chunk dictionaries.
        
        Args:
            chunks: List of chunk dictionaries
            batch_size: Batch size for processing
            
        Returns:
            List of chunks with embeddings added
        """
        # Prepare texts for embedding
        texts = [self.prepare_text_for_embedding(chunk) for chunk in chunks]
        
        # Generate embeddings
        embeddings = await self.generate_embeddings_batch(texts, batch_size=batch_size)
        
        # Add embeddings to chunks
        for chunk, embedding in zip(chunks, embeddings):
            chunk["embedding"] = embedding.tolist()
        
        return chunks
