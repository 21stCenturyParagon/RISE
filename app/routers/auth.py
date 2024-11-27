from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.db import get_supabase
from app.core.auth import get_current_user
from app.core.logging_config import logger
from supabase import Client

router = APIRouter()


class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: Optional[str] = None
    role: Optional[str] = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/signup", response_model=TokenResponse)
async def signup(user_data: UserCreate, supabase: Client = Depends(get_supabase)):
    try:
        auth_response = supabase.auth.sign_up(
            {
                "email": user_data.email,
                "password": user_data.password,
                "options": {"data": {"name": user_data.name}},
            }
        )

        if not auth_response.session:
            # For email confirmation required cases
            return {
                "access_token": "",
                "token_type": "bearer",
                "message": "Please check your email for verification",
            }

        logger.info(f"User registered successfully: {user_data.email}")
        return {
            "access_token": auth_response.session.access_token,
            "token_type": "bearer",
        }

    except Exception as e:
        logger.error(f"Registration error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/login", response_model=TokenResponse)
async def login(credentials: UserLogin, supabase: Client = Depends(get_supabase)):
    """
    Authenticate user and return JWT token
    """
    try:
        # Sign in user
        auth_response = supabase.auth.sign_in_with_password(
            {"email": credentials.email, "password": credentials.password}
        )

        logger.info(f"User logged in successfully: {credentials.email}")

        return {
            "access_token": auth_response.session.access_token,
            "token_type": "bearer",
        }
    except Exception as e:
        logger.error(f"Login error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials"
        )


@router.post("/logout")
async def logout(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Logout current user
    """
    try:
        supabase.auth.sign_out()
        logger.info(f"User logged out successfully: {current_user['email']}")
        return {"message": "Successfully logged out"}
    except Exception as e:
        logger.error(f"Logout error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.get("/me", response_model=UserResponse)
async def get_user_info(current_user: dict = Depends(get_current_user)):
    """
    Get current user information
    """
    try:
        return {
            "id": current_user.id,
            "email": current_user.email,
            "name": current_user.user_metadata.get("name"),
            "role": current_user.user_metadata.get("role", "user"),
        }
    except Exception as e:
        logger.error(f"Error fetching user info: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e)
        )


@router.post("/reset-password")
async def reset_password(email: EmailStr, supabase: Client = Depends(get_supabase)):
    """
    Send password reset email
    """
    try:
        await supabase.auth.reset_password_email(email)
        logger.info(f"Password reset email sent to: {email}")
        return {"message": "Password reset email sent"}
    except Exception as e:
        logger.error(f"Password reset error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/change-password")
async def change_password(
    new_password: str,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Change user password
    """
    try:
        await supabase.auth.update_user({"password": new_password})
        logger.info(f"Password changed successfully for user: {current_user['email']}")
        return {"message": "Password updated successfully"}
    except Exception as e:
        logger.error(f"Password change error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
