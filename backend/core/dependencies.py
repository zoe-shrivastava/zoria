"""FastAPI dependencies for authentication and database access."""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from core.database import get_db, Database
from core.security import jwt_handler

# HTTP Bearer token security scheme
security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Database = Depends(get_db)
) -> dict:
    """Get current authenticated user from JWT token.
    
    Returns:
        Token payload with user information
        
    Raises:
        HTTPException: If token is invalid or expired
    """
    token = credentials.credentials
    payload = jwt_handler.decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return payload


async def get_current_parent(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current authenticated parent user.
    
    Returns:
        Token payload with parent information
        
    Raises:
        HTTPException: If user is not a parent or admin
    """
    role = current_user.get("role")
    if role not in ("parent", "admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Parent or admin role required."
        )
    
    return current_user


async def get_current_admin(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current authenticated admin user.
    
    Returns:
        Token payload with admin information
        
    Raises:
        HTTPException: If user is not an admin
    """
    role = current_user.get("role")
    if role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Admin role required."
        )
    
    return current_user


async def get_current_child(
    current_user: dict = Depends(get_current_user)
) -> dict:
    """Get current authenticated child user.
    
    Returns:
        Token payload with child information
        
    Raises:
        HTTPException: If user is not a child
    """
    role = current_user.get("role")
    if role != "child":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied. Child role required."
        )
    
    return current_user


def get_database() -> Database:
    """Dependency to get database instance.
    
    Returns:
        Database instance
    """
    return get_db()
