# progress.py
from fastapi import APIRouter, Depends, HTTPException
from typing import List
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from pydantic import BaseModel
from datetime import datetime

router = APIRouter()

class AttemptCreate(BaseModel):
    question_id: int
    selected_answer: str
    time_taken: int
    is_correct: bool

@router.post("/attempt")
async def record_attempt(
    attempt: AttemptCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Record a question attempt"""
    try:
        data = {
            "user_id": current_user.id,
            **attempt.dict(),
            "attempted_at": datetime.now().isoformat()
        }

        response = supabase.table("user_progress").insert(data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/profile")
async def get_profile(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get user profile with stats as shown in the profile screen"""
    try:
        # Get attempts by difficulty
        attempts = supabase.table("user_progress")\
            .select("*, TMUA!inner(*)")\
            .eq("user_id", current_user.id)\
            .execute()

        stats = {
            "easy": {"total": 0, "correct": 0},
            "medium": {"total": 0, "correct": 0},
            "hard": {"total": 0, "correct": 0}
        }

        for attempt in attempts.data:
            difficulty = attempt["TMUA"]["difficulty"].lower()
            stats[difficulty]["total"] += 1
            if attempt["is_correct"]:
                stats[difficulty]["correct"] += 1

        solved_count = len(attempts.data)

        return {
            "user": {
                "name": current_user.user_metadata.get("name"),
                "email": current_user.email
            },
            "stats": stats,
            "solved_questions": solved_count
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))