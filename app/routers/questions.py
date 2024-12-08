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
    status: List[QuestionStatus] = Query(None, description="Filter by multiple statuses"),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase)
):
    try:
        # Get user's attempts first
        attempts = supabase.table("user_progress")\
            .select("question_id, is_correct")\
            .eq("user_id", current_user.id)\
            .execute()

        # If status includes correct/incorrect but no attempts exist, return empty result
        if status and (QuestionStatus.CORRECT in status or QuestionStatus.INCORRECT in status) and not attempts.data:
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                size=size,
                total_pages=0,
                has_next=False,
                has_previous=False,
                next_page=None,
                previous_page=None
            )

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
            has_status_filter = False

            for stat in status:
                if stat == QuestionStatus.CORRECT and correct_ids:
                    filter_ids.update(correct_ids)
                    has_status_filter = True
                elif stat == QuestionStatus.INCORRECT and incorrect_ids:
                    filter_ids.update(incorrect_ids)
                    has_status_filter = True

            # Handle unattempted status
            if QuestionStatus.UNATTEMPTED in status:
                if filter_ids:
                    # Include both filter_ids and unattempted questions
                    query = query.or_(
                        f'ques_number.in.({",".join(map(str, filter_ids))}),'
                        f'ques_number.not.in.({",".join(map(str, attempted_ids))})'
                    )
                else:
                    # Only unattempted questions
                    query = query.not_.in_("ques_number", attempted_ids)
            elif has_status_filter:
                # Only include questions with matching correct/incorrect status
                query = query.in_("ques_number", list(filter_ids))

        # Calculate pagination
        offset = (page - 1) * size

        # Get total count and questions
        total_result = query.execute()
        total_count = total_result.count if hasattr(total_result, "count") else 0

        if total_count == 0:
            return PaginatedResponse(
                items=[],
                total=0,
                page=page,
                size=size,
                total_pages=0,
                has_next=False,
                has_previous=False,
                next_page=None,
                previous_page=None
            )

        # Get page of questions
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
        logger.error(f"Error fetching questions: {str(e)}")
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