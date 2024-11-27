from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import Optional, List
from enum import Enum
from app.core.logging_config import logger

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
    id: str  # Changed from int to str since it's a UUID
    user_id: str
    question_id: int
    selected_answer: str
    is_correct: bool
    time_taken: int
    attempted_at: datetime

    class Config:
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }

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
        # Prepare data with the correct user_id
        data = {
            "user_id": str(current_user.id),  # Ensure user_id is string
            "question_id": progress.question_id,
            "selected_answer": progress.selected_answer,
            "time_taken": progress.time_taken,
            "is_correct": progress.is_correct,
            "attempted_at": datetime.now().isoformat()  # Add timestamp
        }

        # Insert data and handle response
        response = supabase.table("user_progress").insert(data).execute()

        if not response.data or not len(response.data):
            raise HTTPException(status_code=400, detail="Failed to record attempt")

        # Return the first record from the response
        attempt_record = response.data[0]

        # Convert the response to match ProgressResponse model
        return {
            "id": attempt_record.get('id'),
            "user_id": attempt_record.get('user_id'),
            "question_id": attempt_record.get('question_id'),
            "selected_answer": attempt_record.get('selected_answer'),
            "is_correct": attempt_record.get('is_correct'),
            "time_taken": attempt_record.get('time_taken'),
            "attempted_at": attempt_record.get('attempted_at')
        }

    except Exception as e:
        logger.error(f"Error recording attempt: {str(e)}")
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
        # First get all user attempts
        progress_data = supabase.table("user_progress")\
            .select("*")\
            .eq("user_id", str(current_user.id))\
            .execute()
        # Then get questions data
        questions_data = supabase.table("TMUA")\
            .select("ques_number, topic")\
            .execute()
        # Create a mapping of question_id to topic
        question_topics = {q['ques_number']: q['topic'] for q in questions_data.data}

        # Process data to group by topic
        topic_stats = {}
        for attempt in progress_data.data:
            topic = question_topics.get(attempt['question_id'])
            if topic:
                if topic not in topic_stats:
                    topic_stats[topic] = {
                        'total_attempts': 0,
                        'correct_attempts': 0,
                        'total_time': 0
                    }

                stats = topic_stats[topic]
                stats['total_attempts'] += 1
                if attempt['is_correct']:
                    stats['correct_attempts'] += 1
                stats['total_time'] += attempt['time_taken']

        # Convert to list of TopicProgress objects
        result = []
        for topic, stats in topic_stats.items():
            accuracy = (stats['correct_attempts'] / stats['total_attempts'] * 100) if stats['total_attempts'] > 0 else 0
            average_time = stats['total_time'] / stats['total_attempts'] if stats['total_attempts'] > 0 else 0

            result.append(TopicProgress(
                topic=topic,
                total_attempts=stats['total_attempts'],
                correct_attempts=stats['correct_attempts'],
                accuracy=round(accuracy, 2),
                average_time=round(average_time, 2)
            ))

        return result

    except Exception as e:
        logger.error(f"Error fetching topic progress: {str(e)}")
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