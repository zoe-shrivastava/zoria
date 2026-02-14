"""Security utilities: JWT tokens, password hashing, PIN hashing, MFA/TOTP."""

import jwt
import logging
import os
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple
import bcrypt
import pyotp
import qrcode
import io
import base64

from core.config import settings

logger = logging.getLogger(__name__)


class JWTHandler:
    """Handles JWT token generation and validation."""
    
    def __init__(self, secret_key: Optional[str] = None, algorithm: str = "HS256"):
        """Initialize JWT handler.
        
        Args:
            secret_key: Secret key for signing tokens (defaults to settings)
            algorithm: JWT algorithm (HS256)
        """
        self.secret_key = secret_key or settings.JWT_SECRET_KEY
        self.algorithm = algorithm
        
        if len(self.secret_key) < 32:
            logger.warning("JWT secret key is too short. Use at least 32 characters for production.")
    
    def generate_parent_token(
        self,
        parent_id: str,
        role: str = "parent",
        expires_in_hours: Optional[int] = None
    ) -> str:
        """Generate parent JWT token.
        
        Args:
            parent_id: Parent identifier (UUID)
            role: User role ('parent' or 'admin')
            expires_in_hours: Token expiration in hours (defaults to settings)
            
        Returns:
            JWT token string
        """
        expires_in = expires_in_hours or settings.JWT_ACCESS_TOKEN_EXPIRE_HOURS
        payload = {
            "parent_id": parent_id,
            "role": role,
            "permissions": ["manage_children", "upload_documents", "view_reports"] if role == "parent" else ["manage_all"],
            "exp": datetime.utcnow() + timedelta(hours=expires_in),
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def generate_child_token(
        self,
        child_id: str,
        expires_in_hours: int = 8
    ) -> str:
        """Generate child JWT token.
        
        Args:
            child_id: Child identifier (UUID)
            expires_in_hours: Token expiration in hours
            
        Returns:
            JWT token string
        """
        payload = {
            "child_id": child_id,
            "role": "child",
            "permissions": ["upload_documents", "take_quizzes", "view_own_profile"],
            "exp": datetime.utcnow() + timedelta(hours=expires_in_hours),
            "iat": datetime.utcnow()
        }
        
        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)
    
    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """Decode and validate JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            Decoded token payload or None if invalid
        """
        try:
            payload = jwt.decode(token, self.secret_key, algorithms=[self.algorithm])
            return payload
        except jwt.ExpiredSignatureError:
            logger.warning("Token has expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None
    
    def verify_token(self, token: str) -> bool:
        """Verify if token is valid.
        
        Args:
            token: JWT token string
            
        Returns:
            True if token is valid, False otherwise
        """
        return self.decode_token(token) is not None


class PasswordHasher:
    """Handles password hashing and verification using bcrypt."""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """Hash a password using bcrypt.
        
        Args:
            password: Plain text password
            
        Returns:
            Hashed password string
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(password: str, hashed: str) -> bool:
        """Verify a password against a hash.
        
        Args:
            password: Plain text password
            hashed: Hashed password string
            
        Returns:
            True if password matches, False otherwise
        """
        try:
            return bcrypt.checkpw(password.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"Password verification error: {e}")
            return False


class PINHasher:
    """Handles PIN hashing and verification for children."""
    
    @staticmethod
    def hash_pin(pin: str) -> str:
        """Hash a PIN using bcrypt.
        
        Args:
            pin: Plain text PIN (4-6 digits)
            
        Returns:
            Hashed PIN string
        """
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(pin.encode('utf-8'), salt)
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_pin(pin: str, hashed: str) -> bool:
        """Verify a PIN against a hash.
        
        Args:
            pin: Plain text PIN
            hashed: Hashed PIN string
            
        Returns:
            True if PIN matches, False otherwise
        """
        try:
            return bcrypt.checkpw(pin.encode('utf-8'), hashed.encode('utf-8'))
        except Exception as e:
            logger.error(f"PIN verification error: {e}")
            return False


class MFAHandler:
    """Handles Multi-Factor Authentication using TOTP (Time-based One-Time Password)."""
    
    @staticmethod
    def generate_secret() -> str:
        """Generate a new TOTP secret.
        
        Returns:
            Base32-encoded secret string
        """
        return pyotp.random_base32()
    
    @staticmethod
    def generate_provisioning_uri(secret: str, email: str, issuer_name: str = "Zoria") -> str:
        """Generate provisioning URI for QR code.
        
        Args:
            secret: TOTP secret
            email: User email
            issuer_name: Service name
            
        Returns:
            otpauth:// URI string
        """
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(
            name=email.lower().strip(),
            issuer_name=issuer_name
        )
    
    @staticmethod
    def generate_qr_code(provisioning_uri: str) -> str:
        """Generate QR code as base64 data URI.
        
        Args:
            provisioning_uri: TOTP provisioning URI
            
        Returns:
            Base64-encoded PNG data URI
        """
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        
        img = qr.make_image(fill_color="black", back_color="white")
        
        # Convert to base64
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        img_bytes = buffer.getvalue()
        img_base64 = base64.b64encode(img_bytes).decode('utf-8')
        
        return f"data:image/png;base64,{img_base64}"
    
    @staticmethod
    def verify_totp(secret: str, code: str, window: int = 1) -> bool:
        """Verify a TOTP code.
        
        Args:
            secret: TOTP secret
            code: 6-digit code from authenticator app
            window: Time window tolerance (default: 1 = ±30 seconds)
            
        Returns:
            True if code is valid, False otherwise
        """
        try:
            totp = pyotp.TOTP(secret)
            return totp.verify(code, valid_window=window)
        except Exception as e:
            logger.error(f"TOTP verification error: {e}")
            return False
    
    @staticmethod
    def generate_mfa_setup(email: str, issuer_name: str = "Zoria") -> Tuple[str, str, str]:
        """Generate complete MFA setup (secret, URI, QR code).
        
        Args:
            email: User email
            issuer_name: Service name
            
        Returns:
            Tuple of (secret, provisioning_uri, qr_code_base64)
        """
        secret = MFAHandler.generate_secret()
        provisioning_uri = MFAHandler.generate_provisioning_uri(secret, email, issuer_name)
        qr_code = MFAHandler.generate_qr_code(provisioning_uri)
        
        return secret, provisioning_uri, qr_code


def generate_child_code_from_name(name: str, max_length: int = 8) -> str:
    """Generate a child code based on the child's name.
    
    Format: CHD + uppercase name characters (letters only, no spaces/special chars)
    Example: "John Doe" -> "CHDJOHNDOE", "Alice" -> "CHDALICE"
    
    If the name is too short, it's padded. If too long, it's truncated.
    If duplicates exist, numbers are appended.
    
    Args:
        name: Child's name
        max_length: Maximum length of name part (default: 8, so total is CHD + 8 = 11)
        
    Returns:
        Child code string (e.g., "CHDJOHNDOE")
    """
    import re
    
    # Clean name: remove special characters, keep only letters, convert to uppercase
    cleaned = re.sub(r'[^A-Za-z]', '', name).upper()
    
    # Take first max_length characters (or pad if shorter)
    if len(cleaned) > max_length:
        name_part = cleaned[:max_length]
    elif len(cleaned) < 3:
        # If name is too short, pad with X
        name_part = cleaned.ljust(3, 'X')[:max_length]
    else:
        name_part = cleaned
    
    return f"CHD{name_part}"


def generate_child_code(length: int = 6) -> str:
    """Generate a random child code (fallback method).
    
    Format: CHD + random alphanumeric characters (uppercase letters and numbers)
    Example: CHD123ABC, CHD456XYZ
    
    Note: This generates a code but does not check uniqueness. 
    The caller should verify uniqueness before using.
    
    Args:
        length: Number of random characters after "CHD" (default: 6)
        
    Returns:
        Child code string (e.g., "CHD123ABC")
    """
    import random
    
    # Use uppercase letters and numbers (exclude confusing characters: 0/O, 1/I)
    chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    
    random_part = ''.join(random.choices(chars, k=length))
    return f"CHD{random_part}"


# Global instances
jwt_handler = JWTHandler()
password_hasher = PasswordHasher()
pin_hasher = PINHasher()
mfa_handler = MFAHandler()