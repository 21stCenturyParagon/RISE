from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
import math
from app.db import get_supabase
from app.core.auth import get_current_user
from supabase import Client
from app.schemas.pagination import PaginatedResponse
from pydantic import BaseModel

router = APIRouter()

# First, let's define our question model
class QuestionResponse(BaseModel):
    ques_number: int
    question: str
    options: str
    topic: str
    difficulty: str
    source: str
    image: Optional[str]
    status: Optional[str]  # For tracking attempt status

@router.get("/", response_model=PaginatedResponse[QuestionResponse])
async def get_questions(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=50, description="Questions per page"),
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Get paginated questions with filters and attempt status.
    The function does the following:
    1. Applies any filters (difficulty, topic, source)
    2. Gets total count for pagination calculations
    3. Gets the specific page of questions requested
    4. Adds attempt status to each question
    5. Returns a paginated response with all necessary metadata
    """
    try:
        # Calculate offset for pagination
        offset = (page - 1) * size

        # Start building our query
        query = supabase.table("TMUA").select("*", count="exact")

        # Apply filters if provided
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        # First get total count for pagination
        total_result = query.execute()
        total_count = total_result.count if hasattr(total_result, "count") else 0

        # Then get the specific page of questions
        query = query.range(offset, offset + size - 1).order("ques_number")
        questions_result = query.execute()

        # Get user's attempts to mark question status
        attempts = supabase.table("user_progress")\
            .select("question_id, is_correct")\
            .eq("user_id", current_user.id)\
            .execute()

        # Create a lookup for quick status checking
        attempt_lookup = {
            a["question_id"]: "correct" if a["is_correct"] else "incorrect"
            for a in attempts.data
        }

        # Add attempt status to each question
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