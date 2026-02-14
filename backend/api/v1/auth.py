"""Authentication API endpoints."""

import logging
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer

from schemas.auth import (
    LoginRequest, LoginResponse, ChildLoginRequest,
    CompleteMFASetupRequest
)
from services.auth_service import AuthService
from core.dependencies import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter()
security = HTTPBearer()


# Registration is disabled - only admins can create parent accounts
# Use POST /api/v1/admin/parents instead (requires admin authentication)

@router.post("/login", response_model=LoginResponse)
async def login(request: LoginRequest):
    """Login as parent or admin with MFA support.
    
    POST /api/v1/auth/login
    
    Returns:
        - If MFA setup required: mfa_setup_required=True with QR code
        - If MFA code required: mfa_required=True
        - If successful: token and user info
    """
    try:
        auth_service = AuthService()
        result = await auth_service.login_parent(
            email=request.email,
            password=request.password,
            mfa_code=request.mfa_code
        )
        return LoginResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/child/login", response_model=LoginResponse)
async def login_child(request: ChildLoginRequest):
    """Login as child using PIN.
    
    POST /api/v1/auth/child/login
    """
    logger.info(f"Child login request received for child_id: {request.child_id[:10]}... (masked)")
    try:
        auth_service = AuthService()
        result = await auth_service.login_child(
            child_identifier=request.child_id,  # Can be UUID or child_code
            pin=request.pin
        )
        logger.info(f"Child login successful for child_id: {request.child_id[:10]}...")
        return LoginResponse(**result)
    except ValueError as e:
        logger.warning(f"Child login failed (invalid credentials) for child_id: {request.child_id[:10]}... - {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Child login error for child_id: {request.child_id[:10]}... - {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Login failed"
        )


@router.post("/mfa/complete-setup", response_model=LoginResponse)
async def complete_mfa_setup(request: CompleteMFASetupRequest):
    """Complete MFA setup by verifying TOTP code.
    
    POST /api/v1/auth/mfa/complete-setup
    """
    try:
        auth_service = AuthService()
        result = await auth_service.complete_mfa_setup(
            parent_id=request.parent_id,
            password=request.password,
            mfa_code=request.mfa_code
        )
        return LoginResponse(**result)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="MFA setup failed"
        )


@router.get("/me")
async def get_current_user_info(current_user: dict = Depends(get_current_user)):
    """Get current authenticated user information.
    
    GET /api/v1/auth/me
    """
    return {
        "user": current_user,
        "role": current_user.get("role")
    }
