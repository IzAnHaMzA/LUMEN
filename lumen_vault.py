from __future__ import annotations

import html
import json
import os
import random
import re
import subprocess
from datetime import datetime
from collections import defaultdict
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from flask import Flask, jsonify, redirect, request, send_from_directory

try:
    from llama_cpp import Llama
except Exception:
    Llama = None

try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None

try:
    import fitz
except Exception:
    fitz = None

try:
    from PIL import Image, ImageOps
except Exception:
    Image = None
    ImageOps = None

try:
    import pytesseract
except Exception:
    pytesseract = None


BASE_DIR = Path(__file__).resolve().parent
UI_DIR = BASE_DIR / "lumen_vault"
LIBRARY_INDEX_PATH = UI_DIR / "data" / "library_index.json"
SYLLABUS_DIR = BASE_DIR / "k scheme syllabus"
PAPERS_DIR = BASE_DIR / "previous year question paper"
UPLOADS_DIR = BASE_DIR / "lumen_vault_uploads"
UPLOADS_MANIFEST_PATH = UPLOADS_DIR / "materials_index.json"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434/api/generate").strip()
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "").strip()
LLAMA_MODEL_PATH = os.environ.get("LLAMA_MODEL_PATH", "").strip()
GEMINI_API_KEY = (
    os.environ.get("GEMINI_API_KEY", "").strip()
    or os.environ.get("gemini_API_KEYnew1", "").strip()
)
GEMINI_API_KEY2 = (
    os.environ.get("GEMINI_API_KEY2", "").strip()
    or os.environ.get("gemini_API_KEYnew2", "").strip()
)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash-lite").strip()
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "").strip()
OPENAI_API_KEY2 = os.environ.get("OPENAI_API_KEY2", "").strip()
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4.1-mini").strip()
AI_BACKEND_ORDER = os.environ.get("AI_BACKEND_ORDER", "ollama,gemini,llama_cpp").strip()
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", "").strip()
TESSERACT_CANDIDATES = (
    TESSERACT_CMD,
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 40 * 1024 * 1024

LIBRARY_INDEX = json.loads(LIBRARY_INDEX_PATH.read_text(encoding="utf-8"))
SUBJECTS = LIBRARY_INDEX.get("subjects", [])
PAPERS_BY_CODE = LIBRARY_INDEX.get("papers_by_code", {})
SUBJECTS_BY_KEY: Dict[str, Dict[str, Any]] = {}
SUBJECTS_BY_CODE: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
MATERIAL_TYPES = {
    "question": "Question File",
    "test": "Subject Test",
    "study": "Book / Study Material",
}
MCQ_SOURCE_LABELS = {
    "papers": "Question Papers",
    "materials": "Uploaded Material",
}
MATERIALS_INDEX: Dict[str, Any] = {"items": []}
MATERIALS_BY_SUBJECT: Dict[str, List[Dict[str, Any]]] = defaultdict(list)


def subject_key(subject: Dict[str, Any]) -> str:
    return f"{subject.get('program_code', '')}|{subject.get('paper_code', '')}|{subject.get('subject', '')}"


for subject in SUBJECTS:
    key = subject_key(subject)
    subject["key"] = key
    SUBJECTS_BY_KEY[key] = subject
    SUBJECTS_BY_CODE[str(subject.get("paper_code", ""))].append(subject)


def sanitize_slug(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9._-]+", "-", value or "").strip("-._")
    return slug or "item"


def load_material_index() -> Dict[str, Any]:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    if not UPLOADS_MANIFEST_PATH.exists():
        return {"items": []}
    try:
        return json.loads(UPLOADS_MANIFEST_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {"items": []}


def rebuild_material_maps() -> None:
    MATERIALS_BY_SUBJECT.clear()
    for item in MATERIALS_INDEX.get("items", []):
        MATERIALS_BY_SUBJECT[str(item.get("subject_key", ""))].append(item)


def save_material_index() -> None:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    UPLOADS_MANIFEST_PATH.write_text(json.dumps(MATERIALS_INDEX, indent=2), encoding="utf-8")


MATERIALS_INDEX = load_material_index()
rebuild_material_maps()


_llama_instance = None
_tesseract_cmd = None
SCORING_STOPWORDS = {
    "answer",
    "answers",
    "approach",
    "create",
    "draft",
    "exam",
    "explain",
    "focus",
    "general",
    "generate",
    "give",
    "help",
    "important",
    "mention",
    "paper",
    "please",
    "preparation",
    "prepare",
    "question",
    "questions",
    "step",
    "steps",
    "study",
    "subject",
    "summary",
    "tell",
    "theory",
    "topic",
    "topics",
    "wise",
}
SUBJECT_SELECTOR_HINTS = {
    "subject",
    "syllabus",
    "paper",
    "course",
    "unit",
    "units",
    "topic",
    "topics",
    "exam",
    "important",
    "semester",
}
SELECTED_CONTEXT_HINTS = (
    "this subject",
    "this paper",
    "current subject",
    "selected subject",
    "same subject",
    "for this subject",
    "for this paper",
)
PREFERRED_OLLAMA_MODELS = [
    "qwen2.5:3b",
    "llama3.2:3b",
    "qwen2.5:1.5b",
    "llama3.2:1b",
]
VALID_AI_BACKENDS = ("ollama", "gemini", "openai", "llama_cpp")
MATH_SUBJECT_HINTS = (
    "math",
    "mathematics",
    "algebra",
    "trigonometry",
    "calculus",
    "statistics",
    "differential",
)
MATH_QUERY_HINTS = (
    "solve",
    "simplify",
    "evaluate",
    "find",
    "equation",
    "log",
    "logarithm",
    "matrix",
    "differentiate",
    "derivative",
    "trigonometric",
    "trigonometry",
    "radius of curvature",
    "maxima",
    "minima",
)
MCQ_CHAT_HINTS = (
    "mcq",
    "multiple choice",
    "multiple-choice",
    "quiz",
)
MCQ_MATERIAL_HINTS = (
    "uploaded material",
    "uploaded materials",
    "uploaded pdf",
    "uploaded file",
    "my material",
    "my uploaded material",
    "study material",
    "book material",
    "notes pdf",
)
MCQ_PAPER_HINTS = (
    "question paper",
    "question papers",
    "past paper",
    "past papers",
    "latest paper",
    "previous paper",
    "previous papers",
)


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").casefold()).strip()


def text_tokens(value: str) -> List[str]:
    tokens = re.findall(r"[a-z0-9]{2,}", normalize_text(value))
    filtered = []
    for token in tokens:
        if token in SCORING_STOPWORDS:
            continue
        if token.isdigit() and len(token) >= 5:
            continue
        filtered.append(token)
    return filtered


def raw_text_tokens(value: str) -> List[str]:
    return re.findall(r"[a-z0-9]{2,}", normalize_text(value))


def significant_subject_tokens(subject_name: str) -> List[str]:
    tokens = []
    for token in raw_text_tokens(subject_name):
        if token in SUBJECT_SELECTOR_HINTS:
            continue
        if len(token) <= 2:
            continue
        tokens.append(token)
    return tokens


def is_noise_line(value: str) -> bool:
    lowered = normalize_text(value)
    noise_fragments = (
        "learning scheme",
        "assessment scheme",
        "actual contact hrs",
        "paper duration",
        "total marks",
        "total iks hrs",
        "legends",
        "internal assessment",
        "external assessment",
        "candidate shall",
        "notional learning hours",
        "programme name",
        "programme code",
        "course title",
        "fa-th",
        "sa-th",
        "fa-pr",
        "sa-pr",
        "course category",
        "max min",
        "slh",
        "nlh",
        "credits assessment scheme",
        "suggested learning pedagogies",
        "seat no",
        "solve any",
        "attempt any",
        "answer any",
        "all questions are compulsory",
        "figures to the right indicate full marks",
        "use of non-programmable",
        "use of non programmable",
        "section a",
        "section b",
        "section c",
        "question no",
    )
    if any(fragment in lowered for fragment in noise_fragments):
        return True
    if "course code" in lowered and "semester" in lowered:
        return True
    if lowered.startswith("course code abbr credits"):
        return True
    if "credits theory based on ll & tl" in lowered:
        return True
    if re.match(r"^\d{6}[-\s].*course code", lowered):
        return True
    if re.fullmatch(r"(max|min|fa-th|sa-th|fa-pr|sa-pr|sla|slh|nlh|\d+|\W+)+", lowered):
        return True
    if re.search(r"\bseat\s*no\b", lowered):
        return True
    if re.search(r"\bsolve any\b|\battempt any\b|\banswer any\b", lowered):
        return True
    if re.match(r"^\d+\.\s*solve any", lowered):
        return True
    if re.match(r"^\d+\.\s*attempt any", lowered):
        return True
    return False


def is_viable_mcq_source_line(value: str) -> bool:
    cleaned = clean_mcq_source_line(value)
    lowered = normalize_text(cleaned)
    if len(cleaned) < 18:
        return False
    if is_noise_line(cleaned):
        return False
    if re.search(r"\bseat\s*no\b", lowered):
        return False
    if re.search(r"\bsolve any\b|\battempt any\b|\banswer any\b", lowered):
        return False
    if re.search(r"\bof the following\b", lowered) and len(cleaned.split()) <= 12:
        return False
    if re.fullmatch(r"[\d.\-() a-z]+", lowered) and len(cleaned.split()) < 5:
        return False
    return True


def unique_preserving_order(items: Iterable[str]) -> List[str]:
    seen = set()
    result = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def repo_path_from_web_path(web_path: str) -> Path:
    relative = web_path.lstrip("/").replace("/", os.sep)
    resolved = (BASE_DIR / relative).resolve()
    if BASE_DIR.resolve() not in resolved.parents and resolved != BASE_DIR.resolve():
        raise ValueError("Path escapes repository root.")
    return resolved


def material_entries_for_subject(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
    return list(MATERIALS_BY_SUBJECT.get(str(subject.get("key", "")), []))


def summarize_material(entry: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": entry.get("id"),
        "subject_key": entry.get("subject_key"),
        "material_type": entry.get("material_type"),
        "material_label": MATERIAL_TYPES.get(str(entry.get("material_type", "")), "Material"),
        "name": entry.get("name"),
        "original_name": entry.get("original_name"),
        "path": entry.get("path"),
        "uploaded_at": entry.get("uploaded_at"),
        "pages": entry.get("pages", 0),
    }


def subject_materials_summary(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [summarize_material(item) for item in material_entries_for_subject(subject)]


@lru_cache(maxsize=512)
def extract_subject_text(syllabus_web_path: str) -> str:
    try:
        syllabus_path = repo_path_from_web_path(syllabus_web_path)
    except Exception:
        return ""

    if not syllabus_path.exists():
        return ""

    raw = syllabus_path.read_text(encoding="utf-8", errors="ignore")
    raw = re.sub(r"(?is)<style.*?</style>", " ", raw)
    raw = re.sub(r"(?is)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|tr|li|ul|ol|table|thead|tbody|tfoot|th|td|h1|h2|h3|h4|h5|h6)>", "\n", raw)
    raw = re.sub(r"(?is)<[^>]+>", " ", raw)
    raw = html.unescape(raw).replace("\xa0", " ")

    lines: List[str] = []
    skip_prefixes = (
        "@page",
        "@media",
        "font-size",
        "background-image",
        "background-position",
        "border-collapse",
        "top:",
        "bottom:",
        "content:",
    )

    for line in raw.splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip(" \t:-")
        if len(cleaned) < 3:
            continue
        if cleaned.startswith(("{", "}", "*", "#", ".")):
            continue
        lowered = cleaned.casefold()
        if any(lowered.startswith(prefix) for prefix in skip_prefixes):
            continue
        if is_noise_line(cleaned):
            continue
        lines.append(cleaned)

    deduped: List[str] = []
    for line in lines:
        if deduped and deduped[-1] == line:
            continue
        deduped.append(line)

    return "\n".join(deduped)


def split_into_chunks(text: str, chunk_size: int = 420) -> List[str]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    chunks: List[str] = []
    current: List[str] = []
    current_len = 0

    for line in lines:
        if current and current_len + len(line) > chunk_size:
            chunks.append(" ".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += len(line) + 1

    if current:
        chunks.append(" ".join(current))

    return chunks


def normalize_extracted_text(text: str) -> str:
    cleaned = html.unescape(text or "").replace("\xa0", " ")
    cleaned = cleaned.replace("\u2022", " ")
    cleaned = cleaned.replace("\uf0b7", " ")
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\s*\n\s*", "\n", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def text_signal_score(text: str) -> int:
    return len(raw_text_tokens(text))


def looks_ocr_worthy(text: str) -> bool:
    cleaned = normalize_extracted_text(text)
    if not cleaned:
        return True
    if text_signal_score(cleaned) < 24:
        return True
    noisy = sum(1 for char in cleaned if char in "|{}[]<>~_")
    return noisy > max(8, len(cleaned) // 18)


def configure_tesseract() -> str:
    global _tesseract_cmd
    if _tesseract_cmd is not None:
        return _tesseract_cmd
    if not pytesseract:
        _tesseract_cmd = ""
        return _tesseract_cmd

    for candidate in TESSERACT_CANDIDATES:
        if candidate and Path(candidate).exists():
            pytesseract.pytesseract.tesseract_cmd = candidate
            _tesseract_cmd = candidate
            return _tesseract_cmd

    _tesseract_cmd = ""
    return _tesseract_cmd


def ocr_ready() -> bool:
    return bool(fitz and Image and ImageOps and pytesseract and configure_tesseract())


def extract_pdf_native_pages(pdf_path: Path, max_pages: int = 6) -> List[str]:
    pages: List[str] = []

    if fitz:
        try:
            document = fitz.open(str(pdf_path))
            try:
                for page_index in range(min(max_pages, document.page_count)):
                    page = document.load_page(page_index)
                    pages.append(normalize_extracted_text(page.get_text("text")))
            finally:
                document.close()
            return pages
        except Exception:
            pages = []

    if not PdfReader:
        return pages

    try:
        reader = PdfReader(str(pdf_path))
    except Exception:
        return pages

    for page in reader.pages[:max_pages]:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        pages.append(normalize_extracted_text(text))
    return pages


def ocr_pdf_pages(pdf_path: Path, page_indexes: List[int], max_pages: int = 6) -> Dict[int, str]:
    if not ocr_ready():
        return {}

    extracted: Dict[int, str] = {}
    try:
        document = fitz.open(str(pdf_path))
    except Exception:
        return extracted

    try:
        for page_index in page_indexes:
            if page_index < 0 or page_index >= min(max_pages, document.page_count):
                continue
            try:
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                image = ImageOps.grayscale(image)
                image = ImageOps.autocontrast(image)
                text = pytesseract.image_to_string(image, lang="eng", config="--oem 1 --psm 6")
            except Exception:
                text = ""
            cleaned = normalize_extracted_text(text)
            if cleaned:
                extracted[page_index] = cleaned
    finally:
        document.close()

    return extracted


@lru_cache(maxsize=256)
def extract_pdf_text(pdf_web_path: str, max_pages: int = 6) -> str:
    try:
        pdf_path = repo_path_from_web_path(pdf_web_path)
    except Exception:
        return ""

    if not pdf_path.exists():
        return ""

    native_pages = extract_pdf_native_pages(pdf_path, max_pages=max_pages)
    page_count = len(native_pages)
    if page_count == 0 and fitz:
        try:
            document = fitz.open(str(pdf_path))
            try:
                page_count = min(max_pages, document.page_count)
                native_pages = [""] * page_count
            finally:
                document.close()
        except Exception:
            page_count = 0

    ocr_candidates = [index for index in range(page_count) if looks_ocr_worthy(native_pages[index] if index < len(native_pages) else "")]
    ocr_pages = ocr_pdf_pages(pdf_path, ocr_candidates, max_pages=max_pages) if ocr_candidates else {}

    merged_pages: List[str] = []
    for index in range(page_count):
        native_text = native_pages[index] if index < len(native_pages) else ""
        ocr_text = ocr_pages.get(index, "")
        if looks_ocr_worthy(native_text) and text_signal_score(ocr_text) >= max(12, text_signal_score(native_text)):
            chosen = ocr_text
        elif text_signal_score(ocr_text) > text_signal_score(native_text) * 2 and text_signal_score(ocr_text) >= 30:
            chosen = ocr_text
        else:
            chosen = native_text or ocr_text
        if chosen:
            merged_pages.append(chosen)

    return "\n".join(merged_pages).strip()


def material_snippets(question: str, subject: Dict[str, Any], limit: int = 3) -> List[str]:
    entries = material_entries_for_subject(subject)
    if not entries:
        return []

    scored: List[Tuple[float, str]] = []
    for entry in entries[:8]:
        label = MATERIAL_TYPES.get(str(entry.get("material_type", "")), "Material")
        text = extract_pdf_text(str(entry.get("path", "")), max_pages=10)
        if not text:
            continue
        for chunk in split_into_chunks(text, chunk_size=380):
            score = score_overlap(question, chunk)
            if score <= 0:
                continue
            scored.append((score, f"{label}: {chunk}"))

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = unique_preserving_order([text for _, text in scored])
    return ordered[:limit]


def first_clean_sentence(text: str, max_words: int = 24) -> str:
    for piece in re.split(r"(?<=[.!?])\s+|\n+", normalize_extracted_text(text)):
        cleaned = re.sub(r"\s+", " ", piece).strip(" \t:-")
        if len(cleaned.split()) < 4:
            continue
        words = cleaned.split()
        if len(words) > max_words:
            cleaned = " ".join(words[:max_words]).rstrip(" ,;:") + "..."
        return cleaned
    return ""


def clean_topic_phrase(value: str, max_words: int = 10) -> str:
    cleaned = re.sub(r"\s+", " ", value or "").strip(" \t:-.,;")
    cleaned = re.sub(r"\b(that|which|who|where|when)\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b(is|are|refers to|means)\b.*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\b.*$", "", cleaned)
    cleaned = cleaned.strip(" \t:-.,;")
    words = cleaned.split()
    if len(words) > max_words:
        cleaned = " ".join(words[:max_words]).rstrip(" ,;:")
    if len(cleaned) < 3:
        return ""
    return cleaned


def material_concept_clues(chunk: str, label: str) -> List[str]:
    cleaned = re.sub(r"\s+", " ", normalize_extracted_text(chunk)).strip(" \t:-")
    if len(cleaned) < 30:
        return []

    clues: List[str] = []

    comparison = re.search(r"\bfeature\s+mongodb\s+rdbms\b", cleaned, flags=re.IGNORECASE)
    if comparison:
        clues.append(f"{label}: Differentiate MongoDB and RDBMS.")
    generic_comparison = re.search(r"\b([A-Z][A-Za-z0-9.+_-]{2,30})\s+(?:vs|versus)\s+([A-Z][A-Za-z0-9.+_-]{2,30})\b", cleaned)
    if generic_comparison:
        left = clean_topic_phrase(generic_comparison.group(1))
        right = clean_topic_phrase(generic_comparison.group(2))
        if left and right and normalize_text(left) != normalize_text(right):
            clues.append(f"{label}: Differentiate {left} and {right}.")

    workflow = re.search(r"(?:workflow|architecture) of ([A-Za-z0-9 /&()_-]{3,80})", cleaned, flags=re.IGNORECASE)
    if workflow:
        topic = workflow.group(1).strip(" .,:;")
        clues.append(f"{label}: Explain the workflow of {topic}.")

    purpose = re.search(r"purpose of ([A-Za-z0-9 /&()_-]{3,80})", cleaned, flags=re.IGNORECASE)
    if purpose:
        topic = clean_topic_phrase(purpose.group(1))
        if topic:
            clues.append(f"{label}: What is the purpose of {topic}?")

    definition = re.search(r"definition\s*[:\-]\s*([A-Za-z0-9 /&()_-]{2,70})", cleaned, flags=re.IGNORECASE)
    if definition:
        topic = clean_topic_phrase(definition.group(1))
        if topic:
            clues.append(f"{label}: What is {topic}?")

    concept = re.search(r"\b([A-Z][A-Za-z0-9()_-]*(?:\s+[A-Za-z][A-Za-z0-9()_-]*){0,6})\s+(?:is|are|refers to|means)\b", cleaned)
    if concept:
        topic = clean_topic_phrase(concept.group(1))
        if topic and normalize_text(topic) not in {"it", "this", "these", "those"}:
            clues.append(f"{label}: What is {topic}?")

    if "role:" in cleaned.casefold():
        lead = cleaned.split("Role:", 1)[0].split("role:", 1)[0].strip(" .,:;")
        if 3 <= len(lead) <= 90:
            clues.append(f"{label}: State the role of {lead}.")

    if "step" in cleaned.casefold() and "workflow" in cleaned.casefold():
        sentence = first_clean_sentence(cleaned, max_words=18)
        if sentence:
            clues.append(f"{label}: Build an MCQ from this answer clue: {sentence}")

    if not clues:
        sentence = first_clean_sentence(cleaned, max_words=18)
        if sentence:
            clues.append(f"{label}: Infer the hidden question from this answer context: {sentence}")

    return unique_preserving_order(clues)[:3]


def clean_question_candidate(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", line).strip(" \t:-")
    if len(cleaned) < 12:
        return ""
    if is_noise_line(cleaned):
        return ""
    if re.match(r"^(page|marks?|total|seat no|time|instructions?)\b", normalize_text(cleaned)):
        return ""
    instruction_starts = (
        "all questions are compulsory",
        "answer each next main question",
        "figures to the right indicate",
        "assume suitable data",
        "use of non programmable",
        "use of non-programmable",
        "mobile phone",
    )
    if any(normalize_text(cleaned).startswith(item) for item in instruction_starts):
        return ""
    return cleaned


@lru_cache(maxsize=256)
def extract_paper_questions(pdf_web_path: str, limit: int = 24) -> Tuple[str, ...]:
    text = extract_pdf_text(pdf_web_path)
    if not text:
        return tuple()

    question_lines: List[str] = []
    patterns = [
        r"(Q\.?\s*\d+[A-Z]?\)?\s+[^?]{10,250}\??)",
        r"((?:\d+[\.\)])\s+[^?]{10,250}\??)",
    ]
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            cleaned = clean_question_candidate(match)
            if cleaned:
                question_lines.append(cleaned)

    if not question_lines:
        pieces = re.split(r"(?<=[.?])\s+", text)
        for piece in pieces:
            cleaned = clean_question_candidate(piece)
            if cleaned:
                question_lines.append(cleaned)

    unique = unique_preserving_order(question_lines)
    return tuple(unique[:limit])


def clean_exam_text(text: str) -> str:
    cleaned = html.unescape(text or "").replace("\xa0", " ")
    cleaned = re.sub(r"\b\d{6}\s*\[\s*\d+\s+of\s+\d+\s*\]", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bpage\s+\d+\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\bP\.?T\.?O\.?\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"_+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


@lru_cache(maxsize=256)
def extract_main_question_blocks(pdf_web_path: str, limit: int = 6) -> Tuple[str, ...]:
    text = clean_exam_text(extract_pdf_text(pdf_web_path, max_pages=8))
    if not text:
        return tuple()

    question_starts = (
        "attempt",
        "answer",
        "write",
        "solve",
        "find",
        "prove",
        "compute",
        "differentiate",
        "derive",
        "draw",
        "state",
        "define",
        "explain",
        "obtain",
        "evaluate",
        "simplify",
    )
    start_pattern = "|".join(question_starts)
    label_pattern = rf"(?:Q\.?\s*)?\d+\s*[A-Z]?\s*[.)]"
    patterns = [
        rf"({label_pattern}\s*(?:{start_pattern}).*?)(?={label_pattern}\s*(?:{start_pattern})|$)",
    ]

    blocks: List[str] = []
    for pattern in patterns:
        for match in re.findall(pattern, text, flags=re.IGNORECASE):
            cleaned = clean_question_candidate(match)
            if not cleaned:
                continue
            cleaned = re.sub(r"^\s*marks\s*", "", cleaned, flags=re.IGNORECASE)
            start = re.search(rf"{label_pattern}\s*(?:{start_pattern})", cleaned, flags=re.IGNORECASE)
            if start:
                cleaned = cleaned[start.start():].strip()
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            normalized = normalize_text(cleaned)
            if any(
                fragment in normalized
                for fragment in (
                    "answer each next main question",
                    "figures to the right indicate full marks",
                    "use of non programmable electronic pocket calculator",
                    "use of non-programmable electronic pocket calculator",
                )
            ):
                continue
            if len(cleaned) > 700:
                cleaned = cleaned[:700].rsplit(" ", 1)[0].rstrip(" .,:;") + " ..."
            blocks.append(cleaned)

    if not blocks:
        fallback: List[str] = []
        for item in extract_paper_questions(pdf_web_path, limit=limit * 3):
            lowered = normalize_text(item)
            if any(f" {token} " in f" {lowered} " for token in question_starts):
                fallback.append(item)
        blocks = fallback

    ordered = unique_preserving_order(blocks)
    return tuple(ordered[:limit])


def paper_snippets(question: str, subject: Dict[str, Any], limit: int = 3) -> List[str]:
    paper_bundle = PAPERS_BY_CODE.get(str(subject.get("paper_code", "")), {})
    files = sorted_paper_files(subject)
    if not files:
        return []

    scored: List[Tuple[float, str]] = []
    for file_info in files[:4]:
        session = file_info.get("session", "")
        for item in extract_paper_questions(file_info.get("path", "")):
            score = score_overlap(question, item)
            if score <= 0:
                continue
            scored.append((score, f"{session}: {item}" if session else item))

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = unique_preserving_order([text for _, text in scored])
    return ordered[:limit]


def score_overlap(query: str, candidate: str) -> float:
    query_tokens = text_tokens(query)
    if not query_tokens:
        return 0.0

    candidate_normalized = normalize_text(candidate)
    candidate_tokens = set(text_tokens(candidate))
    shared = sum(1 for token in query_tokens if token in candidate_tokens)
    phrase_hits = sum(1 for token in query_tokens if token in candidate_normalized)
    return shared * 4 + phrase_hits


def subject_match_details(subject: Dict[str, Any], query: str) -> Dict[str, Any]:
    subject_name = normalize_text(str(subject.get("subject", "")))
    paper_code = str(subject.get("paper_code", ""))
    title_tokens = significant_subject_tokens(subject_name)
    query_tokens = set(raw_text_tokens(query))
    matched_title_tokens = [token for token in title_tokens if token in query_tokens]
    exact_title = bool(subject_name and subject_name in query)
    exact_code = bool(paper_code and paper_code in query)
    selector_hint = any(hint in query_tokens for hint in SUBJECT_SELECTOR_HINTS)
    score = score_overlap(query, " ".join([paper_code, subject_name, str(subject.get("program_name", "")), str(subject.get("semester", ""))]))
    score += len(matched_title_tokens) * 5
    if exact_title:
        score += 20
    if exact_code:
        score += 30
    if matched_title_tokens and selector_hint:
        score += 4

    explicit = exact_code or exact_title or len(matched_title_tokens) >= 2 or (len(matched_title_tokens) >= 1 and selector_hint)
    return {
        "subject": subject,
        "score": score,
        "matched_title_tokens": matched_title_tokens,
        "exact_title": exact_title,
        "exact_code": exact_code,
        "explicit": explicit,
    }


def rank_subject_matches(message: str, limit: int = 5) -> List[Dict[str, Any]]:
    query = normalize_text(message)
    if not query:
        return []

    scored: List[Dict[str, Any]] = []
    for subject in SUBJECTS:
        details = subject_match_details(subject, query)
        if details["score"] > 0:
            details["score"] += min(subject.get("papers_count", 0), 4) * 0.3
            scored.append(details)

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def suggest_subject_matches(message: str, limit: int = 5) -> List[Dict[str, Any]]:
    return [item["subject"] for item in rank_subject_matches(message, limit=limit)]


def query_refers_to_selected_subject(message: str) -> bool:
    query = normalize_text(message)
    if not query:
        return False
    return any(hint in query for hint in SELECTED_CONTEXT_HINTS)


def pick_subject(message: str, subject_key_value: str = "", subject_code_value: str = "") -> Tuple[Optional[Dict[str, Any]], List[Dict[str, Any]]]:
    if subject_code_value:
        matches = SUBJECTS_BY_CODE.get(str(subject_code_value), [])
        if matches:
            return matches[0], matches[:5]

    query = normalize_text(message)
    if not query:
        return None, []

    ranked = rank_subject_matches(message, limit=5)
    explicit_match = next((item for item in ranked if item["explicit"]), None)
    if explicit_match:
        subject = explicit_match["subject"]
        related = SUBJECTS_BY_CODE.get(str(subject.get("paper_code", "")), [])
        return subject, related[:5]

    selected_material_hint = any(hint in query for hint in MCQ_MATERIAL_HINTS) or "uploaded" in query or "my pdf" in query or "my notes" in query
    if subject_key_value and subject_key_value in SUBJECTS_BY_KEY:
        selected = SUBJECTS_BY_KEY[subject_key_value]
        related = SUBJECTS_BY_CODE.get(str(selected.get("paper_code", "")), [])
        return selected, related[:5]

    return None, [item["subject"] for item in ranked]


def top_snippets(question: str, subject: Dict[str, Any], limit: int = 5) -> List[str]:
    subject_text = extract_subject_text(subject.get("syllabus_path", ""))
    chunks = split_into_chunks(subject_text) if subject_text else []
    papers = paper_snippets(question, subject, limit=3)
    materials = material_snippets(question, subject, limit=4)
    prefers_materials = any(hint in normalize_text(question) for hint in MCQ_MATERIAL_HINTS) or "uploaded" in normalize_text(question)
    if not chunks and not papers and not materials:
        return []

    scored: List[Tuple[float, str]] = []
    for chunk in chunks:
        score = score_overlap(question, chunk)
        if score > 0:
            scored.append((score, chunk))
    for snippet in papers:
        score = score_overlap(question, snippet)
        if score > 0:
            scored.append((score + 2, snippet))
    for snippet in materials:
        score = score_overlap(question, snippet)
        if score > 0:
            scored.append((score + (5 if prefers_materials else 3), snippet))

    if not scored:
        seed = materials[:limit] + papers[: max(0, limit - len(materials))] if prefers_materials else papers[:limit] + materials[: max(0, limit - len(papers))]
        return seed + chunks[: max(0, limit - len(seed))]

    scored.sort(key=lambda item: item[0], reverse=True)
    ordered = unique_preserving_order([chunk for _, chunk in scored])
    return ordered[:limit]


def sentence_points(question: str, snippets: List[str], limit: int = 8) -> List[str]:
    collected: List[Tuple[float, str]] = []
    for snippet in snippets:
        pieces = re.split(r"(?<=[.!?])\s+|\n+", snippet)
        for piece in pieces:
            cleaned = re.sub(r"\s+", " ", piece).strip(" \t:-")
            if len(cleaned) < 25:
                continue
            if is_noise_line(cleaned):
                continue
            score = score_overlap(question, cleaned)
            if score <= 0 and question.strip():
                continue
            collected.append((score, cleaned))

    if not collected:
        collected = [(1.0, snippet.strip()) for snippet in snippets if snippet.strip()]

    collected.sort(key=lambda item: item[0], reverse=True)
    points = unique_preserving_order([item[1] for item in collected])
    return points[:limit]


def extract_question_parts(message: str) -> List[str]:
    raw_parts = re.split(r"\n+|(?=\bQ\.?\s*\d+\b)|(?=\b\d+\)\s*)|(?=\b\d+\.\s*)", message)
    parts = [re.sub(r"\s+", " ", part).strip(" \t:-") for part in raw_parts]
    return [part for part in parts if len(part) > 3]


def session_sort_key(session: str) -> Tuple[int, int]:
    lowered = normalize_text(session)
    year_match = re.search(r"(20\d{2})", lowered)
    year = int(year_match.group(1)) if year_match else 0
    if "winter" in lowered:
        season = 2
    elif "summer" in lowered:
        season = 1
    else:
        season = 0
    return year, season


def sorted_paper_files(subject: Dict[str, Any]) -> List[Dict[str, Any]]:
    files = list(PAPERS_BY_CODE.get(str(subject.get("paper_code", "")), {}).get("files", []))
    files.sort(key=lambda item: session_sort_key(str(item.get("session", ""))), reverse=True)
    return files


def latest_paper_file(subject: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    files = sorted_paper_files(subject)
    return files[0] if files else None


def is_math_subject(subject: Optional[Dict[str, Any]]) -> bool:
    if not subject:
        return False
    name = normalize_text(str(subject.get("subject", "")))
    return any(hint in name for hint in MATH_SUBJECT_HINTS)


def is_math_query(question: str) -> bool:
    lowered = normalize_text(question)
    return any(hint in lowered for hint in MATH_QUERY_HINTS)


def is_math_context(subject: Optional[Dict[str, Any]], question: str) -> bool:
    return is_math_subject(subject) or is_math_query(question)


def math_style_instructions() -> str:
    return (
        "For mathematics and calculation questions, follow these rules strictly:\n"
        "1. Show the solution step by step, but keep it concise.\n"
        "2. State the property or rule in plain English before applying it.\n"
        "3. Let each step flow into the next with = signs on clean lines where possible.\n"
        "4. Never guess or jump to a conclusion without showing why.\n"
        "5. Read the question exactly as written and do not reinterpret it.\n"
        "6. If the question uses fractions or exact expressions, keep them exactly as written.\n"
        "7. Do not introduce new bases, new variables, or extra assumptions unless the original question gives them.\n"
        "8. Use plain English and avoid heavy jargon.\n"
        "9. Write formulas in plain text like dy/dx, sqrt(2), log(2/3), sin(theta), or (a+b)/c.\n"
        "10. Do not output Markdown bold, LaTeX delimiters, or backslash commands like \\frac, \\log, \\left, \\right, \\(, or \\[.\n"
        "11. Put the final result on its own line as Final Answer: [ value ]."
    )


def summarize_subject(subject: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not subject:
        return {}
    paper_bundle = PAPERS_BY_CODE.get(str(subject.get("paper_code", "")), {})
    latest = latest_paper_file(subject)
    materials = subject_materials_summary(subject)
    return {
        "key": subject.get("key"),
        "paper_code": subject.get("paper_code"),
        "subject": subject.get("subject"),
        "program_code": subject.get("program_code"),
        "program_name": subject.get("program_name"),
        "semester": subject.get("semester"),
        "syllabus_path": subject.get("syllabus_path"),
        "available_sessions": paper_bundle.get("sessions", subject.get("available_sessions", [])),
        "papers_count": paper_bundle.get("count", subject.get("papers_count", 0)),
        "latest_paper": latest,
        "materials_count": len(materials),
    }


def format_intro(subject: Dict[str, Any], points: List[str]) -> str:
    for point in points:
        lowered = normalize_text(point)
        if lowered.startswith("tlo "):
            continue
        if lowered.startswith("co"):
            continue
        if lowered.startswith("unit"):
            continue
        return point
    if points:
        return points[0]
    return f"{subject.get('subject', 'This topic')} is part of {subject.get('paper_code', 'the selected course')}."


def point_priority(point: str) -> Tuple[int, int]:
    lowered = normalize_text(point)
    if lowered.startswith("summer -") or lowered.startswith("winter -"):
        return (5, len(point))
    if lowered.startswith("tlo "):
        return (4, len(point))
    if lowered.startswith("co"):
        return (4, len(point))
    if lowered.startswith("unit"):
        return (3, len(point))
    if "prepare" in lowered or "explain" in lowered or "procedure" in lowered or "focus" in lowered or "important" in lowered:
        return (1, -len(point))
    return (0, -len(point))


def prioritized_points(points: List[str], limit: int = 8) -> List[str]:
    ordered = unique_preserving_order(points)
    ordered.sort(key=point_priority)
    return ordered[:limit]


def build_theory_conclusion(subject: Dict[str, Any], question: str, points: List[str]) -> str:
    if points:
        summary = points[0]
        return f"In exam answers, conclude by linking {subject.get('subject')} with the main idea: {summary}"
    return f"{subject.get('subject')} should be explained clearly with relevant points from the syllabus and exam context."


def format_theory_answer(question: str, subject: Dict[str, Any], points: List[str], sessions: List[str]) -> str:
    theory_points = prioritized_points(points, limit=8)
    intro = format_intro(subject, theory_points)
    lines = [
        f"Subject: {subject.get('paper_code')} - {subject.get('subject')}",
        "",
        "Exam-Style Theory Answer",
        "",
        "Introduction:",
        intro,
        "",
        "Main points:",
    ]

    body_points = theory_points if theory_points else [f"The syllabus material for {subject.get('subject')} should be used to write the answer in your own words."]
    for index, point in enumerate(body_points, start=1):
        lines.append(f"{index}. {point}")

    lines.extend(
        [
            "",
            "Conclusion:",
            build_theory_conclusion(subject, question, theory_points),
        ]
    )

    if sessions:
        lines.extend(["", f"Related paper sessions: {', '.join(sessions[:4])}"])

    return "\n".join(lines)


def format_study_answer(question: str, subject: Dict[str, Any], points: List[str], sessions: List[str]) -> str:
    study_points = prioritized_points(points, limit=7)
    lines = [
        f"Subject Match: {subject.get('paper_code')} - {subject.get('subject')}",
        "",
        "Study Notes",
    ]
    if study_points:
        for point in study_points:
            lines.append(f"- {point}")
    else:
        lines.append("- I found the subject, but not enough matching syllabus lines for this exact query.")

    if sessions:
        lines.extend(["", f"Past paper sessions linked: {', '.join(sessions[:4])}"])

    return "\n".join(lines)


def format_steps_answer(question: str, subject: Dict[str, Any], points: List[str], sessions: List[str]) -> str:
    step_points = prioritized_points(points, limit=6)
    lines = [
        f"Subject: {subject.get('paper_code')} - {subject.get('subject')}",
        "",
        "Step-Wise Answer Framework",
        "",
        "1. Identify exactly what the question is asking.",
        "2. Write the relevant definition, rule, theorem, or formula from the subject.",
        "3. Break the method into clear ordered steps before writing the final result.",
        "4. For numericals, substitute values carefully and mention units wherever needed.",
        "5. End with the final answer in a neat exam-ready line.",
        "",
        "Useful syllabus points:",
    ]

    if step_points:
        for point in step_points:
            lines.append(f"- {point}")
    else:
        lines.append("- No exact step source was found, so use the topic name and course outcomes to frame the method.")

    if sessions:
        lines.extend(["", f"Practice with paper sessions: {', '.join(sessions[:4])}"])

    return "\n".join(lines)


def format_answer_paper(question: str, subject: Dict[str, Any], points: List[str], sessions: List[str]) -> str:
    parts = extract_question_parts(question)
    paper_points = prioritized_points(points, limit=5)
    if len(parts) <= 1:
        return format_theory_answer(question, subject, paper_points, sessions)

    lines = [
        f"Answer Paper Draft for {subject.get('paper_code')} - {subject.get('subject')}",
        "",
    ]

    for index, part in enumerate(parts[:5], start=1):
        lines.append(f"Q{index}. {part}")
        lines.append("Answer:")
        answer_points = paper_points if paper_points else [f"Write the answer to '{part}' using the syllabus points of {subject.get('subject')}."]
        for point_index, point in enumerate(answer_points, start=1):
            lines.append(f"{point_index}. {point}")
        lines.append("")

    if sessions:
        lines.append(f"Linked paper sessions: {', '.join(sessions[:4])}")

    return "\n".join(lines).strip()


def render_retrieval_answer(question: str, mode: str, subject: Dict[str, Any], snippets: List[str]) -> str:
    paper_bundle = PAPERS_BY_CODE.get(str(subject.get("paper_code", "")), {})
    sessions = paper_bundle.get("sessions", subject.get("available_sessions", []))
    points = sentence_points(question, snippets)

    if mode == "theory":
        return format_theory_answer(question, subject, points, sessions)
    if mode == "steps":
        return format_steps_answer(question, subject, points, sessions)
    if mode == "paper":
        return format_answer_paper(question, subject, points, sessions)
    return format_study_answer(question, subject, points, sessions)


def build_system_prompt(mode: str, subject: Dict[str, Any], snippets: List[str], question: str = "") -> str:
    mode_instruction = {
        "study": "Answer as a patient study assistant using concise study notes and direct teaching language.",
        "theory": "Write an exam-style theory answer with introduction, explanation, and conclusion in natural prose and numbered points.",
        "steps": "Write a step-wise solution format suitable for mathematics, equations, derivations, and procedures.",
        "paper": "Draft answer-paper style responses for one or more exam questions.",
    }.get(mode, "Answer as a study assistant.")

    context = "\n\n".join(snippets[:5])
    extra_math_rules = ""
    if mode in {"steps", "paper"} and is_math_context(subject, question):
        extra_math_rules = f"\n\n{math_style_instructions()}"
    return (
        "You are Lumen Vault AI, a diploma study assistant. "
        "Prefer the supplied study context and keep answers relevant to the selected subject. "
        "The context may include syllabus notes, question papers, uploaded answers, OCR text, comparison tables, and step lists. "
        "Infer the concept behind the material before answering. "
        "If the context is thin, you may add careful general academic explanation, but keep it aligned to the course. "
        "Do not copy raw header metadata, timestamps, course tables, admin labels, or long source lines into the answer. "
        "Rewrite and synthesize the material in clear human-readable language, and silently clean obvious OCR mistakes when the meaning is clear.\n\n"
        f"Selected subject: {subject.get('paper_code')} - {subject.get('subject')} ({subject.get('semester')})\n"
        f"{mode_instruction}\n\n"
        "If the paper or question includes multiple parts, keep the original order and answer each part under a clear heading. "
        "Do not say that you cannot see the paper if extracted question text is already provided. "
        "When uploaded material looks like answer notes, derive the likely question or topic first and then write a fresh answer."
        f"{extra_math_rules}\n\n"
        "Study context:\n"
        f"{context}"
    )


def build_general_system_prompt(mode: str, question: str = "") -> str:
    mode_instruction = {
        "study": "Answer as a general study assistant.",
        "theory": "Write an exam-style general theory answer.",
        "steps": "Write a step-wise method suitable for general problem solving.",
        "paper": "Draft answer-paper style responses in general academic language.",
    }.get(mode, "Answer as a study assistant.")

    extra_math_rules = ""
    if mode in {"steps", "paper"} and is_math_query(question):
        extra_math_rules = f"\n\n{math_style_instructions()}"

    return (
        "You are Lumen Vault AI. The user has not selected a subject, so you should still answer the question directly in clear, helpful general academic language. "
        "Do not refuse, delay, or redirect just because no subject is selected. "
        "Give a real answer first. Only mention subject-specific mode briefly at the end if it would genuinely improve the answer.\n\n"
        f"{mode_instruction}"
        f"{extra_math_rules}"
    )


def render_general_fallback(question: str, mode: str) -> str:
    topic = re.sub(r"\s+", " ", question).strip(" ?")
    if mode == "theory":
        return (
            "General Answer Mode\n\n"
            f"Topic: {topic}\n\n"
            "A subject is not selected, so this answer is written in general theory format.\n\n"
            "Use this theory-answer structure:\n"
            "1. Start with a definition or meaning of the topic.\n"
            "2. Explain why it is important.\n"
            "3. Write the main components, functions, or stages.\n"
            "4. Add advantages, limitations, or applications if relevant.\n"
            "5. End with a short conclusion in exam language.\n\n"
            "If you mention the full subject name later, I can make it more syllabus-focused."
        )
    if mode == "steps":
        return (
            "General Answer Mode\n\n"
            f"Topic: {topic}\n\n"
            "Use this step-wise approach:\n"
            "1. Identify what the question is asking.\n"
            "2. Write the related concept, principle, or formula.\n"
            "3. Break the method into numbered steps.\n"
            "4. Show the working clearly.\n"
            "5. End with the final result or conclusion.\n\n"
            "For a syllabus-grounded version, mention the full subject name or paper code."
        )
    if mode == "paper":
        return (
            "General Answer Mode\n\n"
            f"Topic: {topic}\n\n"
            "A subject is not selected, so this is a general answer-paper style structure.\n"
            "Write each answer with:\n"
            "1. Definition or opening statement.\n"
            "2. Main explanation in 4 to 6 points.\n"
            "3. Example, use case, or brief note if needed.\n"
            "4. Final conclusion line."
        )
    return (
        "General Answer Mode\n\n"
        f"Topic: {topic}\n\n"
        "A subject is not selected, so this answer should be given in general academic mode.\n"
        "If you mention the full subject name or paper code later, the answer can be made more syllabus-focused."
    )


@lru_cache(maxsize=1)
def ollama_command() -> List[str]:
    candidates = [
        "ollama",
        str(Path.home() / "AppData" / "Local" / "Programs" / "Ollama" / "ollama.exe"),
    ]
    for candidate in candidates:
        try:
            result = subprocess.run(
                [candidate, "list"],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except Exception:
            continue
        if result.returncode == 0:
            return [candidate]
    return []


@lru_cache(maxsize=1)
def detect_ollama_model() -> str:
    if OLLAMA_MODEL:
        return OLLAMA_MODEL

    command = ollama_command()
    if not command:
        return ""

    try:
        result = subprocess.run(
            command + ["list"],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )
    except Exception:
        return ""

    if result.returncode != 0:
        return ""

    installed: List[str] = []
    for line in result.stdout.splitlines()[1:]:
        name = line.strip().split()[0] if line.strip() else ""
        if name:
            installed.append(name)

    for preferred in PREFERRED_OLLAMA_MODELS:
        if preferred in installed:
            return preferred

    return installed[0] if installed else ""


def configured_ai_backends() -> List[str]:
    ordered: List[str] = []
    for item in AI_BACKEND_ORDER.split(","):
        backend = normalize_text(item).replace("-", "_")
        if backend in VALID_AI_BACKENDS and backend not in ordered:
            ordered.append(backend)
    if not ordered:
        ordered = ["ollama", "gemini", "llama_cpp"]
    return ordered


def health_backend_label() -> str:
    detected_model = detect_ollama_model()
    for backend in configured_ai_backends():
        if backend == "ollama" and detected_model:
            return f"ollama:{detected_model}"
        if backend == "gemini" and (GEMINI_API_KEY or GEMINI_API_KEY2):
            return f"gemini:{GEMINI_MODEL}"
        if backend == "openai" and (OPENAI_API_KEY or OPENAI_API_KEY2):
            return f"openai:{OPENAI_MODEL}"
        if backend == "llama_cpp" and LLAMA_MODEL_PATH:
            return "llama_cpp"
    return "retrieval"


def generate_with_configured_backends(
    system_prompt: str,
    user_prompt: str,
    ollama_num_predict: int = 900,
    gemini_max_output_tokens: int = 900,
    openai_max_output_tokens: int = 900,
    llama_max_tokens: int = 900,
    timeout_s: int = 120,
) -> Tuple[str, str]:
    detected_model = detect_ollama_model()
    for backend in configured_ai_backends():
        if backend == "ollama":
            answer = ollama_generate(system_prompt, user_prompt, num_predict=ollama_num_predict, timeout_s=timeout_s)
            if answer:
                return answer, f"ollama:{detected_model or detect_ollama_model()}"
        elif backend == "gemini":
            answer = gemini_generate(system_prompt, user_prompt, max_output_tokens=gemini_max_output_tokens, timeout_s=timeout_s)
            if answer:
                return answer, f"gemini:{GEMINI_MODEL}"
        elif backend == "openai":
            answer = openai_generate(system_prompt, user_prompt, max_output_tokens=openai_max_output_tokens, timeout_s=timeout_s)
            if answer:
                return answer, f"openai:{OPENAI_MODEL}"
        elif backend == "llama_cpp":
            answer = llama_cpp_generate(system_prompt, user_prompt, max_tokens=llama_max_tokens)
            if answer:
                return answer, "llama_cpp"
    return "", ""


def ollama_generate(system_prompt: str, user_prompt: str, num_predict: int = 900, timeout_s: int = 120) -> str:
    model_name = detect_ollama_model()
    if not model_name:
        return ""

    payload = {
        "model": model_name,
        "system": system_prompt,
        "prompt": user_prompt,
        "stream": False,
        "options": {"temperature": 0.2, "num_predict": num_predict},
    }
    request_data = json.dumps(payload).encode("utf-8")
    req = Request(OLLAMA_URL, data=request_data, headers={"Content-Type": "application/json"})

    try:
        with urlopen(req, timeout=timeout_s) as response:
            raw = response.read().decode("utf-8")
        parsed = json.loads(raw)
        return (parsed.get("response") or "").strip()
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        return ""


def load_llama_cpp() -> Optional[Any]:
    global _llama_instance
    if _llama_instance is not None:
        return _llama_instance
    if not (Llama and LLAMA_MODEL_PATH):
        return None
    try:
        _llama_instance = Llama(model_path=LLAMA_MODEL_PATH, n_ctx=4096)
    except Exception:
        _llama_instance = None
    return _llama_instance


def llama_cpp_generate(system_prompt: str, user_prompt: str, max_tokens: int = 900) -> str:
    llm = load_llama_cpp()
    if not llm:
        return ""

    full_prompt = f"{system_prompt}\n\nUser question:\n{user_prompt}\n\nAnswer:"
    try:
        output = llm(full_prompt, max_tokens=max_tokens, temperature=0.2, echo=False)
        if isinstance(output, dict) and output.get("choices"):
            return (output["choices"][0].get("text") or "").strip()
    except Exception:
        return ""
    return ""


def _safe_json_loads(raw: str) -> Dict[str, Any]:
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def _gemini_error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        parsed = _safe_json_loads(body)
        error_obj = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        message = str(error_obj.get("message") or body or exc).strip()
        return f"HTTP {exc.code}: {message[:300]}"
    if isinstance(exc, URLError):
        return f"Network error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "Request timed out."
    if isinstance(exc, json.JSONDecodeError):
        return "Gemini returned invalid JSON."
    return str(exc)[:300]


def _extract_gemini_text(parsed: Dict[str, Any]) -> str:
    candidates = parsed.get("candidates") or []
    if not isinstance(candidates, list):
        return ""
    parts: List[str] = []
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        content = candidate.get("content") or {}
        if not isinstance(content, dict):
            continue
        blocks = content.get("parts") or []
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            text = str(block.get("text") or "").strip()
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def gemini_diagnostic_generate(system_prompt: str, user_prompt: str, max_output_tokens: int = 900, timeout_s: int = 120) -> Tuple[str, str]:
    api_keys = [key for key in (GEMINI_API_KEY, GEMINI_API_KEY2) if key]
    if not api_keys:
        return "", "No Gemini API key configured."

    last_detail = "Gemini returned an empty response."
    combined_prompt = f"{system_prompt}\n\nUser question:\n{user_prompt}"
    for index, api_key in enumerate(api_keys, start=1):
        key_label = f"key {index}"
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": combined_prompt}
                    ]
                }
            ],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
            },
        }
        req = Request(
            f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "x-goog-api-key": api_key,
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8")
            parsed = _safe_json_loads(raw)
            text = _extract_gemini_text(parsed)
            if text:
                return text, f"Gemini worked on {key_label}."
            prompt_feedback = parsed.get("promptFeedback") or {}
            block_reason = str(prompt_feedback.get("blockReason") or "").strip()
            if block_reason:
                last_detail = f"Gemini blocked the prompt on {key_label}: {block_reason}"
            else:
                last_detail = f"Gemini returned no text on {key_label}."
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_detail = f"Gemini failed on {key_label}: {_gemini_error_detail(exc)}"

    return "", last_detail


def gemini_generate(system_prompt: str, user_prompt: str, max_output_tokens: int = 900, timeout_s: int = 120) -> str:
    answer, _detail = gemini_diagnostic_generate(
        system_prompt,
        user_prompt,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
    )
    return answer


def _openai_error_detail(exc: Exception) -> str:
    if isinstance(exc, HTTPError):
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        parsed = _safe_json_loads(body)
        error_obj = parsed.get("error") if isinstance(parsed.get("error"), dict) else {}
        message = str(error_obj.get("message") or body or exc).strip()
        return f"HTTP {exc.code}: {message[:300]}"
    if isinstance(exc, URLError):
        return f"Network error: {exc.reason}"
    if isinstance(exc, TimeoutError):
        return "Request timed out."
    if isinstance(exc, json.JSONDecodeError):
        return "OpenAI returned invalid JSON."
    return str(exc)[:300]


def openai_diagnostic_generate(system_prompt: str, user_prompt: str, max_output_tokens: int = 900, timeout_s: int = 120) -> Tuple[str, str]:
    api_keys = [key for key in (OPENAI_API_KEY, OPENAI_API_KEY2) if key]
    if not api_keys:
        return "", "No OpenAI API key configured."

    last_detail = "OpenAI returned an empty response."
    for index, api_key in enumerate(api_keys, start=1):
        key_label = f"key {index}"
        payload = {
            "model": OPENAI_MODEL,
            "instructions": system_prompt,
            "input": user_prompt,
            "max_output_tokens": max_output_tokens,
            "store": False,
        }
        request_data = json.dumps(payload).encode("utf-8")
        req = Request(
            "https://api.openai.com/v1/responses",
            data=request_data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        parsed: Dict[str, Any] = {}
        try:
            with urlopen(req, timeout=timeout_s) as response:
                raw = response.read().decode("utf-8")
            parsed = _safe_json_loads(raw)
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_detail = f"Responses API failed on {key_label}: {_openai_error_detail(exc)}"
            parsed = {}

        output_text = str(parsed.get("output_text") or "").strip()
        if output_text:
            return output_text, f"Responses API worked on {key_label}."

        output = parsed.get("output") or []
        if isinstance(output, list):
            parts: List[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") in {"output_text", "text"}:
                        text_value = block.get("text")
                        if isinstance(text_value, str) and text_value.strip():
                            parts.append(text_value.strip())
                        elif isinstance(text_value, dict):
                            value = str(text_value.get("value") or "").strip()
                            if value:
                                parts.append(value)
            if parts:
                return "\n".join(parts).strip(), f"Responses API worked on {key_label}."

        chat_payload = {
            "model": OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "max_completion_tokens": max_output_tokens,
        }
        chat_request = Request(
            "https://api.openai.com/v1/chat/completions",
            data=json.dumps(chat_payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
        )

        try:
            with urlopen(chat_request, timeout=timeout_s) as response:
                chat_raw = response.read().decode("utf-8")
            chat_parsed = _safe_json_loads(chat_raw)
            choices = chat_parsed.get("choices") or []
            if choices and isinstance(choices[0], dict):
                message = choices[0].get("message") or {}
                content = message.get("content")
                if isinstance(content, str) and content.strip():
                    return content.strip(), f"Chat Completions API worked on {key_label}."
            last_detail = f"Chat Completions returned no text on {key_label}."
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_detail = f"Chat Completions failed on {key_label}: {_openai_error_detail(exc)}"

    return "", last_detail


def openai_generate(system_prompt: str, user_prompt: str, max_output_tokens: int = 900, timeout_s: int = 120) -> str:
    answer, _detail = openai_diagnostic_generate(
        system_prompt,
        user_prompt,
        max_output_tokens=max_output_tokens,
        timeout_s=timeout_s,
    )
    return answer


def generate_answer(message: str, mode: str, subject: Dict[str, Any], snippets: List[str], history: List[Dict[str, str]]) -> Tuple[str, str]:
    user_prompt = message.strip()
    if history:
        recent_turns = []
        for item in history[-6:]:
            role = item.get("role", "user").capitalize()
            content = (item.get("content") or "").strip()
            if content:
                recent_turns.append(f"{role}: {content}")
        if recent_turns:
            user_prompt = "\n".join(recent_turns + [f"User: {user_prompt}"])

    system_prompt = build_system_prompt(mode, subject, snippets, message)

    answer, backend = generate_with_configured_backends(
        system_prompt,
        user_prompt,
        ollama_num_predict=900,
        gemini_max_output_tokens=900,
        openai_max_output_tokens=900,
        llama_max_tokens=900,
        timeout_s=120,
    )
    if answer:
        return answer, backend

    return render_retrieval_answer(message, mode, subject, snippets), "retrieval"


def generate_general_answer(message: str, mode: str, history: List[Dict[str, str]]) -> Tuple[str, str]:
    user_prompt = message.strip()
    if history:
        recent_turns = []
        for item in history[-6:]:
            role = item.get("role", "user").capitalize()
            content = (item.get("content") or "").strip()
            if content:
                recent_turns.append(f"{role}: {content}")
        if recent_turns:
            user_prompt = "\n".join(recent_turns + [f"User: {user_prompt}"])

    system_prompt = build_general_system_prompt(mode, message)

    answer, backend = generate_with_configured_backends(
        system_prompt,
        user_prompt,
        ollama_num_predict=900,
        gemini_max_output_tokens=900,
        openai_max_output_tokens=900,
        llama_max_tokens=900,
        timeout_s=120,
    )
    if answer:
        return answer, backend

    return render_general_fallback(message, mode), "general"


def generate_plain_general_answer(message: str, history: List[Dict[str, str]]) -> Tuple[str, str]:
    user_prompt = message.strip()
    if history:
        recent_turns = []
        for item in history[-6:]:
            role = item.get("role", "user").capitalize()
            content = (item.get("content") or "").strip()
            if content:
                recent_turns.append(f"{role}: {content}")
        if recent_turns:
            user_prompt = "\n".join(recent_turns + [f"User: {user_prompt}"])

    system_prompt = "You are a helpful general assistant. Answer clearly, directly, and naturally."

    answer, backend = generate_with_configured_backends(
        system_prompt,
        user_prompt,
        ollama_num_predict=900,
        gemini_max_output_tokens=900,
        openai_max_output_tokens=900,
        llama_max_tokens=900,
        timeout_s=120,
    )
    if answer:
        return answer, backend

    return "I could not generate a general answer right now. Please try again.", "general"


def diagnose_ai_backends(test_message: str = "Reply with exactly: API OK") -> Dict[str, Any]:
    diagnostics: List[Dict[str, Any]] = []
    detected_model = detect_ollama_model()

    for backend in configured_ai_backends():
        item: Dict[str, Any] = {"backend": backend, "configured": False, "ok": False, "detail": ""}
        if backend == "ollama":
            item["configured"] = bool(detected_model)
            if not item["configured"]:
                item["detail"] = "No local Ollama model detected."
            else:
                answer = ollama_generate("Reply briefly.", test_message, num_predict=40, timeout_s=30)
                item["ok"] = bool(answer)
                item["detail"] = answer[:160] if answer else "Ollama did not return a response."
                item["label"] = f"ollama:{detected_model}"
        elif backend == "gemini":
            item["configured"] = bool(GEMINI_API_KEY or GEMINI_API_KEY2)
            if not item["configured"]:
                item["detail"] = "No Gemini API key configured."
            else:
                answer, detail = gemini_diagnostic_generate("Reply briefly.", test_message, max_output_tokens=40, timeout_s=30)
                item["ok"] = bool(answer)
                item["detail"] = answer[:160] if answer else detail
                item["label"] = f"gemini:{GEMINI_MODEL}"
        elif backend == "openai":
            item["configured"] = bool(OPENAI_API_KEY or OPENAI_API_KEY2)
            if not item["configured"]:
                item["detail"] = "No OpenAI API key configured."
            else:
                answer, detail = openai_diagnostic_generate("Reply briefly.", test_message, max_output_tokens=40, timeout_s=30)
                item["ok"] = bool(answer)
                item["detail"] = answer[:160] if answer else detail
                item["label"] = f"openai:{OPENAI_MODEL}"
        elif backend == "llama_cpp":
            item["configured"] = bool(LLAMA_MODEL_PATH)
            if not item["configured"]:
                item["detail"] = "No llama.cpp model path configured."
            else:
                answer = llama_cpp_generate("Reply briefly.", test_message, max_tokens=40)
                item["ok"] = bool(answer)
                item["detail"] = answer[:160] if answer else "llama.cpp did not return a response."
                item["label"] = "llama_cpp"
        diagnostics.append(item)

    overall_ok = any(item.get("ok") for item in diagnostics)
    return {
        "ok": True,
        "backend": health_backend_label(),
        "backend_order": configured_ai_backends(),
        "token_test_prompt": test_message,
        "providers": diagnostics,
        "any_provider_ok": overall_ok,
    }


def answer_paper_user_prompt(subject: Dict[str, Any], paper_info: Dict[str, Any], questions: List[str]) -> str:
    lines = [
        "Generate a structured answer paper from this extracted latest question paper.",
        f"Subject: {subject.get('paper_code')} - {subject.get('subject')}",
        f"Program: {subject.get('program_name')}",
        f"Semester: {subject.get('semester')}",
        f"Paper session: {paper_info.get('session', 'Unknown session')}",
        "",
        "Instructions:",
        "1. Keep the main question order exactly as given.",
        "2. Use the extracted question wording as the heading for each answer.",
        "3. If a question contains sub-parts like (a), (b), (c), answer them separately under that same question.",
        "4. For theory subjects, write exam-ready answers in natural prose and points.",
        "5. For mathematics or equations, solve step by step and keep exact expressions.",
        "6. Do not repeat course metadata, timestamps, or raw PDF garbage.",
        "",
        "Extracted latest-paper questions:",
    ]
    for index, question in enumerate(questions, start=1):
        lines.append(f"{index}. {question}")
    return "\n".join(lines)


def answer_paper_question_prompt(subject: Dict[str, Any], paper_info: Dict[str, Any], question: str, index: int, total: int) -> str:
    subparts = unique_preserving_order(re.findall(r"\(([a-z])\)", question, flags=re.IGNORECASE))
    lines = [
        f"Generate the answer for main question {index} of {total}.",
        f"Subject: {subject.get('paper_code')} - {subject.get('subject')}",
        f"Paper session: {paper_info.get('session', 'Unknown session')}",
        "Write only the answer for this question.",
        "If the question contains sub-parts like (a), (b), or (c), answer them separately under the same main question.",
        "Do not stop after answering the first visible sub-part.",
        "Keep the answer concise but exam-ready.",
        "Do not repeat course metadata or raw OCR junk.",
    ]
    if subparts:
        joined = ", ".join(f"({item.lower()})" for item in subparts)
        lines.extend(
            [
                f"The visible sub-parts in this extracted question are: {joined}.",
                "Answer every visible sub-part separately with its own label.",
                "If the paper says attempt any, still provide answer-ready content for all visible sub-parts so the student can choose.",
            ]
        )
    if is_math_context(subject, question):
        lines.extend(
            [
                "Use plain text only for maths.",
                "Do not use Markdown bold or LaTeX syntax.",
                "Write equations in readable plain text, for example cos 75 = (sqrt(6) - sqrt(2)) / 4.",
                "For each visible sub-part, state the rule in plain English, then show 1 to 4 clean steps, then end that sub-part with Final Answer: [ value ].",
                "Do not give only the final value without showing why.",
            ]
        )
    else:
        lines.append("Use natural prose and points for theory-style parts.")
    lines.extend(["", f"Question {index}: {question}"])
    return "\n".join(lines)


def clean_generated_answer_text(text: str, math_mode: bool = False) -> str:
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```[\w-]*\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    cleaned = re.sub(r"^(answer|response)\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\*\*(.*?)\*\*", r"\1", cleaned)
    if math_mode:
        replacements = {
            r"\theta": "theta",
            r"\pi": "pi",
            r"\sin": "sin",
            r"\cos": "cos",
            r"\tan": "tan",
            r"\log": "log",
            r"\cdot": "*",
            r"\times": "*",
            r"\div": "/",
            r"\left": "",
            r"\right": "",
            r"\(": "",
            r"\)": "",
            r"\[": "",
            r"\]": "",
        }
        for source, target in replacements.items():
            cleaned = cleaned.replace(source, target)
        cleaned = re.sub(r"\\sqrt\s*\{([^{}]+)\}", r"sqrt(\1)", cleaned)
        cleaned = re.sub(r"\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}", r"(\1) / (\2)", cleaned)
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = cleaned.replace(" Final Answer:", "\nFinal Answer:")
        cleaned = cleaned.replace(". Final Answer:", ".\nFinal Answer:")
        cleaned = cleaned.replace(": Final Answer:", ":\nFinal Answer:")
        cleaned = cleaned.replace(" . ", ". ")
        cleaned = cleaned.strip()
    return cleaned.strip()


def render_question_fallback(question: str, subject: Dict[str, Any], snippets: List[str]) -> str:
    points = sentence_points(question, snippets, limit=5)
    if is_math_context(subject, question):
        lines = [
            "Use this exam-ready solving pattern:",
            "1. Read the exact expression or numerical values from the question.",
            "2. State the formula, identity, or property in plain English before using it.",
            "3. Show the working one step at a time with = signs where possible.",
            "4. Keep fractions and exact values unchanged until the final step.",
            "5. Final Answer: [ write the computed result here ]",
        ]
        if points:
            lines.extend(["", "Useful syllabus support:"] + [f"- {point}" for point in points[:3]])
        return "\n".join(lines)

    if not points:
        return "Write an exam-style answer using the exact wording of the question, then explain the concept in clear points and end with a short conclusion."

    lines = []
    for index, point in enumerate(points[:4], start=1):
        lines.append(f"{index}. {point}")
    return "\n".join(lines)


def assemble_answer_paper(subject: Dict[str, Any], paper_info: Dict[str, Any], question_answers: List[Tuple[str, str]]) -> str:
    lines = [
        f"Latest linked paper: {paper_info.get('session', 'Unknown session')}",
        "",
        f"Answer Paper for {subject.get('paper_code')} - {subject.get('subject')}",
        f"Program: {subject.get('program_name')}",
        f"Semester: {subject.get('semester')}",
        "",
    ]

    for index, (question, answer) in enumerate(question_answers, start=1):
        lines.append(f"Q{index}. {question}")
        lines.append("Answer:")
        lines.append(clean_generated_answer_text(answer, math_mode=is_math_context(subject, question)))
        lines.append("")

    return "\n".join(lines).strip()


def render_answer_paper_fallback(subject: Dict[str, Any], paper_info: Dict[str, Any], questions: List[str], snippets: List[str]) -> str:
    sessions = [paper_info.get("session")] if paper_info.get("session") else []
    joined_questions = "\n".join(questions)
    answer = format_answer_paper(joined_questions, subject, sentence_points(joined_questions, snippets, limit=8), sessions)
    if paper_info.get("session"):
        answer = f"Latest linked paper: {paper_info.get('session')}\n\n{answer}"
    return answer


def generate_latest_answer_paper(subject: Dict[str, Any], paper_path: str = "") -> Tuple[str, str, Dict[str, Any], List[str], List[str]]:
    paper_info = None
    if paper_path:
        for item in sorted_paper_files(subject):
            if item.get("path") == paper_path:
                paper_info = item
                break
    if paper_info is None:
        paper_info = latest_paper_file(subject)
    if not paper_info:
        return (
            "No linked question paper is available for this subject yet.",
            "retrieval",
            {},
            [],
            [],
        )

    paper_path_value = str(paper_info.get("path", ""))
    questions = list(extract_main_question_blocks(paper_path_value, limit=6))
    if not questions:
        questions = list(extract_paper_questions(paper_path_value, limit=8))

    if not questions:
        return (
            "I found the latest linked paper file, but I could not extract readable questions from it yet.",
            "retrieval",
            paper_info,
            [],
            [],
        )

    question_seed = "\n".join(questions)
    combined_snippets: List[str] = []
    question_answers: List[Tuple[str, str]] = []
    used_backend = "retrieval"
    used_model = False

    for index, question in enumerate(questions, start=1):
        snippets = top_snippets(question, subject, limit=5)
        combined_snippets.extend(snippets)
        system_prompt = build_system_prompt("paper", subject, snippets, question)
        user_prompt = answer_paper_question_prompt(subject, paper_info, question, index, len(questions))
        subpart_count = len(re.findall(r"\(([a-z])\)", question, flags=re.IGNORECASE))
        num_predict = 700 if subpart_count >= 4 else 520

        answer = ollama_generate(system_prompt, user_prompt, num_predict=num_predict, timeout_s=120)
        if answer:
            question_answers.append((question, answer))
            used_backend = f"ollama:{detect_ollama_model()}"
            used_model = True
            continue

        answer = gemini_generate(system_prompt, user_prompt, max_output_tokens=num_predict, timeout_s=120)
        if answer:
            question_answers.append((question, answer))
            used_backend = f"gemini:{GEMINI_MODEL}"
            used_model = True
            continue

        answer = openai_generate(system_prompt, user_prompt, max_output_tokens=num_predict, timeout_s=120)
        if answer:
            question_answers.append((question, answer))
            used_backend = f"openai:{OPENAI_MODEL}"
            used_model = True
            continue

        answer = llama_cpp_generate(system_prompt, user_prompt, max_tokens=num_predict)
        if answer:
            question_answers.append((question, answer))
            if used_backend == "retrieval":
                used_backend = "llama_cpp"
            used_model = True
            continue

        question_answers.append((question, render_question_fallback(question, subject, snippets)))

    clean_snippets = unique_preserving_order(combined_snippets)
    if used_model:
        return assemble_answer_paper(subject, paper_info, question_answers), used_backend, paper_info, questions, clean_snippets

    return render_answer_paper_fallback(subject, paper_info, questions, clean_snippets), "retrieval", paper_info, questions, clean_snippets


def paper_question_bank(subject: Dict[str, Any], limit: int = 24) -> List[str]:
    bank: List[str] = []
    for file_info in sorted_paper_files(subject)[:4]:
        session = str(file_info.get("session", "")).strip()
        questions = list(extract_main_question_blocks(str(file_info.get("path", "")), limit=8))
        if not questions:
            questions = list(extract_paper_questions(str(file_info.get("path", "")), limit=8))
        for question in questions:
            prefix = f"{session}: " if session else ""
            bank.append(f"{prefix}{question}")
    return unique_preserving_order(bank)[:limit]


def material_context_bank(subject: Dict[str, Any], limit: int = 10) -> List[str]:
    bank: List[str] = []
    for entry in material_entries_for_subject(subject)[:6]:
        label = MATERIAL_TYPES.get(str(entry.get("material_type", "")), "Material")
        text = extract_pdf_text(str(entry.get("path", "")), max_pages=10)
        if not text:
            continue
        for chunk in split_into_chunks(text, chunk_size=320):
            bank.append(f"{label}: {chunk}")
            if len(bank) >= limit:
                return bank
    return bank[:limit]


def material_concept_bank(subject: Dict[str, Any], limit: int = 18) -> List[str]:
    bank: List[str] = []
    for entry in material_entries_for_subject(subject)[:6]:
        label = MATERIAL_TYPES.get(str(entry.get("material_type", "")), "Material")
        text = extract_pdf_text(str(entry.get("path", "")), max_pages=10)
        if not text:
            continue
        for chunk in split_into_chunks(text, chunk_size=260):
            for clue in material_concept_clues(chunk, label):
                bank.append(clue)
                if len(bank) >= limit:
                    return unique_preserving_order(bank)[:limit]
    return unique_preserving_order(bank)[:limit]


def normalize_mcq_source_mode(value: str) -> str:
    mode = normalize_text(value)
    if mode in MCQ_SOURCE_LABELS:
        return mode
    return "papers"


def mcq_source_label(mode: str) -> str:
    return MCQ_SOURCE_LABELS.get(normalize_mcq_source_mode(mode), "Question Papers")


def material_question_bank(subject: Dict[str, Any], limit: int = 24) -> List[str]:
    bank: List[str] = []
    for entry in material_entries_for_subject(subject)[:6]:
        label = MATERIAL_TYPES.get(str(entry.get("material_type", "")), "Material")
        path = str(entry.get("path", ""))
        seeded_lines: List[str] = []
        if str(entry.get("material_type", "")) in {"question", "test"}:
            seeded_lines.extend(list(extract_main_question_blocks(path, limit=8)))
            if len(seeded_lines) < 4:
                seeded_lines.extend(list(extract_paper_questions(path, limit=10)))

        if not seeded_lines:
            text = extract_pdf_text(path, max_pages=10)
            if not text:
                continue
            for chunk in split_into_chunks(text, chunk_size=280):
                for clue in material_concept_clues(chunk, label):
                    bank.append(clue)
                    if len(bank) >= limit:
                        return unique_preserving_order(bank)[:limit]
                cleaned = re.sub(r"\s+", " ", chunk).strip(" \t:-")
                if len(cleaned) < 35 or is_noise_line(cleaned):
                    continue
                bank.append(f"{label}: Answer/context clue: {cleaned}")
                if len(bank) >= limit:
                    return unique_preserving_order(bank)[:limit]
            continue

        for line in seeded_lines:
            cleaned = re.sub(r"\s+", " ", line).strip(" \t:-")
            if len(cleaned) < 12 or is_noise_line(cleaned):
                continue
            bank.append(f"{label}: {cleaned}")
            if len(bank) >= limit:
                return unique_preserving_order(bank)[:limit]

        text = extract_pdf_text(path, max_pages=10)
        if text:
            for chunk in split_into_chunks(text, chunk_size=260):
                for clue in material_concept_clues(chunk, label):
                    bank.append(clue)
                    if len(bank) >= limit:
                        return unique_preserving_order(bank)[:limit]

    return unique_preserving_order(bank)[:limit]


def mcq_source_refs(subject: Dict[str, Any], source_mode: str) -> List[str]:
    mode = normalize_mcq_source_mode(source_mode)
    if mode == "materials":
        refs = []
        for item in subject_materials_summary(subject)[:5]:
            refs.append(str(item.get("original_name") or item.get("name") or "Uploaded PDF"))
        return refs
    return [str(item.get("session", "")).strip() for item in sorted_paper_files(subject)[:5] if str(item.get("session", "")).strip()]


def detect_mcq_request(message: str) -> Optional[Dict[str, Any]]:
    query = normalize_text(message)
    if not query:
        return None

    has_mcq_intent = any(hint in query for hint in MCQ_CHAT_HINTS)
    has_material_hint = any(hint in query for hint in MCQ_MATERIAL_HINTS)
    has_paper_hint = any(hint in query for hint in MCQ_PAPER_HINTS)
    explicit_make_test = any(
        fragment in query
        for fragment in (
            "make test",
            "generate test",
            "create test",
            "make quiz",
            "generate quiz",
            "create quiz",
        )
    )
    if not has_mcq_intent and not explicit_make_test:
        return None

    if has_material_hint or "from uploaded" in query or "from material" in query:
        return {"source_mode": "materials"}
    if has_paper_hint or "from question paper" in query or "from papers" in query:
        return {"source_mode": "papers"}
    return {"source_mode": "papers"}


def requested_mcq_count(message: str, default: int = 8) -> int:
    query = normalize_text(message)
    if not query:
        return default
    match = re.search(r"\b(4|5|6|7|8|9|10|11|12)\b", query)
    if not match:
        return default
    return max(4, min(int(match.group(1)), 12))


def extract_json_payload(text: str) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    if raw.startswith("{") or raw.startswith("["):
        return raw
    start = raw.find("{")
    end = raw.rfind("}")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    start = raw.find("[")
    end = raw.rfind("]")
    if start != -1 and end != -1 and end > start:
        return raw[start : end + 1]
    return raw


def safe_json_loads(text: str) -> Any:
    payload = extract_json_payload(text)
    if not payload:
        return {}

    candidates = [
        payload,
        re.sub(r"\\(?![\"\\/bfnrtu])", "", payload),
        re.sub(r"[\r\u2028\u2029]", " ", payload),
    ]
    candidates.append(re.sub(r"\\(?![\"\\/bfnrtu])", "", candidates[-1]))

    for candidate in candidates:
        try:
            return json.loads(candidate)
        except Exception:
            continue
    return {}


def parse_answer_index(value: Any, options: List[str]) -> Optional[int]:
    if isinstance(value, int) and 0 <= value < len(options):
        return value
    if isinstance(value, str):
        stripped = value.strip().upper()
        if stripped.isdigit():
            index = int(stripped)
            if 0 <= index < len(options):
                return index
            if 1 <= index <= len(options):
                return index - 1
        if len(stripped) == 1 and "A" <= stripped <= "D":
            return ord(stripped) - ord("A")
        for idx, option in enumerate(options):
            if normalize_text(option) == normalize_text(value):
                return idx
    return None


def shuffle_mcq_options(options: List[str], answer_index: int) -> Tuple[List[str], int]:
    if not options or answer_index < 0 or answer_index >= len(options):
        return options, answer_index
    indexed = list(enumerate(options))
    random.SystemRandom().shuffle(indexed)
    shuffled_options = [option for _, option in indexed]
    shuffled_answer_index = next((idx for idx, (original_idx, _) in enumerate(indexed) if original_idx == answer_index), answer_index)
    return shuffled_options, shuffled_answer_index


def normalize_mcq_items(items: Any, count: int = 8) -> List[Dict[str, Any]]:
    if not isinstance(items, list):
        return []

    normalized_items: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        prompt = re.sub(r"\s+", " ", str(item.get("prompt") or item.get("question") or "")).strip()
        options_raw = item.get("options") or []
        if not prompt or not isinstance(options_raw, list):
            continue
        options = [re.sub(r"\s+", " ", str(option)).strip() for option in options_raw if str(option).strip()]
        options = unique_preserving_order(options)
        if len(options) < 4:
            continue
        options = options[:4]
        answer_index = parse_answer_index(item.get("answer_index", item.get("answer")), options)
        if answer_index is None:
            continue
        options, answer_index = shuffle_mcq_options(options, answer_index)
        explanation = re.sub(r"\s+", " ", str(item.get("explanation") or "")).strip()
        normalized_items.append(
            {
                "prompt": prompt,
                "options": options,
                "answer_index": answer_index,
                "explanation": explanation,
            }
        )
        if len(normalized_items) >= count:
            break
    return normalized_items


def mcq_topic_from_line(subject: Dict[str, Any], line: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(line or "")).strip(" \t:-")
    if not cleaned:
        return str(subject.get("subject") or "the topic")

    cleaned = re.sub(r"^(summer|winter)\s*-\s*\d{4}\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(question file|subject test|book / study material|material)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^answer/context clue:\s*", "", cleaned, flags=re.IGNORECASE)

    if ":" in cleaned:
        lead = cleaned.split(":", 1)[0].strip(" -")
        if 3 <= len(lead) <= 80 and not is_noise_line(lead):
            return lead

    if "differentiate " in cleaned.lower():
        match = re.search(r"differentiate\s+(.+)", cleaned, flags=re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" .:-")
            if topic:
                return topic

    if "what is " in cleaned.lower():
        match = re.search(r"what is\s+(.+)", cleaned, flags=re.IGNORECASE)
        if match:
            topic = match.group(1).strip(" ?.:;-")
            if topic:
                return topic

    words = [word for word in re.findall(r"[A-Za-z0-9][A-Za-z0-9&()/.-]*", cleaned) if len(word) > 2]
    if words:
        return " ".join(words[:8]).strip(" .:-")

    return str(subject.get("subject") or "the topic")


def clean_mcq_source_line(line: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(line or "")).strip(" \t:-")
    cleaned = re.sub(r"^(summer|winter)\s*-\s*\d{4}\s*:\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^(question file|subject test|book / study material|material)\s*:\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"^answer/context clue:\s*", "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def fallback_mcqs(subject: Dict[str, Any], source: List[str], count: int = 8) -> List[Dict[str, Any]]:
    if not source:
        return []

    viable_source = [line for line in source if is_viable_mcq_source_line(line)]
    if not viable_source:
        return []

    prompts = []
    topic_pool = unique_preserving_order([mcq_topic_from_line(subject, item) for item in viable_source if item and is_viable_mcq_source_line(item)])
    base_pool = unique_preserving_order(
        topic_pool
        + [
            str(subject.get("subject") or "Core concept"),
            f"{subject.get('subject', 'Subject')} applications",
            f"{subject.get('subject', 'Subject')} fundamentals",
            f"{subject.get('subject', 'Subject')} methods",
            f"{subject.get('subject', 'Subject')} concepts",
        ]
    )
    for line in viable_source[:count]:
        topic = mcq_topic_from_line(subject, line)
        cleaned_line = clean_mcq_source_line(line)
        if not topic or is_noise_line(topic):
            continue
        distractors = [choice for choice in base_pool if normalize_text(choice) != normalize_text(topic)]
        while len(distractors) < 3:
            distractors.append(f"{subject.get('subject', 'Subject')} topic {len(distractors) + 1}")
        options = [topic] + distractors[:3]
        options, answer_index = shuffle_mcq_options(options, 0)
        prompts.append(
            {
                "prompt": f"Which concept is most directly tested by this item?\n{cleaned_line}",
                "options": options,
                "answer_index": answer_index,
                "explanation": "This fallback MCQ was built from the extracted source line when no AI backend was available.",
            }
        )
    return prompts[:count]


def mcq_system_prompt(subject: Dict[str, Any], source_mode: str) -> str:
    primary_source = (
        "the supplied uploaded-material content"
        if normalize_mcq_source_mode(source_mode) == "materials"
        else "the supplied question-paper content"
    )
    return (
        "You are Lumen Vault MCQ Builder. Create clean, useful diploma-level MCQs. "
        f"Use {primary_source} as the primary source. "
        "Do not use syllabus-only headings or external facts that are not supported by the supplied content. "
        "If the source lines look like answers, notes, OCR text, workflows, or comparison tables instead of direct questions, infer the hidden concept first and then build the MCQ from that understanding. "
        "If optional secondary support lines are supplied, use them only to sharpen the correct answer or explanation. "
        "Do not copy long source lines word for word. Paraphrase them into clean exam-style MCQs. "
        "Return strict JSON only, with no markdown and no extra text. "
        "Use plain text only in questions, options, and explanations. Do not emit LaTeX-style backslashes. "
        'Use this schema: {"questions":[{"prompt":"...","options":["...","...","...","..."],"answer_index":0,"explanation":"..."}]}. '
        "Always return exactly four options per question."
    )


def mcq_user_prompt(
    subject: Dict[str, Any],
    source_lines: List[str],
    support_lines: List[str],
    count: int = 8,
    source_mode: str = "papers",
) -> str:
    primary_label = "uploaded material lines" if normalize_mcq_source_mode(source_mode) == "materials" else "question-paper source lines"
    support_label = "secondary support lines"
    lines = [
        f"Generate {count} MCQs for this subject.",
        f"Subject: {subject.get('paper_code')} - {subject.get('subject')}",
        f"Program: {subject.get('program_name')}",
        f"Semester: {subject.get('semester')}",
        "",
        "Rules:",
        f"1. Build the MCQs mainly from the supplied {primary_label}.",
        "2. If a source line is an answer, note, definition, role, workflow, or comparison table, infer the likely hidden question before creating the MCQ.",
        "3. Rephrase descriptive content into objective-style MCQs.",
        "4. Avoid duplicate questions.",
        "5. Keep one clearly correct answer and three believable distractors.",
        "6. Keep the wording student-friendly and exam-focused.",
        "7. For maths, calculation, or formula topics, you may create quick-solve or concept MCQs.",
        "8. Do not simply copy the uploaded line; understand it and turn it into a fresh question.",
        "",
        f"Primary {primary_label}:",
    ]
    for index, line in enumerate(source_lines, start=1):
        lines.append(f"{index}. {line}")
    if support_lines:
        lines.extend(["", f"Optional {support_label}:"])
        for index, line in enumerate(support_lines, start=1):
            lines.append(f"{index}. {line}")
    return "\n".join(lines)


def generate_mcq_quiz(subject: Dict[str, Any], count: int = 8, source_mode: str = "papers") -> Dict[str, Any]:
    count = max(4, min(int(count or 8), 12))
    materials = subject_materials_summary(subject)
    requested_mode = normalize_mcq_source_mode(source_mode)
    paper_lines = paper_question_bank(subject, limit=max(10, count * 2))
    material_lines = material_question_bank(subject, limit=max(10, count * 2))
    material_concepts = material_concept_bank(subject, limit=max(8, count * 2))
    support_material_lines = material_context_bank(subject, limit=6)

    fallback_note = ""
    if requested_mode == "materials":
        primary_material_lines = unique_preserving_order(material_lines + material_concepts)
        if primary_material_lines:
            primary_lines = primary_material_lines
            support_lines = unique_preserving_order(support_material_lines + paper_lines[:4])[:8]
            used_mode = "materials"
        else:
            primary_lines = paper_lines
            support_lines = []
            used_mode = "papers"
            fallback_note = "No uploaded material with readable text was found, so Lumen Vault used the linked question papers instead."
    else:
        primary_lines = paper_lines
        support_lines = unique_preserving_order(material_concepts[:4] + support_material_lines)
        used_mode = "papers"

    if not primary_lines:
        return {
            "questions": [],
            "backend": "retrieval",
            "source_lines": [],
            "materials": materials,
            "source_mode": used_mode,
            "source_label": mcq_source_label(used_mode),
            "source_refs": mcq_source_refs(subject, used_mode),
            "requested_source": requested_mode,
            "fallback_note": fallback_note,
        }

    system_prompt = mcq_system_prompt(subject, used_mode)
    user_prompt = mcq_user_prompt(subject, primary_lines, support_lines, count=count, source_mode=used_mode)
    backend = "retrieval"

    raw = ollama_generate(system_prompt, user_prompt, num_predict=2200, timeout_s=180)
    if raw:
        data = safe_json_loads(raw)
        items = normalize_mcq_items(data.get("questions") if isinstance(data, dict) else data, count=count)
        if items:
            return {
                "questions": items,
                "backend": f"ollama:{detect_ollama_model()}",
                "source_lines": primary_lines,
                "materials": materials,
                "source_mode": used_mode,
                "source_label": mcq_source_label(used_mode),
                "source_refs": mcq_source_refs(subject, used_mode),
                "requested_source": requested_mode,
                "fallback_note": fallback_note,
            }
        backend = f"ollama:{detect_ollama_model()}"
        retry_prompt = (
            mcq_user_prompt(
                subject,
                primary_lines[: min(len(primary_lines), 6)],
                support_lines[:2],
                count=count,
                source_mode=used_mode,
            )
            + "\n\nPlain text only. No backslashes. No LaTeX."
        )
        retry_raw = ollama_generate(system_prompt, retry_prompt, num_predict=1800, timeout_s=140)
        if retry_raw:
            retry_data = safe_json_loads(retry_raw)
            retry_items = normalize_mcq_items(retry_data.get("questions") if isinstance(retry_data, dict) else retry_data, count=count)
            if retry_items:
                return {
                    "questions": retry_items,
                    "backend": f"ollama:{detect_ollama_model()}",
                    "source_lines": primary_lines,
                    "materials": materials,
                    "source_mode": used_mode,
                    "source_label": mcq_source_label(used_mode),
                    "source_refs": mcq_source_refs(subject, used_mode),
                    "requested_source": requested_mode,
                    "fallback_note": fallback_note,
                }

    raw = openai_generate(system_prompt, user_prompt, max_output_tokens=2200, timeout_s=180)
    if raw:
        data = safe_json_loads(raw)
        items = normalize_mcq_items(data.get("questions") if isinstance(data, dict) else data, count=count)
        if items:
            return {
                "questions": items,
                "backend": f"openai:{OPENAI_MODEL}",
                "source_lines": primary_lines,
                "materials": materials,
                "source_mode": used_mode,
                "source_label": mcq_source_label(used_mode),
                "source_refs": mcq_source_refs(subject, used_mode),
                "requested_source": requested_mode,
                "fallback_note": fallback_note,
            }
        backend = f"openai:{OPENAI_MODEL}"

    raw = gemini_generate(system_prompt, user_prompt, max_output_tokens=2200, timeout_s=180)
    if raw:
        data = safe_json_loads(raw)
        items = normalize_mcq_items(data.get("questions") if isinstance(data, dict) else data, count=count)
        if items:
            return {
                "questions": items,
                "backend": f"gemini:{GEMINI_MODEL}",
                "source_lines": primary_lines,
                "materials": materials,
                "source_mode": used_mode,
                "source_label": mcq_source_label(used_mode),
                "source_refs": mcq_source_refs(subject, used_mode),
                "requested_source": requested_mode,
                "fallback_note": fallback_note,
            }
        backend = f"gemini:{GEMINI_MODEL}"

    raw = llama_cpp_generate(system_prompt, user_prompt, max_tokens=2200)
    if raw:
        data = safe_json_loads(raw)
        items = normalize_mcq_items(data.get("questions") if isinstance(data, dict) else data, count=count)
        if items:
            return {
                "questions": items,
                "backend": "llama_cpp",
                "source_lines": primary_lines,
                "materials": materials,
                "source_mode": used_mode,
                "source_label": mcq_source_label(used_mode),
                "source_refs": mcq_source_refs(subject, used_mode),
                "requested_source": requested_mode,
                "fallback_note": fallback_note,
            }
        backend = "llama_cpp"

    fallback = fallback_mcqs(subject, primary_lines, count=count)
    return {
        "questions": fallback,
        "backend": backend,
        "source_lines": primary_lines,
        "materials": materials,
        "source_mode": used_mode,
        "source_label": mcq_source_label(used_mode),
        "source_refs": mcq_source_refs(subject, used_mode),
        "requested_source": requested_mode,
        "fallback_note": fallback_note,
    }


def store_uploaded_material(subject: Dict[str, Any], material_type: str, uploaded_file: Any) -> Dict[str, Any]:
    if material_type not in MATERIAL_TYPES:
        raise ValueError("Choose a valid material type.")
    if not uploaded_file or not getattr(uploaded_file, "filename", ""):
        raise ValueError("Select a PDF file first.")

    filename = str(uploaded_file.filename)
    if not filename.lower().endswith(".pdf"):
        raise ValueError("Only PDF files are supported.")

    subject_folder = sanitize_slug(f"{subject.get('paper_code')}-{subject.get('subject')}-{subject.get('program_code')}")
    target_dir = UPLOADS_DIR / subject_folder / material_type
    target_dir.mkdir(parents=True, exist_ok=True)

    stored_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}-{sanitize_slug(Path(filename).stem)}.pdf"
    target_path = target_dir / stored_name
    uploaded_file.save(str(target_path))

    web_path = "/" + target_path.relative_to(BASE_DIR).as_posix()
    extracted_text = extract_pdf_text(web_path, max_pages=10)
    if len(re.sub(r"\s+", " ", extracted_text).strip()) < 80:
        try:
            target_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("This PDF could not be read clearly enough, even after OCR. Try a clearer scan or a higher-quality PDF.")

    entry = {
        "id": uuid4().hex,
        "subject_key": subject.get("key"),
        "paper_code": subject.get("paper_code"),
        "subject": subject.get("subject"),
        "program_code": subject.get("program_code"),
        "material_type": material_type,
        "name": stored_name,
        "original_name": filename,
        "path": web_path,
        "uploaded_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "pages": len(PdfReader(str(target_path)).pages) if PdfReader else 0,
    }
    MATERIALS_INDEX.setdefault("items", []).append(entry)
    MATERIALS_BY_SUBJECT[str(subject.get("key"))].append(entry)
    save_material_index()
    return summarize_material(entry)


@app.get("/")
def root() -> Any:
    return redirect("/lumen_vault/", code=302)


@app.get("/lumen_vault/")
def lumen_index() -> Any:
    return send_from_directory(UI_DIR, "index.html")


@app.get("/lumen_vault/api/health")
def health() -> Any:
    backend = health_backend_label()
    return jsonify(
        {
            "ok": True,
            "backend": backend,
            "subjects": len(SUBJECTS),
            "materials": len(MATERIALS_INDEX.get("items", [])),
            "ocr_ready": ocr_ready(),
            "backend_order": configured_ai_backends(),
        }
    )


@app.get("/lumen_vault/api/diagnostics")
def diagnostics_api() -> Any:
    return jsonify(diagnose_ai_backends())


@app.post("/lumen_vault/api/chat")
def chat_api() -> Any:
    payload = request.get_json(force=True) or {}
    message = (payload.get("message") or "").strip()
    mode = (payload.get("mode") or "study").strip().lower()
    history = payload.get("history") or []
    subject_key_value = (payload.get("subject_key") or "").strip()
    subject_code_value = (payload.get("subject_code") or "").strip()

    if not message:
        return jsonify({"ok": False, "error": "Message is required."}), 400

    if mode not in {"study", "theory", "steps", "paper"}:
        mode = "study"

    mcq_request = detect_mcq_request(message)
    subject, matches = pick_subject(message, subject_key_value, subject_code_value)
    if mcq_request and not subject and subject_key_value in SUBJECTS_BY_KEY:
        subject = SUBJECTS_BY_KEY[subject_key_value]
        matches = SUBJECTS_BY_CODE.get(str(subject.get("paper_code", "")), [])[:5]

    if mcq_request and subject:
        quiz = generate_mcq_quiz(subject, count=requested_mcq_count(message), source_mode=mcq_request["source_mode"])
        questions = quiz.get("questions") or []
        answer_text = (
            f"MCQ test ready for {subject.get('paper_code')} - {subject.get('subject')}.\n\n"
            f"Source used: {quiz.get('source_label') or mcq_source_label(mcq_request['source_mode'])}."
        )
        if quiz.get("fallback_note"):
            answer_text += f"\n\n{quiz['fallback_note']}"
        if not questions:
            answer_text = "I could not generate an MCQ test because no readable uploaded material or question-paper content was found for this subject."

        return jsonify(
            {
                "ok": True,
                "action": "open_mcq" if questions else "message",
                "answer": answer_text,
                "backend": quiz.get("backend", "retrieval"),
                "subject": summarize_subject(subject),
                "matches": [summarize_subject(item) for item in matches[:3]],
                "snippets": sentence_points(message, quiz.get("source_lines") or [], limit=3),
                "materials": quiz.get("materials") or [],
                "questions": questions,
                "source_sessions": mcq_source_refs(subject, quiz.get("source_mode", mcq_request["source_mode"])),
                "source_lines": (quiz.get("source_lines") or [])[:10],
                "source_mode": quiz.get("source_mode", mcq_request["source_mode"]),
                "source_label": quiz.get("source_label", mcq_source_label(mcq_request["source_mode"])),
                "source_refs": quiz.get("source_refs") or [],
                "fallback_note": quiz.get("fallback_note", ""),
            }
        )

    if not subject:
        answer, backend = generate_general_answer(message, mode, history)
        return jsonify(
            {
                "ok": True,
                "answer": answer,
                "backend": backend,
                "subject": {},
                "matches": [summarize_subject(item) for item in matches[:3]],
                "snippets": [],
            }
        )

    snippets = top_snippets(message, subject)
    answer, backend = generate_answer(message, mode, subject, snippets, history)
    clean_support = sentence_points(message, snippets, limit=3)

    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "backend": backend,
            "subject": summarize_subject(subject),
            "matches": [summarize_subject(item) for item in matches[:3]],
            "snippets": clean_support,
            "materials": subject_materials_summary(subject),
        }
    )


@app.post("/lumen_vault/api/chat/general")
def general_chat_api() -> Any:
    payload = request.get_json(force=True) or {}
    message = (payload.get("message") or "").strip()
    history = payload.get("history") or []

    if not message:
        return jsonify({"ok": False, "error": "Message is required."}), 400

    answer, backend = generate_plain_general_answer(message, history)
    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "backend": backend,
            "subject": {},
            "matches": [],
            "snippets": [],
        }
    )


@app.post("/lumen_vault/api/answer-paper")
def answer_paper_api() -> Any:
    payload = request.get_json(force=True) or {}
    subject_key_value = (payload.get("subject_key") or "").strip()
    paper_path = (payload.get("paper_path") or "").strip()

    subject = SUBJECTS_BY_KEY.get(subject_key_value)
    if not subject:
        return jsonify({"ok": False, "error": "Select a subject first."}), 400

    answer, backend, paper_info, questions, snippets = generate_latest_answer_paper(subject, paper_path)
    clean_support = sentence_points("\n".join(questions), snippets, limit=4)

    return jsonify(
        {
            "ok": True,
            "answer": answer,
            "backend": backend,
            "subject": summarize_subject(subject),
            "paper": paper_info,
            "questions": questions,
            "snippets": clean_support,
            "materials": subject_materials_summary(subject),
        }
    )


@app.get("/lumen_vault/api/materials")
def materials_api() -> Any:
    subject_key_value = (request.args.get("subject_key") or "").strip()
    if subject_key_value:
        subject = SUBJECTS_BY_KEY.get(subject_key_value)
        if not subject:
            return jsonify({"ok": False, "error": "Subject not found."}), 404
        return jsonify(
            {
                "ok": True,
                "subject": summarize_subject(subject),
                "materials": subject_materials_summary(subject),
            }
        )

    items = [summarize_material(item) for item in MATERIALS_INDEX.get("items", [])]
    return jsonify({"ok": True, "materials": items})


@app.post("/lumen_vault/api/materials/upload")
def upload_material_api() -> Any:
    subject_key_value = (request.form.get("subject_key") or "").strip()
    material_type = (request.form.get("material_type") or "").strip().lower()
    uploaded_file = request.files.get("file")

    subject = SUBJECTS_BY_KEY.get(subject_key_value)
    if not subject:
        return jsonify({"ok": False, "error": "Select a valid subject first."}), 400

    try:
        material = store_uploaded_material(subject, material_type, uploaded_file)
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    except Exception:
        return jsonify({"ok": False, "error": "Upload failed while saving the PDF."}), 500

    return jsonify(
        {
            "ok": True,
            "subject": summarize_subject(subject),
            "material": material,
            "materials": subject_materials_summary(subject),
        }
    )


@app.post("/lumen_vault/api/mcq")
def mcq_api() -> Any:
    payload = request.get_json(force=True) or {}
    subject_key_value = (payload.get("subject_key") or "").strip()
    count = payload.get("count", 8)
    source_mode = normalize_mcq_source_mode(str(payload.get("source_mode") or "papers"))

    subject = SUBJECTS_BY_KEY.get(subject_key_value)
    if not subject:
        return jsonify({"ok": False, "error": "Select a subject first."}), 400

    quiz = generate_mcq_quiz(subject, count=count, source_mode=source_mode)
    questions = quiz.get("questions") or []
    if not questions:
        return jsonify({"ok": False, "error": "No readable uploaded material or question-paper content was found for MCQ generation."}), 400

    return jsonify(
        {
            "ok": True,
            "backend": quiz.get("backend", "retrieval"),
            "subject": summarize_subject(subject),
            "questions": questions,
            "source_sessions": mcq_source_refs(subject, quiz.get("source_mode", source_mode)),
            "source_lines": (quiz.get("source_lines") or [])[:10],
            "materials": quiz.get("materials") or [],
            "source_mode": quiz.get("source_mode", source_mode),
            "source_label": quiz.get("source_label", mcq_source_label(source_mode)),
            "source_refs": quiz.get("source_refs") or [],
            "fallback_note": quiz.get("fallback_note", ""),
        }
    )


@app.get("/lumen_vault/<path:filename>")
def lumen_static(filename: str) -> Any:
    return send_from_directory(UI_DIR, filename)


@app.get("/k scheme syllabus/<path:filename>")
def syllabus_static(filename: str) -> Any:
    return send_from_directory(SYLLABUS_DIR, filename)


@app.get("/previous year question paper/<path:filename>")
def papers_static(filename: str) -> Any:
    return send_from_directory(PAPERS_DIR, filename)


@app.get("/lumen_vault_uploads/<path:filename>")
def uploads_static(filename: str) -> Any:
    return send_from_directory(UPLOADS_DIR, filename)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8002, debug=False)
