# Unit Testing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a comprehensive, fully offline, and deterministic unit and service test suite covering all modules of `resume_worker` using `pytest`, `pytest-asyncio`, and `uv`.

**Architecture:** The test suite is organized into 3 layers: Layer 1 tests pure domain logic (filters, schema validators, Markdown/ZIP exporters, document text parsers) with zero network calls and sub-millisecond execution; Layer 2 tests service orchestration and resilience (WeasyPrint missing library handling, Tavily API fallbacks, LLM JSON extraction and validation retries) via mocks; Layer 3 validates FastAPI endpoints, in-memory caching/eviction, and file downloads using `TestClient`.

**Tech Stack:** Python 3.12, `pytest>=8.0.0`, `pytest-asyncio>=0.23.0`, `httpx>=0.27.0`, `uv` for environment management, `pydantic>=2.8`, `fastapi>=0.115`.

**Spec:** [`docs/superpowers/specs/2026-09-24-unit-testing-design.md`](file:///home/realvarez/projects/resume_worker/docs/superpowers/specs/2026-09-24-unit-testing-design.md)

## Global Constraints

- All tests must run 100% offline with zero live network calls to OpenAI/LiteLLM or Tavily.
- All file generation and parsing tests must use in-memory bytes (`io.BytesIO`) without temporary disk litter.
- Python environment and execution must use `uv` (`uv pip install -r requirements-dev.txt` and `uv run pytest`).
- Existing business logic and docstrings must remain preserved; do not modify application behavior unless fixing a defect uncovered by testing.

## Review Focus

1. **Grouped Experience Role Tech Stack Duplication**: An `ExperienceItem` with groups must reset `tech_stack` to `None` so tech stacks are not rendered twice.
2. **Duplicate Bullets in Grouped Roles**: Group bullets echoed at the top level of an `ExperienceItem` must be normalized and deduplicated.
3. **Missing System Libraries for WeasyPrint**: `render_resume_pdf` and `render_cover_letter_pdf` must raise HTTP 503 with helpful installation instructions when `weasyprint.HTML` encounters an `OSError`.
4. **Malformed LLM JSON Output**: `_validated_llm_call` must retry once with detailed Pydantic validation error feedback before raising HTTP 502.
5. **Missing or Failed Tavily Research**: `build_research_context` must degrade gracefully to offline messages without crashing the generation pipeline.

---

### Task 1: Testing Infrastructure & Dev Dependencies

**Files:**
- Create: `requirements-dev.txt`
- Create: `pytest.ini`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: Nothing
- Produces: `pytest` test runner environment configured for async test execution via `uv`.

- [ ] **Step 1: Create `requirements-dev.txt`**

```text
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

- [ ] **Step 2: Create `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
```

- [ ] **Step 3: Update `.gitignore` to ignore `.pytest_cache/`**

Ensure `.pytest_cache/` is added to `.gitignore`.

- [ ] **Step 4: Install dependencies using `uv`**

Run: `uv pip install -r requirements-dev.txt`
Expected: Installs `pytest` and `pytest-asyncio` into `.venv`.

- [ ] **Step 5: Verify pytest runs via uv**

Run: `uv run pytest --version`
Expected: `pytest 8.x.x`

- [ ] **Step 6: Commit**

```bash
git add requirements-dev.txt pytest.ini .gitignore
git commit -m "chore: setup pytest configuration and dev dependencies via uv"
```

---

### Task 2: Shared Test Fixtures (`tests/conftest.py`)

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: Models from `app.schemas`
- Produces: Fixtures `sample_contact_info`, `sample_experience_item`, `sample_tailored_resume`, `sample_company_research`, `sample_cover_letter`, `sample_interview_questions`, `sample_tips_section`, `sample_match_analysis`, `sample_application_kit`, `sample_generate_inputs`.

- [ ] **Step 1: Write `tests/__init__.py`**

Empty file marking `tests` as a package.

- [ ] **Step 2: Write `tests/conftest.py` with shared fixtures**

```python
import pytest
from app.schemas import (
    ApplicationKit,
    CategoryMatch,
    CompanyResearch,
    ContactInfo,
    CoverLetter,
    EducationItem,
    ExperienceGroup,
    ExperienceItem,
    GapDetail,
    GenerateInputs,
    InterviewProcess,
    InterviewQuestions,
    InterviewStage,
    MatchBreakdown,
    ProfileMatchAnalysis,
    ProjectItem,
    QuestionAdvice,
    SkillMatch,
    StagePrep,
    TailoredResume,
    TipsSection,
)


@pytest.fixture
def sample_contact_info() -> ContactInfo:
    return ContactInfo(
        name="Ricardo Alvarez",
        email="ricardo@example.com",
        phone="+1 555-0199",
        location="Toronto, ON",
        linkedin="https://linkedin.com/in/ricardo",
        website="https://ricardo.dev",
    )


@pytest.fixture
def sample_experience_item() -> ExperienceItem:
    return ExperienceItem(
        title="Senior Software Engineer",
        company="TechCorp Inc.",
        location="Toronto, ON",
        start_date="2022",
        end_date="Present",
        bullets=[
            "Architected high-throughput microservices using Python and FastAPI, reducing latency by 40%.",
            "Led team of 5 engineers to deliver cloud-native data pipelines.",
        ],
        tech_stack=["Python", "FastAPI", "Docker", "PostgreSQL"],
    )


@pytest.fixture
def sample_grouped_experience_item() -> ExperienceItem:
    return ExperienceItem(
        title="Lead Consultant",
        company="Consulting Partners",
        location="Remote",
        start_date="2020",
        end_date="2022",
        groups=[
            ExperienceGroup(
                label="Enterprise Banking Client",
                bullets=["Built real-time fraud detection engine handling 10k TPS."],
                tech_stack=["Python", "Kafka"],
            ),
            ExperienceGroup(
                label="Retail Client",
                bullets=["Automated order fulfillment reducing manual labor by 30%."],
                tech_stack=["FastAPI", "Redis"],
            ),
        ],
    )


@pytest.fixture
def sample_tailored_resume(sample_contact_info, sample_experience_item) -> TailoredResume:
    return TailoredResume(
        contact=sample_contact_info,
        professional_summary="Results-driven Senior Software Engineer with 8+ years building distributed backend systems in Canadian tech.",
        experience=[sample_experience_item],
        education=[
            EducationItem(
                degree="B.S. in Computer Science",
                institution="University of Toronto",
                location="Toronto, ON",
                graduation_date="2018",
                details=["Dean's List", "Specialization in Distributed Systems"],
            )
        ],
        core_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "CI/CD"],
        projects=[
            ProjectItem(
                name="CloudQueue",
                description="Distributed message broker built in Python.",
                technologies=["Python", "Redis", "Asyncio"],
            )
        ],
        certifications=["AWS Certified Solutions Architect"],
        languages=["English (Fluent)", "Spanish (Native)"],
    )


@pytest.fixture
def sample_company_research() -> CompanyResearch:
    return CompanyResearch(
        overview="Shopify is a leading global commerce platform empowering millions of merchants.",
        products_and_services=["Online storefronts", "Shopify POS", "Shopify Payments"],
        tech_stack=["Ruby on Rails", "Python", "React", "Kafka", "Google Cloud"],
        culture_and_values=["Be a constant learner", "Default to open", "Make commerce better"],
        recent_news=["Expanded AI merchant tools and enterprise offerings."],
        role_importance="Critical role to enhance platform scalability and merchant checkout speed.",
        interview_process=InterviewProcess(
            known_from_research=True,
            stages=[
                InterviewStage(
                    stage_name="Life Story Screening",
                    description="45-minute recruiter conversation on career trajectory and values.",
                    what_to_expect="Focus on self-reflection, motivations, and impact.",
                ),
                InterviewStage(
                    stage_name="Technical Deep Dive",
                    description="System design and coding session with senior engineering peers.",
                    what_to_expect="Pair programming in your language of choice.",
                ),
            ],
        ),
    )


@pytest.fixture
def sample_cover_letter() -> CoverLetter:
    return CoverLetter(
        greeting="Dear Shopify Hiring Team,",
        body=[
            "I am excited to apply for the Senior Backend Engineer position at Shopify.",
            "With over 8 years of engineering experience developing high-scale systems in Canada, I bring deep expertise in cloud architectures.",
            "I look forward to discussing how my background aligns with Shopify's mission.",
        ],
        closing="Sincerely,",
    )


@pytest.fixture
def sample_interview_questions() -> InterviewQuestions:
    return InterviewQuestions(
        hr_questions=[
            QuestionAdvice(
                question="Why Shopify?",
                why_they_ask="To assess alignment with commerce mission and merchant empathy.",
                answer_tips="Emphasize admiration for merchant empowerment and scale.",
            )
        ],
        technical_questions=[
            QuestionAdvice(
                question="How do you handle distributed transactions across microservices?",
                why_they_ask="Evaluates distributed systems architecture knowledge.",
                answer_tips="Discuss Saga pattern, two-phase commits, and idempotency keys.",
            )
        ],
        stage_specific=[
            StagePrep(
                stage_name="Life Story Screening",
                questions=[
                    QuestionAdvice(
                        question="Tell me about your career journey and biggest turning point.",
                        answer_tips="Follow chronological arc highlighting intentional career decisions.",
                    )
                ],
            )
        ],
    )


@pytest.fixture
def sample_tips_section() -> TipsSection:
    return TipsSection(
        country_culture_tips=[
            "Canadian workplaces value collaborative consensus and egalitarian communication.",
            "Avoid listing personal details like photo, marital status, or age.",
        ],
        application_best_practices=[
            "Submit ATS-friendly single-column format.",
            "Quantify results using Canadian spelling conventions where applicable.",
        ],
        interview_day_tips=["Test webcam lighting and prepare questions about team culture."],
        resume_adaptation_notes=[
            "Restructured experience bullets to emphasize measurable metrics and CAR framework."
        ],
    )


@pytest.fixture
def sample_match_analysis() -> ProfileMatchAnalysis:
    return ProfileMatchAnalysis(
        match_score=88,
        company="Shopify",
        seniority="Senior",
        position="Senior Backend Engineer",
        summary="Candidate shows strong alignment with Shopify's high-throughput backend needs.",
        breakdown=MatchBreakdown(
            overall_reasoning="Strong technical alignment with Python and distributed architectures.",
            experience=CategoryMatch(score=9, explanation="8+ years exceeding 5+ year requirement."),
            skills=CategoryMatch(score=9, explanation="Strong Python and cloud data systems experience."),
            responsibilities=CategoryMatch(score=8, explanation="Proven tech leadership and architecture."),
            industry=CategoryMatch(score=8, explanation="Solid e-commerce and fintech adjacency."),
            education=CategoryMatch(score=9, explanation="BS in Computer Science aligns with criteria."),
            other=CategoryMatch(score=9, explanation="Canadian market experience and strong communication."),
        ),
        strengths=[
            SkillMatch(
                skill="Python & Microservices",
                category="Core Skill",
                evidence_found="Built high-throughput services reducing latency by 40%.",
            )
        ],
        gaps=[
            GapDetail(
                requirement="Ruby on Rails",
                severity="low",
                mitigation_tip="Highlight quick mastery of backend languages and OOP frameworks.",
            )
        ],
        tailoring_strategy=[
            "Emphasize distributed systems scalability and latency reduction metrics.",
            "Frame backend experience around high-volume transaction processing.",
        ],
    )


@pytest.fixture
def sample_application_kit(
    sample_match_analysis,
    sample_tailored_resume,
    sample_company_research,
    sample_cover_letter,
    sample_interview_questions,
    sample_tips_section,
) -> ApplicationKit:
    return ApplicationKit(
        match_analysis=sample_match_analysis,
        tailored_resume=sample_tailored_resume,
        company_research=sample_company_research,
        cover_letter=sample_cover_letter,
        interview_prep=sample_interview_questions,
        tips=sample_tips_section,
    )


@pytest.fixture
def sample_generate_inputs() -> GenerateInputs:
    return GenerateInputs(
        resume_text="Ricardo Alvarez\nSoftware Engineer with 8 years experience building backend systems in Python.",
        extra_context="Won company hackathon in 2023 for AI developer tooling.",
        job_description="Seeking a Senior Backend Engineer to build scalable microservices.",
        company="Shopify",
        seniority="Senior",
        position="Senior Backend Engineer",
    )
```

- [ ] **Step 3: Run pytest to verify conftest loads cleanly**

Run: `uv run pytest tests/conftest.py`
Expected: 0 tests collected, 0 errors.

- [ ] **Step 4: Commit**

```bash
git add tests/__init__.py tests/conftest.py
git commit -m "test: create conftest with shared domain fixtures"
```

---

### Task 3: Unit Tests for Config & Jinja Filters

**Files:**
- Create: `tests/test_config.py`
- Create: `tests/test_jinja_filters.py`

**Interfaces:**
- Consumes: `app.config.Settings`, `app.config.get_settings`, `app.config.TARGET_COUNTRY`, `app.jinja_filters.bold`
- Produces: Test verification for settings defaults, caching, and custom markdown bold filter.

- [ ] **Step 1: Write `tests/test_config.py`**

```python
from app.config import TARGET_COUNTRY, Settings, get_settings


def test_target_country_is_canada():
    assert TARGET_COUNTRY == "Canada"


def test_default_settings():
    settings = Settings()
    assert settings.llm_model == "gemini/gemini-3.8-flash"
    assert settings.llm_temperature == 0.4
    assert settings.max_upload_bytes == 5 * 1024 * 1024
    assert settings.results_cache_size == 20
    assert settings.request_timeout == 300
    assert settings.tavily_max_results == 4


def test_get_settings_is_cached():
    s1 = get_settings()
    s2 = get_settings()
    assert s1 is s2
```

- [ ] **Step 2: Write `tests/test_jinja_filters.py`**

```python
from markupsafe import Markup
from app.jinja_filters import bold


def test_bold_converts_double_asterisks():
    result = bold("This is **bold** text")
    assert str(result) == "This is <strong>bold</strong> text"
    assert isinstance(result, Markup)


def test_bold_escapes_html_preventing_xss():
    raw = "<script>alert('xss')</script> and **safe bold**"
    result = bold(raw)
    assert "<script>" not in str(result)
    assert "&lt;script&gt;alert(&#39;xss&#39;)&lt;/script&gt;" in str(result)
    assert "<strong>safe bold</strong>" in str(result)


def test_bold_multiple_occurrences():
    raw = "**One** and **Two** and **Three**"
    result = bold(raw)
    assert str(result) == "<strong>One</strong> and <strong>Two</strong> and <strong>Three</strong>"


def test_bold_unmatched_asterisks():
    raw = "This is **unmatched asterisk text"
    result = bold(raw)
    assert str(result) == "This is **unmatched asterisk text"


def test_bold_empty_and_non_string():
    assert str(bold("")) == ""
    assert str(bold(12345)) == "12345"
```

- [ ] **Step 3: Run pytest on config and jinja filters**

Run: `uv run pytest tests/test_config.py tests/test_jinja_filters.py -v`
Expected: All tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_config.py tests/test_jinja_filters.py
git commit -m "test: add unit tests for config and jinja filters"
```

---

### Task 4: Unit Tests for Schemas & Model Validators (`tests/test_schemas.py`)

**Files:**
- Create: `tests/test_schemas.py`

**Interfaces:**
- Consumes: Models from `app.schemas`
- Produces: Test coverage for schema defaults, role-validation logic, and category match properties.

- [ ] **Step 1: Write `tests/test_schemas.py`**

```python
import pytest
from pydantic import ValidationError
from app.schemas import (
    ExperienceGroup,
    ExperienceItem,
    GenerateInputs,
    MatchBreakdown,
    CategoryMatch,
    ProfileMatchAnalysis,
)


def test_generate_inputs_defaults():
    inputs = GenerateInputs(resume_text="My Resume")
    assert inputs.resume_text == "My Resume"
    assert inputs.extra_context == ""
    assert inputs.job_description == ""
    assert inputs.company == ""
    assert inputs.seniority == ""
    assert inputs.position == ""


def test_experience_item_deduplicates_bullets():
    group = ExperienceGroup(
        label="Client A",
        bullets=["Led development of cloud pipeline.", "Optimized SQL queries by 30%."],
    )
    # Role-level bullets contain an exact duplicate (with varied whitespace/casing) and a unique bullet
    role = ExperienceItem(
        title="Software Engineer",
        company="Acme Corp",
        start_date="2021",
        end_date="Present",
        bullets=[
            "  LED DEVELOPMENT OF CLOUD PIPELINE.  ",
            "Mentored junior engineers.",
        ],
        groups=[group],
    )
    # The duplicate should be stripped, keeping only the unique bullet
    assert len(role.bullets) == 1
    assert role.bullets[0] == "Mentored junior engineers."


def test_experience_item_clears_role_tech_stack_when_grouped():
    group = ExperienceGroup(
        label="Client A",
        bullets=["Engineered API."],
        tech_stack=["Python", "FastAPI"],
    )
    role = ExperienceItem(
        title="Consultant",
        company="Acme Corp",
        start_date="2021",
        end_date="Present",
        groups=[group],
        tech_stack=["Python", "Docker"],  # Should be cleared because groups exist
    )
    assert role.tech_stack is None


def test_experience_item_requires_bullets_or_groups():
    with pytest.raises(ValidationError, match="an experience entry needs bullets or groups with bullets"):
        ExperienceItem(
            title="Dev",
            company="Acme",
            start_date="2020",
            end_date="2021",
            bullets=[],
            groups=[],
        )


def test_match_breakdown_categories_property():
    cat = CategoryMatch(score=8, explanation="Solid performance")
    breakdown = MatchBreakdown(
        overall_reasoning="Good match",
        experience=cat,
        skills=cat,
        education=cat,
        responsibilities=cat,
        industry=cat,
        other=cat,
    )
    cats = breakdown.categories
    assert len(cats) == 6
    names = [c["name"] for c in cats]
    assert names == ["Experience", "Skills", "Responsibilities", "Industry", "Education", "Other"]
    assert all("icon" in c and "match" in c for c in cats)


def test_profile_match_analysis_defaults():
    analysis = ProfileMatchAnalysis(
        match_score=85,
        summary="Great candidate",
        strengths=[],
        gaps=[],
        tailoring_strategy=[],
    )
    assert analysis.seniority == "Mid-level"
    assert analysis.company == ""
    assert analysis.position == ""
```

- [ ] **Step 2: Run pytest on schemas**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_schemas.py
git commit -m "test: add schema validation and business logic tests"
```

---

### Task 5: Unit Tests for Export & Formatting Logic (`tests/test_export.py`)

**Files:**
- Create: `tests/test_export.py`

**Interfaces:**
- Consumes: Exporters from `app.services.export`, fixtures from `conftest`
- Produces: Test coverage for initial extraction, token sanitization, Markdown rendering, and ZIP package creation.

- [ ] **Step 1: Write `tests/test_export.py`**

```python
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
    assert "**Position Applied**: Senior Engineer"
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
    assert "Experience: 9/10" in md
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
```

- [ ] **Step 2: Run pytest on exports**

Run: `uv run pytest tests/test_export.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_export.py
git commit -m "test: add tests for export formatting and zip bundle generation"
```

---

### Task 6: Unit Tests for Document Parser & Context Builder (`tests/test_parser.py`)

**Files:**
- Create: `tests/test_parser.py`

**Interfaces:**
- Consumes: `app.services.parser.extract_text`, `app.services.parser.build_extra_context`, `app.services.parser._decode_text`
- Produces: Test verification for file uploads (TXT, MD, DOCX, PDF), size limits, and fallback decoding.

- [ ] **Step 1: Write `tests/test_parser.py`**

```python
import io
from unittest.mock import MagicMock, patch
import docx
import pytest
from fastapi import HTTPException, UploadFile
from app.services.parser import _decode_text, build_extra_context, extract_text


def _make_upload(filename: str, content: bytes) -> UploadFile:
    return UploadFile(filename=filename, file=io.BytesIO(content))


def test_decode_text_utf8_and_latin1():
    assert _decode_text(b"Hello world") == "Hello world"
    latin1_bytes = "Café".encode("latin-1")
    assert _decode_text(latin1_bytes) == "Café"


def test_extract_text_empty_upload():
    assert extract_text(None) == ""
    upload = UploadFile(filename="", file=io.BytesIO(b""))
    assert extract_text(upload) == ""


def test_extract_text_unsupported_extension():
    upload = _make_upload("malicious.exe", b"binary")
    with pytest.raises(HTTPException) as exc:
        extract_text(upload)
    assert exc.value.status_code == 400
    assert "Unsupported file type '.exe'" in exc.value.detail


def test_extract_text_max_upload_size():
    upload = _make_upload("large.txt", b"A" * (6 * 1024 * 1024))
    with pytest.raises(HTTPException) as exc:
        extract_text(upload)
    assert exc.value.status_code == 413
    assert "too large" in exc.value.detail


def test_extract_text_empty_file_min_chars():
    upload = _make_upload("empty.txt", b"")
    assert extract_text(upload, min_chars=0) == ""

    upload2 = _make_upload("empty.txt", b"")
    with pytest.raises(HTTPException) as exc:
        extract_text(upload2, min_chars=50)
    assert exc.value.status_code == 400
    assert "Uploaded file is empty" in exc.value.detail


def test_extract_text_min_chars_threshold():
    upload = _make_upload("short.txt", b"Too short")
    with pytest.raises(HTTPException) as exc:
        extract_text(upload, min_chars=50)
    assert exc.value.status_code == 422
    assert "Could not extract enough readable text" in exc.value.detail


def test_extract_text_txt_and_md():
    txt_upload = _make_upload("resume.txt", b"Senior Python Developer with 10 years experience.")
    assert extract_text(txt_upload) == "Senior Python Developer with 10 years experience."

    md_upload = _make_upload("resume.md", b"# Jane Doe\nSoftware Engineer")
    assert extract_text(md_upload) == "# Jane Doe\nSoftware Engineer"


def test_extract_text_docx():
    doc = docx.Document()
    doc.add_paragraph("Paragraph 1: Summary")
    doc.add_paragraph("Paragraph 2: Experience")
    stream = io.BytesIO()
    doc.save(stream)

    upload = _make_upload("resume.docx", stream.getvalue())
    extracted = extract_text(upload)
    assert "Paragraph 1: Summary" in extracted
    assert "Paragraph 2: Experience" in extracted


def test_extract_text_pdf():
    # Mock pdfplumber to avoid binary font/pdf dependency
    mock_page1 = MagicMock()
    mock_page1.extract_text.return_value = "Page 1 Content"
    mock_page2 = MagicMock()
    mock_page2.extract_text.return_value = "Page 2 Content"

    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page1, mock_page2]
    mock_pdf.__enter__.return_value = mock_pdf

    with patch("pdfplumber.open", return_value=mock_pdf):
        upload = _make_upload("resume.pdf", b"%PDF-1.4 dummy bytes")
        extracted = extract_text(upload)
        assert extracted == "Page 1 Content\nPage 2 Content"


def test_build_extra_context():
    f1 = _make_upload("cert.txt", b"AWS Solutions Architect Certified 2023")
    f2 = _make_upload("awards.md", b"Top Engineer Q3 2022")
    notes = "Looking for remote roles in Canada only."

    context = build_extra_context(supporting_files=[f1, f2], extra_notes=notes)
    assert "### Source: cert.txt\nAWS Solutions Architect Certified 2023" in context
    assert "### Source: awards.md\nTop Engineer Q3 2022" in context
    assert "### Candidate Extra Notes & Highlights\nLooking for remote roles in Canada only." in context


def test_build_extra_context_empty():
    assert build_extra_context([], "") == ""
    assert build_extra_context(None, None) == ""
```

- [ ] **Step 2: Run pytest on parser**

Run: `uv run pytest tests/test_parser.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_parser.py
git commit -m "test: add tests for text parser and context builder"
```

---

### Task 7: Unit & Resilience Tests for Research Service (`tests/test_research.py`)

**Files:**
- Create: `tests/test_research.py`

**Interfaces:**
- Consumes: `app.services.research.build_research_context`, `app.services.research._role_words`, `app.services.research._format_results`
- Produces: Test coverage for Tavily search fallback, formatting, and query resilience.

- [ ] **Step 1: Write `tests/test_research.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.services.research import (
    _format_results,
    _role_words,
    build_research_context,
)


def test_role_words_extraction():
    jd = "Senior Python Backend Engineer building distributed cloud systems at scale"
    assert _role_words(jd, max_words=4) == "Senior Python Backend Engineer"

    # Non-ascii filtered
    jd_mixed = "Senior Engineer 🚀 with Rust & Go skills"
    assert "🚀" not in _role_words(jd_mixed)


def test_format_results():
    results = [
        {"title": "Shopify Tech Blog", "url": "https://shopify.engineering", "content": "Our Kafka architecture"},
        {"title": "Glassdoor", "url": "", "content": "Great engineering culture"},
    ]
    formatted = _format_results("TECH_STACK", results)
    assert "### TECH_STACK" in formatted
    assert "- Shopify Tech Blog (https://shopify.engineering): Our Kafka architecture" in formatted
    assert "- Glassdoor: Great engineering culture" in formatted


@pytest.mark.asyncio
async def test_build_research_context_no_api_key():
    with patch("app.services.research.get_settings") as mock_settings:
        mock_settings.return_value.tavily_api_key = None
        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH: unavailable (no TAVILY_API_KEY configured)" in context


@pytest.mark.asyncio
async def test_build_research_context_success():
    fake_results = [
        {"title": "Overview", "url": "https://example.com", "content": "E-commerce platform"}
    ]

    with patch("app.services.research.get_settings") as mock_settings, \
         patch("app.services.research._search_sync", return_value=fake_results):
        mock_settings.return_value.tavily_api_key = "fake-key"
        mock_settings.return_value.tavily_max_results = 2

        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH RESULTS (source snippets gathered just now for 'Shopify'):" in context
        assert "Overview (https://example.com): E-commerce platform" in context


@pytest.mark.asyncio
async def test_build_research_context_all_queries_fail():
    with patch("app.services.research.get_settings") as mock_settings, \
         patch("app.services.research._search_sync", side_effect=RuntimeError("Network error")):
        mock_settings.return_value.tavily_api_key = "fake-key"

        context = await build_research_context(company="Shopify", job_description="Developer")
        assert "WEB RESEARCH: all queries failed" in context
```

- [ ] **Step 2: Run pytest on research service**

Run: `uv run pytest tests/test_research.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_research.py
git commit -m "test: add tests for company research service and graceful fallbacks"
```

---

### Task 8: Unit & Fallback Tests for PDF Service (`tests/test_pdf.py`)

**Files:**
- Create: `tests/test_pdf.py`

**Interfaces:**
- Consumes: `app.services.pdf.render_resume_pdf`, `app.services.pdf.render_cover_letter_pdf`
- Produces: Test coverage for WeasyPrint rendering and 503 error handling on missing system libraries.

- [ ] **Step 1: Write `tests/test_pdf.py`**

```python
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
    with patch.dict("sys.modules", {"weasyprint": None}):
        # Simulating ImportError or OSError on import
        with patch("app.services.pdf.templates.get_template"):
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
```

- [ ] **Step 2: Run pytest on pdf service**

Run: `uv run pytest tests/test_pdf.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_pdf.py
git commit -m "test: add tests for pdf rendering and system library error handling"
```

---

### Task 9: Unit Tests for Generator Pipeline (`tests/test_generator.py`)

**Files:**
- Create: `tests/test_generator.py`

**Interfaces:**
- Consumes: Functions from `app.services.generator`
- Produces: Test coverage for JSON extraction, validation retry logic, question parsing, and multi-stage orchestration.

- [ ] **Step 1: Write `tests/test_generator.py`**

```python
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.services.generator import (
    _extract_json,
    _parse_questions,
    _validation_feedback,
    _validated_llm_call,
    generate_clarifying_questions,
    run_pipeline,
)
from app.schemas import ClarifyingQuestions, GenerateInputs, ProfileMatchAnalysis


class SimpleModel(BaseModel):
    name: str
    score: int = Field(ge=0)


def test_extract_json():
    # Plain JSON
    assert _extract_json('{"key": "value"}') == {"key": "value"}

    # Markdown fence with json
    fenced_json = "```json\n{\"key\": \"value\"}\n```"
    assert _extract_json(fenced_json) == {"key": "value"}

    # Markdown fence without language
    fenced_plain = "```\n{\"key\": \"value\"}\n```"
    assert _extract_json(fenced_plain) == {"key": "value"}


def test_parse_questions():
    # Case 1: JSON dict matching ClarifyingQuestions
    json_dict = json.dumps({"questions": ["What scale of data?", "Team size?"]})
    assert _parse_questions(json_dict) == ["What scale of data?", "Team size?"]

    # Case 2: JSON list
    json_list = json.dumps(["What scale of data?", "Team size?"])
    assert _parse_questions(json_list) == ["What scale of data?", "Team size?"]

    # Case 3: Markdown numbered list
    md_list = "1. What was the latency reduction achieved?\n2. How many direct reports did you mentor?"
    questions = _parse_questions(md_list)
    assert len(questions) == 2
    assert "What was the latency reduction achieved?" in questions[0]


@pytest.mark.asyncio
async def test_validated_llm_call_success():
    with patch("app.services.generator._call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.return_value = '{"name": "Alice", "score": 95}'
        result = await _validated_llm_call(
            [{"role": "user", "content": "test"}],
            SimpleModel,
            label="test model",
        )
        assert isinstance(result, SimpleModel)
        assert result.name == "Alice"
        assert result.score == 95


@pytest.mark.asyncio
async def test_validated_llm_call_retry_success():
    with patch("app.services.generator._call_llm", new_callable=AsyncMock) as mock_call:
        # First call returns invalid schema (score is negative, violates ge=0)
        # Second call returns valid schema
        mock_call.side_effect = [
            '{"name": "Alice", "score": -5}',
            '{"name": "Alice", "score": 90}',
        ]
        result = await _validated_llm_call(
            [{"role": "user", "content": "test"}],
            SimpleModel,
            label="test model",
        )
        assert isinstance(result, SimpleModel)
        assert result.score == 90
        assert mock_call.call_count == 2


@pytest.mark.asyncio
async def test_validated_llm_call_failure_raises_502():
    with patch("app.services.generator._call_llm", new_callable=AsyncMock) as mock_call:
        # Both calls return invalid JSON
        mock_call.return_value = 'INVALID JSON NOT PARSEABLE'
        with pytest.raises(HTTPException) as exc:
            await _validated_llm_call(
                [{"role": "user", "content": "test"}],
                SimpleModel,
                label="test model",
            )
        assert exc.value.status_code == 502
        assert "non-conforming answer twice" in exc.value.detail


@pytest.mark.asyncio
async def test_generate_clarifying_questions_graceful_on_error(sample_generate_inputs):
    with patch("app.services.generator._call_llm", new_callable=AsyncMock) as mock_call:
        mock_call.side_effect = RuntimeError("LLM error")
        questions = await generate_clarifying_questions(sample_generate_inputs)
        assert questions == []


@pytest.mark.asyncio
async def test_run_pipeline_orchestration(
    sample_generate_inputs,
    sample_match_analysis,
    sample_tailored_resume,
    sample_company_research,
    sample_cover_letter,
    sample_interview_questions,
    sample_tips_section,
):
    with patch("app.services.generator.analyze_job_match", new_callable=AsyncMock) as mock_match, \
         patch("app.services.generator.generate_tailored_resume", new_callable=AsyncMock) as mock_resume, \
         patch("app.services.generator.generate_companion_kit", new_callable=AsyncMock) as mock_companion, \
         patch("app.services.research.build_research_context", new_callable=AsyncMock) as mock_research:

        mock_match.return_value = sample_match_analysis
        mock_resume.return_value = sample_tailored_resume
        mock_research.return_value = "Research context notes"

        from app.schemas import CompanionKit
        mock_companion.return_value = CompanionKit(
            company_research=sample_company_research,
            cover_letter=sample_cover_letter,
            interview_prep=sample_interview_questions,
            tips=sample_tips_section,
        )

        kit, research = await run_pipeline(sample_generate_inputs)
        assert kit.match_analysis == sample_match_analysis
        assert kit.tailored_resume == sample_tailored_resume
        assert kit.company_research == sample_company_research
        assert kit.cover_letter == sample_cover_letter
        assert research == "Research context notes"
```

- [ ] **Step 2: Run pytest on generator**

Run: `uv run pytest tests/test_generator.py -v`
Expected: All tests PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_generator.py
git commit -m "test: add tests for generator pipeline, retries and json parsing"
```

---

### Task 10: Route & Session State Tests (`tests/test_main.py`)

**Files:**
- Create: `tests/test_main.py`

**Interfaces:**
- Consumes: `app.main.app`, `app.main._store_result`, `app.main._get_result`, `app.main._store_draft`, `app.main._get_draft`, `starlette.testclient.TestClient`
- Produces: Test coverage for web routes, in-memory cache eviction, parse preview, and download endpoints.

- [ ] **Step 1: Write `tests/test_main.py`**

```python
import io
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import (
    _drafts,
    _get_draft,
    _get_result,
    _results,
    _store_draft,
    _store_result,
    app,
)
from app.schemas import GenerateInputs


@pytest.fixture
def client():
    return TestClient(app)


def test_cache_storage_and_fifo_eviction(sample_generate_inputs, sample_application_kit):
    _results.clear()
    with patch("app.main.get_settings") as mock_settings:
        mock_settings.return_value.results_cache_size = 2

        id1 = _store_result(sample_generate_inputs, sample_application_kit)
        id2 = _store_result(sample_generate_inputs, sample_application_kit)
        assert len(_results) == 2

        # Storing a 3rd should evict id1
        id3 = _store_result(sample_generate_inputs, sample_application_kit)
        assert len(_results) == 2
        assert id1 not in _results
        assert id2 in _results
        assert id3 in _results


def test_get_result_and_draft_not_found():
    with pytest.raises(HTTPException) as exc1:
        _get_result("nonexistent_id")
    assert exc1.value.status_code == 404

    with pytest.raises(HTTPException) as exc2:
        _get_draft("nonexistent_draft")
    assert exc2.value.status_code == 404


def test_home_page_route(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Resume Worker" in response.text or "Canada" in response.text


def test_api_parse_preview_success(client):
    file_content = b"Alex Developer\nSoftware Engineer with 5 years experience in Python and AWS."
    files = {"file": ("resume.txt", io.BytesIO(file_content), "text/plain")}
    response = client.post("/api/parse-preview", files=files)
    assert response.status_code == 200
    data = response.json()
    assert data["ok"] is True
    assert data["filename"] == "resume.txt"
    assert data["char_count"] > 0
    assert data["word_count"] > 0


def test_api_parse_preview_no_file(client):
    response = client.post("/api/parse-preview", files={})
    assert response.status_code == 400
    data = response.json()
    assert data["ok"] is False


def test_download_endpoints_404_on_missing_id(client):
    response = client.get("/download/invalid_id/resume-pdf")
    assert response.status_code == 404

    response_zip = client.get("/download/invalid_id/zip")
    assert response_zip.status_code == 404
```

- [ ] **Step 2: Run pytest on all tests**

Run: `uv run pytest -v`
Expected: 100% PASS across all test files.

- [ ] **Step 3: Commit**

```bash
git add tests/test_main.py
git commit -m "test: add route, cache eviction and download tests"
```

---

## Plan Self-Review Checklist
- [x] **Spec coverage**: Covers `conftest.py`, `test_config.py`, `test_jinja_filters.py`, `test_schemas.py`, `test_export.py`, `test_parser.py`, `test_research.py`, `test_pdf.py`, `test_generator.py`, `test_main.py`.
- [x] **No Placeholders**: Every task contains full test implementations and exact pytest commands.
- [x] **Deterministic & Offline**: All network calls and external binaries are mocked.
- [x] **Environment consistency**: Explicitly uses `uv run pytest`.
