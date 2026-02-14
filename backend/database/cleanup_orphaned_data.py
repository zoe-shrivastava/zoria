#!/usr/bin/env python3
"""Database cleanup script to remove orphaned data.

This script removes orphaned records after documents and tests have been deleted.
It respects foreign key constraints and runs in a transaction for safety.

Usage:
    python database/cleanup_orphaned_data.py
    # Or via Docker:
    docker-compose exec backend python database/cleanup_orphaned_data.py
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


async def cleanup_orphaned_data():
    """Clean up orphaned data from database."""
    db = init_db()
    await db.connect()
    
    try:
        logger.info("Starting database cleanup...")
        
        # Cleanup SQL - order matters due to foreign key constraints
        cleanup_queries = [
            ("test_responses", """
                DELETE FROM test_responses 
                WHERE test_id NOT IN (SELECT id FROM tests)
            """),
            ("test_questions", """
                DELETE FROM test_questions 
                WHERE test_id NOT IN (SELECT id FROM tests)
            """),
            ("question_skills", """
                DELETE FROM question_skills 
                WHERE question_id NOT IN (SELECT id FROM questions)
            """),
            ("concept_relationships", """
                DELETE FROM concept_relationships 
                WHERE from_concept_id NOT IN (SELECT id FROM concepts)
                   OR to_concept_id NOT IN (SELECT id FROM concepts)
            """),
            ("student_concept_mastery", """
                DELETE FROM student_concept_mastery 
                WHERE concept_id NOT IN (SELECT id FROM concepts)
            """),
            ("visuals", """
                DELETE FROM visuals 
                WHERE (concept_id IS NOT NULL AND concept_id NOT IN (SELECT id FROM concepts))
                   OR (question_id IS NOT NULL AND question_id NOT IN (SELECT id FROM questions))
            """),
            # Remove old generated questions that are no longer used in any tests.
            # This keeps only questions parsed from documents or still attached to at least one test.
            ("generated_questions_without_tests", """
                DELETE FROM questions q
                WHERE q.status = 'generated'
                  AND NOT EXISTS (
                      SELECT 1 FROM test_questions tq
                      WHERE COALESCE(tq.question_id, tq.original_question_id) = q.id
                  )
            """),
            ("questions", """
                DELETE FROM questions 
                WHERE concept_id NOT IN (SELECT id FROM concepts)
            """),
            ("concepts", """
                DELETE FROM concepts 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
            ("content_chunks", """
                DELETE FROM content_chunks 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
            ("chunks (legacy)", """
                DELETE FROM chunks 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
            ("quiz_results", """
                DELETE FROM quiz_results 
                WHERE quiz_id NOT IN (SELECT id FROM quizzes)
            """),
            ("quizzes", """
                DELETE FROM quizzes 
                WHERE document_id IS NOT NULL 
                  AND document_id NOT IN (SELECT id FROM documents)
            """),
            ("skills (unused)", """
                DELETE FROM skills 
                WHERE id NOT IN (SELECT skill_id FROM question_skills)
            """),
            ("document_children", """
                DELETE FROM document_children 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
        ]
        
        # Run cleanup in a transaction
        async with db.pool.acquire() as conn:
            async with conn.transaction():
                total_deleted = 0
                for table_name, query in cleanup_queries:
                    try:
                        result = await conn.execute(query)
                        deleted_count = int(result.split()[-1]) if result else 0
                        total_deleted += deleted_count
                        if deleted_count > 0:
                            logger.info(f"  Deleted {deleted_count} orphaned records from {table_name}")
                    except Exception as e:
                        logger.warning(f"  Error cleaning {table_name}: {e}")
                        # Continue with other tables
                
                logger.info(f"Cleanup completed. Total records deleted: {total_deleted}")
        
        # Verify cleanup - check for remaining orphaned records
        logger.info("\nVerifying cleanup...")
        verification_queries = [
            ("Orphaned concepts", """
                SELECT COUNT(*) FROM concepts 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
            ("Orphaned questions", """
                SELECT COUNT(*) FROM questions 
                WHERE concept_id NOT IN (SELECT id FROM concepts)
            """),
            ("Orphaned test_questions", """
                SELECT COUNT(*) FROM test_questions 
                WHERE test_id NOT IN (SELECT id FROM tests)
            """),
            ("Orphaned test_responses", """
                SELECT COUNT(*) FROM test_responses 
                WHERE test_id NOT IN (SELECT id FROM tests)
            """),
            ("Orphaned content_chunks", """
                SELECT COUNT(*) FROM content_chunks 
                WHERE document_id NOT IN (SELECT id FROM documents)
            """),
            ("Orphaned visuals", """
                SELECT COUNT(*) FROM visuals 
                WHERE (concept_id IS NOT NULL AND concept_id NOT IN (SELECT id FROM concepts))
                   OR (question_id IS NOT NULL AND question_id NOT IN (SELECT id FROM questions))
            """),
        ]
        
        remaining_orphans = 0
        for check_name, query in verification_queries:
            try:
                result = await db.fetchrow(query)
                count = result[0] if result else 0
                if count > 0:
                    logger.warning(f"  ⚠️  {check_name}: {count} records still exist")
                    remaining_orphans += count
                else:
                    logger.info(f"  ✓ {check_name}: 0 (clean)")
            except Exception as e:
                logger.warning(f"  Error checking {check_name}: {e}")
        
        if remaining_orphans == 0:
            logger.info("\n✅ Database cleanup successful! No orphaned records found.")
        else:
            logger.warning(f"\n⚠️  Found {remaining_orphans} orphaned records. You may need to investigate.")
        
    except Exception as e:
        logger.error(f"Error during cleanup: {e}", exc_info=True)
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    try:
        asyncio.run(cleanup_orphaned_data())
    except KeyboardInterrupt:
        logger.info("\nCleanup interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)
