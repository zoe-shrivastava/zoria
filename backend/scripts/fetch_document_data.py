#!/usr/bin/env python3
"""
Fetch all data stored for a document (ingestion pipeline debug).

Use this to verify that every step of document ingestion produced correct data:
  Phase 1: document row (markdown_content, concepts JSON, subject, status)
  Phase 2/3: concepts, document_concepts, questions, question_skills, visuals,
             concept_relationships, content_chunks

Usage:
  From backend directory (with venv activated so asyncpg is available):
    python scripts/fetch_document_data.py <document_id>
    python scripts/fetch_document_data.py a8ee43c2-2504-4d19-b427-28bea4e0ea7c

  From Docker (with backend + postgres running):
    docker compose exec backend python scripts/fetch_document_data.py <document_id>
    docker compose exec backend python scripts/fetch_document_data.py a8ee43c2-2504-4d19-b427-28bea4e0ea7c --no-embedding -o /tmp/doc.json

  Options:
    --output FILE   Write JSON to file instead of stdout
    --no-embedding  Exclude embedding vectors from content_chunks (smaller output)
    --llm-logs      Include llm_logs rows for this document (agent call debug)
"""

import argparse
import asyncio
import json
import sys
from datetime import datetime
from pathlib import Path
from uuid import UUID

# Add backend to path when run as script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Load env before database (optional dotenv)
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(dotenv_path=env_path, override=False)
    else:
        load_dotenv(override=False)
except ImportError:
    pass

from core.database import init_db, get_db


def _serialize(value):
    """Convert asyncpg/DB values to JSON-serializable types."""
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _serialize(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    if hasattr(value, "tolist"):  # numpy/vector type
        return value.tolist()  # full vector when --embedding; use --no-embedding to exclude
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _rows_to_json(rows, exclude_keys=None):
    """Convert list of asyncpg Record to list of JSON-serializable dicts."""
    exclude_keys = set(exclude_keys or [])
    out = []
    for row in rows:
        d = dict(row)
        for k in exclude_keys:
            d.pop(k, None)
        out.append(_serialize(d))
    return out


async def fetch_document_data(document_id: str, include_embeddings: bool = False, include_llm_logs: bool = False):
    """Fetch all DB data for a document. Returns a single dict suitable for JSON."""
    db = get_db()
    if db.pool is None:
        await db.connect()

    # 1. Document row
    doc = await db.fetchrow(
        "SELECT * FROM documents WHERE id = $1",
        document_id
    )
    if not doc:
        return {"error": f"Document not found: {document_id}"}

    result = {
        "document": _serialize(dict(doc)),
        "document_children": [],
        "concepts": [],
        "document_concepts": [],
        "questions": [],
        "question_skills": [],
        "skills": [],
        "visuals": [],
        "concept_relationships": [],
        "content_chunks": [],
        "chunks_legacy": [],
    }
    if include_llm_logs:
        result["llm_logs"] = []

    # 2. document_children
    result["document_children"] = _rows_to_json(
        await db.fetch(
            "SELECT * FROM document_children WHERE document_id = $1",
            document_id
        )
    )

    # 3. Concepts: both direct document_id and via document_concepts
    concept_ids = await db.fetch(
        """
        SELECT id FROM concepts WHERE document_id = $1
        UNION
        SELECT concept_id AS id FROM document_concepts WHERE document_id = $1
        """,
        document_id,
    )
    concept_id_list = [str(r["id"]) for r in concept_ids] if concept_ids else []

    result["concepts"] = _rows_to_json(
        await db.fetch(
            "SELECT * FROM concepts WHERE id = ANY($1::uuid[])",
            concept_id_list
        )
    ) if concept_id_list else []

    result["document_concepts"] = _rows_to_json(
        await db.fetch(
            "SELECT * FROM document_concepts WHERE document_id = $1",
            document_id
        )
    )

    if not concept_id_list:
        result["questions"] = []
        result["question_skills"] = []
        result["skills"] = []
        result["visuals"] = []
        result["concept_relationships"] = []
    else:
        # 4. Questions (for these concepts)
        questions = await db.fetch(
            "SELECT * FROM questions WHERE concept_id = ANY($1::uuid[])",
            concept_id_list
        )
        result["questions"] = _rows_to_json(questions)
        question_ids = [str(r["id"]) for r in questions] if questions else []

        # 5. question_skills + skill names
        result["question_skills"] = _rows_to_json(
            await db.fetch(
                "SELECT * FROM question_skills WHERE question_id = ANY($1::uuid[])",
                question_ids
            )
        ) if question_ids else []

        skill_ids = await db.fetch(
            """
            SELECT DISTINCT skill_id FROM question_skills
            WHERE question_id = ANY($1::uuid[])
            """,
            question_ids
        )
        if skill_ids:
            sid_list = [str(r["skill_id"]) for r in skill_ids]
            result["skills"] = _rows_to_json(
                await db.fetch(
                    "SELECT * FROM skills WHERE id = ANY($1::uuid[])",
                    sid_list
                )
            )

        # 6. Visuals (for these concepts)
        result["visuals"] = _rows_to_json(
            await db.fetch(
                "SELECT * FROM visuals WHERE concept_id = ANY($1::uuid[])",
                concept_id_list
            )
        )

        # 7. Concept relationships (either end is one of our concepts)
        result["concept_relationships"] = _rows_to_json(
            await db.fetch(
                """
                SELECT * FROM concept_relationships
                WHERE from_concept_id = ANY($1::uuid[])
                   OR to_concept_id = ANY($1::uuid[])
                """,
                concept_id_list
            )
        )

    # 8. content_chunks (optionally strip embedding)
    chunks = await db.fetch(
        "SELECT * FROM content_chunks WHERE document_id = $1",
        document_id
    )
    exclude_chunk = [] if include_embeddings else ["embedding"]
    result["content_chunks"] = _rows_to_json(chunks, exclude_keys=exclude_chunk)
    # If we excluded embedding, add a note about dimensions
    if chunks and not include_embeddings:
        result["content_chunks_note"] = "embedding column excluded (use --embedding to include)"

    # 9. Legacy chunks table
    result["chunks_legacy"] = _rows_to_json(
        await db.fetch(
            "SELECT * FROM chunks WHERE document_id = $1",
            document_id
        )
    )

    # 10. Tests that use concepts from this document
    if concept_id_list:
        result["tests_using_concepts"] = _rows_to_json(
            await db.fetch(
                "SELECT * FROM tests WHERE concept_id = ANY($1::uuid[])",
                concept_id_list
            )
        )
    else:
        result["tests_using_concepts"] = []

    if include_llm_logs:
        result["llm_logs"] = _rows_to_json(
            await db.fetch(
                "SELECT * FROM llm_logs WHERE document_id = $1 ORDER BY created_at",
                document_id
            )
        )

    # Counts summary for quick debug
    result["_summary"] = {
        "document_id": document_id,
        "document_children": len(result["document_children"]),
        "concepts": len(result["concepts"]),
        "document_concepts_links": len(result["document_concepts"]),
        "questions": len(result["questions"]),
        "question_skills": len(result["question_skills"]),
        "skills": len(result["skills"]),
        "visuals": len(result["visuals"]),
        "concept_relationships": len(result["concept_relationships"]),
        "content_chunks": len(result["content_chunks"]),
        "chunks_legacy": len(result["chunks_legacy"]),
        "tests_using_concepts": len(result.get("tests_using_concepts", [])),
    }
    if include_llm_logs:
        result["_summary"]["llm_logs"] = len(result["llm_logs"])

    return result


def main():
    parser = argparse.ArgumentParser(
        description="Fetch all data stored for a document (ingestion debug)."
    )
    parser.add_argument(
        "document_id",
        nargs="?",
        default="a8ee43c2-2504-4d19-b427-28bea4e0ea7c",
        help="Document UUID (default: example from spec)",
    )
    parser.add_argument(
        "--output", "-o",
        metavar="FILE",
        help="Write JSON to file instead of stdout",
    )
    parser.add_argument(
        "--no-embedding",
        action="store_true",
        help="Exclude embedding vectors from content_chunks",
    )
    parser.add_argument(
        "--llm-logs",
        action="store_true",
        help="Include llm_logs for this document",
    )
    args = parser.parse_args()

    init_db()
    data = asyncio.run(fetch_document_data(
        args.document_id,
        include_embeddings=not args.no_embedding,
        include_llm_logs=args.llm_logs,
    ))

    if "error" in data:
        print(data["error"], file=sys.stderr)
        sys.exit(1)

    json_str = json.dumps(data, indent=2)
    if args.output:
        Path(args.output).write_text(json_str, encoding="utf-8")
        print(f"Wrote {len(json_str)} bytes to {args.output}", file=sys.stderr)
        print("Summary:", json.dumps(data.get("_summary", {}), indent=2), file=sys.stderr)
    else:
        print(json_str)


if __name__ == "__main__":
    main()
