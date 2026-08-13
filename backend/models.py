"""
models.py — SQLAlchemy ORM models.

Tables: users, profiles, resumes, resume_text, interviews, questions,
answers, feedback, scores, emotion_log, eye_tracking_log, reports.
"""
import enum
from datetime import datetime

from sqlalchemy import (
    Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text
)
from sqlalchemy.orm import relationship

from database import Base


# ---------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------
class InterviewType(str, enum.Enum):
    HR = "HR"
    TECHNICAL = "Technical"
    CODING = "Coding"
    APTITUDE = "Aptitude"


class DifficultyLevel(str, enum.Enum):
    BEGINNER = "Beginner"
    INTERMEDIATE = "Intermediate"
    ADVANCED = "Advanced"


class InterviewStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


# ---------------------------------------------------------------------
# Users & Profiles
# ---------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    full_name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    phone = Column(String(20), nullable=True)
    password_hash = Column(String(255), nullable=False)
    is_admin = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    profile = relationship("Profile", back_populates="user", uselist=False, cascade="all, delete-orphan")
    resumes = relationship("Resume", back_populates="user", cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="user", cascade="all, delete-orphan")


class Profile(Base):
    __tablename__ = "profiles"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    profile_picture_url = Column(String(255), nullable=True)
    college = Column(String(150), nullable=True)
    degree = Column(String(150), nullable=True)
    skills = Column(Text, nullable=True)        # comma-separated, simple + fast to render
    experience = Column(String(100), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User", back_populates="profile")


# ---------------------------------------------------------------------
# Resume + parsed text / embeddings pointer
# ---------------------------------------------------------------------
class Resume(Base):
    __tablename__ = "resumes"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    filepath = Column(String(500), nullable=False)
    is_active = Column(Boolean, default=True)      # most recently uploaded resume in use
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="resumes")
    resume_text = relationship("ResumeText", back_populates="resume", uselist=False, cascade="all, delete-orphan")
    interviews = relationship("Interview", back_populates="resume")


class ResumeText(Base):
    __tablename__ = "resume_text"

    id = Column(Integer, primary_key=True, index=True)
    resume_id = Column(Integer, ForeignKey("resumes.id"), unique=True, nullable=False)

    raw_text = Column(Text, nullable=True)
    skills_json = Column(Text, nullable=True)          # JSON-encoded list
    education_json = Column(Text, nullable=True)        # JSON-encoded list
    projects_json = Column(Text, nullable=True)         # JSON-encoded list
    experience_json = Column(Text, nullable=True)        # JSON-encoded list
    certifications_json = Column(Text, nullable=True)   # JSON-encoded list

    # Identifier of this resume's vectors inside the FAISS index (see services/resume_service.py)
    faiss_namespace = Column(String(100), nullable=True)
    embedded_at = Column(DateTime, nullable=True)

    resume = relationship("Resume", back_populates="resume_text")


# ---------------------------------------------------------------------
# Interview + Questions + Answers
# ---------------------------------------------------------------------
class Interview(Base):
    __tablename__ = "interviews"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    resume_id = Column(Integer, ForeignKey("resumes.id"), nullable=True)

    interview_type = Column(Enum(InterviewType), nullable=False)
    difficulty = Column(Enum(DifficultyLevel), nullable=False)
    job_role = Column(String(100), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    language = Column(String(30), default="English")
    status = Column(Enum(InterviewStatus), default=InterviewStatus.IN_PROGRESS)

    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="interviews")
    resume = relationship("Resume", back_populates="interviews")
    questions = relationship("Question", back_populates="interview", cascade="all, delete-orphan")
    feedback = relationship("Feedback", back_populates="interview", uselist=False, cascade="all, delete-orphan")
    score = relationship("Score", back_populates="interview", uselist=False, cascade="all, delete-orphan")
    emotion_logs = relationship("EmotionLog", back_populates="interview", cascade="all, delete-orphan")
    eye_tracking_logs = relationship("EyeTrackingLog", back_populates="interview", cascade="all, delete-orphan")
    report = relationship("Report", back_populates="interview", uselist=False, cascade="all, delete-orphan")


class Question(Base):
    __tablename__ = "questions"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False)
    question_number = Column(Integer, nullable=False)
    question_text = Column(Text, nullable=False)
    generated_by = Column(String(50), default="gemini")   # audit trail: which model/source produced it
    # Model-answer reference generated alongside the question. NEVER returned by the
    # /questions endpoint while the interview is live — only surfaced afterwards, in
    # the report/detail views, so it can't leak the "correct" answer mid-interview.
    ideal_answer = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("Interview", back_populates="questions")
    answer = relationship("Answer", back_populates="question", uselist=False, cascade="all, delete-orphan")


class Answer(Base):
    __tablename__ = "answers"

    id = Column(Integer, primary_key=True, index=True)
    question_id = Column(Integer, ForeignKey("questions.id"), unique=True, nullable=False)
    transcript_text = Column(Text, nullable=True)
    audio_filepath = Column(String(500), nullable=True)
    was_skipped = Column(Boolean, default=False)
    submitted_at = Column(DateTime, default=datetime.utcnow)

    # --- populated once the interview is scored (see routers/interview.py complete_interview) ---
    correctness_pct = Column(Float, nullable=True)      # 0-100: how much of the expected answer was covered
    ai_feedback = Column(Text, nullable=True)           # short, question-specific feedback from Gemini
    possible_answer = Column(Text, nullable=True)       # a strong model answer, shown for comparison in the report

    question = relationship("Question", back_populates="answer")


# ---------------------------------------------------------------------
# Feedback + Scores
# ---------------------------------------------------------------------
class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), unique=True, nullable=False)

    feedback_text = Column(Text, nullable=True)
    strengths = Column(Text, nullable=True)         # JSON-encoded list of strings
    weaknesses = Column(Text, nullable=True)        # JSON-encoded list of strings
    suggestions = Column(Text, nullable=True)       # JSON-encoded list of strings
    created_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("Interview", back_populates="feedback")


class Score(Base):
    __tablename__ = "scores"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), unique=True, nullable=False)

    technical_score = Column(Float, default=0.0)
    communication_score = Column(Float, default=0.0)
    confidence_score = Column(Float, default=0.0)
    grammar_score = Column(Float, default=0.0)
    problem_solving_score = Column(Float, default=0.0)
    body_language_score = Column(Float, default=0.0)
    eye_contact_score = Column(Float, default=0.0)
    emotion_score = Column(Float, default=0.0)
    overall_score = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("Interview", back_populates="score")


# ---------------------------------------------------------------------
# Live analysis logs (webcam + emotion), captured during the interview
# ---------------------------------------------------------------------
class EmotionLog(Base):
    __tablename__ = "emotion_log"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False)
    timestamp_seconds = Column(Integer, nullable=False)

    happy = Column(Float, default=0.0)
    neutral = Column(Float, default=0.0)
    sad = Column(Float, default=0.0)
    angry = Column(Float, default=0.0)
    fear = Column(Float, default=0.0)
    surprise = Column(Float, default=0.0)

    interview = relationship("Interview", back_populates="emotion_logs")


class EyeTrackingLog(Base):
    __tablename__ = "eye_tracking_log"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), nullable=False)
    timestamp_seconds = Column(Integer, nullable=False)

    eye_contact_pct = Column(Float, default=0.0)
    head_pose = Column(String(30), default="Centered")   # Centered / Left / Right / Up / Down
    face_visible = Column(Boolean, default=True)
    multiple_faces_detected = Column(Boolean, default=False)

    interview = relationship("Interview", back_populates="eye_tracking_logs")


# ---------------------------------------------------------------------
# Reports (generated PDF)
# ---------------------------------------------------------------------
class Report(Base):
    __tablename__ = "reports"

    id = Column(Integer, primary_key=True, index=True)
    interview_id = Column(Integer, ForeignKey("interviews.id"), unique=True, nullable=False)
    pdf_filepath = Column(String(500), nullable=True)
    generated_at = Column(DateTime, default=datetime.utcnow)

    interview = relationship("Interview", back_populates="report")
