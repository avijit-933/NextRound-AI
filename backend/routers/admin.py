"""
routers/admin.py — admin-only endpoints. All routes require an admin JWT
(see utils.security.get_current_admin).
"""
from statistics import mean
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

import models
import schemas
from database import get_db
from utils.security import get_current_admin

router = APIRouter(prefix="/api/admin", tags=["Admin"])


@router.get("/stats", response_model=schemas.AdminStatsOut)
def get_stats(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    total_users = db.query(models.User).count()
    total_interviews = db.query(models.Interview).count()
    scores = [s.overall_score for s in db.query(models.Score).all()]
    reports_generated = db.query(models.Report).count()

    return schemas.AdminStatsOut(
        total_users=total_users,
        total_interviews=total_interviews,
        average_score=round(mean(scores), 1) if scores else 0.0,
        reports_generated=reports_generated,
    )


@router.get("/users", response_model=List[schemas.UserOut])
def list_users(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    return db.query(models.User).order_by(models.User.created_at.desc()).all()


@router.patch("/users/{user_id}/deactivate")
def deactivate_user(user_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = False
    db.commit()
    return {"status": "deactivated", "user_id": user_id}


@router.patch("/users/{user_id}/activate")
def activate_user(user_id: int, admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = True
    db.commit()
    return {"status": "activated", "user_id": user_id}


@router.get("/reports")
def list_all_reports(admin: models.User = Depends(get_current_admin), db: Session = Depends(get_db)):
    reports = db.query(models.Report).order_by(models.Report.generated_at.desc()).all()
    return [
        {
            "report_id": r.id,
            "interview_id": r.interview_id,
            "candidate": r.interview.user.full_name,
            "job_role": r.interview.job_role,
            "interview_type": r.interview.interview_type.value,
            "score": r.interview.score.overall_score if r.interview.score else None,
            "generated_at": r.generated_at,
        }
        for r in reports
    ]
