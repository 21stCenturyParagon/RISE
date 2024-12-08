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
    # Accept multiple status values
    status: List[QuestionStatus] = Query(None, description="Filter by multiple statuses"),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    """
    Get paginated questions with filters including multiple statuses.
    Example: status=correct&status=incorrect will show both correct and incorrect attempts.
    """
    try:
        # Get user's attempts
        attempts = supabase.table("user_progress")\
            .select("question_id, is_correct")\
            .eq("user_id", current_user.id)\
            .execute()

        # Create lookups
        attempt_lookup = {
            a["question_id"]: "correct" if a["is_correct"] else "incorrect"
            for a in attempts.data
        }

        attempted_ids = list(attempt_lookup.keys())
        correct_ids = [qid for qid, stat in attempt_lookup.items() if stat == "correct"]
        incorrect_ids = [qid for qid, stat in attempt_lookup.items() if stat == "incorrect"]

        # Build query
        query = supabase.table("TMUA").select("*", count="exact")

        # Apply basic filters
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        # Apply status filters if provided
        if status:
            filter_ids = set()

            # Collect all question IDs that match any of the requested statuses
            for stat in status:
                if stat == QuestionStatus.CORRECT:
                    filter_ids.update(correct_ids)
                elif stat == QuestionStatus.INCORRECT:
                    filter_ids.update(incorrect_ids)
                elif stat == QuestionStatus.UNATTEMPTED:
                    # For unattempted, we need to handle it differently
                    # We'll apply it after getting the questions
                    continue

            # If unattempted is one of the statuses, we need to include questions
            # that aren't in attempted_ids
            if QuestionStatus.UNATTEMPTED in status:
                if filter_ids:
                    # If we have other statuses, we need to use OR condition
                    query = query.or_(f'ques_number.in.({",".join(map(str, filter_ids))}),ques_number.not.in.({",".join(map(str, attempted_ids))})')
                else:
                    # If only unattempted is requested
                    query = query.not_.in_("ques_number", attempted_ids)
            elif filter_ids:
                # If we only have correct/incorrect statuses
                query = query.in_("ques_number", list(filter_ids))

        # Calculate pagination
        offset = (page - 1) * size

        # Get total count
        total_result = query.execute()
        total_count = total_result.count if hasattr(total_result, "count") else 0

        # Get page of questions
        query = query.range(offset, offset + size - 1).order("ques_number")
        questions_result = query.execute()

        # Add status to questions
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

        return PaginatedResponse(
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