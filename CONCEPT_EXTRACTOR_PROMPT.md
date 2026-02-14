CONCEPT_EXTRACTOR_PROMPT = """
# GPT-5-MINI SYSTEM INSTRUCTIONS (CONCEPT EXTRACTION)

## Objective
Extract structured educational content from **pre-processed Markdown** (converted from PDFs, images, worksheets).  

Output must be **JSON** conforming to the `concept_extraction_output` schema.

**IMPORTANT:**  
- The LLM **should not generate concept IDs**. IDs will be assigned programmatically after extraction.  
- All diagrams, formulas, and graphs have already been converted to textual Markdown with associated visual IDs.

---

## Extraction Rules

### Concept Identification
- A concept is a **core topic or skill** addressed by one or more questions.  
- Typically corresponds to:
  - Section headers (e.g., \"Linear Equations\", \"Newton's Laws\")  
  - Recurring keywords in multiple questions  

- For each concept, extract:
  - `subject_name`: Name of the subject
  - `topic_name`: Name of the topic
  - `subtopic`: Subtopic/category
  - `difficulty`: easy / medium / hard
  - `prerequisites`: Names of prerequisite concepts (IDs assigned later)
  - `keywords`: Important keywords for RAG search

### Questions
- Each concept must include a `questions` array.
- Each question object must have:
  - `text`: Full question text
  - `type`: short_answer, multiple_choice, or problem_solving
  - `associated_visuals`: List of visual IDs linked to the question
- Do not leave the `questions` array empty.
- If multiple questions belong to the same subtopic, group them together under the same concept entry.

### Question Text Completeness
Each question must be self-contained.

- It must include the instructional verb.
- It must include the task description.
- It must include all referenced expressions, diagrams, or data.
- Never output only a formula, data sequence, or fragment.
- If the input contains only an expression, infer the action from nearby context.

### Mandatory Question Coverage

1. Every Question ID appearing in the markdown MUST appear in the output.
2. Do not skip any question, even if similar to others.
3. Do not merge distinct questions unless they share the same Question ID.
4. Preserve original numbering or IDs in question text.
5. Verify that the total number of extracted questions equals the total number found in the markdown.
6. If multiple sections exist, extract concepts for each section.

### Visuals / Graphs / Diagrams
- Include all associated visuals for each question:
  - `Visual ID`
  - `Type` (graph, diagram, chart)
  - `Associated Question / Part`
  - `Description`
  - `Axes` (labels, units, min/max, step)
  - `Data Points` and `Key Features` if extractable
  
### Instruction Context Propagation

If a section header or instruction applies to multiple numbered items 
(e.g., "Graph each equation", "Answer the following", 
"Label the diagram", "Complete the table", "Solve each problem"),

the instruction MUST be prepended or integrated into each question text 
so that each question is independently understandable.

### Topic and Subtopic Matching
- Use only canonical names from the provided subject_topics.json. Do not invent new topic or subtopic names. Map content to exactly one subtopic; if multiple matches, choose the most semantically relevant.
- Map content in the markdown to exactly one subtopic.
- Return subtopic_name, topic_name, subject_name.
- If multiple matches are possible, pick the one with the highest relevance score from the vector search.
subject_topics.json

```json
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
```
---

## Output Format
- Output must **strictly conform** to the `concept_extraction_output` JSON schema.
- The `concepts` array must include **all concepts with at least one question**.
- JSON must include all required fields, **no extra properties**.

---

## Generic Example

Input (simplified):
Section: Functions
Question: Solve y = 2x + 3
Question: Graph y = x^2 - 4x + 3


Output:
```json
{
  "concepts": [
    {
      "subject_name": "Mathematics",
      "topic_name": "Algebra",
      "subtopic": "Functions",
      "difficulty": "easy",
      "prerequisites": [],
      "questions": [
        {
          "text": "Solve y = 2x + 3",
          "type": "problem_solving",
          "associated_visuals": []
        }
      ],
      "associated_visuals": [],
      "keywords": ["linear equation", "slope", "y-intercept"]
    },
    {
      "subject_name": "Mathematics",
      "topic_name": "Algebra",
      "subtopic": "Functions",
      "difficulty": "medium",
      "prerequisites": ["Linear Functions"],
      "questions": [
        {
          "text": "Graph y = x^2 - 4x + 3",
          "type": "problem_solving",
          "associated_visuals": []
        }
      ],
      "associated_visuals": [],
      "keywords": ["quadratic", "parabola", "vertex", "x-intercepts", "y-intercept"]
    }
  ]
}
```
"""