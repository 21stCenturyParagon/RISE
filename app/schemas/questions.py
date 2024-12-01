from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class QuestionBase(BaseModel):
    ques_number: int
    question: str
    options: str  # Raw text format as stored in DB
    solution: str
    topic: str
    difficulty: str
    source: str
    q_type: int
    correct_answer: str
    image: Optional[str] = None
    solution_image: Optional[str] = None


class QuestionCreate(QuestionBase):
    pass


class QuestionResponse(QuestionBase):
    created_at: datetime

    class Config:
        from_attributes = True
