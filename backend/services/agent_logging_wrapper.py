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
    
    # Extract model name from agent
    model_name = getattr(agent, 'model', 'unknown')
    
    # Extract user prompt from input_data
    user_prompt = None
    if isinstance(input_data, list) and len(input_data) > 0:
        first_item = input_data[0]
        if isinstance(first_item, dict):
            content = first_item.get('content', [])
            if isinstance(content, list) and len(content) > 0:
                user_prompt = str(content[0].get('file_data', ''))[:1000] if isinstance(content[0], dict) else str(content[0])[:1000]
            else:
                user_prompt = str(first_item.get('content', ''))[:1000]
        else:
            user_prompt = str(input_data)[:1000]
    else:
        user_prompt = str(input_data)[:1000]
    
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
                except:
                    response_text = str(result.final_output)
            elif hasattr(result.final_output, 'model_dump'):
                response_text = str(result.final_output.model_dump())
            else:
                response_text = str(result.final_output)
        
        # Try to extract usage information if available
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
        
        if hasattr(result, 'usage'):
            usage = result.usage
            if hasattr(usage, 'prompt_tokens'):
                prompt_tokens = usage.prompt_tokens
            if hasattr(usage, 'completion_tokens'):
                completion_tokens = usage.completion_tokens
            if hasattr(usage, 'total_tokens'):
                total_tokens = usage.total_tokens
        
        # Log the call (if logging service is available)
        if logging_service:
            try:
                await logging_service.log_llm_call(
                    call_type="agent_sdk",
                    provider="openai",
                    model=model_name,
                    request_type="agent_run",
                    user_prompt=user_prompt,
                    response_text=response_text[:10000] if response_text else None,
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
