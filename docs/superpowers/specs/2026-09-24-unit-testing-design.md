# Unit Testing Architecture & Test Suite Design

## 1. Overview & Goals
Introduce comprehensive unit and service test coverage across `resume_worker` using `pytest`, `pytest-asyncio`, and `httpx`. The test suite is designed to be:
- **100% Deterministic and Offline**: External API calls (`litellm`, `tavily`, WeasyPrint system rendering) are mocked or safely stubbed.
- **Fast Execution**: Pure logic tests run in sub-milliseconds without disk I/O; file parsing uses in-memory streams (`io.BytesIO`).
- **Environment Managed by `uv`**: Dependencies managed via `requirements-dev.txt` and tests executed via `uv run pytest`.

---

## 2. Dependencies & Tooling

### `requirements-dev.txt`
```text
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

### `pytest.ini`
```ini
[pytest]
asyncio_mode = auto
testpaths = tests
python_files = test_*.py
```

### Execution Commands
- Environment installation: `uv pip install -r requirements-dev.txt`
- Run test suite: `uv run pytest`
- Verbose run with coverage: `uv run pytest -v`

---

## 3. Directory Layout
```
resume_worker/
├── requirements-dev.txt
├── pytest.ini
├── docs/superpowers/specs/2026-09-24-unit-testing-design.md
└── tests/
    ├── __init__.py
    ├── conftest.py               # Shared fixtures for schemas, models, and mock streams
    ├── test_config.py            # Settings validation, defaults, env overrides
    ├── test_jinja_filters.py     # Custom template filters (**bold**, HTML escaping)
    ├── test_schemas.py           # Pydantic schema validation & business logic rules
    ├── test_export.py            # Initials extraction, token sanitization, filenames, Markdown & ZIP export
    ├── test_parser.py            # File extraction (PDF, DOCX, TXT, MD), size limits & extra context builder
    ├── test_research.py          # Tavily search fallback, query generation, parallel execution
    ├── test_pdf.py               # WeasyPrint rendering & graceful 503 handling when system libraries are absent
    ├── test_generator.py         # JSON parsing, LLM retry on schema error, prompt generation & pipeline flow
    └── test_main.py              # In-memory caching, API endpoints (/api/parse-preview, download, error routes)
```

---

## 4. Test Specifications by Module

### 4.1. Shared Fixtures (`tests/conftest.py`)
- `sample_contact_info`: Returns a valid `ContactInfo` model.
- `sample_experience_item`: Flat and grouped `ExperienceItem` models.
- `sample_tailored_resume`: Full valid `TailoredResume` instance covering all sections.
- `sample_company_research`: Populated `CompanyResearch` model with verified interview stages.
- `sample_cover_letter`: Valid `CoverLetter` instance.
- `sample_interview_questions`: Populated `InterviewQuestions` with HR, technical, and stage-specific advice.
- `sample_tips_section`: Complete `TipsSection` model.
- `sample_match_analysis`: Complete `ProfileMatchAnalysis` with 6-pillar `MatchBreakdown`, strengths, gaps, and tailoring strategy.
- `sample_application_kit`: Complete valid `ApplicationKit` instance combining all sub-models.
- `sample_generate_inputs`: Standard `GenerateInputs` instance.

### 4.2. `tests/test_config.py`
- Default configuration values (`TARGET_COUNTRY == "Canada"`, `llm_model`, `max_upload_bytes`, `results_cache_size`, `request_timeout`).
- Caching behavior of `get_settings()` via `@lru_cache`.
- Loading from environment variables with `.env` file settings.

### 4.3. `tests/test_jinja_filters.py`
- `test_bold_converts_double_asterisks`: Transforms `**keyword**` into `<strong>keyword</strong>`.
- `test_bold_escapes_html_preventing_xss`: Escapes `<script>`, `<img>`, and raw HTML tags before wrapping in `<strong>`.
- `test_bold_handles_edge_cases`: Multiple bold blocks on a line, unclosed `**` markers, empty strings, non-string objects.

### 4.4. `tests/test_schemas.py`
- `test_generate_inputs_defaults`: Defaults for `extra_context`, `job_description`, `company`, `seniority`, `position`.
- `test_experience_item_deduplicates_bullets`: Custom validator `_validate_role` removes flat bullets duplicate to group bullets (case- and whitespace-insensitive).
- `test_experience_item_clears_role_tech_stack_when_grouped`: Role-level `tech_stack` reset to `None` when `groups` are present.
- `test_experience_item_requires_bullets_or_groups`: Raises `ValueError` when an experience entry has no bullets and no groups with bullets.
- `test_match_breakdown_categories_property`: `.categories` returns 6 dictionaries (Experience, Skills, Responsibilities, Industry, Education, Other) with names, match objects, and icons.
- `test_profile_match_analysis_defaults`: Default seniority `"Mid-level"`, empty string company/position.
- `test_application_kit_full_validation`: Complete end-to-end model validation.

### 4.5. `tests/test_export.py`
- `test_extract_initials`:
  - Multi-word: `"Ricardo Alvarez"` $\rightarrow$ `"RA"`.
  - Single short word: `"John"` $\rightarrow$ `"JOHN"`.
  - Single long word: `"Engineering"` $\rightarrow$ `"Engineering"`.
  - Empty or punctuation: `""`, `"   "`, `"..."` $\rightarrow$ `"User"`.
- `test_sanitize_token`: Removes non-word characters, collapses underscores, trims ends, falls back to default.
- `test_get_application_filenames`: Position resolution hierarchy (`inputs.position` $\rightarrow$ `match_analysis.position` $\rightarrow$ `experience[0].title` $\rightarrow$ `seniority` $\rightarrow$ `"Position"`), company resolution hierarchy, and output dictionary keys.
- `test_render_markdown_and_text_deliverables`:
  - `render_resume_markdown`: Checks headings, contact info formatting, flat vs grouped experiences, skills, education, projects.
  - `render_cover_letter_markdown` & `render_cover_letter_text`: Formal header formatting, recipient, paragraphs, sign-off.
  - `render_interview_prep_markdown`: HR questions, technical questions, stage-specific questions with STAR method guidance.
  - `render_tips_markdown`: Canadian market norms, ATS tips, adaptation notes.
  - `render_company_research_markdown`: Products, stack, values, and interview process stages.
  - `render_match_analysis_markdown`: 6-pillar breakdown, strengths, gaps with severity badges, tailoring strategy.
- `test_generate_application_zip`: Mocks PDF rendering, validates in-memory zip creation containing all expected filenames and non-empty byte contents.

### 4.6. `tests/test_parser.py`
- `test_decode_text_utf8_and_latin1`: Handles UTF-8 and Latin-1 fallback.
- `test_extract_text_unsupported_extension`: Raises `HTTPException(400)` for disallowed extensions.
- `test_extract_text_size_limit`: Raises `HTTPException(413)` when payload exceeds `max_upload_bytes`.
- `test_extract_text_empty_file`: Raises 400 when empty and `min_chars > 0`, returns empty string when `min_chars == 0`.
- `test_extract_text_min_chars_threshold`: Raises `HTTPException(422)` ("scanned image" error) when text length is below `min_chars`.
- `test_extract_text_plain_text_and_markdown`: Extracts text from `.txt` and `.md` UploadFiles.
- `test_extract_text_docx`: Uses in-memory `docx.Document` to test paragraph extraction.
- `test_extract_text_pdf`: Mocks `pdfplumber.open` and verifies multi-page extraction.
- `test_build_extra_context`: Formats supporting files with `### Source: filename` headers and attaches candidate extra notes.

### 4.7. `tests/test_research.py`
- `test_role_words_extraction`: Truncates to max words and filters non-ASCII characters.
- `test_format_results`: Formats snippets with titles, URLs, and 1200-char truncation.
- `test_build_research_context_no_api_key`: Returns fallback notice when `tavily_api_key` is not configured.
- `test_build_research_context_success`: Mocks `_search_sync`, verifies parallel execution with `asyncio.gather`, company queries, and market norms query.
- `test_build_research_context_resilience`: Recovers gracefully when search queries throw exceptions.

### 4.8. `tests/test_pdf.py`
- `test_render_resume_pdf_success`: Mocks `weasyprint.HTML` and returns PDF bytes.
- `test_render_resume_pdf_missing_system_libs`: Simulates `OSError` on WeasyPrint import/execution and checks for `HTTPException(503)` with Debian/Ubuntu troubleshooting hint.
- `test_render_cover_letter_pdf_success`: Verifies cover letter PDF template rendering with date, company, and position parameters.
- `test_render_cover_letter_pdf_missing_libs`: Simulates `OSError` on cover letter PDF rendering and checks for 503.

### 4.9. `tests/test_generator.py`
- `test_extract_json_variants`: Tests parsing clean JSON, JSON inside markdown code blocks (```` ```json ```` and ```` ``` ````), and trailing whitespace.
- `test_validation_feedback_formatting`: Formats Pydantic `ValidationError` errors into actionable correction hints.
- `test_parse_questions_variants`: Parses question lists from JSON dictionaries, JSON arrays, and numbered/bulleted strings.
- `test_validated_llm_call_success`: Model parsed and validated on first LLM attempt.
- `test_validated_llm_call_retry_recovery`: First attempt returns malformed JSON, second attempt succeeds with validated model.
- `test_validated_llm_call_failure_raises_502`: Two malformed responses raise `HTTPException(502)`.
- `test_call_llm_auth_error`: Mocks `litellm.exceptions.AuthenticationError` and confirms `HTTPException(502)` instructions.
- `test_pipeline_orchestration`: Mocks `analyze_job_match`, `generate_tailored_resume`, and `generate_companion_kit` to verify end-to-end kit assembly in `run_pipeline`.

### 4.10. `tests/test_main.py`
- `test_cache_storage_and_eviction`: Tests FIFO eviction in `_store_result` and `_store_draft` when exceeding `results_cache_size`.
- `test_get_result_and_draft_missing`: Verifies `HTTPException(404)` for missing IDs.
- `test_home_route`: `GET /` returns 200 and loads HTML template.
- `test_api_parse_preview_success`: `POST /api/parse-preview` with an uploaded file returns metrics and extracted preview.
- `test_api_parse_preview_no_file`: `POST /api/parse-preview` without a file returns 400.
- `test_download_endpoints_404_on_missing_id`: Validates 404 response on `/download/{id}/{type}` for missing result IDs.

---

## 5. Implementation Strategy & Next Steps
1. Add `requirements-dev.txt` and `pytest.ini`.
2. Install test dependencies into the `.venv` using `uv pip install -r requirements-dev.txt`.
3. Create `tests/conftest.py` with shared fixtures.
4. Implement Layer 1 tests (pure logic: `test_config.py`, `test_jinja_filters.py`, `test_schemas.py`, `test_export.py`, `test_parser.py`) and verify with `uv run pytest`.
5. Implement Layer 2 tests (mocked services: `test_research.py`, `test_pdf.py`, `test_generator.py`) and verify with `uv run pytest`.
6. Implement Layer 3 tests (FastAPI routes: `test_main.py`) and verify full test suite passes.
