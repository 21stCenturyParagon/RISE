# questions.py
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from pydantic import BaseModel

router = APIRouter()

class QuestionResponse(BaseModel):
    ques_number: int
    question: str
    options: str
    topic: str
    difficulty: str
    source: str
    image: Optional[str]

@router.get("/")
async def get_questions(
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get questions with filters as shown in the study plan"""
    try:
        query = supabase.table("TMUA").select("*")
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        response = query.execute()

        # Get user's attempts to mark status
        attempts = supabase.table("user_progress")\
            .select("question_id, is_correct")\
            .eq("user_id", current_user.id)\
            .execute()

        attempt_lookup = {a["question_id"]: a["is_correct"] for a in attempts.data}

        # Add status to questions
        for q in response.data:
            q["status"] = "correct" if attempt_lookup.get(q["ques_number"]) else \
                         "incorrect" if q["ques_number"] in attempt_lookup else \
                         "unattempted"

        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/filters")
async def get_filters(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get available filters for the study plan"""
    try:
        topics = supabase.table("TMUA").select("topic").execute()
        sources = supabase.table("TMUA").select("source").execute()

        return {
            "topics": sorted(set(t["topic"] for t in topics.data)),
            "difficulties": ["Easy", "Medium", "Hard"],
            "sources": sorted(set(s["source"] for s in sources.data))
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{ques_number}")
async def get_question(
    ques_number: int,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get specific question with solution"""
    try:
        response = supabase.table("TMUA")\
            .select("*")\
            .eq("ques_number", ques_number)\
            .execute()

        if not response.data:
            raise HTTPException(status_code=404, detail="Question not found")

        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))