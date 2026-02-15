#!/usr/bin/env python3
"""Verify and fix migration 016 - Add behavioral tracking metadata column."""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def verify_and_fix():
    """Verify metadata column exists, create if missing."""
    db = init_db()
    await db.connect()
    
    try:
        # Check if metadata column exists
        column_exists = await db.fetchval("""
            SELECT EXISTS (
                SELECT 1 
                FROM information_schema.columns 
                WHERE table_name = 'test_responses' 
                AND column_name = 'metadata'
            )
        """)
        
        if column_exists:
            logger.info("✅ Metadata column exists in test_responses table")
            
            # Check if index exists
            index_exists = await db.fetchval("""
                SELECT EXISTS (
                    SELECT 1 
                    FROM pg_indexes 
                    WHERE tablename = 'test_responses' 
                    AND indexname = 'idx_test_responses_metadata'
                )
            """)
            
            if index_exists:
                logger.info("✅ Index idx_test_responses_metadata exists")
            else:
                logger.warning("⚠️  Index missing, creating...")
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_test_responses_metadata 
                    ON test_responses USING GIN(metadata)
                """)
                logger.info("✅ Index created")
        else:
            logger.warning("⚠️  Metadata column does NOT exist. Applying migration...")
            
            # Add column
            await db.execute("""
                ALTER TABLE test_responses 
                ADD COLUMN IF NOT EXISTS metadata JSONB
            """)
            logger.info("✅ Column added")
            
            # Create index
            await db.execute("""
                CREATE INDEX IF NOT EXISTS idx_test_responses_metadata 
                ON test_responses USING GIN(metadata)
            """)
            logger.info("✅ Index created")
            
            # Add comment
            await db.execute("""
                COMMENT ON COLUMN test_responses.metadata IS 
                'Behavioral tracking data (latency_ms, edit_count, hints_accessed, confidence_score) and evaluation results (error_type, misconception, method_detected)'
            """)
            logger.info("✅ Comment added")
            
            logger.info("✅ Migration 016 applied successfully!")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(verify_and_fix())
