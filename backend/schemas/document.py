"""Document-related request/response schemas."""

from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime


class DocumentUploadResponse(BaseModel):
    """Document upload response schema."""
    document_id: str
    filename: str
    status: str = Field(..., description="processing, completed, failed")
    message: str


class DocumentResponse(BaseModel):
    """Document response schema."""
    id: str
    child_ids: Optional[List[str]] = None
    child_id: Optional[str] = None  # Keep for backward compatibility
    parent_id: Optional[str] = None
    filename: str
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    markdown_content: Optional[str] = None
    concepts: Optional[Dict[str, Any]] = None
    status: Optional[str] = None
    uploaded_at: datetime
    processed_at: Optional[datetime] = None
    processing_started_at: Optional[datetime] = None
    processing_completed_at: Optional[datetime] = None
    is_active: bool


class DocumentListResponse(BaseModel):
    """Document list response schema."""
    documents: List[DocumentResponse]
    total: int
