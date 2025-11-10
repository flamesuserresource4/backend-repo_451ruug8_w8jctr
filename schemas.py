"""
Database Schemas for FluentLeap

Each Pydantic model represents a collection in MongoDB.
Collection name is the lowercase of the class name.
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import date

class Challenge(BaseModel):
    """Daily challenge containing a GRE word and an idiom"""
    date: str = Field(..., description="ISO date string YYYY-MM-DD")
    word: str
    word_meaning: str
    word_example: Optional[str] = None
    idiom: str
    idiom_meaning: str
    idiom_example: Optional[str] = None

class Story(BaseModel):
    """User submitted story entry"""
    date: str = Field(..., description="ISO date string YYYY-MM-DD")
    text: str
    tokens: int
    unique_words: int
    gre_hits: int

class Feedback(BaseModel):
    """Feedback generated for a story"""
    story_id: str
    readability: str
    strengths: List[str] = []
    suggestions: List[str] = []
    best_version: str
    score: int = Field(..., ge=0, le=100)

class Timelineevent(BaseModel):
    """Timeline event for activity feed"""
    kind: str = Field(..., description="story|feedback|practice|milestone")
    title: str
    detail: Optional[str] = None
    ref_id: Optional[str] = None
    date: str = Field(..., description="ISO date string YYYY-MM-DD")

class Practiceresult(BaseModel):
    """Practice quiz result"""
    date: str
    correct: int
    total: int
    breakdown: List[Dict[str, Any]] = []
