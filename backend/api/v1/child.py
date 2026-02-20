"""Child API endpoints."""

from fastapi import APIRouter, HTTPException, status, Depends, Response

from schemas.user import ChildResponse, ChildProfileUpdate
from services.user_service import UserService
from core.dependencies import get_current_child

router = APIRouter()


@router.get("/profile", response_model=ChildResponse)
async def get_profile(response: Response, child: dict = Depends(get_current_child)):
    """Get child's own profile. Never cached so parent-updated data is always fresh on login."""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    try:
        user_service = UserService()
        child_data = await user_service.get_child(child["child_id"])
        if not child_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Profile not found"
            )
        return ChildResponse(**child_data)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get profile"
        )


@router.patch("/profile", response_model=ChildResponse)
async def update_profile(
    request: ChildProfileUpdate,
    child: dict = Depends(get_current_child)
):
    """Update child's own preferences (language, tone, examples, etc.).
    
    PATCH /api/v1/child/profile
    Body: { preferred_language?, interaction_tone?, example_preferences?, interests?, sensitive_topics_to_avoid?, prefer_indirect_guidance? }
    """
    try:
        user_service = UserService()
        child_id = child["child_id"]
        # Only update fields that were sent (non-None); use model_dump(exclude_unset=True)
        payload = request.model_dump(exclude_unset=True)
        if not payload:
            child_data = await user_service.get_child(child_id)
            if not child_data:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found")
            return ChildResponse(**child_data)
        result = await user_service.update_child_preferences(child_id, **payload)
        return ChildResponse(**result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )
