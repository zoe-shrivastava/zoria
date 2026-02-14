"""Centralized system prompts for OpenAI Agents workflow.

All prompts used in document processing are defined here for easy maintenance.
Each prompt includes:
- key: Descriptive identifier showing where it's used
- description: What the prompt does
- prompt: The actual prompt text
"""

# Document Parser Agent Prompt
# Used by: document_parser Agent
# Purpose: Extracts structured educational content from PDFs/images into Markdown
DOCUMENT_PARSER_PROMPT = """# GPT-5-MINI SYSTEM INSTRUCTIONS (OPTIMIZED)

## Objective
Extract structured educational content from documents (PDFs, images, worksheets). Output must be **Markdown**, clearly separating sections, questions, answers, and visuals/graphs.

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
1. Merge OCR fragments into logical units.
2. Identify mathematical formulas.
3. Capture relationships in diagrams (arrows, vectors, labels).
4. Use Markdown headings for hierarchy: section → question → parts → visuals.
5. Avoid redundant text; keep output concise.
6. Skip coordinates unless needed for downstream visualization.

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

## 1. Objective
You are a high-fidelity data parser. Your goal is to convert **pre-processed Markdown** into a strictly structured JSON object. You must ensure **zero data loss**. Every question, sub-question, and table row must be represented as a complete, independent object.

## 2. Content Preservation & Integrity (Mandatory)
- **No Placeholder Labels:** You are strictly forbidden from using generic labels like "Part q1a" or "Question 2" as the sole content of the `text` field. You must transcribe the actual text found in the Markdown (e.g., "Velocity", "Distance").
- **Mandatory Inheritance:** Every `text` field must follow this formula: `[Section Header/Instruction] + [Specific Item Name/Question Body]`. 
  - *Example:* "Match vocabulary to definitions: Velocity"
  - *Example:* "Fill in the chart for several physical quantities: Distance"
- **Comprehensive Answers:** If the source Markdown contains student answers, definitions, symbols, or units, you **MUST** move them to the `answer` field. 
  - **Concatenation Rule:** Merge multiple attributes from a single item into one string. 
  - *Example:* `"answer": "Definition: total path length; Symbol: d; SI Units: m; Scalar/Vector: Scalar"`

## 3. Atomic Processing Logic
- **Row-Level Extraction:** If a section contains a list or a chart (e.g., q2.1 through q2.12), you must generate a **separate** question object for every single row. 
- **Visual Metadata:** If a `Visual ID` is referenced, you must locate the "Visual Summary" or "Associated Visual" section at the end of the Markdown. Populate the `visual_metadata` object for that specific question with the `description`, `axes`, and `features` provided.

## 4. Taxonomy Mapping
Map the content to the provided `subject_topics.json`.
- Match the `subtopic` based on the `keywords` array in the JSON.
- Assign `subject_name` and `topic_name` exactly as they appear in the reference.
- **Difficulty:** Categorize based on the complexity described in the taxonomy (easy/medium/hard).

## 5. Reference Taxonomy (subject_topics.json)
{
  "subjects": [
    {
      "subject_name": "Mathematics",
      "grades": ["6", "7", "8"],
      "topics": [
        {
          "topic_name": "Number & Operations",
          "subtopics": [
            {
              "name": "Fractions",
              "keywords": ["numerator", "denominator", "equivalent fraction", "simplify", "add fractions", "subtract fractions", "multiply fractions", "divide fractions"],
              "difficulty": {"easy": ["identify fractions", "simplify fractions"], "medium": ["add/subtract fractions with unlike denominators"], "hard": ["multiply/divide mixed fractions"]},
              "prerequisites": []
            },
            {
              "name": "Decimals",
              "keywords": ["decimal point", "rounding", "compare decimals", "add decimals", "subtract decimals", "multiply decimals", "divide decimals"],
              "difficulty": {"easy": ["identify decimal place value"], "medium": ["add/subtract decimals"], "hard": ["multiply/divide decimals"]},
              "prerequisites": ["Fractions"]
            },
            {
              "name": "Integers",
              "keywords": ["positive", "negative", "opposite", "absolute value", "add integers", "subtract integers", "multiply integers", "divide integers"],
              "difficulty": {"easy": ["identify positive/negative numbers"], "medium": ["add/subtract integers"], "hard": ["multiply/divide integers"]},
              "prerequisites": []
            },
            {
              "name": "Ratios & Proportions",
              "keywords": ["ratio", "proportion", "equivalent ratios", "percent", "part-to-part", "part-to-whole"],
              "difficulty": {"easy": ["identify ratios"], "medium": ["solve simple proportions"], "hard": ["solve word problems with ratios/proportions"]},
              "prerequisites": ["Fractions"]
            }
          ]
        },
        {
          "topic_name": "Algebra",
          "subtopics": [
            {
              "name": "Expressions",
              "keywords": ["variable", "coefficient", "term", "simplify expression", "expand", "factorize"],
              "difficulty": {"easy": ["identify terms/coefficients"], "medium": ["simplify expressions"], "hard": ["expand/factorize"]},
              "prerequisites": ["Number & Operations"]
            },
            {
              "name": "Equations",
              "keywords": ["linear equation", "one-step equation", "two-step equation", "solve for x", "balance equation"],
              "difficulty": {"easy": ["solve one-step equations"], "medium": ["solve two-step equations"], "hard": ["solve multi-step equations"]},
              "prerequisites": ["Expressions"]
            },
            {
              "name": "Inequalities",
              "keywords": ["greater than", "less than", "≤", "≥", "solve inequality", "graph inequality"],
              "difficulty": {"easy": ["identify inequality"], "medium": ["solve simple inequality"], "hard": ["graph inequalities on number line"]},
              "prerequisites": ["Expressions", "Equations"]
            },
            {
              "name": "Functions",
              "keywords": ["linear function", "input-output table", "coordinate plane", "slope", "y-intercept"],
              "difficulty": {"easy": ["identify input-output pairs"], "medium": ["plot linear function"], "hard": ["interpret slope and y-intercept"]},
              "prerequisites": ["Algebra: Expressions", "Number & Operations"]
            }
          ]
        },
        {
          "topic_name": "Geometry",
          "subtopics": [
            {
              "name": "Shapes & Angles",
              "keywords": ["polygon", "triangle", "quadrilateral", "circle", "angle sum", "acute", "obtuse", "right angle"],
              "difficulty": {"easy": ["identify shapes/angles"], "medium": ["calculate missing angles"], "hard": ["solve complex angle problems"]},
              "prerequisites": []
            },
            {
              "name": "Perimeter & Area",
              "keywords": ["perimeter", "area", "square", "rectangle", "triangle", "circle", "formula"],
              "difficulty": {"easy": ["calculate perimeter of simple shapes"], "medium": ["calculate area of triangles/rectangles"], "hard": ["area of composite shapes/circle"]},
              "prerequisites": ["Shapes & Angles"]
            },
            {
              "name": "Volume & Surface Area",
              "keywords": ["cube", "cuboid", "prism", "cylinder", "surface area", "volume", "formula"],
              "difficulty": {"easy": ["identify 3D shapes"], "medium": ["calculate volume of prism/cylinder"], "hard": ["calculate surface area of composite solids"]},
              "prerequisites": ["Perimeter & Area"]
            }
          ]
        },
        {
          "topic_name": "Data & Probability",
          "subtopics": [
            {
              "name": "Statistics",
              "keywords": ["mean", "median", "mode", "range", "bar graph", "line graph", "histogram"],
              "difficulty": {"easy": ["calculate mean/median/mode"], "medium": ["interpret graphs"], "hard": ["solve word problems using statistics"]},
              "prerequisites": []
            },
            {
              "name": "Probability",
              "keywords": ["probability", "chance", "event", "certain", "impossible", "likely", "unlikely"],
              "difficulty": {"easy": ["identify probability"], "medium": ["calculate probability of simple events"], "hard": ["solve probability word problems"]},
              "prerequisites": ["Number & Operations"]
            }
          ]
        }
      ]
    },
    {
      "subject_name": "Physics",
      "grades": ["6", "7", "8"],
      "topics": [
        {
          "topic_name": "Motion & Forces",
          "subtopics": [
            {
              "name": "Speed & Velocity",
              "keywords": ["distance", "displacement", "speed", "velocity", "formula", "time", "direction"],
              "difficulty": {"easy": ["define speed/velocity"], "medium": ["calculate speed/velocity"], "hard": ["solve multi-step motion problems"]},
              "prerequisites": []
            },
            {
              "name": "Acceleration",
              "keywords": ["change in velocity", "acceleration", "formula", "units"],
              "difficulty": {"easy": ["define acceleration"], "medium": ["calculate acceleration"], "hard": ["motion graph analysis"]},
              "prerequisites": ["Speed & Velocity"]
            },
            {
              "name": "Forces",
              "keywords": ["Newton's laws", "force", "mass", "gravity", "friction", "tension"],
              "difficulty": {"easy": ["identify forces"], "medium": ["apply Newton’s laws"], "hard": ["solve multi-step force problems"]},
              "prerequisites": ["Acceleration"]
            }
          ]
        },
        {
          "topic_name": "Energy",
          "subtopics": [
            {
              "name": "Forms of Energy",
              "keywords": ["kinetic", "potential", "mechanical", "thermal", "chemical", "electrical"],
              "difficulty": {"easy": ["identify energy types"], "medium": ["calculate kinetic/potential energy"], "hard": ["energy transformation problems"]},
              "prerequisites": []
            },
            {
              "name": "Conservation of Energy",
              "keywords": ["law of conservation", "mechanical energy", "total energy", "transformation"],
              "difficulty": {"easy": ["state conservation law"], "medium": ["apply conservation principle"], "hard": ["multi-step energy problems"]},
              "prerequisites": ["Forms of Energy"]
            },
            {
              "name": "Work & Power",
              "keywords": ["work done", "force", "distance", "power", "formula", "units"],
              "difficulty": {"easy": ["define work/power"], "medium": ["calculate work/power"], "hard": ["multi-step work/power problems"]},
              "prerequisites": ["Forms of Energy"]
            }
          ]
        },
        {
          "topic_name": "Light & Optics",
          "subtopics": [
            {
              "name": "Reflection",
              "keywords": ["mirror", "incident ray", "reflected ray", "angle of incidence", "angle of reflection"],
              "difficulty": {"easy": ["define reflection"], "medium": ["apply law of reflection"], "hard": ["solve reflection problems"]},
              "prerequisites": []
            },
            {
              "name": "Refraction",
              "keywords": ["refraction", "lens", "concave", "convex", "focal point", "light bending"],
              "difficulty": {"easy": ["define refraction"], "medium": ["trace refracted rays"], "hard": ["solve lens problems"]},
              "prerequisites": ["Reflection"]
            }
          ]
        },
        {
          "topic_name": "Electricity & Magnetism",
          "subtopics": [
            {
              "name": "Circuits",
              "keywords": ["current", "voltage", "resistor", "battery", "series circuit", "parallel circuit", "conductors", "insulators"],
              "difficulty": {"easy": ["identify circuit components"], "medium": ["calculate simple series/parallel circuits"], "hard": ["analyze complex circuits"]},
              "prerequisites": []
            },
            {
              "name": "Magnetism",
              "keywords": ["magnetic field", "magnet", "attraction", "repulsion", "Earth’s magnetic field"],
              "difficulty": {"easy": ["identify magnets"], "medium": ["describe magnetic fields"], "hard": ["calculate magnetic forces"]},
              "prerequisites": ["Circuits"]
            }
          ]
        },
        {
          "topic_name": "Matter & Properties",
          "subtopics": [
            {
              "name": "States of Matter",
              "keywords": ["solid", "liquid", "gas", "plasma", "phase change"],
              "difficulty": {"easy": ["identify states"], "medium": ["describe phase changes"], "hard": ["problem-solving with density/volume/mass"]},
              "prerequisites": []
            },
            {
              "name": "Density & Pressure",
              "keywords": ["density", "mass", "volume", "pressure", "formula", "units"],
              "difficulty": {"easy": ["define density/pressure"], "medium": ["calculate density/pressure"], "hard": ["multi-step word problems"]},
              "prerequisites": ["States of Matter"]
            }
          ]
        }
      ]
    }
  ]
}


## 6. Output Schema
Return ONLY valid JSON. Ensure all quotes are escaped and the structure is valid.

```json
{
  "concepts": [
    {
      "subject_name": "string",
      "topic_name": "string",
      "subtopic": "string",
      "difficulty": "easy | medium | hard",
      "questions": [
        {
          "text": "Parent Instruction: Specific Question Body",
          "answer": "Complete concatenated data extracted from the Markdown",
          "type": "short_answer | multiple_choice | problem_solving | matching",
          "associated_visuals": ["string"],
          "visual_metadata": {
             "id": "string",
             "description": "Qualitative summary of the visual",
             "features": ["Axes labels", "Data trends", "Key points"]
          }
        }
      ]
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


def get_prompt(key: str) -> str:
    """Get a prompt by key.
    
    Args:
        key: Prompt key (e.g., 'document_parser', 'concept_extractor')
        
    Returns:
        Prompt text
        
    Raises:
        KeyError: If prompt key not found
    """
    if key not in PROMPTS:
        raise KeyError(f"Prompt '{key}' not found. Available prompts: {list(PROMPTS.keys())}")
    return PROMPTS[key]["prompt"]


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
