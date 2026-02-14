"""Schemas for LLM log responses."""

from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field


class LLMLogResponse(BaseModel):
    """LLM log entry response."""
    id: str
    created_at: datetime
    call_type: str
    provider: str
    model: str
    request_type: Optional[str] = None
    system_prompt: Optional[str] = None
    user_prompt: Optional[str] = None
    messages: Optional[List[Dict[str, Any]]] = None
    temperature: Optional[float] = None
    max_tokens: Optional[int] = None
    other_params: Optional[Dict[str, Any]] = None
    response_text: Optional[str] = None
    response_metadata: Optional[Dict[str, Any]] = None
    success: bool
    error_message: Optional[str] = None
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    cached_tokens: int = 0
    input_cost_usd: Optional[float] = None
    cached_input_cost_usd: Optional[float] = None
    output_cost_usd: Optional[float] = None
    total_cost_usd: Optional[float] = None
    latency_ms: Optional[int] = None
    context_source: Optional[str] = None
    document_id: Optional[str] = None
    concept_id: Optional[str] = None
    test_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


class LLMLogListResponse(BaseModel):
    """Response for listing LLM logs."""
    logs: List[LLMLogResponse]
    total: int
    limit: int
    offset: int


class LLMUsageStatsResponse(BaseModel):
    """Response for LLM usage statistics."""
    total_calls: int
    total_prompt_tokens: Optional[int] = None
    total_completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    total_cost_usd: Optional[float] = None
    avg_latency_ms: Optional[float] = None
