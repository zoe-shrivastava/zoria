#!/usr/bin/env python3
"""
Script to create or verify default admin user.
Run this if the migration didn't create the admin user.
"""

import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from core.database import init_db, get_db
from core.security import password_hasher
from database.repositories.user_repository import UserRepository


async def create_admin():
    """Create default admin user if it doesn't exist."""
    # Initialize database
    db = init_db()
    await db.connect()
    
    try:
        user_repo = UserRepository(db)
        
        # Check if admin exists
        admin = await user_repo.get_parent_by_email("admin@zoria.com")
        
        if admin:
            print(f"✓ Admin user already exists:")
            print(f"  Email: {admin['email']}")
            print(f"  Role: {admin['role']}")
            print(f"  ID: {admin['id']}")
            print(f"  MFA Enabled: {admin.get('totp_enabled', False)}")
            
            # Test password
            if password_hasher.verify_password("Admin123!", admin["password_hash"]):
                print(f"  ✓ Password hash is correct")
            else:
                print(f"  ✗ Password hash is INCORRECT - updating...")
                # Update password
                new_hash = password_hasher.hash_password("Admin123!")
                await db.execute(
                    "UPDATE parents SET password_hash = $1 WHERE email = $2",
                    new_hash, "admin@zoria.com"
                )
                print(f"  ✓ Password hash updated")
        else:
            print("Creating admin user...")
            # Hash password
            password_hash = password_hasher.hash_password("Admin123!")
            
            # Create admin
            admin_id = await user_repo.create_parent(
                email="admin@zoria.com",
                password_hash=password_hash,
                role="admin"
            )
            
            print(f"✓ Admin user created successfully!")
            print(f"  Email: admin@zoria.com")
            print(f"  Password: Admin123!")
            print(f"  ID: {admin_id}")
            print(f"  ⚠️  IMPORTANT: Change password and set up MFA after first login!")
        
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(create_admin())
