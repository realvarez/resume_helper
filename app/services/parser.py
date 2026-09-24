"""Extract plain text from uploaded résumé files (PDF / DOCX / TXT)."""
import io
import pdfplumber
from docx import Document as DocxDocument
from fastapi import HTTPException, UploadFile

from app.config import get_settings

ALLOWED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md"}


def _decode_text(data: bytes) -> str:
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def extract_text(upload: UploadFile, min_chars: int = 0) -> str:
    """Return plain text from an uploaded file (PDF / DOCX / TXT / MD)."""
    if not upload or not getattr(upload, "filename", ""):
        return ""
    settings = get_settings()
    suffix = "." + upload.filename.rsplit(".", 1)[-1].lower() if "." in upload.filename else ""

    if suffix not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix or 'unknown'}'. "
                   f"Upload one of: {', '.join(sorted(ALLOWED_EXTENSIONS))}.",
        )

    data = upload.file.read()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(status_code=413, detail=f"File '{upload.filename}' too large (max 5 MB).")
    if not data:
        if min_chars > 0:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")
        return ""

    if suffix == ".pdf":
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    elif suffix == ".docx":
        doc = DocxDocument(io.BytesIO(data))
        text = "\n".join(p.text for p in doc.paragraphs)
    else:  # .txt / .md
        text = _decode_text(data)

    text = text.strip()

    if min_chars > 0 and len(text) < min_chars:
        raise HTTPException(
            status_code=422,
            detail="Could not extract enough readable text from the file — "
                   "it may be a scanned image. Try pasting your résumé text instead.",
        )
    return text


def build_extra_context(supporting_files: list[UploadFile] | None, extra_notes: str | None) -> str:
    """Consolidate multiple supporting files and free-text career notes into a clean context block."""
    blocks = []
    if supporting_files:
        for f in supporting_files:
            if getattr(f, "filename", ""):
                content = extract_text(f, min_chars=0)
                if content:
                    blocks.append(f"### Source: {f.filename}\n{content}")

    if extra_notes and extra_notes.strip():
        blocks.append(f"### Candidate Extra Notes & Highlights\n{extra_notes.strip()}")

    return "\n\n".join(blocks).strip()

