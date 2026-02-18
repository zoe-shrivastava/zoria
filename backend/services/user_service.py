"""User management service for parents and children."""

import logging
from typing import List, Optional, Dict, Any

from core.database import get_db
from core.security import pin_hasher
from database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class UserService:
    """Service for user management operations."""
    
    def __init__(self):
        """Initialize user service."""
        self.db = get_db()
        self.user_repo = UserRepository(self.db)
    
    # Parent operations
    
    async def create_parent_user(
        self,
        email: str,
        password: str,
        role: str = "parent"
    ) -> Dict[str, Any]:
        """Create a new parent user (admin only).
        
        Args:
            email: Parent email
            password: Plain text password
            role: User role ('parent' or 'admin')
            
        Returns:
            Created parent information
            
        Raises:
            ValueError: If email already exists
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        from core.security import password_hasher, mfa_handler
        
        # Check if email already exists
        existing = await self.user_repo.get_parent_by_email(email)
        if existing:
            raise ValueError("Email already registered")
        
        # Hash password
        password_hash = password_hasher.hash_password(password)
        
        # Generate MFA secret (mandatory for all users)
        mfa_secret, _, _ = mfa_handler.generate_mfa_setup(email)
        
        # Create parent with MFA secret
        parent_id = await self.user_repo.create_parent(
            email=email,
            password_hash=password_hash,
            role=role,
            mfa_secret=mfa_secret
        )
        
        # Get created parent
        parent = await self.user_repo.get_parent_by_id(parent_id)
        
        return {
            "id": str(parent["id"]),
            "email": parent["email"],
            "role": parent["role"],
            "created_at": parent["created_at"],
            "is_active": parent["is_active"]
        }
    
    async def list_parents(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        """List all parents (admin only).
        
        Args:
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of parent records
        """
        parents = await self.user_repo.list_parents(limit=limit, offset=offset)
        return [
            {
                "id": str(p["id"]),
                "email": p["email"],
                "role": p["role"],
                "created_at": p["created_at"],
                "last_login": p.get("last_login"),
                "is_active": p["is_active"]
            }
            for p in parents
        ]
    
    async def deactivate_parent(self, parent_id: str) -> None:
        """Deactivate a parent account (admin only).
        
        Args:
            parent_id: Parent UUID
        """
        await self.user_repo.deactivate_parent(parent_id)
    
    # Child operations
    
    async def create_child(
        self,
        parent_id: str,
        name: str,
        pin: Optional[str] = None,
        grade: Optional[str] = None,
        age: Optional[int] = None,
        avatar_url: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new child profile.
        
        Args:
            parent_id: Parent UUID
            name: Child name
            pin: Plain text PIN (optional)
            grade: Child grade
            age: Child age
            avatar_url: Avatar URL
            
        Returns:
            Created child information
        """
        # Hash PIN if provided
        pin_hash = pin_hasher.hash_pin(pin) if pin else None
        
        # Create child
        child_id = await self.user_repo.create_child(
            parent_id=parent_id,
            name=name,
            pin_hash=pin_hash,
            grade=grade,
            age=age,
            avatar_url=avatar_url
        )
        
        # Get created child
        child = await self.user_repo.get_child_by_id(child_id)
        
        return {
            "id": str(child["id"]),
            "parent_id": str(child["parent_id"]),
            "name": child["name"],
            "child_code": child.get("child_code"),
            "grade": child.get("grade"),
            "age": child.get("age"),
            "avatar_url": child.get("avatar_url"),
            "created_at": child["created_at"],
            "is_active": child["is_active"],
            "preferred_language": child.get("preferred_language"),
            "interaction_tone": child.get("interaction_tone"),
            "example_preferences": child.get("example_preferences"),
            "interests": child.get("interests"),
            "sensitive_topics_to_avoid": child.get("sensitive_topics_to_avoid"),
            "prefer_indirect_guidance": child.get("prefer_indirect_guidance"),
        }
    
    async def get_child(self, child_id: str, parent_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """Get child by ID (with ownership check).
        
        Args:
            child_id: Child UUID
            parent_id: Parent UUID (for ownership verification)
            
        Returns:
            Child information or None
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        child = await self.user_repo.get_child_by_id(child_id)
        if not child:
            return None
        
        # Verify ownership if parent_id provided
        if parent_id and str(child["parent_id"]) != parent_id:
            return None
        
        return {
            "id": str(child["id"]),
            "parent_id": str(child["parent_id"]),
            "name": child["name"],
            "child_code": child.get("child_code"),
            "grade": child.get("grade"),
            "age": child.get("age"),
            "avatar_url": child.get("avatar_url"),
            "created_at": child["created_at"],
            "is_active": child["is_active"],
            "preferred_language": child.get("preferred_language"),
            "interaction_tone": child.get("interaction_tone"),
            "example_preferences": child.get("example_preferences"),
            "interests": child.get("interests"),
            "sensitive_topics_to_avoid": child.get("sensitive_topics_to_avoid"),
            "prefer_indirect_guidance": child.get("prefer_indirect_guidance"),
        }
    
    async def list_children(self, parent_id: Optional[str] = None, limit: int = 1000, offset: int = 0) -> List[Dict[str, Any]]:
        """List children - for a parent or all children (admin).
        
        Args:
            parent_id: Parent UUID (if None, returns all children for admin)
            limit: Maximum number of results
            offset: Offset for pagination
            
        Returns:
            List of child records
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        if parent_id:
            children = await self.user_repo.get_children_by_parent(parent_id)
        else:
            # Admin access - get all children
            children = await self.user_repo.get_all_children(limit, offset)
        
        return [
            {
                "id": str(c["id"]),
                "parent_id": str(c["parent_id"]),
                "name": c["name"],
                "child_code": c.get("child_code"),
                "grade": c.get("grade"),
                "age": c.get("age"),
                "avatar_url": c.get("avatar_url"),
                "created_at": c["created_at"],
                "is_active": c["is_active"],
                "preferred_language": c.get("preferred_language"),
                "interaction_tone": c.get("interaction_tone"),
                "example_preferences": c.get("example_preferences"),
                "interests": c.get("interests"),
                "sensitive_topics_to_avoid": c.get("sensitive_topics_to_avoid"),
                "prefer_indirect_guidance": c.get("prefer_indirect_guidance"),
            }
            for c in children
        ]
    
    async def update_child(
        self,
        child_id: str,
        parent_id: str,
        name: Optional[str] = None,
        pin: Optional[str] = None,
        grade: Optional[str] = None,
        age: Optional[int] = None,
        avatar_url: Optional[str] = None,
        preferred_language: Optional[str] = None,
        interaction_tone: Optional[str] = None,
        example_preferences: Optional[str] = None,
        interests: Optional[str] = None,
        sensitive_topics_to_avoid: Optional[str] = None,
        prefer_indirect_guidance: Optional[bool] = None
    ) -> Dict[str, Any]:
        """Update child profile.
        
        Args:
            child_id: Child UUID
            parent_id: Parent UUID (for ownership verification)
            name: Child name
            pin: Plain text PIN
            grade: Child grade
            age: Child age
            avatar_url: Avatar URL
            preferred_language: Preferred language for content
            interaction_tone: playful, encouraging, direct, gentle
            example_preferences: storytelling, step-by-step, factual
            interests: Comma-separated interests
            sensitive_topics_to_avoid: Topics to avoid
            prefer_indirect_guidance: Use indirect phrasing for emotional topics
            
        Returns:
            Updated child information
            
        Raises:
            ValueError: If child not found or ownership mismatch
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        # Verify ownership
        child = await self.user_repo.get_child_by_id(child_id)
        if not child:
            raise ValueError("Child not found")
        
        if str(child["parent_id"]) != parent_id:
            raise ValueError("Access denied")
        
        # Hash PIN if provided
        pin_hash = pin_hasher.hash_pin(pin) if pin else None
        
        # Update child
        await self.user_repo.update_child(
            child_id=child_id,
            name=name,
            pin_hash=pin_hash,
            grade=grade,
            age=age,
            avatar_url=avatar_url,
            preferred_language=preferred_language,
            interaction_tone=interaction_tone,
            example_preferences=example_preferences,
            interests=interests,
            sensitive_topics_to_avoid=sensitive_topics_to_avoid,
            prefer_indirect_guidance=prefer_indirect_guidance
        )
        
        # Get updated child
        updated = await self.user_repo.get_child_by_id(child_id)
        return {
            "id": str(updated["id"]),
            "parent_id": str(updated["parent_id"]),
            "name": updated["name"],
            "child_code": updated.get("child_code"),
            "grade": updated.get("grade"),
            "age": updated.get("age"),
            "avatar_url": updated.get("avatar_url"),
            "created_at": updated["created_at"],
            "is_active": updated["is_active"],
            "preferred_language": updated.get("preferred_language"),
            "interaction_tone": updated.get("interaction_tone"),
            "example_preferences": updated.get("example_preferences"),
            "interests": updated.get("interests"),
            "sensitive_topics_to_avoid": updated.get("sensitive_topics_to_avoid"),
            "prefer_indirect_guidance": updated.get("prefer_indirect_guidance"),
        }
    
    async def update_child_preferences(
        self,
        child_id: str,
        **preferences: Any
    ) -> Dict[str, Any]:
        """Update only preference fields for a child (e.g. when child updates own profile).
        
        Args:
            child_id: Child UUID
            **preferences: preferred_language, interaction_tone, example_preferences,
                          interests, sensitive_topics_to_avoid, prefer_indirect_guidance
            
        Returns:
            Updated child information
        """
        allowed = {
            "preferred_language", "interaction_tone", "example_preferences",
            "interests", "sensitive_topics_to_avoid", "prefer_indirect_guidance"
        }
        payload = {k: v for k, v in preferences.items() if k in allowed}
        if not payload:
            child = await self.user_repo.get_child_by_id(child_id)
            if not child:
                raise ValueError("Child not found")
            return {
                "id": str(child["id"]),
                "parent_id": str(child["parent_id"]),
                "name": child["name"],
                "child_code": child.get("child_code"),
                "grade": child.get("grade"),
                "age": child.get("age"),
                "avatar_url": child.get("avatar_url"),
                "created_at": child["created_at"],
                "is_active": child["is_active"],
                "preferred_language": child.get("preferred_language"),
                "interaction_tone": child.get("interaction_tone"),
                "example_preferences": child.get("example_preferences"),
                "interests": child.get("interests"),
                "sensitive_topics_to_avoid": child.get("sensitive_topics_to_avoid"),
                "prefer_indirect_guidance": child.get("prefer_indirect_guidance"),
            }
        await self.user_repo.update_child(child_id=child_id, **payload)
        updated = await self.user_repo.get_child_by_id(child_id)
        return {
            "id": str(updated["id"]),
            "parent_id": str(updated["parent_id"]),
            "name": updated["name"],
            "child_code": updated.get("child_code"),
            "grade": updated.get("grade"),
            "age": updated.get("age"),
            "avatar_url": updated.get("avatar_url"),
            "created_at": updated["created_at"],
            "is_active": updated["is_active"],
            "preferred_language": updated.get("preferred_language"),
            "interaction_tone": updated.get("interaction_tone"),
            "example_preferences": updated.get("example_preferences"),
            "interests": updated.get("interests"),
            "sensitive_topics_to_avoid": updated.get("sensitive_topics_to_avoid"),
            "prefer_indirect_guidance": updated.get("prefer_indirect_guidance"),
        }
    
    async def delete_child(self, child_id: str, parent_id: str) -> None:
        """Delete a child profile.
        
        Args:
            child_id: Child UUID
            parent_id: Parent UUID (for ownership verification)
            
        Raises:
            ValueError: If child not found or ownership mismatch
        """
        # Ensure database is connected
        if self.db.pool is None:
            await self.db.connect()
        
        # Verify ownership
        child = await self.user_repo.get_child_by_id(child_id)
        if not child:
            raise ValueError("Child not found")
        
        if str(child["parent_id"]) != parent_id:
            raise ValueError("Access denied")
        
        await self.user_repo.delete_child(child_id)
