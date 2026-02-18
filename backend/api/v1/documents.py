"""Document API endpoints."""

from fastapi import APIRouter, HTTPException, status, Depends, UploadFile, File, Form, Body
from typing import Optional, List
from pydantic import BaseModel

from schemas.document import DocumentUploadResponse, DocumentResponse, DocumentListResponse
from services.document_service import DocumentService
from core.dependencies import get_current_parent, get_current_child, get_current_user
from core.config import settings

router = APIRouter()


class ReprocessRequest(BaseModel):
    cleanup_existing: bool = True
    skip_phase1: bool = False


@router.post("/upload", response_model=DocumentUploadResponse, status_code=status.HTTP_201_CREATED)
async def upload_document(
    file: UploadFile = File(...),
    child_id: Optional[str] = Form(None),
    child_ids: Optional[str] = Form(None),  # Comma-separated list of child IDs
    current_user: dict = Depends(get_current_user)
):
    """Upload and process a document.
    
    POST /api/v1/documents/upload
    
    - Parent can upload for any child/children (must provide child_id or child_ids)
    - Child can upload for themselves (child_id is auto-set)
    - child_ids: Comma-separated list of child UUIDs to attach document to multiple children
    """
    try:
        # Validate file
        if file.size > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"File too large. Maximum size: {settings.MAX_UPLOAD_SIZE_MB}MB"
            )
        
        if not file.filename.endswith('.pdf'):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are supported"
            )
        
        # Read file content
        file_content = await file.read()
        
        # Determine child_ids and parent_id based on user role
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        child_ids_list = []
        parent_id_param = None
        
        if user_role == "child":
            # Child can only upload for themselves
            child_ids_list = [user_id]
        elif user_role in ("parent", "admin"):
            # Parent/admin can upload for one or more children
            parent_id_param = user_id
            
            # Require child_ids (comma-separated) for parent/admin; no fallback to child_id
            if not child_ids or not child_ids.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="child_ids is required for parent/admin uploads (comma-separated list of child UUIDs)"
                )
            child_ids_list = [cid.strip() for cid in child_ids.split(',') if cid.strip()]
            if not child_ids_list:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="child_ids must contain at least one valid child UUID"
                )
        
        # Process document
        document_service = DocumentService()
        result = await document_service.process_document(
            file_content=file_content,
            filename=file.filename,
            child_ids=child_ids_list,
            parent_id=parent_id_param
        )
        
        return DocumentUploadResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to upload document: {str(e)}"
        )


@router.get("/", response_model=DocumentListResponse)
async def list_documents(
    child_id: Optional[str] = None,
    limit: int = 100,
    offset: int = 0,
    current_user: dict = Depends(get_current_user)
):
    """List documents with access control.
    
    GET /api/v1/documents
    
    - Child sees only their own documents
    - Parent sees documents for their children
    """
    try:
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        # Access control
        if user_role == "child":
            child_id = user_id  # Child can only see their own
        elif user_role in ("parent", "admin"):
            # Parent can filter by child_id or see all their children's documents
            if child_id:
                # Verify ownership (would need to check parent-child relationship)
                pass
        
        document_service = DocumentService()
        result = await document_service.list_documents(
            child_id=child_id,
            parent_id=user_id if user_role in ("parent", "admin") else None,
            limit=limit,
            offset=offset
        )
        
        return DocumentListResponse(**result)
        
    except HTTPException:
        raise
    except Exception as e:
        import logging
        logger = logging.getLogger(__name__)
        logger.error(f"Error listing documents: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to list documents: {str(e)}"
        )


@router.get("/{document_id}", response_model=DocumentResponse)
async def get_document(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Get a specific document.
    
    GET /api/v1/documents/{document_id}
    """
    try:
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        document_service = DocumentService()
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user_id,
            user_role=user_role
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        return DocumentResponse(**document)
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get document"
        )


@router.delete("/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_document(
    document_id: str,
    current_user: dict = Depends(get_current_user)
):
    """Delete a document.
    
    DELETE /api/v1/documents/{document_id}
    """
    try:
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        document_service = DocumentService()
        await document_service.delete_document(
            document_id=document_id,
            user_id=user_id,
            user_role=user_role
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete document"
        )


@router.post("/{document_id}/reprocess", response_model=DocumentUploadResponse)
async def reprocess_document(
    document_id: str,
    request: ReprocessRequest = Body(...),
    current_user: dict = Depends(get_current_user)
):
    """Reprocess a document.
    
    POST /api/v1/documents/{document_id}/reprocess
    
    - cleanup_existing: If True, delete existing chunks/questions/visuals first
    - skip_phase1: If True, skip Phase 1 and go straight to Phase 2
    """
    try:
        user_role = current_user.get("role")
        user_id = current_user.get("parent_id") or current_user.get("child_id")
        
        document_service = DocumentService()
        
        # Check access
        document = await document_service.get_document(
            document_id=document_id,
            user_id=user_id,
            user_role=user_role
        )
        
        if not document:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Document not found"
            )
        
        # Reprocess
        result = await document_service.reprocess_document(
            document_id=document_id,
            cleanup_existing=request.cleanup_existing,
            skip_phase1=request.skip_phase1
        )
        
        return DocumentUploadResponse(**result)
        
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to reprocess document: {str(e)}"
        )
