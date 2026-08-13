"""
main.py — FastAPI application entrypoint.

Run locally with:
    uvicorn main:app --reload --port 8000

Interactive API docs will be at http://localhost:8000/docs
"""
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from config import settings
from database import Base, engine
import models  # noqa: F401 — ensures all models are registered on Base before create_all
from routers import auth, users, resume, interview, reports, admin, contact

logging.basicConfig(level=logging.INFO if not settings.DEBUG else logging.DEBUG)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.APP_NAME,
    description="Backend for the AI Interview Assistant — resume-aware question "
                 "generation, webcam + speech analysis, and AI evaluation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Public static files — profile pictures ONLY. Deliberately a dedicated
# subfolder, not the whole UPLOAD_DIR: resumes also live under UPLOAD_DIR
# and contain personal data, so they must stay behind the authenticated
# /api/resume endpoints and never be served as public static files.
PROFILE_PICS_DIR = os.path.join(settings.UPLOAD_DIR, "profile_pics")
os.makedirs(PROFILE_PICS_DIR, exist_ok=True)
app.mount("/uploads/profile_pics", StaticFiles(directory=PROFILE_PICS_DIR), name="profile_pics")

app.include_router(auth.router)
app.include_router(users.router)
app.include_router(resume.router)
app.include_router(interview.router)
app.include_router(reports.router)
app.include_router(admin.router)
app.include_router(contact.router)


@app.on_event("startup")
def on_startup():
    # For production, prefer Alembic migrations over create_all().
    Base.metadata.create_all(bind=engine)
    logger.info("%s started in %s mode", settings.APP_NAME, settings.ENV)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": settings.APP_NAME}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
