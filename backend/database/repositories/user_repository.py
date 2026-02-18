"""User repository for database operations."""

import uuid
from typing import Optional, List
from datetime import datetime

from core.database import get_db, Database
from core.security import generate_child_code, generate_child_code_from_name


class UserRepository:
    """Repository for user (parent/child) database operations."""
    
    def __init__(self, db: Database):
        """Initialize repository with database instance."""
        self.db = db
    
    # Parent operations
    
    async def create_parent(
        self,
        email: str,
        password_hash: str,
        role: str = "parent",
        mfa_secret: Optional[str] = None
    ) -> str:
        """Create a new parent user.
        
        Args:
            email: Parent email
            password_hash: Hashed password
            role: User role ('parent' or 'admin')
            mfa_secret: Optional MFA secret (for MFA setup)
            
        Returns:
            Parent UUID
        """
        parent_id = str(uuid.uuid4())
        await self.db.execute(
            """
            INSERT INTO parents (id, email, password_hash, role, mfa_secret, created_at)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            parent_id, email, password_hash, role, mfa_secret, datetime.utcnow()
        )
        return parent_id
    
    async def get_parent_by_email(self, email: str) -> Optional[dict]:
        """Get parent by email.
        
        Args:
            email: Parent email
            
        Returns:
            Parent record or None
        """
        return await self.db.fetchrow(
            """
            SELECT id, email, password_hash, role, mfa_secret, totp_enabled, created_at, last_login, is_active
            FROM parents 
            WHERE email = $1 AND is_active = TRUE
            """,
            email
        )
    
    async def get_parent_by_id(self, parent_id: str) -> Optional[dict]:
        """Get parent by ID.
        
        Args:
            parent_id: Parent UUID
            
        Returns:
            Parent record or None
        """
        return await self.db.fetchrow(
            "SELECT * FROM parents WHERE id = $1 AND is_active = TRUE",
            parent_id
        )
    
    async def list_parents(self, limit: int = 100, offset: int = 0) -> List[dict]:
        """List all parents (admin only).
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of parent records
        """
        return await self.db.fetch(
            """
            SELECT id, email, role, created_at, last_login, is_active
            FROM parents
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def update_parent_last_login(self, parent_id: str) -> None:
        """Update parent's last login timestamp.
        
        Args:
            parent_id: Parent UUID
        """
        await self.db.execute(
            "UPDATE parents SET last_login = $1 WHERE id = $2",
            datetime.utcnow(), parent_id
        )
    
    async def deactivate_parent(self, parent_id: str) -> None:
        """Deactivate a parent account.
        
        Args:
            parent_id: Parent UUID
        """
        await self.db.execute(
            "UPDATE parents SET is_active = FALSE WHERE id = $1",
            parent_id
        )
    
    async def enable_mfa(self, parent_id: str) -> None:
        """Enable MFA for a parent (set totp_enabled = TRUE).
        
        Args:
            parent_id: Parent UUID
        """
        await self.db.execute(
            "UPDATE parents SET totp_enabled = TRUE WHERE id = $1",
            parent_id
        )
    
    async def update_parent_mfa_secret(self, parent_id: str, mfa_secret: str) -> None:
        """Update MFA secret for a parent.
        
        Args:
            parent_id: Parent UUID
            mfa_secret: MFA secret
        """
        await self.db.execute(
            "UPDATE parents SET mfa_secret = $1 WHERE id = $2",
            mfa_secret, parent_id
        )
    
    # Child operations
    
    async def create_child(
        self,
        parent_id: str,
        name: str,
        pin_hash: Optional[str] = None,
        grade: Optional[str] = None,
        age: Optional[int] = None,
        avatar_url: Optional[str] = None
    ) -> str:
        """Create a new child profile with a unique child_code.
        
        Args:
            parent_id: Parent UUID
            name: Child name
            pin_hash: Hashed PIN (optional)
            grade: Child grade
            age: Child age
            avatar_url: Avatar URL
            
        Returns:
            Child UUID
        """
        child_id = str(uuid.uuid4())
        
        # Generate unique child_code based on name
        base_code = generate_child_code_from_name(name)
        child_code = None
        max_attempts = 100  # Allow up to 100 variations (CHDNAME, CHDNAME1, CHDNAME2, etc.)
        
        # Check if base code exists, if so append numbers
        for attempt in range(max_attempts):
            if attempt == 0:
                candidate_code = base_code
            else:
                # Append number to make it unique (CHDNAME1, CHDNAME2, etc.)
                candidate_code = f"{base_code}{attempt}"
            
            # Check if this code already exists
            existing = await self.db.fetchrow(
                "SELECT id FROM children WHERE child_code = $1",
                candidate_code
            )
            if not existing:
                child_code = candidate_code
                break
        
        # Final fallback: use random code if name-based generation failed
        if not child_code:
            # Try random code as last resort
            for _ in range(10):
                candidate_code = generate_child_code()
                existing = await self.db.fetchrow(
                    "SELECT id FROM children WHERE child_code = $1",
                    candidate_code
                )
                if not existing:
                    child_code = candidate_code
                    break
            else:
                # Ultimate fallback: UUID-based
                child_code = f"CHD{str(uuid.uuid4()).replace('-', '').upper()[:8]}"
        
        await self.db.execute(
            """
            INSERT INTO children (id, parent_id, name, pin_hash, grade, age, avatar_url, child_code, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            """,
            child_id, parent_id, name, pin_hash, grade, age, avatar_url, child_code, datetime.utcnow()
        )
        return child_id
    
    async def get_child_by_id(self, child_id: str) -> Optional[dict]:
        """Get child by ID.
        
        Args:
            child_id: Child UUID
            
        Returns:
            Child record or None
        """
        return await self.db.fetchrow(
            """
            SELECT id, parent_id, name, pin_hash, child_code, grade, age, avatar_url, created_at, is_active,
                   preferred_language, interaction_tone, example_preferences, interests,
                   sensitive_topics_to_avoid, prefer_indirect_guidance
            FROM children 
            WHERE id = $1 AND is_active = TRUE
            """,
            child_id
        )
    
    async def get_child_by_code(self, child_code: str) -> Optional[dict]:
        """Get child by child_code.
        
        Args:
            child_code: Child code (e.g., "CHD123ABC")
            
        Returns:
            Child record or None
        """
        return await self.db.fetchrow(
            """
            SELECT id, parent_id, name, pin_hash, child_code, grade, age, avatar_url, created_at, is_active,
                   preferred_language, interaction_tone, example_preferences, interests,
                   sensitive_topics_to_avoid, prefer_indirect_guidance
            FROM children 
            WHERE child_code = $1 AND is_active = TRUE
            """,
            child_code.upper()
        )
    
    async def get_children_by_parent(self, parent_id: str) -> List[dict]:
        """Get all children for a parent.
        
        Args:
            parent_id: Parent UUID
            
        Returns:
            List of child records
        """
        return await self.db.fetch(
            """
            SELECT id, parent_id, name, pin_hash, child_code, grade, age, avatar_url, created_at, is_active,
                   preferred_language, interaction_tone, example_preferences, interests,
                   sensitive_topics_to_avoid, prefer_indirect_guidance
            FROM children
            WHERE parent_id = $1 AND is_active = TRUE
            ORDER BY created_at DESC
            """,
            parent_id
        )
    
    async def get_all_children(self, limit: int = 1000, offset: int = 0) -> List[dict]:
        """Get all children (admin only).
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of child records
        """
        return await self.db.fetch(
            """
            SELECT id, parent_id, name, pin_hash, child_code, grade, age, avatar_url, created_at, is_active,
                   preferred_language, interaction_tone, example_preferences, interests,
                   sensitive_topics_to_avoid, prefer_indirect_guidance
            FROM children
            WHERE is_active = TRUE
            ORDER BY created_at DESC
            LIMIT $1 OFFSET $2
            """,
            limit, offset
        )
    
    async def update_child(
        self,
        child_id: str,
        name: Optional[str] = None,
        pin_hash: Optional[str] = None,
        grade: Optional[str] = None,
        age: Optional[int] = None,
        avatar_url: Optional[str] = None,
        preferred_language: Optional[str] = None,
        interaction_tone: Optional[str] = None,
        example_preferences: Optional[str] = None,
        interests: Optional[str] = None,
        sensitive_topics_to_avoid: Optional[str] = None,
        prefer_indirect_guidance: Optional[bool] = None
    ) -> None:
        """Update child profile.
        
        Args:
            child_id: Child UUID
            name: Child name
            pin_hash: Hashed PIN
            grade: Child grade
            age: Child age
            avatar_url: Avatar URL
            preferred_language: Preferred language for content
            interaction_tone: playful, encouraging, direct, gentle
            example_preferences: storytelling, step-by-step, factual
            interests: Comma-separated interests
            sensitive_topics_to_avoid: Topics to avoid
            prefer_indirect_guidance: Use indirect phrasing for emotional topics
        """
        updates = []
        params = []
        param_idx = 1
        
        if name is not None:
            updates.append(f"name = ${param_idx}")
            params.append(name)
            param_idx += 1
        if pin_hash is not None:
            updates.append(f"pin_hash = ${param_idx}")
            updates.append(f"pin_set_at = ${param_idx + 1}")
            params.extend([pin_hash, datetime.utcnow()])
            param_idx += 2
        if grade is not None:
            updates.append(f"grade = ${param_idx}")
            params.append(grade)
            param_idx += 1
        if age is not None:
            updates.append(f"age = ${param_idx}")
            params.append(age)
            param_idx += 1
        if avatar_url is not None:
            updates.append(f"avatar_url = ${param_idx}")
            params.append(avatar_url)
            param_idx += 1
        if preferred_language is not None:
            updates.append(f"preferred_language = ${param_idx}")
            params.append(preferred_language)
            param_idx += 1
        if interaction_tone is not None:
            updates.append(f"interaction_tone = ${param_idx}")
            params.append(interaction_tone)
            param_idx += 1
        if example_preferences is not None:
            updates.append(f"example_preferences = ${param_idx}")
            params.append(example_preferences)
            param_idx += 1
        if interests is not None:
            updates.append(f"interests = ${param_idx}")
            params.append(interests)
            param_idx += 1
        if sensitive_topics_to_avoid is not None:
            updates.append(f"sensitive_topics_to_avoid = ${param_idx}")
            params.append(sensitive_topics_to_avoid)
            param_idx += 1
        if prefer_indirect_guidance is not None:
            updates.append(f"prefer_indirect_guidance = ${param_idx}")
            params.append(prefer_indirect_guidance)
            param_idx += 1
        
        if updates:
            updates.append(f"updated_at = ${param_idx}")
            params.append(datetime.utcnow())
            params.append(child_id)
            
            await self.db.execute(
                f"UPDATE children SET {', '.join(updates)} WHERE id = ${param_idx + 1}",
                *params
            )
    
    async def delete_child(self, child_id: str) -> None:
        """Delete (deactivate) a child profile.
        
        Args:
            child_id: Child UUID
        """
        await self.db.execute(
            "UPDATE children SET is_active = FALSE WHERE id = $1",
            child_id
        )
