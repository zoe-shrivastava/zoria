"""LLM service for text generation using either Ollama (local) or OpenAI."""

import logging
import os
import aiohttp
import json
import time
from typing import Dict, Any, Optional, List

from openai import AsyncOpenAI

logger = logging.getLogger(__name__)


class LLMService:
    """Service for LLM text generation.
    
    - If model_name starts with 'gpt-', uses OpenAI Chat Completions.
    - Otherwise, defaults to local Ollama HTTP API.
    """
    
    def __init__(
        self,
        model_name: str = "llama3.2:3b-instruct-fp16",
        ollama_base_url: Optional[str] = None,
        openai_client: Optional[AsyncOpenAI] = None,
        enable_logging: bool = True,
        context_source: Optional[str] = None,
        db: Optional[Any] = None,
    ):
        """Initialize LLM service.
        
        Args:
            model_name: Model name. 'gpt-*' will use OpenAI, others use Ollama.
            ollama_base_url: Ollama API base URL (for local models)
            openai_client: Optional pre-configured OpenAI async client
            enable_logging: Whether to log LLM calls
            context_source: Context identifier for logging (e.g., 'question_generation')
            db: Database instance for logging (optional, will try to get from core.database if not provided)
        """
        self.model_name = model_name
        self.use_openai = model_name.startswith("gpt-")
        self.enable_logging = enable_logging
        self.context_source = context_source
        
        if self.use_openai:
            self.openai_client = openai_client or AsyncOpenAI()
            self.provider = "openai"
            logger.info(f"LLMService initialized with OpenAI model: {self.model_name}")
            self.ollama_base_url = None
        else:
            self.provider = "ollama"
            self.ollama_base_url = (
                ollama_base_url or 
                os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
            ).rstrip('/')
            self.openai_client = None
            logger.info(f"LLMService initialized with Ollama model: {self.model_name}")
        
        # Initialize logging service if enabled
        self.logging_service = None
        if self.enable_logging:
            try:
                if db:
                    from services.llm_logging_service import LLMLoggingService
                    self.logging_service = LLMLoggingService(db)
                else:
                    from core.database import get_db
                    from services.llm_logging_service import LLMLoggingService
                    self.logging_service = LLMLoggingService(get_db())
            except Exception as e:
                logger.warning(f"Failed to initialize LLM logging service: {e}")
    
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
        top_p: Optional[float] = None,
        repeat_penalty: Optional[float] = None,
        document_id: Optional[str] = None,
        concept_id: Optional[str] = None,
        test_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate text using either OpenAI or Ollama.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            format: Response format ('json' for JSON output, Ollama only)
            top_p: Top-p sampling (Ollama only; e.g. 0.8 for stable study guides)
            repeat_penalty: Repeat penalty (Ollama only; e.g. 1.1)
            document_id: Related document ID for logging
            concept_id: Related concept ID for logging
            test_id: Related test ID for logging
            metadata: Additional metadata for logging
            
        Returns:
            Dictionary with 'text' and 'metadata' keys
        """
        start_time = time.time()
        error_message = None
        success = True
        
        # OpenAI path
        if self.use_openai:
            try:
                messages: List[Dict[str, str]] = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})
                
                client = self.openai_client

                # Log full prompts for debugging
                logger.info("OpenAI LLM prompt:\n%s", prompt if prompt else "<empty>")
                if system_prompt:
                    logger.info("OpenAI LLM system prompt:\n%s", system_prompt)

                kwargs: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": messages,
                }
                # Some models (e.g. gpt-5-nano) only support default temperature=1.
                # Only pass temperature when it's not None and model supports it.
                if temperature is not None and not self.model_name.startswith("gpt-5-"):
                    kwargs["temperature"] = temperature
                # Some newer models (like gpt-5-nano) use max_completion_tokens instead of max_tokens
                if max_tokens is not None:
                    kwargs["max_completion_tokens"] = max_tokens
                # Add response_format for JSON mode (OpenAI API)
                if format == "json":
                    kwargs["response_format"] = {"type": "json_object"}

                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                
                # Log choice details for debugging
                finish_reason = getattr(choice, 'finish_reason', 'unknown')
                logger.info(f"LLM response finish_reason: {finish_reason}")
                
                # Check finish_reason for issues
                if finish_reason == "length":
                    logger.warning("Response was truncated due to max_tokens limit")
                elif finish_reason == "content_filter":
                    logger.error("Response was filtered by content safety filters")
                elif finish_reason == "stop":
                    logger.debug("Response completed normally")
                else:
                    logger.warning(f"Unexpected finish_reason: {finish_reason}")
                
                logger.debug(f"Choice message type: {type(choice.message)}")
                logger.debug(f"Choice message attributes: {dir(choice.message)}")
                
                # GPT-5 Nano sometimes returns choice.text instead of choice.message.content
                content = getattr(choice.message, "content", None) or getattr(choice, "text", "")
                content = (content or "").strip()
                
                # Try alternative ways to get content
                if not content:
                    # Check if there's a delta (streaming response)
                    if hasattr(choice, 'delta') and choice.delta:
                        content = getattr(choice.delta, "content", None) or ""
                        content = (content or "").strip()
                    
                    # Check if content is in a different attribute
                    if not content and hasattr(choice.message, '__dict__'):
                        msg_dict = choice.message.__dict__
                        logger.debug(f"Message dict keys: {list(msg_dict.keys())}")
                        for key in ['text', 'text_content', 'response', 'output']:
                            if key in msg_dict:
                                content = str(msg_dict[key]).strip()
                                if content:
                                    logger.info(f"Found content in message.{key}")
                                    break
                
                if not content:
                    finish_reason = getattr(choice, 'finish_reason', 'unknown')
                    usage_info = resp.usage.model_dump() if resp.usage else {}
                    
                    logger.error("Received empty response from GPT-5 Nano / OpenAI LLM")
                    logger.error(f"Finish reason: {finish_reason}")
                    logger.error(f"Usage: {usage_info}")
                    logger.error(f"Model: {resp.model}")
                    logger.error(f"Max tokens requested: {max_tokens}")
                    
                    # Provide specific guidance based on finish_reason
                    if finish_reason == "length":
                        logger.error("Response was truncated - consider increasing max_tokens")
                    elif finish_reason == "content_filter":
                        logger.error("Response was filtered - check prompt for content policy violations")
                    elif finish_reason == "stop":
                        logger.error("Response stopped normally but content is empty - possible model issue")
                    
                    # Log full response structure for debugging
                    try:
                        logger.error(f"Full response structure: {resp.model_dump()}")
                    except:
                        logger.error(f"Response object: {resp}")
                    
                    # Don't raise here - let it continue and fail in JSON parsing with better error

                # Log raw content from OpenAI (truncated) to debug JSON issues
                logger.info(
                    "OpenAI LLM raw content (first 500 chars): %s",
                    content[:500] if content else "<empty>"
                )
                
                if not content:
                    logger.error("Cannot proceed with empty content - this will cause JSON parsing to fail")

                metadata_dict = {
                    "model": resp.model,
                    "usage": resp.usage.model_dump() if resp.usage else None,
                }
                
                # Log the call
                if self.logging_service:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self.logging_service.log_llm_call(
                        call_type="llm_service",
                        provider=self.provider,
                        model=self.model_name,
                        request_type="generate",
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        other_params={"format": format},
                        response_text=content,
                        response_metadata=metadata_dict,
                        success=success,
                        error_message=error_message,
                        prompt_tokens=resp.usage.prompt_tokens if resp.usage else None,
                        completion_tokens=resp.usage.completion_tokens if resp.usage else None,
                        total_tokens=resp.usage.total_tokens if resp.usage else None,
                        latency_ms=latency_ms,
                        context_source=self.context_source,
                        document_id=document_id,
                        concept_id=concept_id,
                        test_id=test_id,
                        metadata=metadata
                    )
                
                return {"text": content, "metadata": metadata_dict}
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Error generating text via OpenAI: {e}")
                
                # Log error
                if self.logging_service:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self.logging_service.log_llm_call(
                        call_type="llm_service",
                        provider=self.provider,
                        model=self.model_name,
                        request_type="generate",
                        system_prompt=system_prompt,
                        user_prompt=prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        success=False,
                        error_message=error_message,
                        latency_ms=latency_ms,
                        context_source=self.context_source,
                        document_id=document_id,
                        concept_id=concept_id,
                        test_id=test_id,
                        metadata=metadata
                    )
                
                raise
        
        # Ollama path
        try:
            async with aiohttp.ClientSession() as session:
                options: Dict[str, Any] = {"temperature": temperature}
                if top_p is not None:
                    options["top_p"] = top_p
                if repeat_penalty is not None:
                    options["repeat_penalty"] = repeat_penalty
                payload = {
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": options
                }
                
                if system_prompt:
                    payload["system"] = system_prompt
                
                if max_tokens:
                    payload["options"]["num_predict"] = max_tokens
                
                if format:
                    payload["format"] = format
                
                async with session.post(
                    f"{self.ollama_base_url}/api/generate",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama generate API error {response.status}: {error_text}")
                        raise RuntimeError(f"Ollama API error {response.status}: {error_text}")
                    
                    data = await response.json()
                    response_text = data.get('response', '').strip()
                    
                    metadata = {
                        'model': data.get('model', self.model_name),
                        'done': data.get('done', True),
                        'total_duration': data.get('total_duration', 0),
                        'prompt_eval_count': data.get('prompt_eval_count', 0),
                        'eval_count': data.get('eval_count', 0)
                    }
                    
                    # Log Ollama call
                    if self.logging_service:
                        latency_ms = int((time.time() - start_time) * 1000)
                        await self.logging_service.log_llm_call(
                            call_type="llm_service",
                            provider=self.provider,
                            model=self.model_name,
                            request_type="generate",
                            system_prompt=system_prompt,
                            user_prompt=prompt,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            other_params={"format": format},
                            response_text=response_text,
                            response_metadata=metadata,
                            success=True,
                            prompt_tokens=data.get('prompt_eval_count'),
                            completion_tokens=data.get('eval_count'),
                            total_tokens=(data.get('prompt_eval_count', 0) + data.get('eval_count', 0)),
                            latency_ms=latency_ms,
                            context_source=self.context_source,
                            document_id=document_id,
                            concept_id=concept_id,
                            test_id=test_id,
                            metadata=metadata
                        )
                    
                    return {
                        'text': response_text,
                        'metadata': metadata
                    }
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Error generating text via LLM (Ollama): {e}")
            
            # Log error
            if self.logging_service:
                latency_ms = int((time.time() - start_time) * 1000)
                await self.logging_service.log_llm_call(
                    call_type="llm_service",
                    provider=self.provider,
                    model=self.model_name,
                    request_type="generate",
                    system_prompt=system_prompt,
                    user_prompt=prompt,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    success=False,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    context_source=self.context_source,
                    document_id=document_id,
                    concept_id=concept_id,
                    test_id=test_id,
                    metadata=metadata
                )
            
            raise
    
    async def chat(
        self,
        messages: List[Dict[str, str]],
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        format: Optional[str] = None,
        document_id: Optional[str] = None,
        concept_id: Optional[str] = None,
        test_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate text using chat-style API (OpenAI or Ollama)."""
        start_time = time.time()
        error_message = None
        success = True
        
        # OpenAI path
        if self.use_openai:
            try:
                client = self.openai_client
                openai_messages: List[Dict[str, str]] = []
                if system_prompt:
                    openai_messages.append({"role": "system", "content": system_prompt})
                # Append passed messages (user/assistant/system)
                for msg in messages:
                    role = msg.get("role", "user")
                    content = msg.get("content", "")
                    openai_messages.append({"role": role, "content": content})
                
                kwargs: Dict[str, Any] = {
                    "model": self.model_name,
                    "messages": openai_messages,
                }
                if temperature is not None and not self.model_name.startswith("gpt-5-"):
                    kwargs["temperature"] = temperature
                if max_tokens is not None:
                    kwargs["max_completion_tokens"] = max_tokens

                resp = await client.chat.completions.create(**kwargs)
                choice = resp.choices[0]
                content = (choice.message.content or "").strip()
                metadata_dict = {
                    "model": resp.model,
                    "usage": resp.usage.model_dump() if resp.usage else None,
                }
                
                # Log the call
                if self.logging_service:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self.logging_service.log_llm_call(
                        call_type="llm_service",
                        provider=self.provider,
                        model=self.model_name,
                        request_type="chat",
                        system_prompt=system_prompt,
                        messages=openai_messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        other_params={"format": format},
                        response_text=content,
                        response_metadata=metadata_dict,
                        success=success,
                        error_message=error_message,
                        prompt_tokens=resp.usage.prompt_tokens if resp.usage else None,
                        completion_tokens=resp.usage.completion_tokens if resp.usage else None,
                        total_tokens=resp.usage.total_tokens if resp.usage else None,
                        latency_ms=latency_ms,
                        context_source=self.context_source,
                        document_id=document_id,
                        concept_id=concept_id,
                        test_id=test_id,
                        metadata=metadata
                    )
                
                return {"text": content, "metadata": metadata_dict}
            except Exception as e:
                success = False
                error_message = str(e)
                logger.error(f"Error generating text via OpenAI chat: {e}")
                
                # Log error
                if self.logging_service:
                    latency_ms = int((time.time() - start_time) * 1000)
                    await self.logging_service.log_llm_call(
                        call_type="llm_service",
                        provider=self.provider,
                        model=self.model_name,
                        request_type="chat",
                        system_prompt=system_prompt,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        success=False,
                        error_message=error_message,
                        latency_ms=latency_ms,
                        context_source=self.context_source,
                        document_id=document_id,
                        concept_id=concept_id,
                        test_id=test_id,
                        metadata=metadata
                    )
                
                raise

        # Ollama path
        try:
            async with aiohttp.ClientSession() as session:
                # Prepare messages for Ollama
                ollama_messages = []
                
                if system_prompt:
                    ollama_messages.append({"role": "system", "content": system_prompt})
                
                for msg in messages:
                    role = msg.get('role', 'user')
                    content = msg.get('content', '')
                    if role in ['system', 'user', 'assistant']:
                        ollama_messages.append({"role": role, "content": content})
                
                payload = {
                    "model": self.model_name,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": temperature
                    }
                }
                
                if max_tokens:
                    payload["options"]["num_predict"] = max_tokens
                
                if format:
                    payload["format"] = format
                
                async with session.post(
                    f"{self.ollama_base_url}/api/chat",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=120)
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"Ollama chat API error {response.status}: {error_text}")
                        raise RuntimeError(f"Ollama API error {response.status}: {error_text}")
                    
                    data = await response.json()
                    message = data.get('message', {})
                    response_text = message.get('content', '').strip()
                    
                    metadata = {
                        'model': data.get('model', self.model_name),
                        'done': data.get('done', True),
                        'total_duration': data.get('total_duration', 0),
                        'prompt_eval_count': data.get('prompt_eval_count', 0),
                        'eval_count': data.get('eval_count', 0)
                    }
                    
                    # Log Ollama call
                    if self.logging_service:
                        latency_ms = int((time.time() - start_time) * 1000)
                        await self.logging_service.log_llm_call(
                            call_type="llm_service",
                            provider=self.provider,
                            model=self.model_name,
                            request_type="chat",
                            system_prompt=system_prompt,
                            messages=ollama_messages,
                            temperature=temperature,
                            max_tokens=max_tokens,
                            other_params={"format": format},
                            response_text=response_text,
                            response_metadata=metadata,
                            success=True,
                            prompt_tokens=data.get('prompt_eval_count'),
                            completion_tokens=data.get('eval_count'),
                            total_tokens=(data.get('prompt_eval_count', 0) + data.get('eval_count', 0)),
                            latency_ms=latency_ms,
                            context_source=self.context_source,
                            document_id=document_id,
                            concept_id=concept_id,
                            test_id=test_id,
                            metadata=metadata
                        )
                    
                    return {
                        'text': response_text,
                        'metadata': metadata
                    }
        except Exception as e:
            success = False
            error_message = str(e)
            logger.error(f"Error generating text via LLM chat (Ollama): {e}")
            
            # Log error
            if self.logging_service:
                latency_ms = int((time.time() - start_time) * 1000)
                await self.logging_service.log_llm_call(
                    call_type="llm_service",
                    provider=self.provider,
                    model=self.model_name,
                    request_type="chat",
                    system_prompt=system_prompt,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    success=False,
                    error_message=error_message,
                    latency_ms=latency_ms,
                    context_source=self.context_source,
                    document_id=document_id,
                    concept_id=concept_id,
                    test_id=test_id,
                    metadata=metadata
                )
            
            raise
    
    async def generate_json(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        document_id: Optional[str] = None,
        concept_id: Optional[str] = None,
        test_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Generate JSON response using the underlying LLM.
        
        This uses the generic generate() method (OpenAI or Ollama) and
        then attempts to parse the returned text as JSON. The prompt
        should explicitly instruct the model to return strict JSON.
        
        Args:
            prompt: User prompt
            system_prompt: Optional system prompt
            temperature: Temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            document_id: Related document ID for logging
            concept_id: Related concept ID for logging
            test_id: Related test ID for logging
            metadata: Additional metadata for logging
        
        Returns:
            Parsed JSON dictionary
        """
        response = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            format="json",
            document_id=document_id,
            concept_id=concept_id,
            test_id=test_id,
            metadata=metadata
        )
        
        response_text = response.get('text', '')
        
        # Check for empty response
        if not response_text or not response_text.strip():
            error_msg = "LLM returned empty response. This may indicate:"
            error_msg += "\n1. The model hit a safety filter"
            error_msg += "\n2. The response was truncated due to max_tokens"
            error_msg += "\n3. The model encountered an error"
            error_msg += f"\nResponse metadata: {response.get('metadata', {})}"
            logger.error(error_msg)
            raise ValueError("LLM returned empty response. Check logs for details.")
        
        # Log raw response at INFO level for debugging
        logger.info(f"Raw LLM response text length: {len(response_text)} characters")
        logger.info(f"Raw LLM response (first 2000 chars):\n{response_text[:2000]}")
        if len(response_text) > 2000:
            logger.info(f"Raw LLM response (last 1000 chars):\n{response_text[-1000:]}")
        
        # Also log full response if it's not too long (under 10K chars)
        if len(response_text) <= 10000:
            logger.info(f"Full raw LLM response:\n{response_text}")
        else:
            logger.info(f"Raw LLM response (middle section, chars 2000-4000):\n{response_text[2000:4000]}")
        
        # Clean response (remove markdown code blocks if present)
        original_response_text = response_text
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            json_lines = []
            in_json = False
            for line in lines:
                if line.strip().startswith('```'):
                    if not in_json:
                        in_json = True
                    else:
                        break
                elif in_json:
                    json_lines.append(line)
            response_text = '\n'.join(json_lines)
            logger.info(f"Cleaned response text (removed markdown): {len(response_text)} chars (was {len(original_response_text)})")
            if len(response_text) != len(original_response_text):
                logger.info(f"Cleaned response text (first 2000 chars):\n{response_text[:2000]}")
        
        try:
            parsed = json.loads(response_text)
            logger.info(f"Successfully parsed JSON response. Keys: {list(parsed.keys()) if isinstance(parsed, dict) else 'not a dict'}")
            
            # Check if response might be truncated (common when hitting max_tokens)
            if isinstance(parsed, dict) and "questions" in parsed:
                questions = parsed.get("questions", [])
                if len(questions) > 0:
                    # Check if last question looks incomplete
                    last_q = questions[-1]
                    last_q_str = json.dumps(last_q)
                    # If response ends abruptly, it might be truncated
                    if not response_text.rstrip().endswith("}") and not response_text.rstrip().endswith("]"):
                        logger.warning(f"Response may be truncated - doesn't end with proper JSON closing")
            return parsed
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.error(f"JSON error at position {e.pos}: {e.msg}")
            logger.error(f"Response text length: {len(response_text)}")
            logger.error(f"Response text (first 1000 chars): {response_text[:1000]}")
            logger.error(f"Response text (last 500 chars): {response_text[-500:]}")
            # Try to extract partial JSON if possible
            if e.pos and e.pos > 0:
                try:
                    # Try to find the last complete question
                    partial_text = response_text[:e.pos]
                    # Try to extract what we can
                    if '"questions"' in partial_text:
                        logger.warning("Attempting to extract partial questions from truncated response")
                        # Find the questions array start
                        q_start = partial_text.find('"questions"')
                        if q_start > 0:
                            # Try to find array start
                            array_start = partial_text.find('[', q_start)
                            if array_start > 0:
                                # Count open brackets to find where we can safely cut
                                open_count = 0
                                safe_end = array_start
                                for i in range(array_start, len(partial_text)):
                                    if partial_text[i] == '[':
                                        open_count += 1
                                    elif partial_text[i] == ']':
                                        open_count -= 1
                                        if open_count == 0:
                                            safe_end = i + 1
                                            break
                                if safe_end > array_start:
                                    try:
                                        partial_json = json.loads(partial_text[:safe_end] + ']}')
                                        logger.warning(f"Extracted {len(partial_json.get('questions', []))} questions from truncated response")
                                        return partial_json
                                    except:
                                        pass
                except Exception as extract_error:
                    logger.error(f"Failed to extract partial JSON: {extract_error}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
