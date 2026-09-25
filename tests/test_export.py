import io
import zipfile
from unittest.mock import patch
from app.services.export import (
    extract_initials,
    generate_application_zip,
    get_application_filenames,
    render_company_research_markdown,
    render_cover_letter_markdown,
    render_cover_letter_text,
    render_interview_prep_markdown,
    render_match_analysis_markdown,
    render_resume_markdown,
    render_tips_markdown,
    sanitize_token,
)
from app.schemas import GenerateInputs


def test_extract_initials():
    assert extract_initials("Ricardo Alvarez") == "RA"
    assert extract_initials("John") == "JOHN"
    assert extract_initials("Alexandria") == "Alexandria"
    assert extract_initials("") == "User"
    assert extract_initials("   ") == "User"
    assert extract_initials("!@#$%") == "User"
    assert extract_initials("Jane Mary Doe") == "JMD"


def test_sanitize_token():
    assert sanitize_token("Senior Backend Engineer") == "Senior_Backend_Engineer"
    assert sanitize_token("Shopify, Inc. / Canada") == "Shopify_Inc_Canada"
    assert sanitize_token("____test____") == "test"
    assert sanitize_token("", default="Fallback") == "Fallback"


def test_get_application_filenames(sample_application_kit):
    filenames = get_application_filenames(sample_application_kit)
    assert filenames["initials"] == "RA"
    assert filenames["clean_position"] == "Senior_Backend_Engineer"
    assert filenames["clean_company"] == "Shopify"
    assert filenames["prefix"] == "RA_Senior_Backend_Engineer_Shopify"
    assert filenames["zip_name"] == "RA_Senior_Backend_Engineer_Shopify.zip"
    assert filenames["resume_pdf_name"] == "RA_Senior_Backend_Engineer_Shopify_resume.pdf"
    assert filenames["resume_md_name"] == "RA_Senior_Backend_Engineer_Shopify_resume.md"


def test_get_application_filenames_fallback(sample_application_kit):
    # Test when match_analysis and inputs are None
    kit_no_match = sample_application_kit.model_copy(update={"match_analysis": None})
    filenames = get_application_filenames(kit_no_match)
    assert filenames["initials"] == "RA"
    # Position resolved from first experience title ("Senior Software Engineer")
    assert filenames["clean_position"] == "Senior_Software_Engineer"
    assert filenames["clean_company"] == "Company"


def test_render_resume_markdown(sample_tailored_resume):
    md = render_resume_markdown(sample_tailored_resume)
    assert "# Ricardo Alvarez" in md
    assert "ricardo@example.com" in md
    assert "## Professional Summary" in md
    assert "## Professional Experience" in md
    assert "### Senior Software Engineer — TechCorp Inc." in md
    assert "## Core Skills" in md
    assert "Python, FastAPI" in md
    assert "## Education" in md
    assert "## Notable Projects" in md
    assert "## Certifications" in md
    assert "## Languages" in md


def test_render_cover_letter_markdown_and_text(sample_cover_letter, sample_tailored_resume):
    md = render_cover_letter_markdown(
        sample_cover_letter, sample_tailored_resume, company="Shopify", position="Senior Engineer"
    )
    assert "# Cover Letter — Ricardo Alvarez" in md
    assert "**Target Company**: Shopify" in md
    assert "**Position Applied**: Senior Engineer" in md
    assert "Dear Shopify Hiring Team," in md
    assert "Sincerely," in md

    txt = render_cover_letter_text(
        sample_cover_letter, sample_tailored_resume, company="Shopify", position="Senior Engineer"
    )
    assert "Ricardo Alvarez" in txt
    assert "RE: Application for Senior Engineer at Shopify" in txt
    assert "Dear Shopify Hiring Team," in txt


def test_render_interview_prep_markdown(sample_interview_questions):
    md = render_interview_prep_markdown(sample_interview_questions, position="Engineer", company="Shopify")
    assert "# Interview Preparation Guide — Engineer at Shopify" in md
    assert "## 1. HR & Behavioral Questions" in md
    assert "Why Shopify?" in md
    assert "## 2. Technical & Domain Questions" in md
    assert "How do you handle distributed transactions" in md
    assert "## 3. Stage-Specific Interview Questions" in md
    assert "Stage: Life Story Screening" in md


def test_render_tips_markdown(sample_tips_section):
    md = render_tips_markdown(sample_tips_section, target_country="Canada")
    assert "Job Search & Interview Success Guide (Canada Market)" in md
    assert "## 1. Workplace & Cultural Norms (Canada)" in md
    assert "## 2. Application & ATS Best Practices" in md


def test_render_company_research_markdown(sample_company_research):
    md = render_company_research_markdown(sample_company_research, company="Shopify")
    assert "# Company Research & Intelligence: Shopify" in md
    assert "## Core Products & Services" in md
    assert "Shopify POS" in md
    assert "## Interview Process (Verified via research)" in md
    assert "Stage 1: Life Story Screening" in md


def test_render_match_analysis_markdown(sample_match_analysis):
    md = render_match_analysis_markdown(sample_match_analysis, position="Engineer", company="Shopify")
    assert "# Profile-Role Match & Gap Analysis" in md
    assert "**Overall Match Fit Score**: 88/100" in md
    assert "## 6-Pillar Completeness Breakdown" in md
    assert "**Experience**: 9/10" in md
    assert "## Verified Strengths" in md
    assert "## Identified Gaps & Mitigation" in md
    assert "Ruby on Rails [LOW impact]" in md


def test_generate_application_zip(sample_application_kit):
    with patch("app.services.pdf.render_resume_pdf", return_value=b"%PDF-1.4 dummy resume"), \
         patch("app.services.pdf.render_cover_letter_pdf", return_value=b"%PDF-1.4 dummy letter"):
        zip_bytes, zip_name = generate_application_zip(sample_application_kit)

    assert zip_name == "RA_Senior_Backend_Engineer_Shopify.zip"
    assert len(zip_bytes) > 0

    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        file_list = zf.namelist()
        assert "RA_Senior_Backend_Engineer_Shopify_resume.pdf" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_resume.md" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_cover_letter.pdf" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_cover_letter.md" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_cover_letter.txt" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_interview_prep.md" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_tips.md" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_company_research.md" in file_list
        assert "RA_Senior_Backend_Engineer_Shopify_match_analysis.md" in file_list

        # Verify content of one entry
        resume_md_content = zf.read("RA_Senior_Backend_Engineer_Shopify_resume.md").decode("utf-8")
        assert "# Ricardo Alvarez" in resume_md_content
