"""Child API endpoints."""

from fastapi import APIRouter, HTTPException, status, Depends

from schemas.user import ChildResponse
from services.user_service import UserService
from core.dependencies import get_current_child

router = APIRouter()


@router.get("/profile", response_model=ChildResponse)
async def get_profile(child: dict = Depends(get_current_child)):
    """Get child's own profile.
    
    GET /api/v1/child/profile
    """
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
