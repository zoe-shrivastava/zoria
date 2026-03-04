"""Authentication API endpoints."""

import json
import logging
from fastapi import APIRouter, HTTPException, status, Depends, Request
from fastapi.security import HTTPBearer

from schemas.auth import (
    LoginRequest, LoginResponse, ChildLoginRequest,
    CompleteMFASetupRequest
)
from schemas.admin_settings import TimestampSettings
from services.auth_service import AuthService
from core.dependencies import get_current_user, get_database
from core.database import Database, get_db

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
async def get_current_user_info(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_database)
):
    """Get current authenticated user information.
    
    GET /api/v1/auth/me
    Enriches parent/admin with email from DB so the frontend always has a display name
    (covers old JWTs that did not include email).
    """
    role = current_user.get("role")
    user = dict(current_user)

    if role in ("parent", "admin") and not user.get("email"):
        parent_id = current_user.get("parent_id")
        if parent_id:
            from database.repositories.user_repository import UserRepository
            user_repo = UserRepository(db)
            parent = await user_repo.get_parent_by_id(str(parent_id))
            if parent and parent.get("email"):
                user["email"] = parent["email"]
                user["id"] = str(parent["id"])

    return {
        "user": user,
        "role": role
    }


def _is_undefined_table_error(exc: Exception) -> bool:
    """True if the exception is asyncpg 'relation does not exist'."""
    return getattr(exc, "__class__", None).__name__ == "UndefinedTableError" or (
        "admin_settings" in str(exc) and "does not exist" in str(exc).lower()
    )


@router.get("/settings/timestamps", response_model=TimestampSettings)
async def get_timestamp_display_settings(
    current_user: dict = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get timestamp display settings (admin-configured, applies to all roles).

    GET /api/v1/auth/settings/timestamps
    Any authenticated user (parent, child, admin) can read. If admin_settings
    table is missing, returns defaults.
    """
    if db.pool is None:
        await db.connect()

    try:
        row = await db.fetchrow(
            "SELECT value FROM admin_settings WHERE key = 'timestamp_settings'"
        )
    except Exception as e:
        if _is_undefined_table_error(e):
            return TimestampSettings()
        raise

    if not row or row.get("value") is None:
        return TimestampSettings()

    value = row["value"]
    if isinstance(value, str):
        value = json.loads(value) if value.strip() else {}
    if not isinstance(value, dict):
        value = {}
    return TimestampSettings(**value)
