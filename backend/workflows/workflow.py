"""OpenAI Agents workflow for document processing.

Adapted from test/test_openai_workflow.py
"""

import base64
import os
import logging
import re
from collections import Counter
from typing import Optional, Any, Dict, List, Tuple
from pydantic import BaseModel

from agents import FileSearchTool, Agent, ModelSettings, TResponseInputItem, Runner, RunConfig, trace
from openai.types.shared.reasoning import Reasoning

from workflows.prompts import get_prompt
from services.llm_service import LLMService
from services.agent_logging_wrapper import run_agent_with_logging
from subject_config import get_subject_for_classification, get_subject_display_name, normalize_subject_name

logger = logging.getLogger(__name__)


def _estimate_question_count_from_markdown(markdown: str) -> int:
    """Heuristic lower-bound estimate of how many questions exist in the markdown.

    This is intentionally cheap and conservative. We just want a signal when the
    concept extractor has clearly under-recalled questions compared to obvious
    cues in the markdown.
    """
    if not markdown:
        return 0

    # Count main questions like "Question q9"
    q_main = len(re.findall(r"^Question\\s+q\\d+", markdown, flags=re.MULTILINE))

    # Count parts like "- Part q9.a"
    q_parts = len(re.findall(r"^-\\s+Part\\s+q\\d+\\.[a-z]", markdown, flags=re.MULTILINE))

    # Concept questions like "- Q4:", "- Q5:"
    concept_qs = len(re.findall(r"^-\\s+Q\\d+:", markdown, flags=re.MULTILINE))

    # Lettered sub-parts like "a.", "b.", "c.", "d." at the start of a line
    # These often indicate multi-part questions under a single numbered stem (e.g. "41. ... a. ... b. ...").
    lettered_parts = len(re.findall(r"^[a-z]\\.", markdown, flags=re.MULTILINE))

    return q_main + q_parts + concept_qs + lettered_parts


def _normalize_difficulty_for_concepts_json(raw: Any) -> str:
    """Normalize difficulty to one of easy/medium/hard."""
    text = (raw or "").__str__().strip().lower()
    if "|" in text:
        for part in [p.strip() for p in text.split("|")]:
            if part in {"easy", "medium", "hard"}:
                return part
        return "medium"
    if text in {"easy", "medium", "hard"}:
        return text
    return "medium"


def _canonical_key(subject_name: str, topic_name: str, subtopic: str) -> str:
    return f"{(subject_name or '').strip().lower()}::{(topic_name or '').strip().lower()}::{(subtopic or '').strip().lower()}"


def _postprocess_concepts_output(output_parsed: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Deduplicate concepts and sanitize prerequisites for KG-ready concepts JSON."""
    concepts = output_parsed.get("concepts", []) if isinstance(output_parsed, dict) else []
    if not isinstance(concepts, list):
        return {"concepts": []}, {
            "concept_count": 0,
            "duplicate_concept_ratio": 0.0,
            "question_count_total": 0,
            "prereq_coverage": 0.0,
            "invalid_prereq_refs": 0,
        }

    grouped: Dict[str, Dict[str, Any]] = {}
    seen_count = 0
    for c in concepts:
        if not isinstance(c, dict):
            continue
        subject_name = str(c.get("subject_name") or "").strip()
        topic_name = str(c.get("topic_name") or "").strip()
        subtopic = str(c.get("subtopic") or "").strip()
        if not subtopic:
            continue
        key = _canonical_key(subject_name, topic_name, subtopic)
        seen_count += 1

        if key not in grouped:
            grouped[key] = {
                "subject_name": subject_name,
                "topic_name": topic_name,
                "subtopic": subtopic,
                "difficulty": _normalize_difficulty_for_concepts_json(c.get("difficulty")),
                "prerequisites": list(c.get("prerequisites") or []),
                "questions": list(c.get("questions") or []),
                "associated_visuals": list(c.get("associated_visuals") or []),
                "keywords": list(c.get("keywords") or []),
            }
        else:
            existing = grouped[key]
            # Keep hardest difficulty among duplicates.
            rank = {"easy": 1, "medium": 2, "hard": 3}
            new_diff = _normalize_difficulty_for_concepts_json(c.get("difficulty"))
            if rank.get(new_diff, 2) > rank.get(existing.get("difficulty", "medium"), 2):
                existing["difficulty"] = new_diff
            existing["questions"].extend(list(c.get("questions") or []))
            existing["associated_visuals"].extend(list(c.get("associated_visuals") or []))
            existing["keywords"].extend(list(c.get("keywords") or []))
            existing["prerequisites"].extend(list(c.get("prerequisites") or []))

    deduped = list(grouped.values())
    concept_name_set = {str(c.get("subtopic") or "").strip().lower() for c in deduped if c.get("subtopic")}

    invalid_prereq_refs = 0
    for c in deduped:
        # Deduplicate lists while preserving order.
        c["associated_visuals"] = list(dict.fromkeys([v for v in c.get("associated_visuals", []) if v]))
        c["keywords"] = list(dict.fromkeys([k for k in c.get("keywords", []) if k]))

        # Sanitize prerequisites: keep only refs that map to existing subtopics, remove self refs.
        cleaned_prereqs: List[str] = []
        subtopic_lower = str(c.get("subtopic") or "").strip().lower()
        for p in c.get("prerequisites", []) or []:
            p_text = str(p or "").strip()
            if not p_text:
                continue
            p_lower = p_text.lower()
            if p_lower == subtopic_lower:
                continue
            if p_lower not in concept_name_set:
                invalid_prereq_refs += 1
                continue
            if p_text not in cleaned_prereqs:
                cleaned_prereqs.append(p_text)
        c["prerequisites"] = cleaned_prereqs

    question_count_total = sum(len(c.get("questions", [])) for c in deduped)
    concepts_with_prereqs = sum(1 for c in deduped if c.get("prerequisites"))
    concept_count = len(deduped)
    prereq_coverage = (concepts_with_prereqs / concept_count) if concept_count else 0.0
    duplicate_concept_ratio = ((seen_count - concept_count) / seen_count) if seen_count else 0.0

    metrics = {
        "concept_count": concept_count,
        "duplicate_concept_ratio": round(duplicate_concept_ratio, 4),
        "question_count_total": question_count_total,
        "prereq_coverage": round(prereq_coverage, 4),
        "invalid_prereq_refs": invalid_prereq_refs,
    }
    return {"concepts": deduped}, metrics

# Tool definitions
file_search = FileSearchTool(
    vector_store_ids=[
        "vs_6988e2999fe08191be7522fb1d842925"
    ]
)


class ConceptExtratorSchema__QuestionsItem(BaseModel):
    text: str
    type: str
    associated_visuals: list[str]
    answer: str | None = None


class ConceptExtratorSchema__ConceptsItem(BaseModel):
    subject_name: str
    topic_name: str
    subtopic: str
    difficulty: str
    prerequisites: list[str]
    questions: list[ConceptExtratorSchema__QuestionsItem]
    associated_visuals: list[str]
    keywords: list[str]


class ConceptExtratorSchema(BaseModel):
    concepts: list[ConceptExtratorSchema__ConceptsItem]


document_parser = Agent(
    name="Document Parser",
    instructions=get_prompt("document_parser"),
    model="gpt-5-mini",
    model_settings=ModelSettings(
        store=True,
        reasoning=Reasoning(
            effort="low"
        )
    )
)


def get_concept_extractor_agent(subject: Optional[str] = None):
    """Build concept extractor agent with optional subject-specific taxonomy.
    
    When subject is set (e.g. display name 'Mathematics', 'Physics'), only that
    subject's slice of subject_topics.json is included in the prompt.
    """
    return Agent(
        name="Concept Extrator",
        instructions=get_prompt("concept_extractor", subject=subject),
        model="gpt-5-mini",
        tools=[],
        output_type=ConceptExtratorSchema,
        model_settings=ModelSettings(
            store=True,
            max_tokens=128000,
            reasoning=Reasoning(
                effort="medium",
                summary="auto"
            )
        )
    )


# Legacy agent with full taxonomy (used only when no subject is available)
concept_extrator = get_concept_extractor_agent(subject=None)


class WorkflowInput(BaseModel):
    pdf_path: Optional[str] = None
    pdf_base64: Optional[str] = None
    pdf_filename: Optional[str] = None
    document_id: Optional[str] = None  # For logging purposes


def pdf_to_base64(pdf_path: str) -> str:
    """Convert a PDF file to base64 string."""
    with open(pdf_path, 'rb') as pdf_file:
        pdf_bytes = pdf_file.read()
        base64_encoded = base64.b64encode(pdf_bytes).decode('utf-8')
    return base64_encoded


# Initialize LLM service for subject extraction
_subject_llm_service = None

def get_subject_llm_service() -> LLMService:
    """Get or create LLM service for subject extraction."""
    global _subject_llm_service
    if _subject_llm_service is None:
        # Use a lightweight model for simple classification
        try:
            from core.database import get_db
            _subject_llm_service = LLMService(
                model_name="llama3.2:3b-instruct-fp16",
                enable_logging=True,
                context_source="subject_extraction"
            )
        except Exception:
            # Fallback if database not available
            _subject_llm_service = LLMService(
                model_name="llama3.2:3b-instruct-fp16",
                enable_logging=False,
                context_source="subject_extraction"
            )
    return _subject_llm_service


async def extract_subject_from_markdown(markdown: str) -> Optional[str]:
    """Extract subject from markdown using local LLM with JSON output.
    
    Uses subject profiles to determine valid subject IDs.
    Returns normalized subject_id (e.g., 'mathematics', 'physics', 'other').
    
    Args:
        markdown: Markdown text from document parser
        
    Returns:
        Subject ID ('mathematics', 'physics', 'other') or None if extraction fails
    """
    if not markdown:
        return None
    
    # Use first 2000 characters (title + first section) for efficiency
    sample_text = markdown[:2000]
    
    # Get valid subject IDs from profiles
    valid_subject_ids = get_subject_for_classification()
    
    # Build human-readable list for LLM
    subject_choices = []
    for sid in valid_subject_ids:
        display_name = get_subject_display_name(sid)
        subject_choices.append(f'"{sid}" ({display_name})')
    
    subject_choices_str = ", ".join(subject_choices)
    
    system_prompt = f"""You are a subject classifier for educational documents.

You must classify the content into ONE of these subjects by subject_id:
{subject_choices_str}

Rules:
- Use the most specific matching subject.
- If multiple could apply, choose the strongest signal.
- If content is not clearly about any listed subject, return "other".

Return your response as JSON:
{{ "subject_id": "<one of: {', '.join(valid_subject_ids)}>" }}"""

    user_prompt = f"""Classify this educational document excerpt:

{sample_text}

Return JSON with a single field "subject_id" only.
"""

    try:
        llm_service = get_subject_llm_service()
        
        response = await llm_service.generate_json(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.0,  # Low temperature for deterministic classification
            max_tokens=50
        )
        
        subject_id = (response.get("subject_id") or "").strip().lower()
        
        # Validate against known subjects
        if subject_id in valid_subject_ids:
            return subject_id
        
        # Try to match by display name if LLM returned a name instead of ID
        normalized = normalize_subject_name(subject_id)
        if normalized in valid_subject_ids:
            return normalized
        
        # Default to "other" if invalid
        logger.warning(f"LLM returned invalid subject_id: {subject_id}, defaulting to 'other'")
        return "other"
        
    except Exception as e:
        logger.error(f"Failed to extract subject via local LLM: {e}", exc_info=True)
        return None


async def run_workflow(workflow_input: WorkflowInput) -> dict:
    """
    Run the OpenAI Agents workflow with PDF input.
    
    Args:
        workflow_input: WorkflowInput containing PDF path or base64
        
    Returns:
        Dictionary with markdown, subject, and concepts
    """
    with trace("Study Material Processor"):
        state = {
            "markdown": None,
            "subject": None
        }
        workflow = workflow_input.model_dump()
        
        # Prepare conversation history
        conversation_history: list[TResponseInputItem] = []
        
        # Handle PDF input - using input_file format
        if workflow.get("pdf_path"):
            pdf_path = workflow["pdf_path"]
            if not os.path.exists(pdf_path):
                raise FileNotFoundError(f"PDF file not found: {pdf_path}")
            
            # Convert PDF to base64 and send as input_file
            b64_file = pdf_to_base64(pdf_path)
            filename = os.path.basename(pdf_path)
            
            conversation_history.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_data": f"data:application/pdf;base64,{b64_file}",
                        "filename": filename,
                    },
                    {
                        "type": "input_text",
                        "text": "Extract the entire document into structured Markdown format. Process all sections, all questions (including numbered problems 1-133 or whatever exists), all answer supplements, and all visuals. Do not ask questions - extract everything automatically."
                    }
                ],
            })
        elif workflow.get("pdf_base64"):
            # Use provided base64 PDF
            filename = workflow.get("pdf_filename", "document.pdf")
            conversation_history.append({
                "role": "user",
                "content": [
                    {
                        "type": "input_file",
                        "file_data": f"data:application/pdf;base64,{workflow['pdf_base64']}",
                        "filename": filename,
                    },
                    {
                        "type": "input_text",
                        "text": "Extract the entire document into structured Markdown format. Process all sections, all questions (including numbered problems 1-133 or whatever exists), all answer supplements, and all visuals. Do not ask questions - extract everything automatically."
                    }
                ],
            })
        else:
            raise ValueError("Either pdf_path or pdf_base64 must be provided")
        
        # Run document parser with logging
        document_parser_result_temp = await run_agent_with_logging(
            document_parser,
            input_data=conversation_history,
            run_config=RunConfig(trace_metadata={
                "__trace_source__": "agent-builder",
                "workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef"
            }),
            context_source="document_processing",
            document_id=workflow.get("document_id") if isinstance(workflow, dict) else None,
            metadata={"workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef", "agent": "document_parser"}
        )
        document_parser_result = {
            "output_text": document_parser_result_temp.final_output_as(str)
        }
        state["markdown"] = document_parser_result["output_text"]
        
        # Debug: Log markdown length and preview
        markdown_length = len(state["markdown"]) if state["markdown"] else 0
        markdown_preview = state["markdown"][:500] if state["markdown"] else "EMPTY"
        logger.info(f"Document parser output: {markdown_length} characters")
        logger.debug(f"Markdown preview (first 500 chars): {markdown_preview}")
        
        if not state["markdown"] or markdown_length < 100:
            logger.error(f"Document parser returned empty or very short markdown ({markdown_length} chars). This will cause zero concepts.")
        
        # Infer subject from markdown so we send only that subject's taxonomy to the concept extractor
        subject_id = await extract_subject_from_markdown(state["markdown"])
        subject_for_taxonomy = None
        if subject_id and subject_id != "other":
            subject_for_taxonomy = get_subject_display_name(subject_id)
            logger.info(f"Using subject-specific taxonomy for concept extractor: {subject_for_taxonomy} (subject_id={subject_id})")
        else:
            logger.info("Using full subject_topics taxonomy for concept extractor (subject unknown or 'other')")
        
        # Create fresh conversation history with only markdown for concept extractor
        # The concept extractor needs markdown input, not the PDF
        markdown_text = state["markdown"] if state["markdown"] else "No markdown content available. Please extract concepts from the document."
        
        # Add explicit instruction to ensure concepts are extracted
        concept_extractor_input = f"""Extract all concepts from the following markdown. You MUST return at least one concept. Process all questions, sections, and educational content.

{markdown_text}"""
        
        concept_extractor_history = [{
            "role": "user",
            "content": [
                {
                    "type": "input_text",
                    "text": concept_extractor_input
                }
            ]
        }]
        
        logger.info(f"Sending {len(markdown_text)} characters to concept extractor")
        
        # Run concept extractor with subject-specific taxonomy when available,
        # and retry once if we get zero concepts (LLM can be flaky).
        concept_extractor_agent = get_concept_extractor_agent(subject_for_taxonomy)
        max_attempts = 2
        last_error: Exception | None = None
        concept_extrator_result_temp = None
        concept_extrator_result = None

        for attempt in range(1, max_attempts + 1):
            logger.info(f"Running concept extractor (attempt {attempt}/{max_attempts})")
            concept_extrator_result_temp = await run_agent_with_logging(
                concept_extractor_agent,
                input_data=concept_extractor_history,
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef"
                }),
                context_source="document_processing",
                document_id=workflow.get("document_id") if isinstance(workflow, dict) else None,
                metadata={"workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef", "agent": "concept_extractor"}
            )

            conversation_history.extend([item.to_input_item() for item in concept_extrator_result_temp.new_items])

            try:
                concept_extrator_result = {
                    "output_text": concept_extrator_result_temp.final_output.json(),
                    "output_parsed": concept_extrator_result_temp.final_output.model_dump()
                }
                logger.debug(f"Concept extractor output keys: {list(concept_extrator_result['output_parsed'].keys())}")
                logger.debug(f"Concept extractor output type: {type(concept_extrator_result['output_parsed'])}")
            except Exception as e:
                last_error = e
                logger.error(f"Failed to parse concept extractor output on attempt {attempt}: {e}")
                logger.error(f"Raw output type: {type(concept_extrator_result_temp.final_output)}")
                logger.error(f"Raw output: {str(concept_extrator_result_temp.final_output)[:500]}")
                try:
                    raw_text = concept_extrator_result_temp.final_output_as(str)
                    logger.error(f"Raw text output (first 1000 chars): {raw_text[:1000]}")
                except Exception as e2:
                    logger.error(f"Could not get string output: {e2}")

                if attempt == max_attempts:
                    raise
                else:
                    continue

            concepts_list_peek = concept_extrator_result["output_parsed"].get("concepts", [])
            if concepts_list_peek:
                # Got at least one concept, proceed
                break

            logger.warning("Concept extractor returned ZERO concepts on this attempt.")
            if attempt == max_attempts:
                logger.error("Max attempts reached; proceeding with zero concepts result.")
            # Loop continues to retry once when attempt == 1
        
        # Post-process concepts JSON for KG readiness (dedupe + sanitize prerequisites).
        postprocessed_concepts, quality_metrics = _postprocess_concepts_output(
            concept_extrator_result["output_parsed"]
        )
        concept_extrator_result["output_parsed"] = postprocessed_concepts
        logger.info(
            "Concept extraction quality: concept_count=%s question_count_total=%s duplicate_concept_ratio=%s prereq_coverage=%s invalid_prereq_refs=%s",
            quality_metrics["concept_count"],
            quality_metrics["question_count_total"],
            quality_metrics["duplicate_concept_ratio"],
            quality_metrics["prereq_coverage"],
            quality_metrics["invalid_prereq_refs"],
        )

        # One optional retry if prerequisites are missing on concept-rich docs.
        concepts_list = concept_extrator_result["output_parsed"].get("concepts", [])
        if len(concepts_list) >= 5 and quality_metrics["prereq_coverage"] < 0.1:
            logger.warning(
                "Low prerequisite coverage (%.3f) with %d concepts. Running one focused retry for prerequisite links.",
                quality_metrics["prereq_coverage"],
                len(concepts_list),
            )
            retry_history = [{
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "Re-extract concepts from this markdown and focus on prerequisite links. "
                            "Return the same schema, ensure prerequisites reference only concept names present in your output, "
                            "and avoid self-prerequisites.\n\n" + markdown_text
                        )
                    }
                ]
            }]
            retry_temp = await run_agent_with_logging(
                concept_extractor_agent,
                input_data=retry_history,
                run_config=RunConfig(trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef"
                }),
                context_source="document_processing",
                document_id=workflow.get("document_id") if isinstance(workflow, dict) else None,
                metadata={"workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef", "agent": "concept_extractor_retry"}
            )
            retry_parsed = retry_temp.final_output.model_dump()
            retry_postprocessed, retry_metrics = _postprocess_concepts_output(retry_parsed)
            if (
                retry_metrics["prereq_coverage"] > quality_metrics["prereq_coverage"]
                or retry_metrics["question_count_total"] >= quality_metrics["question_count_total"]
            ):
                logger.info(
                    "Accepted retry concepts output: prereq_coverage %.3f -> %.3f, question_count_total %s -> %s",
                    quality_metrics["prereq_coverage"],
                    retry_metrics["prereq_coverage"],
                    quality_metrics["question_count_total"],
                    retry_metrics["question_count_total"],
                )
                concept_extrator_result["output_parsed"] = retry_postprocessed
                quality_metrics = retry_metrics

        # Extract subject_name from concepts output (no need for separate LLM call)
        extracted_subject = None
        concepts_list = concept_extrator_result["output_parsed"].get("concepts", [])
        total_questions = sum(len(c.get("questions", [])) for c in concepts_list)
        logger.info(f"Extracted {len(concepts_list)} concepts and {total_questions} total questions from output")

        # Heuristic coverage check: how many questions should we have?
        expected_questions = _estimate_question_count_from_markdown(markdown_text)
        if expected_questions > 0 and total_questions < expected_questions:
            logger.warning(
                "Concept extractor under-recalled questions: expected at least %d, got %d. "
                "This will cause missing questions in Concept JSON.",
                expected_questions,
                total_questions,
            )

        if len(concepts_list) == 1 and total_questions < 10:
            logger.warning("Only one concept with few questions—possible truncation or over-grouping; check max_tokens and prompt.")
        if len(concepts_list) == 0:
            logger.warning("⚠️  ZERO CONCEPTS EXTRACTED!")
            logger.warning(f"Output structure: {list(concept_extrator_result['output_parsed'].keys())}")
            logger.warning(f"Full output (first 2000 chars): {str(concept_extrator_result['output_parsed'])[:2000]}")
        if concepts_list:
            # Collect all subject_names from concepts
            subject_names = [c.get("subject_name") for c in concepts_list if c.get("subject_name")]
            
            if subject_names:
                # Use the most common subject_name (or first if all are the same)
                subject_name_counts = Counter(subject_names)
                most_common_subject_name = subject_name_counts.most_common(1)[0][0]
                
                # Log if there are multiple different subjects
                if len(subject_name_counts) > 1:
                    logger.warning(
                        f"Multiple subjects found in concepts: {dict(subject_name_counts)}. "
                        f"Using most common: '{most_common_subject_name}'"
                    )
                
                # Normalize subject_name to subject_id
                extracted_subject = normalize_subject_name(most_common_subject_name)
                logger.info(f"Extracted subject from concepts: '{most_common_subject_name}' -> '{extracted_subject}'")
            else:
                logger.warning("Concepts output does not contain subject_name. Subject will be None.")
        else:
            logger.warning("No concepts found in output. Subject will be None.")
        
        state["subject"] = extracted_subject
        if state["subject"]:
            logger.info(f"Final subject: {state['subject']}")
        else:
            logger.warning("Could not extract subject from concepts output")
        
        end_result = {
            "markdown": state["markdown"],
            "subject": state["subject"],
            "concepts": concept_extrator_result["output_parsed"]
        }
        return end_result


async def extract_concepts_from_markdown(
    markdown: str,
    document_id: Optional[str] = None
) -> dict:
    """Extract concepts from existing markdown (without re-parsing document).
    
    This is used for reprocessing when we want to re-extract concepts
    from existing markdown without running the document parser again.
    
    Args:
        markdown: Existing markdown content
        document_id: Document ID for logging
        
    Returns:
        Dictionary with concepts and subject
    """
    from services.agent_logging_wrapper import run_agent_with_logging
    from agents import RunConfig
    
    # Infer subject from markdown so we send only that subject's taxonomy
    subject_id = await extract_subject_from_markdown(markdown)
    subject_for_taxonomy = None
    if subject_id and subject_id != "other":
        subject_for_taxonomy = get_subject_display_name(subject_id)
        logger.info(f"extract_concepts_from_markdown: using taxonomy for subject {subject_for_taxonomy}")
    
    # Prepare conversation history with markdown as text input
    conversation_history = [{
        "role": "user",
        "content": [
            {
                "type": "input_text",
                "text": markdown
            }
        ]
    }]
    
    # Run concept extractor with subject-specific taxonomy when available
    concept_extractor_agent = get_concept_extractor_agent(subject_for_taxonomy)
    concept_extrator_result_temp = await run_agent_with_logging(
        concept_extractor_agent,
        input_data=conversation_history,
        run_config=RunConfig(trace_metadata={
            "__trace_source__": "agent-builder",
            "workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef"
        }),
        context_source="document_processing",
        document_id=document_id,
        metadata={"workflow_id": "wf_69801d60f7b081908e575da4a2b2c44c0a6a346a012420ef", "agent": "concept_extractor"}
    )
    
    # Parse agent output defensively. Reprocess failures have been observed when
    # final_output is not directly JSON/model-dump compatible.
    try:
        output_text = concept_extrator_result_temp.final_output.json()
    except Exception:
        output_text = concept_extrator_result_temp.final_output_as(str)

    try:
        output_parsed = concept_extrator_result_temp.final_output.model_dump()
    except Exception:
        # Fallback path when SDK returns a string-like output.
        try:
            output_parsed = json.loads(output_text) if isinstance(output_text, str) else {}
        except Exception as e:
            logger.error(
                "extract_concepts_from_markdown: failed to parse concept extractor output. "
                "document_id=%s output_type=%s preview=%s",
                document_id,
                type(concept_extrator_result_temp.final_output),
                str(output_text)[:1000],
                exc_info=True,
            )
            raise ValueError(f"Concept extractor output parsing failed: {e}")

    concept_extrator_result = {
        "output_text": output_text,
        "output_parsed": output_parsed
    }
    postprocessed_concepts, quality_metrics = _postprocess_concepts_output(
        concept_extrator_result["output_parsed"]
    )
    concept_extrator_result["output_parsed"] = postprocessed_concepts
    logger.info(
        "extract_concepts_from_markdown quality: concept_count=%s question_count_total=%s duplicate_concept_ratio=%s prereq_coverage=%s invalid_prereq_refs=%s",
        quality_metrics["concept_count"],
        quality_metrics["question_count_total"],
        quality_metrics["duplicate_concept_ratio"],
        quality_metrics["prereq_coverage"],
        quality_metrics["invalid_prereq_refs"],
    )
    
    # Extract subject_name from concepts output
    extracted_subject = None
    concepts_list = concept_extrator_result["output_parsed"].get("concepts", [])
    if concepts_list:
        subject_names = [c.get("subject_name") for c in concepts_list if c.get("subject_name")]
        if subject_names:
            subject_name_counts = Counter(subject_names)
            most_common_subject_name = subject_name_counts.most_common(1)[0][0]
            if len(subject_name_counts) > 1:
                logger.warning(
                    f"Multiple subjects found in concepts: {dict(subject_name_counts)}. "
                    f"Using most common: '{most_common_subject_name}'"
                )
            extracted_subject = normalize_subject_name(most_common_subject_name)
            logger.info(f"Extracted subject from concepts: '{most_common_subject_name}' -> '{extracted_subject}'")
        else:
            logger.warning("Concepts output does not contain subject_name. Subject will be None.")
    else:
        logger.warning("No concepts found in output. Subject will be None.")
    
    return {
        "concepts": concept_extrator_result["output_parsed"],
        "subject": extracted_subject
    }
