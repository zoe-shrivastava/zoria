# OpenAI Agents Workflow

This module contains the OpenAI Agents workflow for processing educational documents.

## Components

### `workflow.py`
Main workflow implementation that:
- Accepts PDF input (file path or base64)
- Processes documents through two agents:
  1. **Document Parser**: Extracts structured content to Markdown
  2. **Concept Extractor**: Extracts educational concepts to JSON
- Returns markdown content and structured concepts

### `prompts.py`
Centralized system prompts for all agents. All prompts are defined here for easy maintenance.

**Available Prompts:**
- `document_parser` - Extracts structured content from PDFs to Markdown
- `concept_extractor` - Extracts concepts from Markdown to JSON

**Usage:**
```python
from workflows.prompts import get_prompt, list_prompts

# Get a prompt
prompt = get_prompt("document_parser")

# List all prompts with metadata
all_prompts = list_prompts()
```

## Adding New Prompts

1. Define the prompt constant in `prompts.py`:
```python
NEW_PROMPT = """Your prompt text here..."""
```

2. Add to PROMPTS registry:
```python
PROMPTS = {
    # ... existing prompts
    "new_prompt_key": {
        "key": "new_prompt_key",
        "description": "What this prompt does",
        "used_by": "Which agent uses it",
        "output_format": "Expected output format",
        "prompt": NEW_PROMPT
    }
}
```

3. Use in your agent:
```python
agent = Agent(
    name="Agent Name",
    instructions=get_prompt("new_prompt_key"),
    ...
)
```

## Workflow Usage

```python
from workflows.workflow import run_workflow, WorkflowInput

# With file path
result = await run_workflow(WorkflowInput(pdf_path="/path/to/document.pdf"))

# With base64
result = await run_workflow(WorkflowInput(
    pdf_base64="base64_string_here",
    pdf_filename="document.pdf"
))

# Result contains:
# - result["markdown"]: Extracted markdown content
# - result["concepts"]: Extracted concepts (JSON structure)
```
