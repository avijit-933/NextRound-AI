"""
routers/resume.py — resume upload, parsing, and FAISS embedding.
"""
import json
import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session

import models
import schemas
from config import settings
from database import get_db
from services import resume_service, rag_service
from utils.security import get_current_user

router = APIRouter(prefix="/api/resume", tags=["Resume"])


@router.post("/upload", response_model=schemas.ResumeOut, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="Only PDF files are accepted")

    contents = await file.read()
    if len(contents) > settings.MAX_RESUME_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"File exceeds {settings.MAX_RESUME_SIZE_MB}MB limit")

    # Mark any previous resumes inactive — only the latest upload is used for RAG.
    db.query(models.Resume).filter(
        models.Resume.user_id == current_user.id, models.Resume.is_active == True  # noqa: E712
    ).update({"is_active": False})

    os.makedirs(settings.UPLOAD_DIR, exist_ok=True)
    stored_name = f"{current_user.id}_{uuid.uuid4().hex[:8]}_{file.filename}"
    filepath = os.path.join(settings.UPLOAD_DIR, stored_name)
    with open(filepath, "wb") as f:
        f.write(contents)

    resume = models.Resume(user_id=current_user.id, filename=file.filename, filepath=filepath)
    db.add(resume)
    db.commit()
    db.refresh(resume)

    # --- Extract + parse (PyMuPDF) ---
    parsed = resume_service.process_resume(filepath)

    resume_text = models.ResumeText(
        resume_id=resume.id,
        raw_text=parsed["raw_text"],
        skills_json=json.dumps(parsed["skills"]),
        education_json=json.dumps(parsed["education"]),
        projects_json=json.dumps(parsed["projects"]),
        experience_json=json.dumps(parsed["experience"]),
        certifications_json=json.dumps(parsed["certifications"]),
    )
    db.add(resume_text)
    db.commit()

    # --- Build FAISS embeddings (Sentence Transformers via LangChain) ---
    namespace = f"user_{current_user.id}_resume_{resume.id}"
    try:
        rag_service.build_index(namespace, parsed["raw_text"])
        resume_text.faiss_namespace = namespace
        resume_text.embedded_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001 — resume is still usable without embeddings
        raise HTTPException(status_code=500, detail=f"Resume saved, but embedding failed: {exc}")

    return _to_resume_out(resume, resume_text)


@router.get("/active", response_model=schemas.ResumeOut)
def get_active_resume(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    resume = (
        db.query(models.Resume)
        .filter(models.Resume.user_id == current_user.id, models.Resume.is_active == True)  # noqa: E712
        .order_by(models.Resume.uploaded_at.desc())
        .first()
    )
    if not resume:
        raise HTTPException(status_code=404, detail="No resume uploaded yet")
    return _to_resume_out(resume, resume.resume_text)


def _to_resume_out(resume: models.Resume, resume_text: models.ResumeText | None) -> schemas.ResumeOut:
    extracted = None
    embedded = False
    if resume_text:
        extracted = schemas.ResumeExtractedData(
            skills=json.loads(resume_text.skills_json or "[]"),
            education=json.loads(resume_text.education_json or "[]"),
            projects=json.loads(resume_text.projects_json or "[]"),
            experience=json.loads(resume_text.experience_json or "[]"),
            certifications=json.loads(resume_text.certifications_json or "[]"),
        )
        embedded = resume_text.faiss_namespace is not None
    return schemas.ResumeOut(
        id=resume.id, filename=resume.filename, uploaded_at=resume.uploaded_at,
        extracted=extracted, embedded=embedded,
    )
