"""Centralized system prompts for OpenAI Agents workflow.

All prompts used in document processing are defined here for easy maintenance.
Each prompt includes:
- key: Descriptive identifier showing where it's used
- description: What the prompt does
- prompt: The actual prompt text
"""

import json
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Cache for subject_topics.json
_SUBJECT_TOPICS_CACHE: dict | None = None


def _load_subject_topics() -> dict:
    """Load subject_topics.json from backend directory.
    
    Returns:
        Dictionary containing subject topics taxonomy
    """
    global _SUBJECT_TOPICS_CACHE
    if _SUBJECT_TOPICS_CACHE is None:
        # Use only zoria/backend/subject_topics.json
        # This file is at zoria/backend/workflows/prompts.py
        # So parent.parent gives us zoria/backend/
        config_path = Path(__file__).resolve().parent.parent / "subject_topics.json"
        
        if not config_path.exists():
            logger.error(f"subject_topics.json not found at {config_path}")
            logger.error(f"Current working directory: {Path.cwd()}")
            logger.error(f"__file__ location: {Path(__file__).resolve()}")
            _SUBJECT_TOPICS_CACHE = {}
            return _SUBJECT_TOPICS_CACHE
        
        try:
            with config_path.open("r", encoding="utf-8") as f:
                _SUBJECT_TOPICS_CACHE = json.load(f)
            logger.info(f"Loaded subject_topics.json from {config_path}")
        except Exception as e:
            logger.error(f"Failed to load subject_topics.json from {config_path}: {e}", exc_info=True)
            _SUBJECT_TOPICS_CACHE = {}
    
    return _SUBJECT_TOPICS_CACHE


def _get_subject_topics_json_string() -> str:
    """Get subject_topics.json as a formatted JSON string for embedding in prompts.
    
    Returns:
        JSON string representation of subject topics
    """
    topics = _load_subject_topics()
    return json.dumps(topics, indent=2, ensure_ascii=False)


def _get_subject_topics_json_string_for_subject(subject_name: Optional[str]) -> str:
    """Get subject_topics.json for a single subject, or full taxonomy if subject is None.
    
    Used for content extraction so only the related subject's taxonomy is sent to the concept extractor.
    
    Args:
        subject_name: Display name of the subject (e.g. 'Mathematics', 'Physics') from
                      get_subject_display_name(subject_id). If None or no match, returns full taxonomy.
    
    Returns:
        JSON string: either {"subjects": [single_subject]} or full subject_topics
    """
    topics = _load_subject_topics()
    subjects_list = topics.get("subjects") or []
    if not subject_name or not subjects_list:
        return json.dumps(topics, indent=2, ensure_ascii=False)
    subject_name_clean = (subject_name or "").strip()
    for s in subjects_list:
        if (s.get("subject_name") or "").strip() == subject_name_clean:
            return json.dumps({"subjects": [s]}, indent=2, ensure_ascii=False)
    logger.debug(f"No subject_topics match for '{subject_name}'; using full taxonomy")
    return json.dumps(topics, indent=2, ensure_ascii=False)

# Document Parser Agent Prompt
# Used by: document_parser Agent
# Purpose: Extracts structured educational content from PDFs/images into Markdown
DOCUMENT_PARSER_PROMPT = """# GPT-5-MINI SYSTEM INSTRUCTIONS (OPTIMIZED)

## Objective
Extract structured educational content from documents (PDFs, images, worksheets). Output must be **Markdown**, clearly separating sections, questions, answers, and visuals/graphs.

## CRITICAL: Processing Instructions
- **DO NOT ask questions or request clarification.** Process the entire document automatically.
- **Extract ALL content:** Every section, every question (1-133 or whatever numbering exists), all answer supplements, and all visuals.
- **Complete extraction required:** Do not ask if you should extract everything - just do it. Extract the complete worksheet/document.
- **No partial extractions:** Process the entire document from start to finish without asking for page ranges or problem numbers.
- **Output immediately:** Begin extraction and output the Markdown structure without waiting for confirmation.

---

## Extraction Rules

### Sections / Headers
- Capture document sections or headers.
- Include: `Section Title`, `Type` (instruction / instruction_fields).

### Questions
- Capture each question with:
  - `ID` (q1, q2, etc.)
  - `Text`
  - `Type` (question, conceptual_question, problem_solving, multiple_choice)
  - Include parts if subdivided.

### Question Parts
- Include:
  - `Part ID` or `Label` (e.g., 9(a))
  - `Text`
  - `Type` (short_answer, multiple_choice, problem_solving)
  - `Student Answer` if available
  - `Classification` (answer, mathematical_formula)

### Visuals / Graphs / Diagrams
- Include all associated visuals.
- Capture:
  - `Visual ID`
  - `Type` (graph, diagram, chart)
  - `Associated Question / Part`
  - `Description`
  - `Axes` (labels, units, min/max, step)
  - `Data Points` and `Key Features` if extractable.
- For all graphs associated with questions:

1. Identify the function type (linear, quadratic, absolute value, etc.).
2. Calculate key points directly from the formula:
   - Vertex
   - One unit left/right of vertex (or as appropriate for function type)
   - Any intercepts or maxima/minima if relevant
3. Correctly determine slope direction and graph opening (up/down).
4. Populate the \"Data Points / Key Features\" section based on computation, not visual inspection.


---

## Additional Instructions
1. **Process the ENTIRE document automatically** - Extract all sections, all questions (numbered 1-133 or whatever exists), all answer supplements, and all visuals. Do NOT ask questions or request clarification.
2. Merge OCR fragments into logical units.
3. Identify mathematical formulas.
4. Capture relationships in diagrams (arrows, vectors, labels).
5. Use Markdown headings for hierarchy: section → question → parts → visuals.
6. Avoid redundant text; keep output concise.
7. Skip coordinates unless needed for downstream visualization.
8. **Begin extraction immediately** - Do not wait for user confirmation or ask which parts to extract. Process everything.

---

## Output Example
```markdown
Section: Physics 8 Study Guide
Type: instruction

Question 9
Type: question
Text: A tennis ball is hit at an angle starting 1 m above ground.

Part 9(a)
Type: short_answer
Text: Describe vertical motion.
Student Answer:
a = -9.8 m/s^2
v decreases upward, 0 at top, increases downward.
Δx decreases by smaller amount each second upward, max at top, decreases faster downward.
Classification: answer

Associated Visual: Position vs Time graph
Visual ID: v_q10
Type: graph
Associated Question: q10
Description: Piecewise position vs time graph showing motion
Axes:
  x: time (s), y: position (m)
Data Points:
  - {x: 0, y: -3}
  - {x: 5, y: 2}
Key Features: [\"position changes sign at t=5s\"]"""


# Concept Extractor Agent Prompt
# Used by: concept_extrator Agent
# Purpose: Extracts educational concepts from pre-processed Markdown into structured JSON
CONCEPT_EXTRACTOR_PROMPT = """
# SYSTEM INSTRUCTIONS: DOMAIN-AGNOSTIC ATOMIC EXTRACTION

## CRITICAL: Extract ALL Questions from the Markdown
- **You MUST extract every question in the markdown.** Process the entire document from start to finish. Do not stop early. Do not summarize. Do not skip any question, part, table row, or matching item.
- **Completeness check:** Before returning, ensure the total number of question objects in your output equals (or exceeds) the number of distinct questions/parts/rows in the markdown. If the markdown has 50 items (e.g. Q1–Q10, each with parts, or 20 matching terms, or 15 table rows), your output MUST contain at least 50 question objects. Omission of any item is a failure.
- **One concept per section or distinct subtopic.** Do NOT put all questions from the entire document into a single concept. Split by section headings, topic blocks, or distinct subtopics from the taxonomy so that each concept has a clear, narrow scope.
- **Every question/part must appear exactly once.** Every numbered item (e.g. Q1, Q2.1–Q2.12, Q3.1–Q3.5, Q4–Q8, Q9a–Q9c, Q10a–Q10c), every table row, every matching pair, and every fill-in item in the markdown MUST be represented as its own question object in the output. Count them and ensure none are omitted.
- **Multi-part lettered questions:** When a numbered question has sub-parts labeled with letters on their own lines (e.g. "41. ... a. ... b. ... c. ... d. ..."), you MUST emit one separate question object for **each** lettered part (a, b, c, d, etc.). It is forbidden to drop or merge any lettered sub-part.
- **FORBIDDEN:** Outputting a single question for an entire "Match the vocabulary", "Match the terms", table, or list is forbidden. You MUST emit one question object per term, per term-definition pair, or per row. If the markdown lists 10 vocabulary terms, you MUST output 10 question objects (each with type "matching" and text like "[Instruction] + [Term name]").
- **FORBIDDEN:** Stopping after the first section or first few questions. You MUST continue until every question in the markdown has been extracted.

## 1. Objective
You are a high-fidelity data parser. Your goal is to convert **pre-processed Markdown** into a strictly structured JSON object. You must ensure **zero data loss**. Extract **all** questions from the markdown: every question, sub-question, part, table row, and matching item must be represented as a complete, independent object. Process the full markdown; do not truncate or summarize the output.

## 2. Content Preservation & Integrity (Mandatory)
- **No Placeholder Labels:** You are strictly forbidden from using generic labels like "Part q1a" or "Question 2" as the sole content of the `text` field. You must transcribe the actual text found in the Markdown (e.g., "Velocity", "Distance").
- **Mandatory Inheritance:** Every `text` field must follow this formula: `[Section Header/Instruction] + [Specific Item Name/Question Body]`. 
  - *Example:* "Match vocabulary to definitions: Velocity"
  - *Example:* "Fill in the chart for several physical quantities: Distance"
- **Comprehensive Answers:** If the source Markdown contains student answers, definitions, symbols, or units, you **MUST** move them to the `answer` field. 
  - **Concatenation Rule:** Merge multiple attributes from a single item into one string. 
  - *Example:* `"answer": "Definition: total path length; Symbol: d; SI Units: m; Scalar/Vector: Scalar"`

## 3. Atomic Processing Logic & Type Mapping
- **Row-Level Extraction (Mandatory):** You are strictly forbidden from grouping multiple rows of a table or multiple items in a list into a single JSON object. Every independent data point must be its own `question` object.
    - **Tabular Data:** Every row in a chart must generate a unique object.
    - **Matching Lists:** "Match the vocabulary/terms to definitions" sections MUST be expanded: one question object per term or per term-definition pair, each with type `matching` and text = "[Section instruction] + [Specific term or item]" (e.g. "Match vocabulary to definitions: Velocity", "Match vocabulary to definitions: Distance"). Never output one question for the whole matching section.
    - **Text Formula:** Every `text` field must follow: `[Context/Instruction] + [Specific Item Name]`. 
      *Example:* "Fill in the chart for physical quantities: Displacement"
- **Strict Type Enforcement:** You must map every item to one of these six recognized types. Do not hallucinate types (e.g., do not use "diagram", "graph", or "mathematical_formula"):
    1. `multiple_choice`: Fixed options or "circle the answer" format.
    2. `short_answer`: Brief factual, numeric, or one-word responses.
    3. `problem_solving`: Multi-step applications, calculations, or tasks requiring the student to "Draw", "Plot", or "Sketch".
    4. `conceptual_question`: Qualitative explanations or "Why/How" reasoning.
    5. `matching`: Use for each term-definition pair or vocabulary-matching item. Every "match X to Y" item must be type `matching`, not conceptual_question.
    6. `fill_in_the_blank`: Sentences with missing words or specific empty data cells in a table.

## 3.1. Content Preservation & Answer Concatenation
- **Zero Data Loss:** If a table row has multiple columns (e.g., Symbol, Unit, Definition), concatenate all data for that specific row into the `answer` field.
  *Example:* `"answer": "Symbol: Δx; SI Units: m; Type: Vector"`
- **Visual Integration:** If an item refers to a `Visual ID`, you must populate the `visual_metadata` object using the data found in the "Associated Visual" section. Include the description, axes labels, and key trends.
- **Visual Action Mapping:** If a question asks a student to "Draw", "Graph", or "Plot", you must map the type to `problem_solving`. These are not "diagram" types; they are active problem-solving tasks.
- **Visual Metadata:** If a `Visual ID` is referenced, you must locate the "Visual Summary" or "Associated Visual" section at the end of the Markdown. Populate the `visual_metadata` object for that specific question with the `description`, `axes`, and `features` provided.

## 4. Taxonomy Mapping
Map the content to the provided `subject_topics.json`.
- Match the `subtopic` based on the `keywords` array in the JSON.
- Assign `subject_name` and `topic_name` exactly as they appear in the reference.
- **Difficulty:** Categorize based on the complexity described in the taxonomy (easy/medium/hard).

## 4.1 Prerequisites Extraction Rules (Strict)
- `prerequisites` MUST be an array of concept names that are also present in the same extracted concepts output.
- Never include the concept itself in its own prerequisites.
- Do not invent external concepts that do not appear in the extracted concept list.
- If a prerequisite is not clearly inferable from the source markdown, use an empty array (`[]`).
- Keep prerequisite names text-exact and consistent with extracted concept names so downstream matching succeeds.

## 5. Reference Taxonomy (subject_topics.json)
{subject_topics_json}

CRITICAL: You may only use subject_name, topic_name, and subtopic from the provided subject_topics.json. Do not invent new topics, subtopics, or subjects. If a question does not match any keywords, you must still assign it to the closest matching subtopic from the taxonomy. Never create a custom topic or subtopic.

## 6. Coverage Self-Check (MANDATORY)
- Before returning, you MUST perform a coverage self-check:
  1. Count all distinct questions, sub-questions, parts, table rows, and matching terms in the markdown (for example: every line beginning with "Question", "Part", "Q4:", "Q5:", "Q6:", "Practice Question", "Free Response Question", or equivalent numbered/lettered item).
  2. Let this count be N_expected.
  3. Count the number of question objects you are returning across ALL concepts (sum of len(concept.questions) for every concept). Let this be N_output.
  4. You MUST ensure N_output >= N_expected. If N_output < N_expected, you MUST continue extracting additional questions from the remaining sections until EVERY question, part, table row, matching term, and free-response item in the markdown is represented exactly once in your JSON.
- It is STRICTLY FORBIDDEN to stop after the first section, the first matching block, or the first page. You must process the ENTIRE markdown.

## 7. Output Schema
Return ONLY valid JSON. Ensure all quotes are escaped and the structure is valid.
- Include **every** concept and **every** question from the markdown in your response. The JSON must be complete (all concepts, all questions); do not cut off the output.
Each concept must include: subject_name, topic_name, subtopic, difficulty, prerequisites, questions, associated_visuals, keywords.
Each question must include:
- `text`: "[Section Header/Instruction] + [Specific Question Body]"
- `type`: one of `multiple_choice | short_answer | problem_solving | conceptual_question | matching | fill_in_the_blank`
- `associated_visuals`: array of strings
- `answer` (OPTIONAL but REQUIRED when present in the markdown): If the markdown contains a worked answer, numeric result, definition, completed table row, or student/teacher solution (for example, "FN = 127.31 N"), you MUST copy that content into the `answer` field for that question.

```json
{
  "concepts": [
    {
      "subject_name": "string",
      "topic_name": "string",
      "subtopic": "string",
      "difficulty": "easy | medium | hard",
      "prerequisites": [],
      "questions": [
        {
          "text": "Parent Instruction: Specific Question Body",
          "type": "multiple_choice | short_answer | problem_solving | conceptual_question | matching | fill_in_the_blank",
          "associated_visuals": ["string"],
          "answer": "Answer, numeric result, definition, or completed row (if present in markdown)"
        }
      ],
      "associated_visuals": ["string"],
      "keywords": ["string"]
    }
  ]
}
"""


# Prompt Registry
# Dictionary mapping prompt keys to their values and metadata
PROMPTS = {
    "document_parser": {
        "key": "document_parser",
        "description": "Extracts structured educational content from PDFs/images into Markdown format",
        "used_by": "document_parser Agent",
        "output_format": "Markdown",
        "prompt": DOCUMENT_PARSER_PROMPT
    },
    "concept_extractor": {
        "key": "concept_extractor",
        "description": "Extracts educational concepts from pre-processed Markdown into structured JSON",
        "used_by": "concept_extrator Agent",
        "output_format": "JSON (ConceptExtratorSchema)",
        "prompt": CONCEPT_EXTRACTOR_PROMPT
    }
}


def get_prompt(key: str, subject: Optional[str] = None) -> str:
    """Get a prompt by key.
    
    Args:
        key: Prompt key (e.g., 'document_parser', 'concept_extractor')
        subject: Optional subject display name (e.g. 'Mathematics', 'Physics'). For
                 concept_extractor, only that subject's slice of subject_topics.json
                 is injected; if None, full taxonomy is used.
        
    Returns:
        Prompt text with subject_topics.json injected if needed
        
    Raises:
        KeyError: If prompt key not found
    """
    if key not in PROMPTS:
        raise KeyError(f"Prompt '{key}' not found. Available prompts: {list(PROMPTS.keys())}")
    
    prompt_text = PROMPTS[key]["prompt"]
    
    # Inject subject_topics.json for concept_extractor (only related subject when subject is set)
    if key == "concept_extractor":
        subject_topics_json = _get_subject_topics_json_string_for_subject(subject)
        prompt_text = prompt_text.replace("{subject_topics_json}", subject_topics_json)
    
    return prompt_text


def list_prompts() -> dict:
    """List all available prompts with metadata.
    
    Returns:
        Dictionary of prompts with metadata (excluding actual prompt text)
    """
    return {
        key: {
            "key": value["key"],
            "description": value["description"],
            "used_by": value["used_by"],
            "output_format": value["output_format"]
        }
        for key, value in PROMPTS.items()
    }
