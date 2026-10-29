import re
import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
from fastapi import HTTPException, status
from core.config import settings

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    """Hash plain text password."""
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify plain password against hashed password."""
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """Generate JWT access token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(data: dict) -> str:
    """Generate JWT refresh token."""
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> Dict[str, Any]:
    """Decode and validate JWT token."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Please log in again.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


def sanitize_input(text: str) -> str:
    """
    Sanitize text input to prevent XSS and basic prompt injection attacks.
    Removes dangerous tags and wraps content safely.
    """
    if not text:
        return ""
    # Strip HTML tags
    text = re.sub(r'<[^>]*>', '', text)
    # Neutralize system prompt injection delimiters
    text = text.replace("<SYSTEM_MESSAGE>", "[REDACTED]").replace("</SYSTEM_MESSAGE>", "[REDACTED]")
    text = text.replace("<USER_REQUEST>", "[REDACTED]").replace("</USER_REQUEST>", "[REDACTED]")
    return text.strip()


def safe_path_join(base_dir: str, filename: str) -> str:
    """
    Prevent path traversal security vulnerabilities (e.g., ../../etc/passwd).
    """
    target_path = os.path.abspath(os.path.join(base_dir, filename))
    base_path = os.path.abspath(base_dir)
    if not target_path.startswith(base_path):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Illegal file path / Path traversal attempt detected."
        )
    return target_path
