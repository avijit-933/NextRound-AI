"""
services/gemini_service.py — wraps Google's Gemini API for two jobs:
  1. Generating interview questions personalized to the candidate's resume
     (using retrieved RAG context from rag_service.py) and chosen interview
     settings (type / difficulty / role).
  2. Evaluating a submitted answer against several rubric dimensions, plus
     the session's aggregated body-language / emotion signals.

Requires GEMINI_API_KEY in the environment. If it's not set, both functions
fall back to deterministic mock output so the rest of the app keeps working
in local/dev environments without a real key.
"""
import json
import logging
from typing import Dict, List

import google.generativeai as genai

from config import settings

logger = logging.getLogger(__name__)

if settings.GEMINI_API_KEY:
    genai.configure(api_key=settings.GEMINI_API_KEY)


def _model():
    return genai.GenerativeModel(settings.GEMINI_MODEL)


QUESTION_PROMPT_TEMPLATE = """You are a senior, experienced {interview_type} interviewer at a top tech
company, conducting a real {difficulty}-difficulty interview for the role of {job_role}.

Relevant context from the candidate's resume:
---
{resume_context}
---

Write exactly {num_questions} interview questions that a real interviewer would actually ask for
this role and difficulty. Follow these rules strictly:
1. Questions must be STANDARD and MEANINGFUL — the kind commonly asked in real {job_role}
   interviews — not vague, not trick questions, not filler.
2. Each question must be clear, specific, and answerable in 1-3 minutes out loud.
3. Do not repeat the same concept twice across the set; cover a good spread of relevant sub-topics
   for a {interview_type} interview (e.g. for Technical/Coding: fundamentals, applied
   problem-solving, system/design thinking, and one resume-grounded question if resume context is
   available; for HR: motivation, teamwork, conflict handling, ownership; for Aptitude: quantitative,
   logical, and estimation reasoning).
4. Calibrate depth and terminology to the stated difficulty level.
5. Where resume context is available and relevant, personalize at least one question to a specific
   project, skill, or experience mentioned in it — otherwise ask well-known, general questions for
   the role.
6. For every question, also write a concise "ideal_answer": a strong model answer (3-6 sentences,
   or a short annotated solution for coding questions) that a hiring manager would consider a great
   response. This will be used later to grade the candidate — do not mention that purpose in the
   question text itself.

Return ONLY a JSON array of objects, no markdown fences, no commentary, matching exactly this shape:
[{{"question": "...", "ideal_answer": "..."}}]
"""

EVALUATION_PROMPT_TEMPLATE = """You are evaluating one answer from a {interview_type} interview for a
{job_role} role at {difficulty} difficulty.

Question: {question}
A strong model/ideal answer for reference: {ideal_answer}
Candidate's answer (transcribed from speech): {answer}

Additional signals captured during this answer:
- Average eye contact: {eye_contact}%
- Dominant detected emotion: {dominant_emotion}
- Head pose stability: {head_pose_notes}

Carefully compare the candidate's answer against the model answer and what the question is really
asking. Score the answer from 0-100 on each dimension below, and return ONLY valid JSON
(no markdown fences, no commentary) matching this exact shape:
{{
  "technical_score": 0,
  "communication_score": 0,
  "confidence_score": 0,
  "grammar_score": 0,
  "problem_solving_score": 0,
  "correctness_percentage": 0,
  "possible_answer": "a strong, correct answer to this exact question, written as if for this candidate's level",
  "feedback": "one short paragraph of specific, actionable feedback on THIS answer, mentioning what was right and what was missing"
}}

Notes on fields:
- "correctness_percentage" is your best estimate (0-100) of how much of the expected/correct answer
  the candidate actually covered — not a vibe score, a factual coverage estimate. 0 means the answer
  was empty/skipped or entirely wrong; 100 means it fully and accurately covered the ideal answer.
- "possible_answer" should closely reflect the model/ideal answer above, adapted only if needed.
"""


def _safe_json_parse(text: str, fallback: dict) -> dict:
    cleaned = text.strip().strip("`")
    if cleaned.lower().startswith("json"):
        cleaned = cleaned[4:]
    try:
        return json.loads(cleaned)
    except (json.JSONDecodeError, TypeError):
        logger.warning("Gemini returned non-JSON output, using fallback. Raw: %s", text[:200])
        return fallback


def generate_questions(
    interview_type: str,
    job_role: str,
    difficulty: str,
    resume_context: List[str],
    num_questions: int = 6,
) -> List[Dict[str, str]]:
    """Generate personalized, standard/meaningful interview questions, each paired
    with a model "ideal_answer" used later for correctness grading. Returns a list
    of {"question": ..., "ideal_answer": ...} dicts. Falls back to a curated static
    bank if no Gemini key is configured, so the interview flow still works in dev."""
    if not settings.GEMINI_API_KEY:
        return _fallback_questions(interview_type, num_questions)

    prompt = QUESTION_PROMPT_TEMPLATE.format(
        interview_type=interview_type,
        job_role=job_role,
        difficulty=difficulty,
        resume_context="\n---\n".join(resume_context) or "No resume on file — ask general questions.",
        num_questions=num_questions,
    )
    try:
        response = _model().generate_content(prompt)
        items = _safe_json_parse(response.text, {})
        questions = _normalize_questions(items)
        if questions:
            return questions[:num_questions]
    except Exception as exc:  # noqa: BLE001 — surface upstream, don't crash the interview
        logger.error("Gemini question generation failed: %s", exc)

    return _fallback_questions(interview_type, num_questions)


def _normalize_questions(items) -> List[Dict[str, str]]:
    """Accepts either the expected [{"question","ideal_answer"}, ...] shape or a
    plain list of strings (in case the model ignores the object format), and
    always returns the dict shape so callers don't need to special-case it."""
    if not isinstance(items, list):
        return []
    normalized = []
    for item in items:
        if isinstance(item, dict) and item.get("question"):
            normalized.append({
                "question": str(item["question"]).strip(),
                "ideal_answer": str(item.get("ideal_answer", "")).strip(),
            })
        elif isinstance(item, str) and item.strip():
            normalized.append({"question": item.strip(), "ideal_answer": ""})
    return normalized


def evaluate_answer(
    interview_type: str,
    job_role: str,
    difficulty: str,
    question: str,
    answer: str,
    eye_contact: float,
    dominant_emotion: str,
    head_pose_notes: str = "stable",
    ideal_answer: str = "",
) -> Dict:
    """Return per-dimension scores, a 0-100 correctness_percentage, a possible/model
    answer for comparison, and written feedback for a single answer."""
    fallback = _fallback_evaluation(ideal_answer, bool((answer or "").strip()))
    if not settings.GEMINI_API_KEY:
        return fallback

    prompt = EVALUATION_PROMPT_TEMPLATE.format(
        interview_type=interview_type,
        job_role=job_role,
        difficulty=difficulty,
        question=question,
        ideal_answer=ideal_answer or "(no reference answer available — grade on general expertise for this role/difficulty)",
        answer=answer or "(no answer provided / skipped)",
        eye_contact=round(eye_contact, 1),
        dominant_emotion=dominant_emotion,
        head_pose_notes=head_pose_notes,
    )
    try:
        response = _model().generate_content(prompt)
        result = _safe_json_parse(response.text, fallback)
        for key in ("technical_score", "communication_score", "confidence_score",
                    "grammar_score", "problem_solving_score", "correctness_percentage"):
            result[key] = max(0, min(100, float(result.get(key, fallback[key]))))
        result.setdefault("possible_answer", fallback["possible_answer"])
        result.setdefault("feedback", fallback["feedback"])
        return result
    except Exception as exc:  # noqa: BLE001
        logger.error("Gemini evaluation failed: %s", exc)
        return fallback


# ---------------------------------------------------------------------
# Deterministic fallbacks (used when GEMINI_API_KEY is unset, e.g. local dev)
# Each entry is a standard, commonly-asked question for the category paired
# with a concise model/ideal answer, so the rest of the pipeline (correctness
# scoring, report "possible answer" display) still works without a live key.
# ---------------------------------------------------------------------
_FALLBACK_BANK = {
    "HR": [
        {"question": "Tell me about yourself and why you're interested in this role.",
         "ideal_answer": "A strong answer gives a brief, structured walk-through of relevant background, "
                          "highlights 1-2 achievements that map to this role, and ends with a clear, "
                          "specific reason for wanting this position at this company."},
        {"question": "Describe a time you disagreed with a teammate — how did you resolve it?",
         "ideal_answer": "A good answer uses a real, specific example (situation, action, outcome), focuses "
                          "on listening and finding common ground rather than 'winning', and states what "
                          "was learned or changed afterward."},
        {"question": "Tell me about a project you're most proud of and your specific contribution.",
         "ideal_answer": "The candidate names a concrete project, clearly separates their own contribution "
                          "from the team's, quantifies impact where possible, and reflects on what made it "
                          "successful or what they'd improve."},
        {"question": "How do you handle tight deadlines with incomplete requirements?",
         "ideal_answer": "A solid answer describes prioritizing ruthlessly, communicating assumptions and "
                          "risks early to stakeholders, delivering an incremental/MVP version, and adjusting "
                          "as clarity improves — with a real example."},
        {"question": "Where do you see yourself professionally in three years, and how does this role fit?",
         "ideal_answer": "A good answer connects a believable growth trajectory (skills/scope, not just "
                          "title) to what this specific role and company can offer, showing genuine research "
                          "and alignment rather than a generic script."},
    ],
    "Technical": [
        {"question": "Walk me through how you'd design a rate limiter for a public API.",
         "ideal_answer": "Covers picking an algorithm (token bucket or sliding window log), where state "
                          "lives (in-memory vs. distributed store like Redis), per-key vs. global limits, "
                          "handling bursts gracefully, and what happens on limit breach (429 + retry-after)."},
        {"question": "Describe a technical challenge from one of your projects and how you solved it.",
         "ideal_answer": "Names a specific, non-trivial problem, explains the diagnostic process (not just "
                          "the fix), the trade-offs considered, and the measurable result or lesson learned."},
        {"question": "How would you debug a memory leak in a long-running service?",
         "ideal_answer": "Describes reproducing the leak, using profiling/heap-dump tools appropriate to the "
                          "stack, narrowing down via allocation tracking or generational diffs, and forming "
                          "a hypothesis before patching — plus how they'd verify the fix under load."},
        {"question": "What are the trade-offs between SQL and NoSQL for a system like this one?",
         "ideal_answer": "Weighs schema flexibility, consistency guarantees (ACID vs. eventual), query "
                          "patterns and joins, horizontal scaling, and picks based on the access pattern "
                          "rather than a blanket preference."},
        {"question": "How does a vector database like FAISS find nearest neighbors efficiently at scale?",
         "ideal_answer": "Explains approximate nearest-neighbor search (e.g. IVF, HNSW, product quantization) "
                          "trading a small accuracy loss for large speed/memory gains versus brute-force "
                          "exact search, and when exact search is still preferable."},
    ],
    "Coding": [
        {"question": "Given an array, find the length of the longest subarray with a sum equal to k.",
         "ideal_answer": "Optimal approach uses a running prefix sum with a hash map storing the earliest "
                          "index each prefix sum was seen; for each index check if (prefix_sum - k) exists "
                          "in the map. Runs in O(n) time, O(n) space, versus O(n^2) brute force."},
        {"question": "How would you implement an LRU cache from scratch?",
         "ideal_answer": "Combine a hash map (key -> node) with a doubly linked list ordered by recency. "
                          "get() moves the node to the front; put() evicts the tail node on capacity overflow. "
                          "Both operations run in O(1)."},
        {"question": "Write pseudocode to detect a cycle in a linked list.",
         "ideal_answer": "Floyd's cycle detection: a slow pointer advances one node and a fast pointer "
                          "advances two nodes per step; if they meet, a cycle exists; if fast reaches null, "
                          "there is no cycle. O(n) time, O(1) space."},
        {"question": "How would you find the kth largest element in an unsorted array efficiently?",
         "ideal_answer": "A min-heap of size k gives O(n log k), or Quickselect gives average O(n) time by "
                          "partitioning around a pivot and recursing only into the side containing the kth "
                          "element."},
        {"question": "Explain how you'd design the core data model for a URL shortener.",
         "ideal_answer": "A table mapping a short code to the long URL plus metadata (creator, created_at, "
                          "expiry, click count); short codes generated via base62 encoding of an auto-"
                          "increment ID or a hash with collision checks; reads dominate, so cache hot codes."},
    ],
    "Aptitude": [
        {"question": "A train 120m long crosses a platform in 30s while moving at 20m/s. Find the platform's length.",
         "ideal_answer": "Total distance covered = speed x time = 20 x 30 = 600m. Platform length = total "
                          "distance - train length = 600 - 120 = 480 meters."},
        {"question": "If a value increases by 20% and then decreases by 20%, what is the net percentage change?",
         "ideal_answer": "Net change = -(20*20)/100 = -4%, i.e. a net decrease of 4% versus the original "
                          "value (since the second percentage is taken on a larger base)."},
        {"question": "Three people can finish a task in 6 days working together; one leaves after day 2 — how many more days for the remaining two to finish?",
         "ideal_answer": "Combined rate = 1/6 per day. After 2 days, 2/6 = 1/3 of the work is done, 2/3 "
                          "remains. Two people's combined rate is 2/3 of the original rate (assuming equal "
                          "individual rates), so remaining time = (2/3) / (2/9) = 3 more days."},
        {"question": "You have 9 identical-looking balls, one of which is heavier. How do you find it using a balance scale in 2 weighings?",
         "ideal_answer": "Split into groups of 3. Weigh two groups of 3 against each other: if balanced, the "
                          "heavy ball is in the third group; otherwise it's in the heavier group. Take that "
                          "group of 3, weigh two of the balls against each other to identify the heavy one "
                          "(or it's the one left aside if they balance)."},
        {"question": "Estimate how many liters of paint would be needed to paint a school building, stating your assumptions.",
         "ideal_answer": "A good answer states clear assumptions (number of floors, wall area per floor, "
                          "coverage per liter, number of coats), shows the arithmetic explicitly, and arrives "
                          "at a defensible order-of-magnitude estimate rather than a single guessed number."},
    ],
}


def _fallback_questions(interview_type: str, num_questions: int) -> List[Dict[str, str]]:
    bank = _FALLBACK_BANK.get(interview_type, _FALLBACK_BANK["Technical"])
    return (bank * ((num_questions // len(bank)) + 1))[:num_questions]


def _fallback_evaluation(ideal_answer: str = "", has_answer: bool = True) -> Dict:
    return {
        "technical_score": 70.0 if has_answer else 0.0,
        "communication_score": 70.0 if has_answer else 0.0,
        "confidence_score": 70.0 if has_answer else 0.0,
        "grammar_score": 75.0 if has_answer else 0.0,
        "problem_solving_score": 68.0 if has_answer else 0.0,
        "correctness_percentage": 65.0 if has_answer else 0.0,
        "possible_answer": ideal_answer or (
            "No model answer is available for this question. Configure GEMINI_API_KEY to "
            "get a real, question-specific model answer here."
        ),
        "feedback": (
            "This is placeholder feedback generated without a live Gemini API key. "
            "Configure GEMINI_API_KEY to receive real, answer-specific evaluation."
        ) if has_answer else "No answer was submitted for this question, so it was scored as 0% correct.",
    }
