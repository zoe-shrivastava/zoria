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
