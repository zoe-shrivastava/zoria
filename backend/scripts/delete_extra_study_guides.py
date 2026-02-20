#!/usr/bin/env python3
"""Delete extra study guides for a child, keeping only the most recent per concept (subject/topic).

Usage:
    cd backend && python scripts/delete_extra_study_guides.py 58b578d6-3f09-409e-ab9d-8d08109f8ff8
    # Or with env:
    python scripts/delete_extra_study_guides.py <child_id>
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

CHILD_ID = "58b578d6-3f09-409e-ab9d-8d08109f8ff8"


async def delete_extra_study_guides(child_id: str) -> None:
    db = init_db()
    await db.connect()
    try:
        # Ids to keep: one per concept_name (most recent by generated_at)
        keep_ids = await db.fetch(
            """
            SELECT DISTINCT ON (concept_name) id
            FROM study_guides
            WHERE child_id = $1
            ORDER BY concept_name, generated_at DESC
            """,
            child_id,
        )
        keep_id_set = {str(row["id"]) for row in keep_ids}

        # All guides for this child
        all_rows = await db.fetch(
            "SELECT id, concept_name, focus_area, generated_at FROM study_guides WHERE child_id = $1 ORDER BY concept_name, generated_at DESC",
            child_id,
        )
        to_delete = [r for r in all_rows if str(r["id"]) not in keep_id_set]

        if not to_delete:
            logger.info("No extra study guides to delete for child %s (one per concept already).", child_id)
            return

        logger.info("Keeping %s guide(s), deleting %s extra for child %s.", len(keep_id_set), len(to_delete), child_id)
        for r in to_delete:
            logger.info("  Delete: id=%s concept_name=%s focus_area=%s generated_at=%s", r["id"], r["concept_name"], r["focus_area"], r["generated_at"])

        # Delete rows that are not in the "keep" set (most recent per concept_name)
        # $1 is used twice in the query; pass child_id once (same param for both)
        deleted = await db.execute(
            """
            DELETE FROM study_guides
            WHERE child_id = $1
            AND id NOT IN (
                SELECT DISTINCT ON (concept_name) id
                FROM study_guides
                WHERE child_id = $1
                ORDER BY concept_name, generated_at DESC
            )
            """,
            child_id,
        )
        logger.info("Deleted extra study guides for child %s. Result: %s", child_id, deleted)
    finally:
        await db.close()


if __name__ == "__main__":
    child_id = sys.argv[1] if len(sys.argv) > 1 else CHILD_ID
    try:
        asyncio.run(delete_extra_study_guides(child_id))
    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
