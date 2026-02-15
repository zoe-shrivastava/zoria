"""Database migration runner for Zoria.

Run migrations to set up the database schema.
Migrations are tracked in schema_migrations table to prevent re-running.
"""

import asyncio
import logging
import os
import sys
from pathlib import Path

# Load environment variables from .env file if it exists
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # dotenv is optional
    pass

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import init_db, get_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def run_migrations():
    """Run all migration scripts with tracking to prevent re-running."""
    # Initialize database
    db = init_db()
    await db.connect()
    
    try:
        # Create schema_migrations table if it doesn't exist
        await db.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                migration_name VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # Get migrations directory
        migrations_dir = Path(__file__).parent / "migrations"
        
        # Get all SQL migration files, sorted by name
        # Include migrations 00-19 (supports up to 199 migrations)
        migration_files = sorted([
            f for f in migrations_dir.glob("*.sql")
            if f.name.startswith(("00", "01", "02", "03", "04", "05", "06", "07", "08", "09", "10", "11", "12", "13", "14", "15", "16", "17", "18", "19"))
        ], key=lambda x: x.name)
        
        if not migration_files:
            logger.warning("No migration files found")
            return
        
        logger.info(f"Found {len(migration_files)} migration files")
        
        # Get already applied migrations
        applied_migrations = await db.fetch(
            "SELECT migration_name FROM schema_migrations"
        )
        applied_set = {row["migration_name"] for row in applied_migrations}
        
        logger.info(f"Found {len(applied_set)} already applied migrations")
        
        # Run each migration that hasn't been applied yet
        for migration_file in migration_files:
            migration_name = migration_file.name
            
            # Skip if already applied
            if migration_name in applied_set:
                logger.info(f"⏭️  Skipping {migration_name} (already applied)")
                continue
            
            logger.info(f"🔄 Running migration: {migration_name}")
            
            # Read migration SQL
            with open(migration_file, 'r', encoding='utf-8') as f:
                migration_sql = f.read()
            
            try:
                # Run migration in a transaction
                async with db.pool.acquire() as conn:
                    async with conn.transaction():
                        await conn.execute(migration_sql)
                        # Record that migration was applied
                        await conn.execute(
                            "INSERT INTO schema_migrations (migration_name) VALUES ($1) ON CONFLICT DO NOTHING",
                            migration_name
                        )
                logger.info(f"✅ Migration {migration_name} completed successfully")
            except Exception as e:
                error_str = str(e).lower()
                # Some errors are expected (e.g., extension already exists, column already exists)
                if "already exists" in error_str or "duplicate" in error_str:
                    logger.info(f"  (Migration {migration_name} already applied or partially applied)")
                    # Mark as applied even if it was already done
                    await db.execute(
                        "INSERT INTO schema_migrations (migration_name) VALUES ($1) ON CONFLICT DO NOTHING",
                        migration_name
                    )
                else:
                    logger.error(f"❌ Migration {migration_name} failed: {e}")
                    raise
        
        logger.info("✅ All migrations completed successfully")
        
    except Exception as e:
        logger.error(f"❌ Migration failed: {e}")
        raise
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
