-- LLM Logs Migration
-- Tracks all LLM API calls for monitoring, cost analysis, and debugging

CREATE TABLE IF NOT EXISTS llm_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    
    -- Call Identification
    call_type VARCHAR(50) NOT NULL,  -- 'llm_service', 'agent_sdk', 'workflow'
    provider VARCHAR(50) NOT NULL,  -- 'openai', 'ollama'
    model VARCHAR(100) NOT NULL,  -- 'gpt-5-nano', 'gpt-5-mini', etc.
    
    -- Request Details
    request_type VARCHAR(50),  -- 'generate', 'chat', 'generate_json', 'agent_run'
    system_prompt TEXT,  -- Full system prompt (may be truncated)
    user_prompt TEXT,  -- User prompt/message
    messages JSONB,  -- Full conversation history if applicable
    temperature DECIMAL(3,2),
    max_tokens INTEGER,
    other_params JSONB,  -- Additional parameters (format, etc.)
    
    -- Response Details
    response_text TEXT,  -- LLM response text
    response_metadata JSONB,  -- Full API response metadata
    success BOOLEAN NOT NULL DEFAULT TRUE,
    error_message TEXT,  -- Error if call failed
    
    -- Token Usage
    prompt_tokens INTEGER,  -- Input tokens
    completion_tokens INTEGER,  -- Output tokens
    total_tokens INTEGER,  -- Total tokens
    cached_tokens INTEGER DEFAULT 0,  -- Cached input tokens (if applicable)
    
    -- Cost Calculation
    input_cost_usd DECIMAL(10, 8),  -- Cost for input tokens
    cached_input_cost_usd DECIMAL(10, 8),  -- Cost for cached input tokens
    output_cost_usd DECIMAL(10, 8),  -- Cost for output tokens
    total_cost_usd DECIMAL(10, 8),  -- Total cost
    
    -- Performance
    latency_ms INTEGER,  -- Time taken in milliseconds
    
    -- Context
    context_source VARCHAR(100),  -- 'question_generation', 'document_processing', etc.
    document_id UUID,  -- Related document if applicable
    concept_id UUID,  -- Related concept if applicable
    test_id UUID,  -- Related test if applicable
    metadata JSONB  -- Additional context
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_llm_logs_created_at ON llm_logs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_llm_logs_model ON llm_logs(model);
CREATE INDEX IF NOT EXISTS idx_llm_logs_call_type ON llm_logs(call_type);
CREATE INDEX IF NOT EXISTS idx_llm_logs_provider ON llm_logs(provider);
CREATE INDEX IF NOT EXISTS idx_llm_logs_document_id ON llm_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_llm_logs_concept_id ON llm_logs(concept_id);
CREATE INDEX IF NOT EXISTS idx_llm_logs_test_id ON llm_logs(test_id);
