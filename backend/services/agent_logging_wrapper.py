"""Wrapper for Agent SDK calls to enable logging."""

import time
import logging
from typing import Dict, Any, Optional
from agents import Runner, Agent

from services.llm_logging_service import LLMLoggingService
from core.database import get_db

logger = logging.getLogger(__name__)


async def run_agent_with_logging(
    agent: Agent,
    input_data: Any,
    run_config: Optional[Any] = None,
    context_source: Optional[str] = None,
    document_id: Optional[str] = None,
    concept_id: Optional[str] = None,
    test_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Any:
    """Run an agent with logging.
    
    Args:
        agent: Agent instance
        input_data: Input data for the agent
        run_config: Run configuration
        context_source: Context identifier
        document_id: Related document ID
        concept_id: Related concept ID
        test_id: Related test ID
        metadata: Additional metadata
        
    Returns:
        Agent result
    """
    start_time = time.time()
    
    # Initialize logging service (may fail gracefully)
    logging_service = None
    try:
        db = get_db()
        # Check if database pool is available, and connect if needed
        if db.pool is None or db.pool.is_closing():
            logger.debug(f"Database pool not available for LLM logging, attempting to connect (document_id={document_id})")
            try:
                await db.connect()
                logging_service = LLMLoggingService(db)
                logger.debug(f"Successfully connected database pool for LLM logging (document_id={document_id})")
            except Exception as connect_error:
                logger.warning(f"Failed to connect database pool for LLM logging (document_id={document_id}): {connect_error}")
        else:
            logging_service = LLMLoggingService(db)
    except Exception as e:
        logger.warning(f"Failed to initialize LLM logging service for agent: {e}")
    
    # Extract model name and system prompt (instructions) from agent
    model_name = getattr(agent, 'model', 'unknown')
    system_prompt = getattr(agent, 'instructions', None)
    if system_prompt is not None:
        system_prompt = str(system_prompt)

    # Extract user prompt from input_data (support list of messages or single value)
    user_prompt = None
    if isinstance(input_data, list) and len(input_data) > 0:
        for item in input_data:
            if isinstance(item, dict) and item.get('role') == 'user':
                content = item.get('content', [])
                if isinstance(content, list):
                    parts = []
                    for c in content:
                        if isinstance(c, dict):
                            if 'text' in c:
                                parts.append(str(c['text']))
                            elif 'file_data' in c:
                                parts.append(str(c['file_data']))
                        else:
                            parts.append(str(c))
                    user_prompt = '\n'.join(parts) if parts else None
                else:
                    user_prompt = str(content) if content else None
                break
        if user_prompt is None:
            first_item = input_data[0]
            if isinstance(first_item, dict):
                content = first_item.get('content', [])
                if isinstance(content, list) and len(content) > 0:
                    c0 = content[0]
                    user_prompt = (c0.get('text') or str(c0.get('file_data', '')) or str(c0)) if isinstance(c0, dict) else str(c0)
                else:
                    user_prompt = str(first_item.get('content', ''))
            else:
                user_prompt = str(first_item)
    else:
        user_prompt = str(input_data) if input_data is not None else None

    try:
        result = await Runner.run(agent, input=input_data, run_config=run_config)

        # Extract information from result
        latency_ms = int((time.time() - start_time) * 1000)

        # Try to extract prompt/response from agent result
        response_text = None
        response_metadata = None

        if hasattr(result, 'final_output'):
            if hasattr(result.final_output, 'json'):
                try:
                    response_text = result.final_output.json()
                except Exception:
                    response_text = str(result.final_output)
            elif hasattr(result.final_output, 'model_dump'):
                response_text = str(result.final_output.model_dump())
            else:
                response_text = str(result.final_output)

        # Extract usage: Agents SDK uses context_wrapper.usage with input_tokens/output_tokens
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        usage_obj = None
        if hasattr(result, 'context_wrapper') and result.context_wrapper is not None and hasattr(result.context_wrapper, 'usage'):
            usage_obj = result.context_wrapper.usage
        elif hasattr(result, 'usage'):
            usage_obj = result.usage
        if usage_obj is not None:
            if hasattr(usage_obj, 'input_tokens'):
                prompt_tokens = getattr(usage_obj, 'input_tokens', None)
            if prompt_tokens is None and hasattr(usage_obj, 'prompt_tokens'):
                prompt_tokens = getattr(usage_obj, 'prompt_tokens', None)
            if hasattr(usage_obj, 'output_tokens'):
                completion_tokens = getattr(usage_obj, 'output_tokens', None)
            if completion_tokens is None and hasattr(usage_obj, 'completion_tokens'):
                completion_tokens = getattr(usage_obj, 'completion_tokens', None)
            if hasattr(usage_obj, 'total_tokens'):
                total_tokens = getattr(usage_obj, 'total_tokens', None)
            if total_tokens is None and prompt_tokens is not None and completion_tokens is not None:
                total_tokens = prompt_tokens + completion_tokens

        # Log the call (if logging service is available)
        if logging_service:
            try:
                await logging_service.log_llm_call(
                    call_type="agent_sdk",
                    provider="openai",
                    model=model_name,
                    request_type="agent_run",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_text=response_text,
                    response_metadata=response_metadata,
                    success=True,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    latency_ms=latency_ms,
                    context_source=context_source,
                    document_id=document_id,
                    concept_id=concept_id,
                    test_id=test_id,
                    metadata=metadata
                )
                logger.debug(f"Logged agent call: model={model_name}, document_id={document_id}, context_source={context_source}")
            except Exception as e:
                logger.error(f"Failed to log agent call: {e}", exc_info=True)
        
        return result
        
    except Exception as e:
        latency_ms = int((time.time() - start_time) * 1000)
        if logging_service:
            try:
                await logging_service.log_llm_call(
                    call_type="agent_sdk",
                    provider="openai",
                    model=model_name,
                    request_type="agent_run",
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    success=False,
                    error_message=str(e),
                    latency_ms=latency_ms,
                    context_source=context_source,
                    document_id=document_id,
                    concept_id=concept_id,
                    test_id=test_id,
                    metadata=metadata
                )
            except Exception as log_error:
                logger.error(f"Failed to log agent error: {log_error}", exc_info=True)
        raise
