"""
schemas.py — Pydantic models for request/response validation.
Keeps the API contract separate from the SQLAlchemy ORM models in models.py.
"""
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------
class UserRegister(BaseModel):
    full_name: str = Field(..., min_length=3, max_length=120)
    email: EmailStr
    phone: str = Field(..., min_length=10, max_length=15)
    password: str = Field(..., min_length=8)
    confirm_password: str

    @field_validator("confirm_password")
    @classmethod
    def passwords_match(cls, v, info):
        if "password" in info.data and v != info.data["password"]:
            raise ValueError("Passwords do not match")
        return v

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, v):
        digits = "".join(filter(str.isdigit, v))
        if len(digits) != 10:
            raise ValueError("Phone number must have exactly 10 digits")
        return digits


class UserLogin(BaseModel):
    email: EmailStr
    password: str
    remember_me: bool = False


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: "UserOut"


class UserOut(BaseModel):
    id: int
    full_name: str
    email: EmailStr
    phone: Optional[str] = None
    is_admin: bool
    created_at: datetime

    class Config:
        from_attributes = True


class PublicCandidateOut(BaseModel):
    """
    Deliberately minimal — used on the public landing page (testimonials
    section) to show real recently-registered candidates WITHOUT leaking
    email/phone/is_admin the way UserOut does. Never expose UserOut on an
    unauthenticated endpoint.
    """
    full_name: str
    created_at: datetime

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------
# Profile
# ---------------------------------------------------------------------
class ProfileUpdate(BaseModel):
    college: Optional[str] = None
    degree: Optional[str] = None
    skills: Optional[str] = None          # comma-separated
    experience: Optional[str] = None
    profile_picture_url: Optional[str] = None


class ProfileOut(BaseModel):
    college: Optional[str]
    degree: Optional[str]
    skills: Optional[str]
    experience: Optional[str]
    profile_picture_url: Optional[str]

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------
# Resume
# ---------------------------------------------------------------------
class ResumeExtractedData(BaseModel):
    skills: List[str] = []
    education: List[str] = []
    projects: List[str] = []
    experience: List[str] = []
    certifications: List[str] = []


class ResumeOut(BaseModel):
    id: int
    filename: str
    uploaded_at: datetime
    extracted: Optional[ResumeExtractedData] = None
    embedded: bool = False

    class Config:
        from_attributes = True


# ---------------------------------------------------------------------
# Interview setup / flow
# ---------------------------------------------------------------------
class InterviewCreate(BaseModel):
    interview_type: str = Field(..., pattern="^(HR|Technical|Coding|Aptitude)$")
    difficulty: str = Field(..., pattern="^(Beginner|Intermediate|Advanced)$")
    job_role: str
    duration_minutes: int = Field(..., ge=5, le=60)
    language: str = "English"


class InterviewOut(BaseModel):
    id: int
    interview_type: str
    difficulty: str
    job_role: str
    duration_minutes: int
    status: str
    started_at: datetime

    class Config:
        from_attributes = True


class QuestionOut(BaseModel):
    id: int
    question_number: int
    question_text: str

    class Config:
        from_attributes = True


class AnswerSubmit(BaseModel):
    question_id: int
    transcript_text: str
    was_skipped: bool = False


class EmotionLogCreate(BaseModel):
    interview_id: int
    timestamp_seconds: int
    happy: float = 0
    neutral: float = 0
    sad: float = 0
    angry: float = 0
    fear: float = 0
    surprise: float = 0


class EyeTrackingLogCreate(BaseModel):
    interview_id: int
    timestamp_seconds: int
    eye_contact_pct: float
    head_pose: str = "Centered"
    face_visible: bool = True
    multiple_faces_detected: bool = False


# ---------------------------------------------------------------------
# Evaluation / Scores / Feedback
# ---------------------------------------------------------------------
class ScoreOut(BaseModel):
    technical_score: float
    communication_score: float
    confidence_score: float
    grammar_score: float
    problem_solving_score: float
    body_language_score: float
    eye_contact_score: float
    emotion_score: float
    overall_score: float

    class Config:
        from_attributes = True


class FeedbackOut(BaseModel):
    feedback_text: Optional[str]
    strengths: List[str] = []
    weaknesses: List[str] = []
    suggestions: List[str] = []

    class Config:
        from_attributes = True


class InterviewResultOut(BaseModel):
    interview: InterviewOut
    score: ScoreOut
    feedback: FeedbackOut


# ---------------------------------------------------------------------
# History / Admin
# ---------------------------------------------------------------------
class HistoryItemOut(BaseModel):
    id: int
    job_role: str
    interview_type: str
    duration_minutes: int
    overall_score: Optional[float]
    started_at: datetime

    class Config:
        from_attributes = True


class AdminStatsOut(BaseModel):
    total_users: int
    total_interviews: int
    average_score: float
    reports_generated: int
