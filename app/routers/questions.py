import math
from io import BytesIO
from typing import Optional, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from supabase import Client

from app.core.auth import get_current_user
from app.core.logging_config import logger, OperationLogger
from app.db import get_supabase
from app.schemas.pagination import PaginatedResponse
from app.schemas.questions import QuestionResponse

router = APIRouter()


@router.get("/", response_model=PaginatedResponse[QuestionResponse])
async def get_questions(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(10, ge=1, le=100, description="Items per page"),
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    q_type: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    try:
        logger.info(
            f"Fetching questions - page: {page}, size: {size}, "
            f"filters: difficulty={difficulty}, topic={topic}, "
            f"source={source}, q_type={q_type}"
        )

        # Calculate skip for pagination
        skip = (page - 1) * size

        # Build base query
        query = supabase.table("TMUA").select("*", count="exact")

        # Apply filters
        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)
        if q_type is not None:
            query = query.eq("q_type", q_type)

        # Get total count without pagination
        total_result = query.execute()
        total_count = total_result.count if hasattr(total_result, "count") else 0

        # Apply pagination and ordering
        query = query.range(skip, skip + size - 1).order("ques_number")
        result = query.execute()

        # Calculate pagination metadata
        total_pages = math.ceil(total_count / size)
        has_next = page < total_pages
        has_previous = page > 1

        response = PaginatedResponse(
            items=result.data,
            total=total_count,
            page=page,
            size=size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=has_previous,
            next_page=page + 1 if has_next else None,
            previous_page=page - 1 if has_previous else None,
        )

        logger.info(
            f"Successfully fetched {len(result.data)} questions. "
            f"Total: {total_count}, Page: {page}/{total_pages}"
        )

        return response

    except Exception as e:
        logger.error(f"Error fetching questions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/filters")
async def get_filter_options(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get all available filter options from the database"""
    try:
        logger.info("Fetching filter options")

        # Get unique values for each filter
        difficulties = supabase.table("TMUA").select("difficulty").execute()
        topics = supabase.table("TMUA").select("topic").execute()
        sources = supabase.table("TMUA").select("source").execute()
        q_types = supabase.table("TMUA").select("q_type").execute()

        # Extract unique values
        unique_difficulties = list(
            set(item["difficulty"] for item in difficulties.data)
        )
        unique_topics = list(set(item["topic"] for item in topics.data))
        unique_sources = list(set(item["source"] for item in sources.data))
        unique_q_types = list(set(item["q_type"] for item in q_types.data))

        return {
            "difficulties": sorted(unique_difficulties),
            "topics": sorted(unique_topics),
            "sources": sorted(unique_sources),
            "q_types": sorted(unique_q_types),
        }
    except Exception as e:
        logger.error(f"Error fetching filter options: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/search")
async def search_questions(
    query: str = Query(None, min_length=3),
    source: Optional[str] = None,
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    skip: int = 0,
    limit: int = 10,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Search questions with optional filters"""
    try:
        logger.info(
            f"Searching questions with query: {query} and filters - source: {source}, difficulty: {difficulty}, topic: {topic}"
        )

        base_query = supabase.table("TMUA").select("*")

        # Apply text search if query is provided
        if query:
            base_query = base_query.textearch("question", query)

        # Apply filters
        if source:
            base_query = base_query.eq("source", source)
        if difficulty:
            base_query = base_query.eq("difficulty", difficulty)
        if topic:
            base_query = base_query.eq("topic", topic)

        # Apply pagination and ordering
        base_query = base_query.range(skip, skip + limit - 1).order("ques_number")
        response = base_query.execute()

        logger.info(f"Found {len(response.data)} questions matching search criteria")
        return response.data
    except Exception as e:
        logger.error(f"Error searching questions: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats")
async def get_questions_stats(
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """Get statistics about the questions database"""
    try:
        logger.info("Fetching question statistics")

        # Total questions count
        total = supabase.table("TMUA").select("*", count="exact").execute()

        # Get unique values for each category
        sources = supabase.table("TMUA").select("source").execute()
        difficulties = supabase.table("TMUA").select("difficulty").execute()
        topics = supabase.table("TMUA").select("topic").execute()

        # Process the data
        unique_sources = list(set(item["source"] for item in sources.data))
        unique_difficulties = list(
            set(item["difficulty"] for item in difficulties.data)
        )
        unique_topics = list(set(item["topic"] for item in topics.data))

        return {
            "total_questions": total.count if hasattr(total, "count") else 0,
            "sources": sorted(unique_sources),
            "difficulties": sorted(unique_difficulties),
            "topics": sorted(unique_topics),
        }
    except Exception as e:
        logger.error(f"Error fetching question statistics: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{ques_number}", response_model=QuestionResponse)
async def get_question(
    ques_number: int,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    try:
        response = (
            supabase.table("TMUA").select("*").eq("ques_number", ques_number).execute()
        )
        if not response.data:
            raise HTTPException(status_code=404, detail="Question not found")
        logger.info(f"Successfully fetched question {ques_number}")
        return response.data[0]
    except Exception as e:
        logger.error(f"Error fetching question {ques_number}: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/import")
async def import_questions(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    with OperationLogger("import_questions", filename=file.filename) as op_logger:
        if not file.filename.endswith((".xls", ".xlsx")):
            logger.warning(f"Invalid file format attempted: {file.filename}")
            raise HTTPException(
                status_code=400,
                detail="Invalid file format. Please upload an Excel file",
            )

        try:
            contents = await file.read()
            df = pd.read_excel(BytesIO(contents))
            questions = []

            for _, row in df.iterrows():
                try:
                    question = {
                        "ques_number": int(row["Serial No"]),
                        "question": str(row["QUESTION"]),
                        "options": str(row["Options"]),
                        "solution": str(row["Correct option"]),
                        "topic": str(row["TAG"]),
                        "difficulty": str(row["Difiiculty tag"]),
                        "source": str(row["Source"]),
                        "q_type": int(row.get("q_type", 0)),
                        "correct_answer": str(row["Correct option"]),
                        "image": str(row["image"])
                        if "image" in row and pd.notna(row["image"])
                        else None,
                        "solution_image": str(row["solution_image"])
                        if "solution_image" in row and pd.notna(row["solution_image"])
                        else None,
                    }
                    questions.append(question)
                except Exception as row_error:
                    logger.error(f"Error processing row: {row_error}")
                    continue

            logger.info(f"Processed {len(questions)} questions from file")

            batch_size = 50
            successful_imports = 0

            for i in range(0, len(questions), batch_size):
                batch = questions[i : i + batch_size]
                try:
                    response = supabase.table("TMUA").insert(batch).execute()
                    successful_imports += len(response.data)
                    logger.debug(
                        f"Imported batch {i//batch_size + 1}, size: {len(batch)}"
                    )
                except Exception as batch_error:
                    logger.error(
                        f"Error importing batch {i//batch_size + 1}: {str(batch_error)}"
                    )
                    continue

            logger.info(
                f"Import completed. Success: {successful_imports}/{len(questions)}"
            )
            return {
                "message": f"Successfully imported {successful_imports} questions out of {len(questions)}",
                "total_processed": len(questions),
                "successful_imports": successful_imports,
            }

        except Exception as e:
            logger.error("Import failed", exc_info=True)
            raise HTTPException(status_code=400, detail=str(e))


@router.post("/validate-excel")
async def validate_excel(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    """
    Validate the Excel file structure before importing.
    """
    if not file.filename.endswith((".xls", ".xlsx")):
        raise HTTPException(
            status_code=400, detail="Invalid file format. Please upload an Excel file"
        )

    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
        required_columns = [
            "Serial No",
            "QUESTION",
            "Options",
            "Correct option",
            "TAG",
            "Difiiculty tag",
            "Source",
        ]

        # Check required columns
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            return {
                "valid": False,
                "error": f"Missing required columns: {', '.join(missing_columns)}",
            }

        # Validate first row as sample
        sample_row = df.iloc[0].to_dict() if not df.empty else None

        return {"valid": True, "total_rows": len(df), "sample": sample_row}

    except Exception as e:
        logger.error(f"Excel validation failed: {str(e)}")
        return {"valid": False, "error": str(e)}


@router.get("/random", response_model=QuestionResponse)
async def get_random_question(
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    exclude_attempted: bool = False,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    try:
        query = supabase.table("TMUA")

        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        if exclude_attempted:
            attempted = (
                supabase.table("user_progress")
                .select("question_id")
                .eq("user_id", current_user.id)
                .execute()
            )
            attempted_ids = [r["question_id"] for r in attempted.data]
            if attempted_ids:
                query = query.not_.in_("id", attempted_ids)

        response = query.limit(1).execute()
        if not response.data:
            raise HTTPException(status_code=404, detail="No questions found")

        return response.data[0]
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/practice-set", response_model=List[QuestionResponse])
async def generate_practice_set(
    count: int = 10,
    difficulty: Optional[str] = None,
    topic: Optional[str] = None,
    source: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    supabase: Client = Depends(get_supabase),
):
    try:
        query = supabase.table("TMUA").select("*")

        if difficulty:
            query = query.eq("difficulty", difficulty)
        if topic:
            query = query.eq("topic", topic)
        if source:
            query = query.eq("source", source)

        response = query.limit(count).execute()
        return response.data
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/topics", response_model=List[str])
async def get_topics(supabase: Client = Depends(get_supabase)):
    try:
        response = supabase.table("TMUA").select("topic").execute()
        topics = list(set(item["topic"] for item in response.data))
        return sorted(topics)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/sources", response_model=List[str])
async def get_sources(supabase: Client = Depends(get_supabase)):
    try:
        response = supabase.table("TMUA").select("source").execute()
        sources = list(set(item["source"] for item in response.data))
        return sorted(sources)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
