"""
routers/contact.py — public contact-form endpoint (landing page). No auth
required since anonymous visitors submit it.
"""
import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, EmailStr, Field

from services import contact_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["Contact"])


class ContactMessage(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    email: EmailStr
    message: str = Field(..., min_length=1, max_length=5000)


@router.post("/contact", status_code=201)
def submit_contact_message(payload: ContactMessage):
    try:
        contact_service.send_contact_message(payload.name, payload.email, payload.message)
    except Exception as exc:  # noqa: BLE001 — surface a clean error, don't leak SMTP internals
        logger.error("Failed to send contact email: %s", exc)
        raise HTTPException(status_code=502, detail="Couldn't send your message right now. Please try again shortly.")
    return {"status": "sent"}
