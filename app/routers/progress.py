# backend/app/routers/progress.py
from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum

router = APIRouter()

class TimeRange(str, Enum):
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"

class ProgressCreate(BaseModel):
    question_id: int
    selected_answer: str
    time_taken: int
    is_correct: bool

class ProgressResponse(BaseModel):
    id: int
    user_id: str
    question_id: int
    selected_answer: str
    is_correct: bool
    time_taken: int
    attempted_at: datetime

class TopicProgress(BaseModel):
    topic: str
    total_attempts: int
    correct_attempts: int
    accuracy: float
    average_time: float

@router.post("/attempt", response_model=ProgressResponse)
async def record_attempt(
    progress: ProgressCreate,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    try:
        data = {"user_id": current_user.id, **progress.dict()}
        response = supabase.table("user_progress").insert(data).execute()
        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/stats", response_model=dict)
async def get_user_stats(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    time_range: TimeRange = TimeRange.ALL
):
    try:
        query = supabase.table("user_progress").select("*", count="exact").eq("user_id", current_user.id)

        # Apply time range filter
        if time_range != TimeRange.ALL:
            if time_range == TimeRange.TODAY:
                start_date = datetime.now().date()
            elif time_range == TimeRange.WEEK:
                start_date = datetime.now().date() - timedelta(days=7)
            elif time_range == TimeRange.MONTH:
                start_date = datetime.now().date() - timedelta(days=30)

            query = query.gte("attempted_at", start_date.isoformat())

        total = query.execute()
        correct = query.eq("is_correct", True).execute()

        return {
            "total_attempts": total.count,
            "correct_answers": correct.count,
            "accuracy": (correct.count / total.count * 100) if total.count else 0
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/topic-progress", response_model=List[TopicProgress])
async def get_topic_progress(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get progress statistics by topic"""
    try:
        # Join progress with questions to get topic information
        query = """
        SELECT
            q.topic,
            COUNT(*) as total_attempts,
            SUM(CASE WHEN p.is_correct THEN 1 ELSE 0 END) as correct_attempts,
            AVG(p.time_taken) as average_time
        FROM user_progress p
        JOIN TMUA q ON p.question_id = q.ques_number
        WHERE p.user_id = ?
        GROUP BY q.topic
        """
        response = supabase.table("user_progress").select("*").execute()

        topic_stats = []
        for row in response.data:
            accuracy = (row['correct_attempts'] / row['total_attempts'] * 100) if row['total_attempts'] else 0
            topic_stats.append(TopicProgress(
                topic=row['topic'],
                total_attempts=row['total_attempts'],
                correct_attempts=row['correct_attempts'],
                accuracy=accuracy,
                average_time=row['average_time']
            ))

        return topic_stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/recent-attempts", response_model=List[ProgressResponse])
async def get_recent_attempts(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    limit: int = Query(10, ge=1, le=50)
):
    """Get user's recent attempts"""
    try:
        response = supabase.table("user_progress")\
            .select("*")\
            .eq("user_id", current_user.id)\
            .order("attempted_at", desc=True)\
            .limit(limit)\
            .execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/daily-streak")
async def get_daily_streak(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get user's current daily practice streak"""
    try:
        # Get all attempt dates
        response = supabase.table("user_progress")\
            .select("attempted_at")\
            .eq("user_id", current_user.id)\
            .execute()

        if not response.data:
            return {"current_streak": 0, "longest_streak": 0}

        # Process dates to calculate streak
        dates = sorted(set(attempt['attempted_at'].date() for attempt in response.data))
        current_streak = 1
        longest_streak = 1
        current_date = datetime.now().date()

        # Calculate streaks
        for i in range(len(dates)-1, 0, -1):
            if dates[i] == current_date - timedelta(days=1):
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                break

        return {
            "current_streak": current_streak,
            "longest_streak": longest_streak
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/difficulty-progress")
async def get_difficulty_progress(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """Get progress statistics by difficulty level"""
    try:
        query = """
        SELECT
            q.difficulty,
            COUNT(*) as total_attempts,
            SUM(CASE WHEN p.is_correct THEN 1 ELSE 0 END) as correct_attempts,
            AVG(p.time_taken) as average_time
        FROM user_progress p
        JOIN TMUA q ON p.question_id = q.ques_number
        WHERE p.user_id = ?
        GROUP BY q.difficulty
        """
        response = supabase.table("user_progress").select("*").execute()
        
        difficulty_stats = {}
        for row in response.data:
            difficulty = row['difficulty']
            difficulty_stats[difficulty] = {
                "total_attempts": row['total_attempts'],
                "correct_attempts": row['correct_attempts'],
                "accuracy": (row['correct_attempts'] / row['total_attempts'] * 100) if row['total_attempts'] else 0,
                "average_time": row['average_time']
            }

        return difficulty_stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/performance-timeline")
async def get_performance_timeline(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    days: int = Query(30, ge=1, le=365)
):
    """Get daily performance timeline"""
    try:
        start_date = datetime.now().date() - timedelta(days=days)
        response = supabase.table("user_progress")\
            .select("*")\
            .eq("user_id", current_user.id)\
            .gte("attempted_at", start_date.isoformat())\
            .execute()

        # Group attempts by date
        daily_stats = {}
        for attempt in response.data:
            date = attempt['attempted_at'].date()
            if date not in daily_stats:
                daily_stats[date] = {"total": 0, "correct": 0}
            daily_stats[date]["total"] += 1
            if attempt['is_correct']:
                daily_stats[date]["correct"] += 1

        return [
            {
                "date": date.isoformat(),
                "attempts": stats["total"],
                "correct": stats["correct"],
                "accuracy": (stats["correct"] / stats["total"] * 100) if stats["total"] else 0
            }
            for date, stats in sorted(daily_stats.items())
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))