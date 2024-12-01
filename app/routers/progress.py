from fastapi import APIRouter, Depends, HTTPException, Query
from app.db import get_supabase
from app.core.auth import get_current_user, check_roles, UserRole
from supabase import Client
from pydantic import BaseModel
from datetime import datetime, timedelta
from typing import List, Dict
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
        json_encoders = {datetime: lambda v: v.isoformat()}


class TopicProgress(BaseModel):
    topic: str
    total_attempts: int
    correct_attempts: int
    accuracy: float
    average_time: float


class DetailedProgress(BaseModel):
    user_id: str
    total_questions_attempted: int
    unique_questions_attempted: int
    total_time_spent: int  # in seconds
    average_accuracy: float
    topic_breakdown: Dict[str, float]  # topic: accuracy
    difficulty_breakdown: Dict[str, float]  # difficulty: accuracy
    recent_improvement: float  # trend in last 7 days


@router.post("/attempt", response_model=ProgressResponse)
async def record_attempt(
    progress: ProgressCreate,
    current_user: dict = Depends(check_roles([UserRole.STUDENT, UserRole.TEACHER])),
    supabase: Client = Depends(get_supabase),
):
    """Record a question attempt - Students and Teachers only"""
    try:
        # Prepare data with the correct user_id
        data = {
            "user_id": str(current_user.id),  # Ensure user_id is string
            "question_id": progress.question_id,
            "selected_answer": progress.selected_answer,
            "time_taken": progress.time_taken,
            "is_correct": progress.is_correct,
            "attempted_at": datetime.now().isoformat(),  # Add timestamp
        }

        # Insert data and handle response
        response = supabase.table("user_progress").insert(data).execute()

        if not response.data or not len(response.data):
            raise HTTPException(status_code=400, detail="Failed to record attempt")

        # Return the first record from the response
        attempt_record = response.data[0]

        # Convert the response to match ProgressResponse model
        return {
            "id": attempt_record.get("id"),
            "user_id": attempt_record.get("user_id"),
            "question_id": attempt_record.get("question_id"),
            "selected_answer": attempt_record.get("selected_answer"),
            "is_correct": attempt_record.get("is_correct"),
            "time_taken": attempt_record.get("time_taken"),
            "attempted_at": attempt_record.get("attempted_at"),
        }

    except Exception as e:
        logger.error(f"Error recording attempt: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/class-performance")
async def get_class_performance(
    current_user: dict = Depends(check_roles([UserRole.TEACHER, UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Get performance statistics for all students - Teachers/Admins only"""
    try:
        # Get all students
        students = supabase.auth.admin.list_users()
        student_stats = []

        for student in students:
            if student.user_metadata.get("role") == "student":
                # Get student's attempts
                attempts = (
                    supabase.table("user_progress")
                    .select("*")
                    .eq("user_id", student.id)
                    .execute()
                )

                if attempts.data:
                    accuracy = (
                        sum(1 for a in attempts.data if a["is_correct"])
                        / len(attempts.data)
                        * 100
                    )
                    student_stats.append(
                        {
                            "student_id": student.id,
                            "name": student.user_metadata.get("name", "Unknown"),
                            "attempts": len(attempts.data),
                            "accuracy": accuracy,
                            "last_attempt": max(
                                a["attempted_at"] for a in attempts.data
                            ),
                        }
                    )

        return student_stats
    except Exception as e:
        logger.error(f"Error fetching class performance: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats", response_model=dict)
async def get_user_stats(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    time_range: TimeRange = TimeRange.ALL,
):
    try:
        query = (
            supabase.table("user_progress")
            .select("*", count="exact")
            .eq("user_id", current_user.id)
        )

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
            "accuracy": (correct.count / total.count * 100) if total.count else 0,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/topic-progress", response_model=List[TopicProgress])
async def get_topic_progress(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get progress statistics by topic"""
    try:
        # First get all user attempts
        progress_data = (
            supabase.table("user_progress")
            .select("*")
            .eq("user_id", str(current_user.id))
            .execute()
        )
        # Then get questions data
        questions_data = supabase.table("TMUA").select("ques_number, topic").execute()
        # Create a mapping of question_id to topic
        question_topics = {q["ques_number"]: q["topic"] for q in questions_data.data}

        # Process data to group by topic
        topic_stats = {}
        for attempt in progress_data.data:
            topic = question_topics.get(attempt["question_id"])
            if topic:
                if topic not in topic_stats:
                    topic_stats[topic] = {
                        "total_attempts": 0,
                        "correct_attempts": 0,
                        "total_time": 0,
                    }

                stats = topic_stats[topic]
                stats["total_attempts"] += 1
                if attempt["is_correct"]:
                    stats["correct_attempts"] += 1
                stats["total_time"] += attempt["time_taken"]

        # Convert to list of TopicProgress objects
        result = []
        for topic, stats in topic_stats.items():
            accuracy = (
                (stats["correct_attempts"] / stats["total_attempts"] * 100)
                if stats["total_attempts"] > 0
                else 0
            )
            average_time = (
                stats["total_time"] / stats["total_attempts"]
                if stats["total_attempts"] > 0
                else 0
            )

            result.append(
                TopicProgress(
                    topic=topic,
                    total_attempts=stats["total_attempts"],
                    correct_attempts=stats["correct_attempts"],
                    accuracy=round(accuracy, 2),
                    average_time=round(average_time, 2),
                )
            )

        return result

    except Exception as e:
        logger.error(f"Error fetching topic progress: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/recent-attempts", response_model=List[ProgressResponse])
async def get_recent_attempts(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    limit: int = Query(10, ge=1, le=50),
):
    """Get user's recent attempts"""
    try:
        response = (
            supabase.table("user_progress")
            .select("*")
            .eq("user_id", current_user.id)
            .order("attempted_at", desc=True)
            .limit(limit)
            .execute()
        )
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/daily-streak")
async def get_daily_streak(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get user's current daily practice streak"""
    try:
        # Get all attempt dates
        response = (
            supabase.table("user_progress")
            .select("attempted_at")
            .eq("user_id", current_user.id)
            .execute()
        )

        if not response.data:
            return {"current_streak": 0, "longest_streak": 0}

        # Process dates to calculate streak
        dates = sorted(set(attempt["attempted_at"].date() for attempt in response.data))
        current_streak = 1
        longest_streak = 1
        current_date = datetime.now().date()

        # Calculate streaks
        for i in range(len(dates) - 1, 0, -1):
            if dates[i] == current_date - timedelta(days=1):
                current_streak += 1
                longest_streak = max(longest_streak, current_streak)
            else:
                break

        return {"current_streak": current_streak, "longest_streak": longest_streak}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/difficulty-progress")
async def get_difficulty_progress(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get progress statistics by difficulty level"""
    try:
        response = supabase.table("user_progress").select("*").execute()

        difficulty_stats = {}
        for row in response.data:
            difficulty = row["difficulty"]
            difficulty_stats[difficulty] = {
                "total_attempts": row["total_attempts"],
                "correct_attempts": row["correct_attempts"],
                "accuracy": (row["correct_attempts"] / row["total_attempts"] * 100)
                if row["total_attempts"]
                else 0,
                "average_time": row["average_time"],
            }

        return difficulty_stats
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/performance-timeline")
async def get_performance_timeline(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
    days: int = Query(30, ge=1, le=365),
):
    """Get daily performance timeline"""
    try:
        start_date = datetime.now().date() - timedelta(days=days)
        response = (
            supabase.table("user_progress")
            .select("*")
            .eq("user_id", current_user.id)
            .gte("attempted_at", start_date.isoformat())
            .execute()
        )

        # Group attempts by date
        daily_stats = {}
        for attempt in response.data:
            date = attempt["attempted_at"].date()
            if date not in daily_stats:
                daily_stats[date] = {"total": 0, "correct": 0}
            daily_stats[date]["total"] += 1
            if attempt["is_correct"]:
                daily_stats[date]["correct"] += 1

        return [
            {
                "date": date.isoformat(),
                "attempts": stats["total"],
                "correct": stats["correct"],
                "accuracy": (stats["correct"] / stats["total"] * 100)
                if stats["total"]
                else 0,
            }
            for date, stats in sorted(daily_stats.items())
        ]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/user/{user_id}/detailed", response_model=DetailedProgress)
async def get_user_detailed_progress(
    user_id: str,
    current_user: dict = Depends(check_roles([UserRole.ADMIN, UserRole.TEACHER])),
    supabase: Client = Depends(get_supabase),
):
    """Get detailed progress for a specific user - Admin/Teacher only"""
    try:
        # Get all attempts for the user
        attempts = (
            supabase.table("user_progress").select("*").eq("user_id", user_id).execute()
        )

        # Get all questions attempted by the user
        questions = (
            supabase.table("TMUA")
            .select("*")
            .in_("ques_number", [a["question_id"] for a in attempts.data])
            .execute()
        )

        # Calculate detailed statistics
        unique_questions = len(set(a["question_id"] for a in attempts.data))
        total_time = sum(a["time_taken"] for a in attempts.data)

        # Calculate topic and difficulty breakdowns
        topic_stats = {}
        difficulty_stats = {}
        for q in questions.data:
            topic_attempts = [
                a for a in attempts.data if a["question_id"] == q["ques_number"]
            ]
            if topic_attempts:
                topic_accuracy = sum(
                    1 for a in topic_attempts if a["is_correct"]
                ) / len(topic_attempts)
                topic_stats[q["topic"]] = topic_accuracy * 100

                diff_accuracy = sum(1 for a in topic_attempts if a["is_correct"]) / len(
                    topic_attempts
                )
                difficulty_stats[q["difficulty"]] = diff_accuracy * 100

        # Calculate recent improvement
        week_ago = datetime.now() - timedelta(days=7)
        recent_attempts = [
            a for a in attempts.data if a["attempted_at"] >= week_ago.isoformat()
        ]
        older_attempts = [
            a for a in attempts.data if a["attempted_at"] < week_ago.isoformat()
        ]

        recent_accuracy = (
            sum(1 for a in recent_attempts if a["is_correct"]) / len(recent_attempts)
            if recent_attempts
            else 0
        )
        older_accuracy = (
            sum(1 for a in older_attempts if a["is_correct"]) / len(older_attempts)
            if older_attempts
            else 0
        )
        improvement = recent_accuracy - older_accuracy

        return DetailedProgress(
            user_id=user_id,
            total_questions_attempted=len(attempts.data),
            unique_questions_attempted=unique_questions,
            total_time_spent=total_time,
            average_accuracy=sum(1 for a in attempts.data if a["is_correct"])
            / len(attempts.data)
            * 100
            if attempts.data
            else 0,
            topic_breakdown=topic_stats,
            difficulty_breakdown=difficulty_stats,
            recent_improvement=improvement * 100,
        )
    except Exception as e:
        logger.error(f"Error fetching detailed progress: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
