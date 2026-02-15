"""Authentication service for login and registration."""

import logging
import time
from typing import Optional, Dict, Any

from core.database import get_db
from core.security import jwt_handler, password_hasher, pin_hasher, mfa_handler
from database.repositories.user_repository import UserRepository

logger = logging.getLogger(__name__)


class AuthService:
    """Service for authentication operations."""
    
    def __init__(self):
        """Initialize auth service."""
        self.db = get_db()
        self.user_repo = UserRepository(self.db)
    
    async def register_parent(
        self,
        email: str,
        password: str
    ) -> Dict[str, Any]:
        """Register a new parent user with mandatory MFA setup.
        
        Args:
            email: Parent email
            password: Plain text password
            
        Returns:
            Registration response with MFA setup info
            
        Raises:
            ValueError: If email already exists
        """
        # Check if email already exists
        existing = await self.user_repo.get_parent_by_email(email)
        if existing:
            raise ValueError("Email already registered")
        
        # Hash password
        password_hash = password_hasher.hash_password(password)
        
        # Generate MFA secret (mandatory for all users)
        mfa_secret, provisioning_uri, qr_code = mfa_handler.generate_mfa_setup(email)
        
        # Create parent with MFA secret (not enabled yet)
        parent_id = await self.user_repo.create_parent(
            email=email,
            password_hash=password_hash,
            role="parent",
            mfa_secret=mfa_secret
        )
        
        return {
            "parent_id": parent_id,
            "email": email,
            "role": "parent",
            "mfa_setup_required": True,
            "totp_secret": mfa_secret,
            "provisioning_uri": provisioning_uri,
            "qr_code": qr_code,
            "message": "Registration successful. Please complete MFA setup."
        }
    
    async def login_parent(
        self,
        email: str,
        password: str,
        mfa_code: Optional[str] = None
    ) -> Dict[str, Any]:
        """Login a parent user with MFA.
        
        Args:
            email: Parent email
            password: Plain text password
            mfa_code: Optional TOTP code (required if MFA is enabled)
            
        Returns:
            Login response with token and user info, or MFA requirement
            
        Raises:
            ValueError: If credentials are invalid or MFA code is invalid
        """
        start_time = time.time()
        db_time = 0.0
        pwd_time = 0.0
        token_time = 0.0
        
        # Get parent by email
        db_start = time.time()
        parent = await self.user_repo.get_parent_by_email(email)
        db_time = time.time() - db_start
        logger.debug(f"Login: DB query took {db_time:.3f}s")
        
        if not parent:
            raise ValueError("Invalid email or password")
        
        # Verify password
        pwd_start = time.time()
        if not password_hasher.verify_password(password, parent["password_hash"]):
            raise ValueError("Invalid email or password")
        pwd_time = time.time() - pwd_start
        logger.debug(f"Login: Password verification took {pwd_time:.3f}s")
        
        mfa_secret = parent.get("mfa_secret")
        totp_enabled = parent.get("totp_enabled", False)
        
        # If no MFA secret exists, generate one (for default admin or legacy users)
        if not mfa_secret:
            mfa_secret, provisioning_uri, qr_code = mfa_handler.generate_mfa_setup(email)
            # Store the secret in database
            await self.user_repo.update_parent_mfa_secret(str(parent["id"]), mfa_secret)
            # Return MFA setup info immediately
            total_time = time.time() - start_time
            logger.info(f"Login (MFA setup) completed in {total_time:.3f}s (DB: {db_time:.3f}s, PWD: {pwd_time:.3f}s)")
            return {
                "mfa_setup_required": True,
                "email": email,
                "role": parent.get("role", "parent"),
                "parent_id": str(parent["id"]),
                "totp_secret": mfa_secret,
                "provisioning_uri": provisioning_uri,
                "qr_code": qr_code,
                "message": "MFA setup required. Please scan QR code and verify."
            }
        
        # Check if MFA setup is required (secret exists but not enabled)
        if mfa_secret and not totp_enabled:
            # Return MFA setup info
            provisioning_uri = mfa_handler.generate_provisioning_uri(mfa_secret, email)
            qr_code = mfa_handler.generate_qr_code(provisioning_uri)
            total_time = time.time() - start_time
            logger.info(f"Login (MFA setup) completed in {total_time:.3f}s (DB: {db_time:.3f}s, PWD: {pwd_time:.3f}s)")
            return {
                "mfa_setup_required": True,
                "email": email,
                "role": parent.get("role", "parent"),
                "parent_id": str(parent["id"]),
                "totp_secret": mfa_secret,
                "provisioning_uri": provisioning_uri,
                "qr_code": qr_code,
                "message": "MFA setup required. Please scan QR code and verify."
            }
        
        # MFA is enabled - require TOTP code
        if totp_enabled and mfa_secret:
            if not mfa_code:
                # Step 1: Credentials valid, MFA code required
                total_time = time.time() - start_time
                logger.info(f"Login (MFA required) completed in {total_time:.3f}s (DB: {db_time:.3f}s, PWD: {pwd_time:.3f}s)")
                return {
                    "mfa_required": True,
                    "email": email,
                    "role": parent.get("role", "parent"),
                    "message": "MFA code required"
                }
            
            # Step 2: Verify TOTP code
            if not mfa_handler.verify_totp(mfa_secret, mfa_code):
                raise ValueError("Invalid MFA code")
        
        # Update last login (non-blocking, don't wait if slow)
        try:
            await self.user_repo.update_parent_last_login(parent["id"])
        except Exception as e:
            logger.warning(f"Failed to update last login: {e}")
        
        # Generate token
        token_start = time.time()
        role = parent.get("role", "parent")
        token = jwt_handler.generate_parent_token(
            parent_id=str(parent["id"]),
            role=role,
            email=parent.get("email")
        )
        token_time = time.time() - token_start
        logger.debug(f"Login: Token generation took {token_time:.3f}s")
        
        total_time = time.time() - start_time
        logger.info(f"Login completed in {total_time:.3f}s (DB: {db_time:.3f}s, PWD: {pwd_time:.3f}s, Token: {token_time:.3f}s)")
        
        return {
            "token": token,
            "user": {
                "id": str(parent["id"]),
                "email": parent["email"],
                "role": role
            },
            "role": role
        }
    
    async def login_child(
        self,
        child_identifier: str,
        pin: str
    ) -> Dict[str, Any]:
        """Login a child user with PIN.
        
        Args:
            child_identifier: Child UUID or child_code (e.g., "CHD123ABC")
            pin: Plain text PIN
            
        Returns:
            Login response with token and user info
            
        Raises:
            ValueError: If credentials are invalid
        """
        start_time = time.time()
        
        # Try to get child by code first (more user-friendly)
        child = None
        db_start = time.time()
        if child_identifier.upper().startswith("CHD"):
            child = await self.user_repo.get_child_by_code(child_identifier.upper())
        
        # If not found by code, try by UUID
        if not child:
            child = await self.user_repo.get_child_by_id(child_identifier)
        db_time = time.time() - db_start
        logger.debug(f"Child login: DB query took {db_time:.3f}s")
        
        if not child:
            raise ValueError("Invalid child ID or PIN")
        
        # Verify PIN
        if not child.get("pin_hash"):
            raise ValueError("PIN not set for this child")
        
        pwd_start = time.time()
        if not pin_hasher.verify_pin(pin, child["pin_hash"]):
            raise ValueError("Invalid child ID or PIN")
        pwd_time = time.time() - pwd_start
        logger.debug(f"Child login: PIN verification took {pwd_time:.3f}s")
        
        # Generate token
        token_start = time.time()
        token = jwt_handler.generate_child_token(child_id=str(child["id"]))
        token_time = time.time() - token_start
        logger.debug(f"Child login: Token generation took {token_time:.3f}s")
        
        total_time = time.time() - start_time
        logger.info(f"Child login completed in {total_time:.3f}s (DB: {db_time:.3f}s, PIN: {pwd_time:.3f}s, Token: {token_time:.3f}s)")
        
        return {
            "token": token,
            "user": {
                "id": str(child["id"]),
                "name": child["name"],
                "role": "child",
                "child_code": child.get("child_code")
            },
            "role": "child"
        }
    
    async def complete_mfa_setup(
        self,
        parent_id: str,
        password: str,
        mfa_code: str
    ) -> Dict[str, Any]:
        """Complete MFA setup by verifying TOTP code and enabling MFA.
        
        Args:
            parent_id: Parent UUID
            password: Plain text password (for verification)
            mfa_code: TOTP code from authenticator app
            
        Returns:
            Login response with token
            
        Raises:
            ValueError: If credentials or MFA code are invalid
        """
        # Get parent
        parent = await self.user_repo.get_parent_by_id(parent_id)
        if not parent:
            raise ValueError("Invalid parent ID")
        
        # Verify password
        if not password_hasher.verify_password(password, parent["password_hash"]):
            raise ValueError("Invalid password")
        
        # Verify MFA secret exists
        mfa_secret = parent.get("mfa_secret")
        if not mfa_secret:
            raise ValueError("MFA secret not found. Please register again.")
        
        # Verify TOTP code
        if not mfa_handler.verify_totp(mfa_secret, mfa_code):
            raise ValueError("Invalid MFA code")
        
        # Enable MFA
        await self.user_repo.enable_mfa(parent_id)
        
        # Update last login
        await self.user_repo.update_parent_last_login(parent_id)
        
        # Generate token
        role = parent.get("role", "parent")
        token = jwt_handler.generate_parent_token(
            parent_id=parent_id,
            role=role,
            email=parent.get("email")
        )
        
        return {
            "token": token,
            "user": {
                "id": parent_id,
                "email": parent["email"],
                "role": role
            },
            "role": role,
            "message": "MFA setup completed successfully"
        }