# NextRound AI — AI Interview Assistant

A resume-aware mock interview platform: upload your resume, take a mock
interview on camera, and get an AI-scored report on technical depth,
communication, confidence, eye contact and emotion.

The project has two parts, in sibling folders:

```
your-project-root/
├── .gitignore
├── README.md                   ← this file
├── backend/            # FastAPI + MySQL
└── frontend/          # Static HTML/CSS/JS, no build step
```

---

## Stack

**Backend**
- FastAPI + Uvicorn
- MySQL via SQLAlchemy (Alembic for migrations)
- JWT auth (access + refresh tokens), bcrypt password hashing
- Google Gemini — question generation & scoring
- LangChain + FAISS + Sentence-Transformers — RAG over the candidate's resume
- OpenAI Whisper — answer transcription
- OpenCV + MediaPipe — eye contact / head pose
- DeepFace + TensorFlow — emotion recognition
- fpdf2 — downloadable PDF scorecards

**Frontend**
- Plain HTML + vanilla JS (no framework, no bundler)
- Bootstrap 5 + Bootstrap Icons (CDN)
- Google Fonts: Space Grotesk (display), Inter (body), JetBrains Mono (data)
- `js/api.js` — typed wrappers around every backend endpoint, including
  token storage/refresh
- `js/main.js` — shared chrome: theme toggle, auth-aware nav, avatar
  painting, scroll-reveal, toasts

---

## Backend setup

**1. Prerequisites:** Python 3.10+, a running MySQL server.

**2. Install dependencies**

```bash
cd nextround-backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

**3. Configure environment variables**

Create a `.env` file in `nextround-backend/`. At minimum you need a real
database connection, a `JWT_SECRET_KEY`, and a `GEMINI_API_KEY`.

| Variable | Default | Notes |
|---|---|---|
| `ENV` | `development` | `production` disables debug logging |
| `DEBUG` | `true` | |
| `CORS_ORIGINS` | `http://localhost:5500,http://127.0.0.1:5500` | **Must exactly match** the scheme+host+port the frontend is served from, or requests get silently blocked |
| `DATABASE_URL` | built from `DB_*` below | Full SQLAlchemy URL overrides the individual `DB_*` vars |
| `DB_USER` / `DB_PASSWORD` / `DB_HOST` / `DB_PORT` / `DB_NAME` | `root` / `password` / `localhost` / `3306` / `nextround_ai` | |
| `JWT_SECRET_KEY` | `CHANGE_ME_IN_PRODUCTION` | **Set a real secret before deploying** |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `7` | |
| `GEMINI_API_KEY` | — | Required for question generation & scoring |
| `GEMINI_MODEL` | `gemini-1.5-pro` | |
| `EMBEDDING_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model for resume RAG |
| `WHISPER_MODEL_SIZE` | `base` | Larger = more accurate, slower, more RAM |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `CONTACT_TO_EMAIL` | — | If `SMTP_HOST` is blank, the contact form logs messages instead of emailing them |
| `UPLOAD_DIR` | `uploads` | |

**4. Create the database**

```sql
CREATE DATABASE nextround_ai CHARACTER SET utf8mb4;
```

Tables are created automatically on startup (`Base.metadata.create_all`). For
production, switch to Alembic migrations instead.

**5. Run**

```bash
uvicorn main:app --reload --port 8000
```

- API docs (Swagger): `http://localhost:8000/docs`
- Health check: `GET /health`

### Backend layout

```
nextround-backend/
├── main.py            # FastAPI app entrypoint, CORS, router registration
├── config.py           # Settings loaded from environment variables
├── database.py         # SQLAlchemy engine/session
├── models.py            # ORM models
├── schemas.py            # Pydantic request/response models
├── routers/               # auth, users, resume, interview, reports, admin, contact
├── services/                # Gemini, RAG, Whisper, OpenCV/MediaPipe, DeepFace, PDF, email
├── utils/security.py          # JWT + password hashing helpers
├── uploads/                     # Resumes, profile pictures (gitignored)
└── vector_db/                     # Per-user FAISS indexes (gitignored)
```

---

## Frontend setup

**1. Point it at your backend**

By default `js/api.js` talks to `http://localhost:8000`. To use a different
backend URL, set it before `api.js` loads:

```html
<script>window.NR_API_BASE_URL = 'https://api.yourdomain.com';</script>
<script src="js/api.js"></script>
```

**2. Serve it locally**

Static site — any local server works:

```bash
cd ai-interview-frontend
python -m http.server 5500
# or: npx serve -l 5500
```

Then open `http://localhost:5500`.

> The backend's `CORS_ORIGINS` must exactly match the origin you serve this
> from. If you use a different port than 5500, or open files directly via
> `file://`, update `CORS_ORIGINS` in the backend's `.env`.

### Frontend layout

```
ai-interview-frontend/
├── index.html              # Landing page
├── login.html / register.html
├── dashboard.html            # Logged-in home
├── profile.html                # Edit profile, upload photo
├── resume.html                   # Upload/manage resume
├── interview_setup.html            # Choose interview type/role/duration
├── interview.html                    # Live interview: camera, mic, transcript
├── result.html                         # Score breakdown for one interview
├── report.html                           # Downloadable PDF report view
├── history.html                            # Past interviews
├── admin.html                                # Admin-only stats
├── css/style.css                               # Shared design system
└── js/api.js, js/main.js                         # API client, shared behavior
```

---

## Deployment notes

- Set `DEBUG=false`, a strong random `JWT_SECRET_KEY`, and `CORS_ORIGINS` to
  your real frontend domain(s) on the backend.
- Run migrations with Alembic rather than relying on `create_all` in
  production.
- `uploads/` and `vector_db/` hold user data and grow over time — mount
  persistent storage for them (gitignored, not meant to ship in the repo).
- Deploy the frontend as static files (Netlify, Vercel, S3+CloudFront,
  GitHub Pages, or behind the same reverse proxy as the API) — no build step
  needed. Set `window.NR_API_BASE_URL` to the production backend URL and add
  that frontend origin to the backend's `CORS_ORIGINS`.
- Serve both over HTTPS in production — auth tokens are stored client-side.