"""
routers/interview.py — the core interview loop:
  1. POST /api/interview/            create an interview + generate personalized
                                      questions (Gemini + RAG over the resume).
  2. GET  /api/interview/{id}/questions
  3. POST /api/interview/{id}/answer            submit a transcribed/typed answer
  4. POST /api/interview/{id}/answer-audio      submit raw audio -> Whisper -> text
  5. POST /api/interview/{id}/vision-frame      one webcam frame -> OpenCV/MediaPipe
  6. POST /api/interview/{id}/emotion-frame     one webcam frame -> DeepFace
  7. POST /api/interview/{id}/complete          finalize: evaluate all answers,
                                                 aggregate scores, generate feedback
"""
from datetime import datetime
from statistics import mean
from typing import List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from pydantic import BaseModel
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from services import gemini_service, rag_service, speech_service, vision_service, emotion_service
from utils.security import get_current_user

router = APIRouter(prefix="/api/interview", tags=["Interview"])


@router.post("/", response_model=schemas.InterviewOut, status_code=201)
def create_interview(
    payload: schemas.InterviewCreate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    resume = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == current_user.id, models.Resume.is_active == True)  # noqa: E712
        .first()
    )

    interview = models.Interview(
        user_id=current_user.id,
        resume_id=resume.id if resume else None,
        interview_type=payload.interview_type,
        difficulty=payload.difficulty,
        job_role=payload.job_role,
        duration_minutes=payload.duration_minutes,
        language=payload.language,
        status=models.InterviewStatus.IN_PROGRESS,
    )
    db.add(interview)
    db.commit()
    db.refresh(interview)

    # --- RAG: pull relevant resume chunks for this role/type ---
    resume_context: List[str] = []
    if resume and resume.resume_text and resume.resume_text.faiss_namespace:
        query = f"{payload.job_role} {payload.interview_type} {payload.difficulty}"
        resume_context = rag_service.retrieve_relevant_context(resume.resume_text.faiss_namespace, query)

    question_count = {"10": 4, "20": 6, "30": 8}.get(str(payload.duration_minutes), 6)
    generated_questions = gemini_service.generate_questions(
        interview_type=payload.interview_type,
        job_role=payload.job_role,
        difficulty=payload.difficulty,
        resume_context=resume_context,
        num_questions=question_count,
    )

    for i, q in enumerate(generated_questions, start=1):
        db.add(models.Question(
            interview_id=interview.id,
            question_number=i,
            question_text=q["question"],
            ideal_answer=q.get("ideal_answer") or None,
        ))
    db.commit()

    return interview


@router.get("/{interview_id}/questions", response_model=List[schemas.QuestionOut])
def get_questions(
    interview_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned_interview(interview_id, current_user, db)
    return (
        db.query(models.Question)
        .filter(models.Question.interview_id == interview.id)
        .order_by(models.Question.question_number)
        .all()
    )


@router.post("/{interview_id}/answer")
def submit_answer(
    interview_id: int,
    payload: schemas.AnswerSubmit,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned_interview(interview_id, current_user, db)
    question = (
        db.query(models.Question)
        .filter(models.Question.id == payload.question_id, models.Question.interview_id == interview.id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found in this interview")

    answer = question.answer or models.Answer(question_id=question.id)
    answer.transcript_text = payload.transcript_text
    answer.was_skipped = payload.was_skipped
    answer.submitted_at = datetime.utcnow()
    db.add(answer)
    db.commit()
    return {"status": "ok"}


@router.post("/{interview_id}/answer-audio")
async def submit_answer_audio(
    interview_id: int,
    question_id: int,
    audio: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Alternative to /answer: upload raw recorded audio and let Whisper transcribe it."""
    interview = _get_owned_interview(interview_id, current_user, db)
    question = (
        db.query(models.Question)
        .filter(models.Question.id == question_id, models.Question.interview_id == interview.id)
        .first()
    )
    if not question:
        raise HTTPException(status_code=404, detail="Question not found in this interview")

    audio_bytes = await audio.read()
    suffix = "." + (audio.filename.split(".")[-1] if "." in audio.filename else "webm")
    transcript = speech_service.transcribe_audio_bytes(audio_bytes, suffix=suffix)

    answer = question.answer or models.Answer(question_id=question.id)
    answer.transcript_text = transcript
    answer.submitted_at = datetime.utcnow()
    db.add(answer)
    db.commit()
    return {"transcript_text": transcript}


class FrameIn(BaseModel):
    image_base64: str
    timestamp_seconds: int


@router.post("/{interview_id}/vision-frame")
def submit_vision_frame(
    interview_id: int,
    payload: FrameIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned_interview(interview_id, current_user, db)
    analysis = vision_service.analyze_frame(payload.image_base64)

    db.add(models.EyeTrackingLog(
        interview_id=interview.id,
        timestamp_seconds=payload.timestamp_seconds,
        eye_contact_pct=analysis["eye_contact_pct"],
        head_pose=analysis["head_pose"],
        face_visible=analysis["face_visible"],
        multiple_faces_detected=analysis["multiple_faces_detected"],
    ))
    db.commit()
    return analysis


@router.post("/{interview_id}/emotion-frame")
def submit_emotion_frame(
    interview_id: int,
    payload: FrameIn,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned_interview(interview_id, current_user, db)
    scores = emotion_service.analyze_emotion(payload.image_base64)

    db.add(models.EmotionLog(
        interview_id=interview.id,
        timestamp_seconds=payload.timestamp_seconds,
        **scores,
    ))
    db.commit()
    return scores


@router.post("/{interview_id}/complete", response_model=schemas.InterviewResultOut)
def complete_interview(
    interview_id: int,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    interview = _get_owned_interview(interview_id, current_user, db)
    questions = (
        db.query(models.Question)
        .filter(models.Question.interview_id == interview.id)
        .order_by(models.Question.question_number)
        .all()
    )

    eye_logs = db.query(models.EyeTrackingLog).filter(models.EyeTrackingLog.interview_id == interview.id).all()
    emotion_logs = db.query(models.EmotionLog).filter(models.EmotionLog.interview_id == interview.id).all()

    avg_eye_contact = mean([e.eye_contact_pct for e in eye_logs]) if eye_logs else 75.0
    avg_emotions = {
        key: mean([getattr(e, key) for e in emotion_logs]) if emotion_logs else 0.0
        for key in ("happy", "neutral", "sad", "angry", "fear", "surprise")
    }
    dominant = emotion_service.dominant_emotion(avg_emotions) if emotion_logs else "neutral"
    pct_face_visible = (
        sum(1 for e in eye_logs if e.face_visible) / len(eye_logs) * 100 if eye_logs else 100.0
    )

    per_question_results = []
    for q in questions:
        answer_text = q.answer.transcript_text if q.answer else ""
        eval_result = gemini_service.evaluate_answer(
            interview_type=interview.interview_type.value,
            job_role=interview.job_role,
            difficulty=interview.difficulty.value,
            question=q.question_text,
            answer=answer_text,
            eye_contact=avg_eye_contact,
            dominant_emotion=dominant,
            ideal_answer=q.ideal_answer or "",
        )
        per_question_results.append(eval_result)

        # Persist per-question correctness/feedback/model-answer so the report
        # page can show "what a possible correct answer looks like" and "how
        # much of your answer was correct" without re-calling Gemini.
        answer_row = q.answer or models.Answer(question_id=q.id)
        answer_row.correctness_pct = eval_result.get("correctness_percentage")
        answer_row.ai_feedback = eval_result.get("feedback")
        answer_row.possible_answer = eval_result.get("possible_answer") or q.ideal_answer
        db.add(answer_row)

    def avg_field(field):
        vals = [r[field] for r in per_question_results if field in r]
        return mean(vals) if vals else 70.0

    technical = avg_field("technical_score")
    communication = avg_field("communication_score")
    confidence = avg_field("confidence_score")
    grammar = avg_field("grammar_score")
    problem_solving = avg_field("problem_solving_score")
    body_language = pct_face_visible
    eye_contact_score = avg_eye_contact
    emotion_score = avg_emotions.get("happy", 0) + avg_emotions.get("neutral", 0)

    overall = mean([
        technical, communication, confidence, grammar,
        problem_solving, body_language, eye_contact_score, min(emotion_score, 100),
    ])

    score = interview.score or models.Score(interview_id=interview.id)
    score.technical_score = technical
    score.communication_score = communication
    score.confidence_score = confidence
    score.grammar_score = grammar
    score.problem_solving_score = problem_solving
    score.body_language_score = body_language
    score.eye_contact_score = eye_contact_score
    score.emotion_score = min(emotion_score, 100)
    score.overall_score = overall
    db.add(score)

    combined_feedback_text = " ".join(r.get("feedback", "") for r in per_question_results)
    strengths, weaknesses, suggestions = _summarize_feedback(overall, avg_eye_contact, dominant)

    feedback = interview.feedback or models.Feedback(interview_id=interview.id)
    feedback.feedback_text = combined_feedback_text[:2000]
    feedback.strengths = _json(strengths)
    feedback.weaknesses = _json(weaknesses)
    feedback.suggestions = _json(suggestions)
    db.add(feedback)

    interview.status = models.InterviewStatus.COMPLETED
    interview.completed_at = datetime.utcnow()
    db.add(interview)
    db.commit()
    db.refresh(interview)
    db.refresh(score)
    db.refresh(feedback)

    return schemas.InterviewResultOut(
        interview=interview,
        score=score,
        feedback=schemas.FeedbackOut(
            feedback_text=feedback.feedback_text,
            strengths=strengths, weaknesses=weaknesses, suggestions=suggestions,
        ),
    )


# ---------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------
def _get_owned_interview(interview_id: int, user: models.User, db: Session) -> models.Interview:
    interview = db.query(models.Interview).filter(models.Interview.id == interview_id).first()
    if not interview:
        raise HTTPException(status_code=404, detail="Interview not found")
    if interview.user_id != user.id:
        raise HTTPException(status_code=403, detail="Not your interview")
    return interview


def _json(items: List[str]) -> str:
    import json
    return json.dumps(items)


def _summarize_feedback(overall: float, eye_contact: float, dominant_emotion: str):
    strengths, weaknesses, suggestions = [], [], []

    if overall >= 80:
        strengths.append("Strong overall command of the material across most questions")
    elif overall < 60:
        weaknesses.append("Overall performance suggests more preparation is needed")
        suggestions.append("Revisit the core fundamentals for this role before the next attempt")

    if eye_contact >= 80:
        strengths.append("Maintained strong eye contact throughout the session")
    else:
        weaknesses.append("Eye contact dropped below an ideal level during parts of the interview")
        suggestions.append("Practice keeping your gaze on the camera lens, even while thinking")

    if dominant_emotion in ("happy", "neutral"):
        strengths.append("Composed, steady emotional tone during responses")
    elif dominant_emotion in ("fear", "sad", "angry"):
        weaknesses.append(f"Detected emotional tone skewed toward '{dominant_emotion}' — may read as tension")
        suggestions.append("Take a breath before answering to settle nerves and steady your tone")

    if not strengths:
        strengths.append("Completed the full interview session")
    if not suggestions:
        suggestions.append("Keep practicing with varied question types to build consistency")

    return strengths, weaknesses, suggestions
