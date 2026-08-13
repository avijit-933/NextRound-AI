"""
services/report_service.py — generates a downloadable PDF interview report:
questions/answers, AI feedback, score breakdown, emotion timeline summary,
eye-contact percentage and recommendations.

Two fpdf2 gotchas this file works around, both of which will silently crash
report generation (and therefore the download endpoint) if missed:

1. fpdf2's default core fonts (Helvetica etc.) only support Latin-1. Any
   text containing smart quotes, em/en dashes, ellipses, or other Unicode
   punctuation (which Gemini-generated feedback commonly includes) raises
   FPDFUnicodeEncodingException. Every string is passed through `_safe()`.
2. `multi_cell()` does NOT reset the cursor back to the left margin after
   it finishes by default in this fpdf2 version — it leaves x wherever the
   text ended. A second multi_cell() call in a row then has ~0 width left
   to the right margin and raises "Not enough horizontal space to render a
   single character". Every multi_cell()/cell() call below explicitly
   passes new_x=XPos.LMARGIN, new_y=YPos.NEXT to force the reset.
"""
import os
from datetime import datetime
from typing import Dict, List

from fpdf import FPDF
from fpdf.enums import XPos, YPos

from config import settings

PRIMARY_RGB = (99, 102, 241)
MUTED_RGB = (91, 97, 120)

# Common Unicode punctuation -> closest Latin-1-safe ASCII equivalent.
_UNICODE_REPLACEMENTS = {
    "\u2014": "-",   # em dash —
    "\u2013": "-",   # en dash –
    "\u2018": "'",   # left single quote '
    "\u2019": "'",   # right single quote '
    "\u201c": '"',   # left double quote "
    "\u201d": '"',   # right double quote "
    "\u2026": "...", # ellipsis …
    "\u2022": "-",   # bullet •
    "\u2192": "->",  # right arrow →
    "\u2190": "<-",  # left arrow ←
    "\u00a0": " ",   # non-breaking space
}


def _safe(text) -> str:
    """Make any string safe to pass to fpdf2's core-font cell()/multi_cell().
    Replaces common smart punctuation with ASCII, then drops anything else
    outside Latin-1 rather than letting it crash report generation."""
    text = str(text)
    for bad, good in _UNICODE_REPLACEMENTS.items():
        text = text.replace(bad, good)
    return text.encode("latin-1", errors="replace").decode("latin-1")


class InterviewReportPDF(FPDF):
    def header(self):
        self.set_font("Helvetica", "B", 16)
        self.set_text_color(*PRIMARY_RGB)
        self.cell(0, 10, _safe("NextRound AI - Interview Report"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        self.set_draw_color(*PRIMARY_RGB)
        self.line(10, 20, 200, 20)
        self.ln(6)

    def footer(self):
        self.set_y(-15)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(*MUTED_RGB)
        self.cell(0, 10, _safe(f"Page {self.page_no()} - generated {datetime.utcnow():%Y-%m-%d}"), align="C")


def _section_title(pdf: FPDF, title: str):
    pdf.set_font("Helvetica", "B", 13)
    pdf.set_text_color(20, 20, 30)
    pdf.ln(3)
    pdf.cell(0, 8, _safe(title), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "", 11)
    pdf.set_text_color(40, 40, 50)


def generate_interview_report(
    output_dir: str,
    interview_meta: Dict,
    qa_pairs: List[Dict],
    scores: Dict,
    feedback: Dict,
    eye_contact_avg: float,
    emotion_summary: Dict[str, float],
) -> str:
    """
    interview_meta: {candidate_name, job_role, interview_type, date, duration_minutes}
    qa_pairs: [{question, answer, ai_feedback}, ...]
    scores: dict of score fields (see schemas.ScoreOut)
    feedback: {strengths: [...], weaknesses: [...], suggestions: [...]}
    """
    pdf = InterviewReportPDF()
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.add_page()

    # --- summary block ---
    pdf.set_font("Helvetica", "", 11)
    pdf.cell(0, 7, _safe(f"Candidate: {interview_meta['candidate_name']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, _safe(f"Role: {interview_meta['job_role']}  |  Type: {interview_meta['interview_type']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.cell(0, 7, _safe(f"Date: {interview_meta['date']}  |  Duration: {interview_meta['duration_minutes']} min"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font("Helvetica", "B", 12)
    pdf.set_text_color(*PRIMARY_RGB)
    pdf.cell(0, 9, _safe(f"Overall score: {scores.get('overall_score', 0):.0f} / 100"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- score breakdown ---
    _section_title(pdf, "Score breakdown")
    for label, key in [
        ("Technical", "technical_score"), ("Communication", "communication_score"),
        ("Confidence", "confidence_score"), ("Grammar", "grammar_score"),
        ("Problem solving", "problem_solving_score"), ("Body language", "body_language_score"),
        ("Eye contact", "eye_contact_score"), ("Emotion", "emotion_score"),
    ]:
        pdf.cell(0, 6, _safe(f"  {label}: {scores.get(key, 0):.0f}/100"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- questions & answers ---
    _section_title(pdf, "Questions & Answers")
    for i, qa in enumerate(qa_pairs, start=1):
        pdf.set_font("Helvetica", "B", 11)
        pdf.multi_cell(0, 6, _safe(f"Q{i}. {qa['question']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_font("Helvetica", "", 10)
        pdf.set_text_color(*MUTED_RGB)
        pdf.multi_cell(0, 6, _safe(f"Your answer: {qa.get('answer') or '(skipped)'}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if qa.get("correctness_pct") is not None:
            pdf.set_font("Helvetica", "B", 10)
            pdf.set_text_color(*PRIMARY_RGB)
            pdf.cell(0, 6, _safe(f"Correctness: {qa['correctness_pct']:.0f}% of the expected answer covered"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_text_color(*MUTED_RGB)
        if qa.get("possible_answer"):
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 6, _safe(f"A possible correct answer: {qa['possible_answer']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        if qa.get("ai_feedback"):
            pdf.set_font("Helvetica", "I", 10)
            pdf.multi_cell(0, 6, _safe(f"AI feedback: {qa['ai_feedback']}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
        pdf.set_text_color(40, 40, 50)
        pdf.ln(2)

    # --- webcam / emotion analysis ---
    _section_title(pdf, "Body language & emotion")
    pdf.cell(0, 6, _safe(f"Average eye contact: {eye_contact_avg:.0f}%"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    emotion_line = ", ".join(f"{k.title()}: {v:.0f}%" for k, v in emotion_summary.items())
    pdf.multi_cell(0, 6, _safe(f"Emotion distribution - {emotion_line}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    # --- strengths / weaknesses / suggestions ---
    _section_title(pdf, "Strengths")
    for s in feedback.get("strengths", []):
        pdf.multi_cell(0, 6, _safe(f"+ {s}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _section_title(pdf, "Weaknesses")
    for w in feedback.get("weaknesses", []):
        pdf.multi_cell(0, 6, _safe(f"- {w}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    _section_title(pdf, "Recommendations")
    for r in feedback.get("suggestions", []):
        pdf.multi_cell(0, 6, _safe(f"> {r}"), new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    os.makedirs(output_dir, exist_ok=True)
    filename = f"report_{interview_meta['interview_id']}_{int(datetime.utcnow().timestamp())}.pdf"
    filepath = os.path.join(output_dir, filename)
    pdf.output(filepath)
    return filepath
