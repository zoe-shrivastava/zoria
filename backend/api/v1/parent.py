"""Parent API endpoints."""

from fastapi import APIRouter, HTTPException, status, Depends
from typing import List

from schemas.user import ChildCreate, ChildUpdate, ChildResponse
from services.user_service import UserService
from core.dependencies import get_current_parent

router = APIRouter()


@router.post("/children", response_model=ChildResponse, status_code=status.HTTP_201_CREATED)
async def create_child(
    request: ChildCreate,
    parent: dict = Depends(get_current_parent)
):
    """Create a new child profile.
    
    POST /api/v1/parent/children
    """
    try:
        user_service = UserService()
        result = await user_service.create_child(
            parent_id=parent["parent_id"],
            name=request.name,
            pin=request.pin,
            grade=request.grade,
            age=request.age
        )
        return ChildResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create child"
        )


@router.get("/children", response_model=List[ChildResponse])
async def list_children(parent: dict = Depends(get_current_parent)):
    """List all children for the current parent.
    
    GET /api/v1/parent/children
    """
    try:
        user_service = UserService()
        children = await user_service.list_children(parent["parent_id"])
        return [ChildResponse(**c) for c in children]
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list children"
        )


@router.get("/children/{child_id}", response_model=ChildResponse)
async def get_child(
    child_id: str,
    parent: dict = Depends(get_current_parent)
):
    """Get a specific child profile.
    
    GET /api/v1/parent/children/{child_id}
    """
    try:
        user_service = UserService()
        child = await user_service.get_child(child_id, parent["parent_id"])
        if not child:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Child not found"
            )
        return ChildResponse(**child)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get child"
        )


@router.put("/children/{child_id}", response_model=ChildResponse)
async def update_child(
    child_id: str,
    request: ChildUpdate,
    parent: dict = Depends(get_current_parent)
):
    """Update a child profile.
    
    PUT /api/v1/parent/children/{child_id}
    """
    try:
        user_service = UserService()
        result = await user_service.update_child(
            child_id=child_id,
            parent_id=parent["parent_id"],
            name=request.name,
            pin=request.pin,
            grade=request.grade,
            age=request.age,
            avatar_url=request.avatar_url
        )
        return ChildResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update child"
        )


@router.delete("/children/{child_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_child(
    child_id: str,
    parent: dict = Depends(get_current_parent)
):
    """Delete a child profile.
    
    DELETE /api/v1/parent/children/{child_id}
    """
    try:
        user_service = UserService()
        await user_service.delete_child(child_id, parent["parent_id"])
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete child"
        )
