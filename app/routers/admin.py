from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from app.core.auth import check_roles, UserRole
from app.core.logging_config import logger
from app.db import get_supabase
from supabase import Client
from typing import List, Optional
from pydantic import BaseModel
import pandas as pd
from datetime import datetime, timedelta

router = APIRouter()


class UserStats(BaseModel):
    user_id: str
    email: str
    name: Optional[str]
    role: str
    total_attempts: int
    correct_attempts: int
    last_active: Optional[datetime]


class UserUpdate(BaseModel):
    role: Optional[UserRole]
    is_active: Optional[bool]


@router.get("/users", response_model=List[UserStats])
async def get_all_users(
    current_user: dict = Depends(check_roles([UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Get statistics for all users"""
    try:
        # Get all users from auth
        users = supabase.auth.admin.list_users()

        # Get progress data for all users
        progress = supabase.table("user_progress").select("*").execute()

        user_stats = []
        for user in users:
            # Filter progress for this user
            user_progress = [p for p in progress.data if p["user_id"] == user.id]

            # Calculate stats
            total_attempts = len(user_progress)
            correct_attempts = len([p for p in user_progress if p["is_correct"]])
            last_active = (
                max([p["attempted_at"] for p in user_progress])
                if user_progress
                else None
            )

            user_stats.append(
                UserStats(
                    user_id=user.id,
                    email=user.email,
                    name=user.user_metadata.get("name"),
                    role=user.user_metadata.get("role", "student"),
                    total_attempts=total_attempts,
                    correct_attempts=correct_attempts,
                    last_active=last_active,
                )
            )

        return user_stats
    except Exception as e:
        logger.error(f"Error fetching user stats: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    user_update: UserUpdate,
    current_user: dict = Depends(check_roles([UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Update user role or status"""
    try:
        update_data = {}
        if user_update.role is not None:
            update_data["role"] = user_update.role

        if update_data:
            await supabase.auth.admin.update_user_by_id(
                user_id, user_metadata=update_data
            )

        return {"message": "User updated successfully"}
    except Exception as e:
        logger.error(f"Error updating user: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(check_roles([UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Delete a user and their data"""
    try:
        # Delete user's progress first
        await supabase.table("user_progress").delete().eq("user_id", user_id).execute()

        # Delete user from auth
        await supabase.auth.admin.delete_user(user_id)

        return {"message": "User and associated data deleted successfully"}
    except Exception as e:
        logger.error(f"Error deleting user: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/stats/system")
async def get_system_stats(
    current_user: dict = Depends(check_roles([UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Get overall system statistics"""
    try:
        # Get counts
        users = len(supabase.auth.admin.list_users())
        questions = supabase.table("TMUA").select("*", count="exact").execute()
        attempts = supabase.table("user_progress").select("*", count="exact").execute()

        # Get recent activity
        recent_attempts = (
            supabase.table("user_progress")
            .select("*")
            .gte("attempted_at", (datetime.now() - timedelta(days=7)).isoformat())
            .execute()
        )

        return {
            "total_users": users,
            "total_questions": questions.count,
            "total_attempts": attempts.count,
            "weekly_active_users": len(set(a["user_id"] for a in recent_attempts.data)),
            "weekly_attempts": len(recent_attempts.data),
        }
    except Exception as e:
        logger.error(f"Error fetching system stats: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/bulk-upload")
async def bulk_upload_questions(
    file: UploadFile = File(...),
    current_user: dict = Depends(check_roles([UserRole.ADMIN])),
    supabase: Client = Depends(get_supabase),
):
    """Bulk upload questions from Excel with validation"""
    try:
        df = pd.read_excel(file.file)
        valid_records = []
        errors = []

        for index, row in df.iterrows():
            try:
                # Validate record
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
                }
                valid_records.append(question)
            except Exception as e:
                errors.append(f"Row {index + 2}: {str(e)}")

        if errors:
            return {
                "status": "partial_success" if valid_records else "failed",
                "errors": errors,
                "valid_count": len(valid_records),
            }

        # Insert valid records
        for batch in [
            valid_records[i : i + 50] for i in range(0, len(valid_records), 50)
        ]:
            supabase.table("TMUA").insert(batch).execute()

        return {
            "status": "success",
            "message": f"Successfully imported {len(valid_records)} questions",
        }
    except Exception as e:
        logger.error(f"Error in bulk upload: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
