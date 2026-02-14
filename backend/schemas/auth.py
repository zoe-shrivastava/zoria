"""Authentication request/response schemas."""

from pydantic import BaseModel, EmailStr, Field
from typing import Optional


class LoginRequest(BaseModel):
    """Login request schema."""
    email: EmailStr
    password: str
    mfa_code: Optional[str] = Field(None, description="6-digit TOTP code (required if MFA is enabled)")


class ChildLoginRequest(BaseModel):
    """Child PIN login request schema."""
    child_id: str = Field(..., description="Child UUID or child_code (e.g., CHD123ABC)")
    pin: str = Field(..., min_length=4, max_length=6, description="4-6 digit PIN")


class LoginResponse(BaseModel):
    """Login response schema."""
    token: Optional[str] = None
    user: Optional[dict] = None
    role: Optional[str] = None
    mfa_required: Optional[bool] = None
    mfa_setup_required: Optional[bool] = None
    email: Optional[str] = None
    parent_id: Optional[str] = None
    totp_secret: Optional[str] = None
    provisioning_uri: Optional[str] = None
    qr_code: Optional[str] = None
    message: Optional[str] = None


class RegisterRequest(BaseModel):
    """Parent registration request schema."""
    email: EmailStr
    password: str = Field(..., min_length=8, description="Password must be at least 8 characters")


class RegisterResponse(BaseModel):
    """Registration response schema."""
    parent_id: str
    email: str
    role: str
    message: str
    mfa_setup_required: bool = True
    totp_secret: str
    provisioning_uri: str
    qr_code: str


class MFARequiredResponse(BaseModel):
    """MFA required response schema."""
    mfa_required: bool = True
    email: str
    role: str


class CompleteMFASetupRequest(BaseModel):
    """Complete MFA setup request schema."""
    parent_id: str
    password: str
    mfa_code: str = Field(..., min_length=6, max_length=6, description="6-digit TOTP code")
