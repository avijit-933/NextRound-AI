"""
services/resume_service.py — resume text extraction (PyMuPDF) and lightweight
section parsing (skills / education / projects / experience / certifications).

The section splitter here is a fast heuristic (keyword + line-based), good enough
to bootstrap the RAG pipeline. Swap in a proper NER/LLM-based parser later if the
heuristic misses too much on real-world resume formats.
"""
import re
from typing import Dict, List

import fitz  # PyMuPDF

SECTION_HEADERS = {
    "skills": ["skills", "technical skills", "technologies"],
    "education": ["education", "academic background"],
    "projects": ["projects", "personal projects", "academic projects"],
    "experience": ["experience", "work experience", "internships", "employment"],
    "certifications": ["certifications", "certificates", "licenses"],
}

SKILL_KEYWORDS = [
    "python", "java", "javascript", "typescript", "c++", "c#", "sql", "fastapi",
    "django", "flask", "react", "angular", "vue", "node.js", "langchain", "faiss",
    "tensorflow", "pytorch", "scikit-learn", "docker", "kubernetes", "aws", "gcp",
    "azure", "mysql", "postgresql", "mongodb", "redis", "git", "opencv", "mediapipe",
    "nlp", "computer vision", "html", "css", "bootstrap", "rest api", "graphql",
]


def extract_text_from_pdf(filepath: str) -> str:
    """Extract raw text from a PDF using PyMuPDF."""
    text_parts: List[str] = []
    with fitz.open(filepath) as doc:
        for page in doc:
            text_parts.append(page.get_text("text"))
    return "\n".join(text_parts)


def _find_section_block(lines: List[str], headers: List[str]) -> List[str]:
    """Return the lines belonging to a section, from its header until the next
    recognized header (or end of document)."""
    all_headers_flat = [h for group in SECTION_HEADERS.values() for h in group]
    start = None
    for i, line in enumerate(lines):
        norm = line.strip().lower().strip(":")
        if norm in headers:
            start = i + 1
            break
    if start is None:
        return []

    block = []
    for line in lines[start:]:
        norm = line.strip().lower().strip(":")
        if norm in all_headers_flat and norm not in headers:
            break
        if line.strip():
            block.append(line.strip())
    return block


def parse_resume_sections(raw_text: str) -> Dict[str, List[str]]:
    """Heuristically split resume text into structured sections."""
    lines = raw_text.split("\n")
    lower_text = raw_text.lower()

    result: Dict[str, List[str]] = {}

    # Skills: prefer an explicit "Skills" section; fall back to keyword scan.
    skills_block = _find_section_block(lines, SECTION_HEADERS["skills"])
    if skills_block:
        joined = " ".join(skills_block)
        result["skills"] = sorted(set(re.split(r",|\u2022|\||/", joined)))
        result["skills"] = [s.strip() for s in result["skills"] if s.strip()]
    else:
        result["skills"] = [kw.title() for kw in SKILL_KEYWORDS if kw in lower_text]

    result["education"] = _find_section_block(lines, SECTION_HEADERS["education"]) or []
    result["projects"] = _find_section_block(lines, SECTION_HEADERS["projects"]) or []
    result["experience"] = _find_section_block(lines, SECTION_HEADERS["experience"]) or []
    result["certifications"] = _find_section_block(lines, SECTION_HEADERS["certifications"]) or []

    return result


def process_resume(filepath: str) -> Dict:
    """Full pipeline: extract text + parse sections. Embeddings are handled
    separately in rag_service.py so this stays fast and side-effect free."""
    raw_text = extract_text_from_pdf(filepath)
    sections = parse_resume_sections(raw_text)
    return {"raw_text": raw_text, **sections}
