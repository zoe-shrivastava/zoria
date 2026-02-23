"""LLM logging service for tracking all LLM calls, requests, responses, and costs."""

import logging
import json
from typing import Dict, Any, Optional, List
from datetime import datetime
from decimal import Decimal

from core.database import Database

logger = logging.getLogger(__name__)


# OpenAI Pricing per 1M tokens (from user specification)
OPENAI_PRICING = {
    "gpt-5.2": {
        "input": Decimal("1.75"),
        "cached_input": Decimal("0.175"),
        "output": Decimal("14.00")
    },
    "gpt-5.1": {
        "input": Decimal("1.25"),
        "cached_input": Decimal("0.125"),
        "output": Decimal("10.00")
    },
    "gpt-5": {
        "input": Decimal("1.25"),
        "cached_input": Decimal("0.125"),
        "output": Decimal("10.00")
    },
    "gpt-5-mini": {
        "input": Decimal("0.25"),
        "cached_input": Decimal("0.025"),
        "output": Decimal("2.00")
    },
    "gpt-5-nano": {
        "input": Decimal("0.05"),
        "cached_input": Decimal("0.005"),
        "output": Decimal("0.40")
    }
}


class LLMLoggingService:
    """Service for logging LLM calls with cost tracking."""
    
    def __init__(self, db: Database):
        """Initialize LLM logging service.
        
        Args:
            db: Database instance
        """
        self.db = db
    
    def get_model_pricing(self, model_name: str) -> Optional[Dict[str, Decimal]]:
        """Get pricing for a model.
        
        Args:
            model_name: Model name (e.g., 'gpt-5-nano')
            
        Returns:
            Pricing dict with 'input', 'cached_input', 'output' or None if not found
        """
        # Direct match
        if model_name in OPENAI_PRICING:
            return OPENAI_PRICING[model_name]
        
        # Try to match model variants (e.g., 'gpt-5-nano-1234' -> 'gpt-5-nano')
        for base_model, pricing in OPENAI_PRICING.items():
            if model_name.startswith(base_model):
                return pricing
        
        logger.warning(f"No pricing found for model: {model_name}")
        return None
    
    def calculate_cost(
        self,
        model_name: str,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0
    ) -> Dict[str, Decimal]:
        """Calculate cost for an LLM call.
        
        Args:
            model_name: Model name
            prompt_tokens: Number of input tokens
            completion_tokens: Number of output tokens
            cached_tokens: Number of cached input tokens (default 0)
            
        Returns:
            Dict with 'input_cost', 'cached_input_cost', 'output_cost', 'total_cost'
        """
        pricing = self.get_model_pricing(model_name)
        if not pricing:
            return {
                "input_cost": Decimal("0"),
                "cached_input_cost": Decimal("0"),
                "output_cost": Decimal("0"),
                "total_cost": Decimal("0")
            }
        
        # Calculate costs (pricing is per 1M tokens)
        input_tokens = prompt_tokens - cached_tokens
        input_cost = (Decimal(input_tokens) / Decimal("1000000")) * pricing["input"]
        cached_input_cost = (Decimal(cached_tokens) / Decimal("1000000")) * pricing["cached_input"]
        output_cost = (Decimal(completion_tokens) / Decimal("1000000")) * pricing["output"]
        total_cost = input_cost + cached_input_cost + output_cost
        
        return {
            "input_cost": input_cost,
            "cached_input_cost": cached_input_cost,
            "output_cost": output_cost,
            "total_cost": total_cost
        }
    
    async def log_llm_call(
        self,
        call_type: str,
        provider: str,
        model: str,
        request_type: str,
        system_prompt: Optional[str] = None,
        user_prompt: Optional[str] = None,
        messages: Optional[List[Dict[str, Any]]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        other_params: Optional[Dict[str, Any]] = None,
        response_text: Optional[str] = None,
        response_metadata: Optional[Dict[str, Any]] = None,
        success: bool = True,
        error_message: Optional[str] = None,
        prompt_tokens: Optional[int] = None,
        completion_tokens: Optional[int] = None,
        total_tokens: Optional[int] = None,
        cached_tokens: int = 0,
        latency_ms: Optional[int] = None,
        context_source: Optional[str] = None,
        document_id: Optional[str] = None,
        concept_id: Optional[str] = None,
        test_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[str]:
        """Log an LLM call to the database.
        
        Args:
            call_type: Type of call ('llm_service', 'agent_sdk', 'workflow')
            provider: Provider ('openai', 'ollama')
            model: Model name
            request_type: Request type ('generate', 'chat', 'generate_json', 'agent_run')
            system_prompt: Full system prompt
            user_prompt: Full user prompt
            messages: Conversation messages
            temperature: Temperature parameter
            max_tokens: Max tokens parameter
            other_params: Other parameters
            response_text: Full response text
            response_metadata: Full response metadata
            success: Whether call succeeded
            error_message: Error message if failed
            prompt_tokens: Input tokens
            completion_tokens: Output tokens
            total_tokens: Total tokens
            cached_tokens: Cached input tokens
            latency_ms: Latency in milliseconds
            context_source: Context source identifier
            document_id: Related document ID
            concept_id: Related concept ID
            test_id: Related test ID
            metadata: Additional metadata
            
        Returns:
            Log entry ID or None if logging failed
        """
        try:
            # Store full content (DB columns are TEXT; no truncation)
            # Extract token usage from metadata if not provided
            if not prompt_tokens and response_metadata:
                usage = response_metadata.get("usage") or response_metadata
                if isinstance(usage, dict):
                    prompt_tokens = usage.get("prompt_tokens") or usage.get("prompt_eval_count")
                    completion_tokens = usage.get("completion_tokens") or usage.get("eval_count")
                    total_tokens = usage.get("total_tokens") or (prompt_tokens + completion_tokens if prompt_tokens and completion_tokens else None)
            
            # Calculate costs (only for OpenAI)
            costs = {
                "input_cost": Decimal("0"),
                "cached_input_cost": Decimal("0"),
                "output_cost": Decimal("0"),
                "total_cost": Decimal("0")
            }
            
            if provider == "openai" and prompt_tokens and completion_tokens:
                costs = self.calculate_cost(
                    model,
                    prompt_tokens or 0,
                    completion_tokens or 0,
                    cached_tokens
                )
            
            # Prepare JSONB fields
            messages_json = json.dumps(messages) if messages else None
            other_params_json = json.dumps(other_params) if other_params else None
            response_metadata_json = json.dumps(response_metadata) if response_metadata else None
            metadata_json = json.dumps(metadata) if metadata else None
            
            # Insert into database
            # Check if database pool is available before inserting
            if self.db.pool is None or self.db.pool.is_closing():
                logger.warning(
                    f"Cannot log LLM call: database pool unavailable "
                    f"(call_type={call_type}, document_id={document_id}, context_source={context_source})"
                )
                return None
            
            log_id = await self.db.fetchval(
                """
                INSERT INTO llm_logs (
                    call_type, provider, model,
                    request_type,
                    system_prompt, user_prompt, messages,
                    temperature, max_tokens, other_params,
                    response_text, response_metadata,
                    success, error_message,
                    prompt_tokens, completion_tokens, total_tokens, cached_tokens,
                    input_cost_usd, cached_input_cost_usd, output_cost_usd, total_cost_usd,
                    latency_ms,
                    context_source, document_id, concept_id, test_id, metadata
                ) VALUES (
                    $1, $2, $3,
                    $4,
                    $5, $6, $7,
                    $8, $9, $10,
                    $11, $12,
                    $13, $14,
                    $15, $16, $17, $18,
                    $19, $20, $21, $22,
                    $23,
                    $24, $25, $26, $27, $28
                ) RETURNING id
                """,
                call_type, provider, model,
                request_type,
                system_prompt, user_prompt, messages_json,
                temperature, max_tokens, other_params_json,
                response_text, response_metadata_json,
                success, error_message,
                prompt_tokens, completion_tokens, total_tokens, cached_tokens,
                float(costs["input_cost"]), float(costs["cached_input_cost"]), 
                float(costs["output_cost"]), float(costs["total_cost"]),
                latency_ms,
                context_source, document_id, concept_id, test_id, metadata_json
            )
            
            logger.info(
                f"Logged LLM call: {call_type}/{request_type} - model={model}, "
                f"tokens={total_tokens or 'N/A'}, cost=${costs['total_cost']:.8f}"
            )
            
            return str(log_id) if log_id else None
            
        except Exception as e:
            logger.error(f"Failed to log LLM call: {e}", exc_info=True)
            # Don't raise - logging should not break the application
            return None
    
    async def get_usage_stats(
        self,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model: Optional[str] = None,
        call_type: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get usage statistics.
        
        Args:
            start_date: Start date filter
            end_date: End date filter
            model: Model filter
            call_type: Call type filter
            
        Returns:
            Dictionary with usage statistics
        """
        conditions = []
        params = []
        param_index = 1
        
        if start_date:
            conditions.append(f"created_at >= ${param_index}")
            params.append(start_date)
            param_index += 1
        
        if end_date:
            conditions.append(f"created_at <= ${param_index}")
            params.append(end_date)
            param_index += 1
        
        if model:
            conditions.append(f"model = ${param_index}")
            params.append(model)
            param_index += 1
        
        if call_type:
            conditions.append(f"call_type = ${param_index}")
            params.append(call_type)
            param_index += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        stats = await self.db.fetchrow(
            f"""
            SELECT 
                COUNT(*) as total_calls,
                SUM(prompt_tokens) as total_prompt_tokens,
                SUM(completion_tokens) as total_completion_tokens,
                SUM(total_tokens) as total_tokens,
                SUM(total_cost_usd) as total_cost_usd,
                AVG(latency_ms) as avg_latency_ms
            FROM llm_logs
            {where_clause}
            """,
            *params
        )
        
        return dict(stats) if stats else {}
    
    async def get_logs(
        self,
        limit: int = 100,
        offset: int = 0,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        model: Optional[str] = None,
        call_type: Optional[str] = None,
        provider: Optional[str] = None,
        success: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Get LLM logs with filtering and pagination.
        
        Args:
            limit: Maximum number of logs to return
            offset: Number of logs to skip
            start_date: Start date filter
            end_date: End date filter
            model: Model filter
            call_type: Call type filter
            provider: Provider filter
            success: Success status filter
            
        Returns:
            Dictionary with 'logs' list and 'total' count
        """
        conditions = []
        params = []
        param_index = 1
        
        if start_date:
            conditions.append(f"created_at >= ${param_index}")
            params.append(start_date)
            param_index += 1
        
        if end_date:
            conditions.append(f"created_at <= ${param_index}")
            params.append(end_date)
            param_index += 1
        
        if model:
            conditions.append(f"model = ${param_index}")
            params.append(model)
            param_index += 1
        
        if call_type:
            conditions.append(f"call_type = ${param_index}")
            params.append(call_type)
            param_index += 1
        
        if provider:
            conditions.append(f"provider = ${param_index}")
            params.append(provider)
            param_index += 1
        
        if success is not None:
            conditions.append(f"success = ${param_index}")
            params.append(success)
            param_index += 1
        
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        
        # Get total count
        total = await self.db.fetchval(
            f"SELECT COUNT(*) FROM llm_logs {where_clause}",
            *params
        )
        
        # Get logs
        limit_param = param_index
        offset_param = param_index + 1
        params_with_pagination = list(params) + [limit, offset]
        
        logs = await self.db.fetch(
            f"""
            SELECT * FROM llm_logs
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ${limit_param} OFFSET ${offset_param}
            """,
            *params_with_pagination
        )
        
        # Parse JSONB fields and convert to dict
        parsed_logs = []
        for log in logs:
            log_dict = dict(log)
            
            # Convert UUID fields to strings
            uuid_fields = ['id', 'document_id', 'concept_id', 'test_id']
            for field in uuid_fields:
                if log_dict.get(field) is not None:
                    log_dict[field] = str(log_dict[field])
            
            # Parse JSONB fields if they're strings
            for jsonb_field in ['messages', 'other_params', 'response_metadata', 'metadata']:
                if log_dict.get(jsonb_field) and isinstance(log_dict[jsonb_field], str):
                    try:
                        log_dict[jsonb_field] = json.loads(log_dict[jsonb_field])
                    except:
                        pass  # Keep as string if parsing fails
            
            parsed_logs.append(log_dict)
        
        return {
            "logs": parsed_logs,
            "total": total or 0
        }
