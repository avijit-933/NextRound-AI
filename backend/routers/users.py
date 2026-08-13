"""
routers/users.py — current user + profile endpoints.
"""
import os
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import desc
from sqlalchemy.orm import Session

import models
import schemas
from config import settings
from database import get_db
from utils.security import get_current_user

router = APIRouter(prefix="/api/users", tags=["Users"])

ALLOWED_PICTURE_TYPES = {"image/jpeg", "image/png", "image/webp"}
PROFILE_PICS_DIR = os.path.join(settings.UPLOAD_DIR, "profile_pics")


@router.get("/recent-candidates", response_model=list[schemas.PublicCandidateOut])
def recent_candidates(limit: int = 3, db: Session = Depends(get_db)):
    """
    Public, unauthenticated. Powers the "Candidates who rehearsed here"
    testimonials section on the landing page. Returns only full_name +
    created_at for the most recently registered active, non-admin users —
    never email/phone/is_admin.
    """
    limit = max(1, min(limit, 20))
    return (
        db.query(models.User)
        .filter(models.User.is_admin == False, models.User.is_active == True)  # noqa: E712
        .order_by(desc(models.User.created_at))
        .limit(limit)
        .all()
    )


@router.get("/me", response_model=schemas.UserOut)
def get_me(current_user: models.User = Depends(get_current_user)):
    return current_user


@router.get("/me/profile", response_model=schemas.ProfileOut)
def get_my_profile(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        profile = models.Profile(user_id=current_user.id)
        db.add(profile)
        db.commit()
        db.refresh(profile)
    return profile


@router.put("/me/profile", response_model=schemas.ProfileOut)
def update_my_profile(
    payload: schemas.ProfileUpdate,
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        profile = models.Profile(user_id=current_user.id)
        db.add(profile)

    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)

    db.commit()
    db.refresh(profile)
    return profile


@router.post("/me/profile-picture", response_model=schemas.ProfileOut, status_code=201)
async def upload_profile_picture(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    This is what was actually missing: profile.html's "Change photo" button
    used to just show a toast and do nothing. This endpoint saves the file,
    stores its public URL on the profile, and returns the updated profile
    so the frontend can repaint the avatar immediately — everywhere,
    including the dashboard, since every page reads from this same profile.
    """
    if file.content_type not in ALLOWED_PICTURE_TYPES:
        raise HTTPException(status_code=400, detail="Only JPEG, PNG, or WEBP images are accepted")

    contents = await file.read()
    if len(contents) > settings.MAX_PROFILE_PICTURE_SIZE_MB * 1024 * 1024:
        raise HTTPException(status_code=400, detail=f"Image exceeds {settings.MAX_PROFILE_PICTURE_SIZE_MB}MB limit")

    os.makedirs(PROFILE_PICS_DIR, exist_ok=True)
    ext = os.path.splitext(file.filename or "")[1] or ".jpg"
    stored_name = f"user_{current_user.id}_{uuid.uuid4().hex[:8]}{ext}"
    filepath = os.path.join(PROFILE_PICS_DIR, stored_name)
    with open(filepath, "wb") as f:
        f.write(contents)

    profile = db.query(models.Profile).filter(models.Profile.user_id == current_user.id).first()
    if not profile:
        profile = models.Profile(user_id=current_user.id)
        db.add(profile)

    # Delete the old picture file, if any, now that it's being replaced.
    if profile.profile_picture_url:
        old_name = profile.profile_picture_url.rsplit("/", 1)[-1]
        old_path = os.path.join(PROFILE_PICS_DIR, old_name)
        if os.path.isfile(old_path):
            try:
                os.remove(old_path)
            except OSError:
                pass  # not fatal — an orphaned file is harmless

    profile.profile_picture_url = f"{settings.BACKEND_BASE_URL}/uploads/profile_pics/{stored_name}"

    db.commit()
    db.refresh(profile)
    return profile
