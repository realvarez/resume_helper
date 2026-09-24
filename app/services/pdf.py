"""Render the tailored résumé to an ATS-safe PDF via WeasyPrint."""
import logging

from fastapi import HTTPException
from fastapi.templating import Jinja2Templates

from app.config import TARGET_COUNTRY
from app.jinja_filters import bold
from app.schemas import ApplicationKit

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/templates")
templates.env.filters["bold"] = bold


def render_resume_pdf(kit: ApplicationKit) -> bytes:
    """HTML -> PDF. Raises 503 with setup guidance if system libs are missing."""
    try:
        from weasyprint import HTML
    except OSError as exc:  # missing pango/cairo system libraries
        logger.error("WeasyPrint unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="PDF generation is not available: WeasyPrint system libraries are missing. "
                   "On Debian/Ubuntu run: sudo apt install libpango-1.0-0 libpangocairo-1.0-0 "
                   "libgdk-pixbuf-2.0-0 libcairo2",
        ) from exc

    html = templates.get_template("resume_pdf.html").render(resume=kit.tailored_resume)
    pdf_bytes: bytes = HTML(string=html, base_url=".").write_pdf()
    return pdf_bytes


def render_cover_letter_pdf(kit: ApplicationKit, company: str = "", position: str = "") -> bytes:
    """Render the tailored cover letter to an executive PDF via WeasyPrint."""
    try:
        from weasyprint import HTML
    except OSError as exc:
        logger.error("WeasyPrint unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="PDF generation is not available: WeasyPrint system libraries are missing.",
        ) from exc

    import datetime
    today = datetime.date.today().strftime("%B %d, %Y")

    html = templates.get_template("cover_letter_pdf.html").render(
        cover_letter=kit.cover_letter,
        resume=kit.tailored_resume,
        company=company,
        position=position,
        target_country=TARGET_COUNTRY,
        date_str=today,
    )
    pdf_bytes: bytes = HTML(string=html, base_url=".").write_pdf()
    return pdf_bytes

