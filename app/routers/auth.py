# auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from app.db import get_supabase
from supabase import Client

router = APIRouter()

class UserCreate(BaseModel):
    email: EmailStr
    password: str
    name: str  # Name is required as per design

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: str
    email: str
    name: str
    stats: dict  # For storing solving statistics

@router.post("/signup")
async def signup(user_data: UserCreate, supabase: Client = Depends(get_supabase)):
    """Simple signup with email/password"""
    try:
        auth_response = supabase.auth.sign_up({
            "email": user_data.email,
            "password": user_data.password,
            "options": {
                "data": {"name": user_data.name}
            }
        })
        return {
            "message": "Signup successful",
            "user": auth_response.user
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/login")
async def login(credentials: UserLogin, supabase: Client = Depends(get_supabase)):
    """Simple login with email/password"""
    try:
        auth_response = supabase.auth.sign_in_with_password({
            "email": credentials.email,
            "password": credentials.password
        })
        return {
            "access_token": auth_response.session.access_token,
            "user": auth_response.user
        }
    except Exception as e:
        raise HTTPException(status_code=401, detail="Invalid credentials")