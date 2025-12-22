"""
Authentication utilities for Error Debug feature.

Dev-only implementation using headers. In production, replace with portal JWT validation.
"""

from fastapi import Header, HTTPException, Depends
from typing import Optional

# Role strings must be exact uppercase: "ADMIN", "TECHNICIAN", "CUSTOMER"
ALLOWED_ROLES = {"ADMIN", "TECHNICIAN"}


class DevUser:
    """Dev user model."""
    def __init__(self, email: str, role: str):
        self.email = email
        self.role = role


def require_role(
    x_dev_role: Optional[str] = Header(None, alias="X-DEV-ROLE"),
    x_dev_user: Optional[str] = Header(None, alias="X-DEV-USER")
) -> DevUser:
    """
    FastAPI dependency to require TECHNICIAN or ADMIN role.
    
    In production, replace this with portal JWT validation.
    
    Args:
        x_dev_role: Header with role (ADMIN, TECHNICIAN, or CUSTOMER)
        x_dev_user: Header with user email
    
    Returns:
        DevUser object
    
    Raises:
        HTTPException 403 if role is not ADMIN or TECHNICIAN
    """
    if not x_dev_role:
        raise HTTPException(
            status_code=403,
            detail="Missing X-DEV-ROLE header. Required roles: ADMIN, TECHNICIAN"
        )
    
    # Normalize to uppercase
    role = x_dev_role.upper().strip()
    
    if role not in ALLOWED_ROLES:
        raise HTTPException(
            status_code=403,
            detail=f"Access denied. Required role: ADMIN or TECHNICIAN, got: {role}"
        )
    
    email = x_dev_user or "dev@example.com"
    
    return DevUser(email=email, role=role)


def get_current_user(
    x_dev_role: Optional[str] = Header(None, alias="X-DEV-ROLE"),
    x_dev_user: Optional[str] = Header(None, alias="X-DEV-USER")
) -> DevUser:
    """
    Get current user (doesn't require specific role).
    Used for endpoints that need user info but don't restrict access.
    """
    role = (x_dev_role or "TECHNICIAN").upper().strip()
    email = x_dev_user or "dev@example.com"
    return DevUser(email=email, role=role)

