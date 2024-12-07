from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from enum import Enum
import math
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from app.schemas.pagination import PaginatedResponse
from pydantic import BaseModel

router = APIRouter()

# Let's first define an enum for valid status values to ensure type safety
class QuestionStatus(str, Enum):
    CORRECT = "correct"
    INCORRECT = "incorrect"
    UNATTEMPTED = "unattempted"

class QuestionResponse(BaseModel):
    ques_number: int
    question: str
    options: str
    topic: str
    difficulty: str
    source: str
    image: Optional[str]
    status: QuestionStatus

@router.get("/", response_model=PaginatedResponse[QuestionResponse])
async def get_questions(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=50, description="Questions per page"),
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    status: Optional[QuestionStatus] = None,  # New status filter
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Get paginated questions with filters including attempt status.
    The status filter allows viewing only questions that are:
    - correct: successfully answered questions
    - incorrect: attempted but wrong answers
    - unattempted: questions not yet tried
    """
    try:
        # First, get user's attempts to help with status filtering
        attempts = supabase.table("user_progress")\
            .select("question_id, is_correct")\
            .eq("user_id", current_user.id)\
            .execute()

        # Create attempt lookup dictionary
        attempt_lookup = {
            a["question_id"]: "correct" if a["is_correct"] else "incorrect"
            for a in attempts.data
        }

        # Get all question IDs the user has attempted
        attempted_ids = list(attempt_lookup.keys())
        correct_ids = [qid for qid, status in attempt_lookup.items() if status == "correct"]
        incorrect_ids = [qid for qid, status in attempt_lookup.items() if status == "incorrect"]

        # Start building our query
        query = supabase.table("TMUA").select("*", count="exact")

        # Apply basic filters
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        # Apply status filter
        if status:
            if status == QuestionStatus.CORRECT:
                query = query.in_("ques_number", correct_ids)
            elif status == QuestionStatus.INCORRECT:
                query = query.in_("ques_number", incorrect_ids)
            elif status == QuestionStatus.UNATTEMPTED:
                query = query.not_.in_("ques_number", attempted_ids)

        # Calculate offset for pagination
        offset = (page - 1) * size

        # Get total count for pagination
        total_result = query.execute()
        total_count = total_result.count if hasattr(total_result, "count") else 0

        # Get the specific page of questions
        query = query.range(offset, offset + size - 1).order("ques_number")
        questions_result = query.execute()

        # Add status to each question
        questions_with_status = []
        for question in questions_result.data:
            question_data = dict(question)
            question_data["status"] = attempt_lookup.get(
                question["ques_number"], "unattempted"
            )
            questions_with_status.append(question_data)

        # Calculate pagination metadata
        total_pages = math.ceil(total_count / size)
        has_next = page < total_pages
        has_previous = page > 1

        # Construct the paginated response
        response = PaginatedResponse(
            items=questions_with_status,
            total=total_count,
            page=page,
            size=size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            next_page=page + 1 if has_next else None,
            previous_page=page - 1 if has_previous else None
        )

        return response

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