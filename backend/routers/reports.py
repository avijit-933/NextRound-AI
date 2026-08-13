"""
routers/reports.py — interview history, a single result's detail, and
PDF report generation/download.
"""
import json
from statistics import mean
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from services import report_service
from config import settings
from utils.security import get_current_user

router = APIRouter(prefix="/api", tags=["Reports & History"])


@router.get("/history", response_model=List[schemas.HistoryItemOut])
def get_history(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    interviews = (
        db.query(models.Interview)
        .filter(models.Interview.user_id == current_user.id)
        .order_by(models.Interview.started_at.desc())
        .all()
    )
    results = []
    for interview in interviews:
        results.append(schemas.HistoryItemOut(
            id=interview.id,
            job_role=interview.job_role,
            interview_type=interview.interview_type.value,
            duration_minutes=interview.duration_minutes,
            overall_score=interview.score.overall_score if interview.score else None,
            started_at=interview.started_at,
        ))
    return results


@router.get("/interview/{interview_id}/result", response_model=schemas.InterviewResultOut)
def get_result(interview_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview or interview.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    if not interview.score or not interview.feedback:
        raise HTTPException(status_code=409, detail="Interview has not been evaluated yet")

    return schemas.InterviewResultOut(
        interview=interview,
        score=interview.score,
        feedback=schemas.FeedbackOut(
            feedback_text=interview.feedback.feedback_text,
            strengths=json.loads(interview.feedback.strengths or "[]"),
            weaknesses=json.loads(interview.feedback.weaknesses or "[]"),
            suggestions=json.loads(interview.feedback.suggestions or "[]"),
        ),
    )


@router.get("/interview/{interview_id}/detail")
def get_interview_detail(interview_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Full detail for the on-page report view: Q&A pairs, emotion timeline,
    and eye-contact series — everything report_service.py also bakes into the
    PDF, but as JSON so the frontend can render it without downloading a file."""
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview or interview.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    if not interview.score or not interview.feedback:
        raise HTTPException(status_code=409, detail="Interview has not been evaluated yet")

    qa_pairs = [
        {
            "question": q.question_text,
            "answer": q.answer.transcript_text if q.answer else None,
            "was_skipped": q.answer.was_skipped if q.answer else True,
            "correctness_pct": q.answer.correctness_pct if q.answer else None,
            "possible_answer": (q.answer.possible_answer if q.answer else None) or q.ideal_answer,
            "ai_feedback": q.answer.ai_feedback if q.answer else None,
        }
        for q in sorted(interview.questions, key=lambda q: q.question_number)
    ]

    eye_logs = sorted(interview.eye_tracking_logs, key=lambda e: e.timestamp_seconds)
    emotion_logs = sorted(interview.emotion_logs, key=lambda e: e.timestamp_seconds)

    correctness_values = [qa["correctness_pct"] for qa in qa_pairs if qa["correctness_pct"] is not None]
    avg_correctness_pct = mean(correctness_values) if correctness_values else None

    return {
        "interview": schemas.InterviewOut.model_validate(interview),
        "score": schemas.ScoreOut.model_validate(interview.score),
        "feedback": {
            "strengths": json.loads(interview.feedback.strengths or "[]"),
            "weaknesses": json.loads(interview.feedback.weaknesses or "[]"),
            "suggestions": json.loads(interview.feedback.suggestions or "[]"),
        },
        "avg_correctness_pct": avg_correctness_pct,
        "qa_pairs": qa_pairs,
        "eye_contact_timeline": [
            {"timestamp_seconds": e.timestamp_seconds, "eye_contact_pct": e.eye_contact_pct} for e in eye_logs
        ],
        "emotion_timeline": [
            {
                "timestamp_seconds": e.timestamp_seconds, "happy": e.happy, "neutral": e.neutral,
                "sad": e.sad, "angry": e.angry, "fear": e.fear, "surprise": e.surprise,
            }
            for e in emotion_logs
        ],
        "candidate_name": interview.user.full_name,
    }


@router.post("/interview/{interview_id}/report", status_code=201)
def generate_report(interview_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview or interview.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    if not interview.score or not interview.feedback:
        raise HTTPException(status_code=409, detail="Interview has not been evaluated yet")

    qa_pairs = [
        {
            "question": q.question_text,
            "answer": q.answer.transcript_text if q.answer else None,
            "ai_feedback": q.answer.ai_feedback if q.answer else None,
            "correctness_pct": q.answer.correctness_pct if q.answer else None,
            "possible_answer": (q.answer.possible_answer if q.answer else None) or q.ideal_answer,
        }
        for q in interview.questions
    ]

    eye_logs = interview.eye_tracking_logs
    emotion_logs = interview.emotion_logs
    avg_eye_contact = mean([e.eye_contact_pct for e in eye_logs]) if eye_logs else interview.score.eye_contact_score
    emotion_summary = {
        key: mean([getattr(e, key) for e in emotion_logs]) if emotion_logs else 0.0
        for key in ("happy", "neutral", "sad", "angry", "fear", "surprise")
    }

    filepath = report_service.generate_interview_report(
        output_dir=settings.UPLOAD_DIR + "/reports",
        interview_meta={
            "interview_id": interview.id,
            "candidate_name": interview.user.full_name,
            "job_role": interview.job_role,
            "interview_type": interview.interview_type.value,
            "date": interview.started_at.strftime("%Y-%m-%d"),
            "duration_minutes": interview.duration_minutes,
        },
        qa_pairs=qa_pairs,
        scores={
            "technical_score": interview.score.technical_score,
            "communication_score": interview.score.communication_score,
            "confidence_score": interview.score.confidence_score,
            "grammar_score": interview.score.grammar_score,
            "problem_solving_score": interview.score.problem_solving_score,
            "body_language_score": interview.score.body_language_score,
            "eye_contact_score": interview.score.eye_contact_score,
            "emotion_score": interview.score.emotion_score,
            "overall_score": interview.score.overall_score,
        },
        feedback={
            "strengths": json.loads(interview.feedback.strengths or "[]"),
            "weaknesses": json.loads(interview.feedback.weaknesses or "[]"),
            "suggestions": json.loads(interview.feedback.suggestions or "[]"),
        },
        eye_contact_avg=avg_eye_contact,
        emotion_summary=emotion_summary,
    )

    report = interview.report or models.Report(interview_id=interview.id)
    report.pdf_filepath = filepath
    db.add(report)
    db.commit()

    return {"report_id": report.id, "download_url": f"/api/interview/{interview.id}/report/download"}


@router.get("/interview/{interview_id}/report/download")
def download_report(interview_id: int, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview or interview.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Interview not found")
    if not interview.report or not interview.report.pdf_filepath:
        raise HTTPException(status_code=404, detail="Report has not been generated yet — call POST .../report first")

    return FileResponse(
        interview.report.pdf_filepath,
        media_type="application/pdf",
        filename=f"NextRoundAI_Report_{interview.id}.pdf",
    )
