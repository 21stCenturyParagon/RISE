# backend/app/core/auth.py
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.db import get_supabase
from app.core.logging_config import logger
from typing import List
from supabase import Client
from enum import Enum

security = HTTPBearer()


class UserRole(str, Enum):
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


def check_roles(required_roles: List[UserRole]):
    """Decorator factory for role checking"""

    async def role_checker(current_user: dict = Depends(get_current_user)) -> dict:
        user_role = UserRole(current_user.user_metadata.get("role", "student"))
        if user_role not in required_roles:
            logger.warning(
                f"User {current_user.id} with role {user_role} attempted to access restricted endpoint"
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient permissions"
            )
        return current_user

    return role_checker


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_supabase),
) -> dict:
    try:
        user = supabase.auth.get_user(credentials.credentials)
        return user.user
    except Exception as e:
        logger.error(f"Authentication error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )
