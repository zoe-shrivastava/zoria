"""User-related request/response schemas."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional
from datetime import datetime


class ParentCreate(BaseModel):
    """Create parent user schema (admin only)."""
    email: EmailStr
    password: str = Field(..., min_length=8)
    role: str = Field(default="parent", pattern="^(parent|admin)$")


class ParentResponse(BaseModel):
    """Parent response schema."""
    id: str
    email: str
    role: str
    created_at: datetime
    is_active: bool


class ChildCreate(BaseModel):
    """Create child profile schema."""
    name: str = Field(..., min_length=1, max_length=255)
    pin: Optional[str] = Field(None, min_length=4, max_length=6, description="4-6 digit PIN")
    grade: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=18)


class ChildUpdate(BaseModel):
    """Update child profile schema."""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    pin: Optional[str] = Field(None, min_length=4, max_length=6)
    grade: Optional[str] = None
    age: Optional[int] = Field(None, ge=0, le=18)
    avatar_url: Optional[str] = None
    # Cultural / context preferences
    preferred_language: Optional[str] = Field(None, max_length=50, description="e.g. English, Hindi, Spanish")
    interaction_tone: Optional[str] = Field(None, max_length=50, description="playful, encouraging, direct, gentle")
    example_preferences: Optional[str] = Field(None, max_length=100, description="storytelling, step-by-step, factual")
    interests: Optional[str] = Field(None, description="Comma-separated interests for examples")
    sensitive_topics_to_avoid: Optional[str] = Field(None, description="Topics to avoid (parent-configured)")
    prefer_indirect_guidance: Optional[bool] = Field(None, description="Use indirect phrasing for emotional topics")


class ChildProfileUpdate(BaseModel):
    """Child's own profile update (preferences only). Used by PATCH /api/v1/child/profile."""
    preferred_language: Optional[str] = Field(None, max_length=50)
    interaction_tone: Optional[str] = Field(None, max_length=50)
    example_preferences: Optional[str] = Field(None, max_length=100)
    interests: Optional[str] = None
    sensitive_topics_to_avoid: Optional[str] = None
    prefer_indirect_guidance: Optional[bool] = None


class ChildResponse(BaseModel):
    """Child response schema."""
    id: str
    parent_id: str
    name: str
    child_code: Optional[str] = None
    grade: Optional[str] = None
    age: Optional[int] = None
    avatar_url: Optional[str] = None
    created_at: datetime
    is_active: bool
    # Cultural / context preferences (optional)
    preferred_language: Optional[str] = None
    interaction_tone: Optional[str] = None
    example_preferences: Optional[str] = None
    interests: Optional[str] = None
    sensitive_topics_to_avoid: Optional[str] = None
    prefer_indirect_guidance: Optional[bool] = None
