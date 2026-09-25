import sys
from unittest.mock import MagicMock, patch
import pytest
from fastapi import HTTPException
from app.services.pdf import render_cover_letter_pdf, render_resume_pdf


def test_render_resume_pdf_success(sample_application_kit):
    mock_html = MagicMock()
    mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 dummy resume"

    with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html)}):
        pdf_bytes = render_resume_pdf(sample_application_kit)
        assert pdf_bytes == b"%PDF-1.4 dummy resume"


def test_render_resume_pdf_missing_system_libs(sample_application_kit):
    with patch("weasyprint.HTML", side_effect=OSError("libpango not found")):
        with pytest.raises(HTTPException) as exc:
            render_resume_pdf(sample_application_kit)
        assert exc.value.status_code == 503
        assert "WeasyPrint system libraries are missing" in exc.value.detail


def test_render_cover_letter_pdf_success(sample_application_kit):
    mock_html = MagicMock()
    mock_html.return_value.write_pdf.return_value = b"%PDF-1.4 dummy cover letter"

    with patch.dict("sys.modules", {"weasyprint": MagicMock(HTML=mock_html)}):
        pdf_bytes = render_cover_letter_pdf(sample_application_kit, company="Shopify", position="Senior Engineer")
        assert pdf_bytes == b"%PDF-1.4 dummy cover letter"


def test_render_cover_letter_pdf_missing_libs(sample_application_kit):
    with patch("weasyprint.HTML", side_effect=OSError("libcairo not found")):
        with pytest.raises(HTTPException) as exc:
            render_cover_letter_pdf(sample_application_kit, company="Shopify", position="Senior Engineer")
        assert exc.value.status_code == 503
        assert "WeasyPrint system libraries are missing" in exc.value.detail
