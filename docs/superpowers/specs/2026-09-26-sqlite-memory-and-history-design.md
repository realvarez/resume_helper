# Design Spec: SQLite Memory, Persistence, and Application History

**Date:** 2026-09-26  
**Status:** Approved for Implementation  
**Topic:** SQLite Memory Layer, Checkpoint Persistence, Web Research Caching, Candidate Fact Memory, and Application History UI  

---

## 1. Overview & Motivation

Currently, `resume_worker` stores all drafts, match analyses, candidate inputs, and completed application kits exclusively in in-memory Python dictionaries (`OrderedDict`) in `app/main.py`. This ephemeral setup presents several limitations:

1. **Data Loss on Restart**: Any application, refined résumé, or active draft is permanently lost when the process terminates or restarts.
2. **Redundant Web Research**: Tavily API search is called repeatedly for the same company, consuming external API rate limits and adding 2–3s of latency per run.
3. **No Candidate Memory**: Answers to clarifying intake questions (e.g., team size, revenue metrics, KPIs) are discarded at the end of the session rather than enriching future applications.
4. **No History Tracking**: Candidates cannot review past applications, compare match scores over time, re-download deliverables, or reuse past applications as templates.

This specification introduces a zero-dependency SQLite storage repository (`app/services/storage.py`), connects it to the generation and research pipelines, and provides an application history dashboard (`/history`).

---

## 2. Goals & Non-Goals

### Goals
- **Persistence Across Restarts**: Safely store drafts, completed kits, and refined versions in an embedded SQLite database.
- **Zero New Dependencies**: Use Python's standard library `sqlite3` with WAL mode for fast concurrent operations.
- **Web Research Caching**: Cache Tavily company research with a 14-day TTL to save API credits and reduce latency.
- **Candidate Fact Memory**: Accumulate answered intake questions and inject them into future résumé generation prompts.
- **Application History Dashboard**: Provide a `/history` route with search, filtering, score badges, 1-click downloads, and deletion.
- **Full Backward Compatibility**: Keep all existing routes, download endpoints, and Pydantic validation contracts 100% working.

### Non-Goals
- Multi-user authentication or multi-tenant user account isolation (remains a single-user local tool).
- Heavy ORM or migration engines (no SQLAlchemy or Alembic; schema evolution is handled through JSON payloads).
- Cloud database connectors (Postgres/MySQL are out of scope; SQLite is optimal for local use).

---

## 3. Architecture & Data Model

### 3.1 Database Location & Configuration
- **File Path**: `data/resume_worker.db`
- **Directory**: `data/` is automatically created if absent and gitignored in `.gitignore`.
- **Connection Configuration**:
  ```sql
  PRAGMA journal_mode = WAL;
  PRAGMA synchronous = NORMAL;
  PRAGMA foreign_keys = ON;
  PRAGMA busy_timeout = 5000;
  ```

### 3.2 Database Schema

```sql
-- 1. In-progress drafts from Stage 1 (Match Analysis)
CREATE TABLE IF NOT EXISTS drafts (
    draft_id TEXT PRIMARY KEY,
    company TEXT,
    position TEXT,
    seniority TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    inputs_json TEXT NOT NULL,
    match_analysis_json TEXT,
    questions_json TEXT
);

-- 2. Completed Application Kits and refined versions
CREATE TABLE IF NOT EXISTS applications (
    result_id TEXT PRIMARY KEY,
    draft_id TEXT,
    company TEXT NOT NULL,
    position TEXT NOT NULL,
    seniority TEXT NOT NULL,
    match_score INTEGER,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    inputs_json TEXT NOT NULL,
    kit_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_applications_created ON applications(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);

-- 3. Cache for Tavily web research
CREATE TABLE IF NOT EXISTS company_research_cache (
    company_normalized TEXT PRIMARY KEY,
    company_display TEXT NOT NULL,
    research_markdown TEXT NOT NULL,
    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 4. Accumulated Candidate Memory (facts & Q&A pairs from intake)
CREATE TABLE IF NOT EXISTS candidate_facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 4. Storage Repository API (`app/services/storage.py`)

A dedicated module encapsulating all SQLite operations:

```python
class StorageRepository:
    def __init__(self, db_path: str | Path | None = None):
        ...

    # Draft Operations
    def save_draft(
        self,
        draft_id: str,
        inputs: GenerateInputs,
        match_analysis: ProfileMatchAnalysis | None,
        questions: list[str] | None = None,
    ) -> None: ...

    def get_draft(self, draft_id: str) -> dict | None: ...
    def delete_draft(self, draft_id: str) -> bool: ...

    # Application Kit Operations
    def save_application(
        self,
        result_id: str,
        inputs: GenerateInputs,
        kit: ApplicationKit,
        draft_id: str | None = None,
    ) -> None: ...

    def get_application(self, result_id: str) -> dict | None: ...
    def update_application_kit(self, result_id: str, kit: ApplicationKit) -> bool: ...
    def list_applications(self, limit: int = 100) -> list[dict]: ...
    def delete_application(self, result_id: str) -> bool: ...

    # Web Research Cache
    def get_cached_research(self, company: str, max_age_days: int = 14) -> str | None: ...
    def cache_research(self, company: str, research_markdown: str) -> None: ...

    # Candidate Memory Facts
    def add_candidate_facts(self, qa_pairs: list[tuple[str, str]]) -> None: ...
    def get_all_candidate_facts() -> list[tuple[str, str]]: ...
```

---

## 5. Pipeline & Service Integrations

### 5.1 `app/main.py`
- Replace `_results` and `_drafts` dictionaries with calls to a global `storage` singleton:
  - `_store_result(...)` -> `storage.save_application(...)`
  - `_get_result(...)` -> `storage.get_application(...)`
  - `_store_draft(...)` -> `storage.save_draft(...)`
  - `_get_draft(...)` -> `storage.get_draft(...)`
- When `POST /refine/{result_id}` runs:
  - Save updated kit via `storage.update_application_kit(result_id, stored["kit"])`.
- When `POST /generate-from-match/{draft_id}` runs:
  - If `candidate_answers` are provided, save them via `storage.add_candidate_facts(candidate_answers)`.

### 5.2 `app/services/research.py`
- In `build_research_context(company, job_description)`:
  - If `company` is non-empty, check `storage.get_cached_research(company, max_age_days=14)`.
  - On hit: Return cached markdown immediately.
  - On miss: Call Tavily API, then call `storage.cache_research(company, formatted_text)`.

### 5.3 `app/services/generator.py`
- In `generate_tailored_resume`:
  - Fetch historical candidate facts via `storage.get_all_candidate_facts()`.
  - Merge past facts with current `candidate_answers` (avoiding duplicates).
  - Feed combined facts into the user prompt under `<candidate_answers>`.

---

## 6. User Interface & Endpoints

### 6.1 Routes
- `GET /history`:
  - Retrieves `applications = storage.list_applications()`.
  - Calculates summary metrics (total applications, average match score, top companies).
  - Renders `history.html`.
- `DELETE /api/applications/{result_id}`:
  - Deletes the application row from SQLite.
  - Returns `200 OK` (empty response) for HTMX in-place row removal.

### 6.2 Templates & Navigation
- **`app/templates/base.html`**:
  - Add "Past Applications" link in the top header with a dynamic count badge.
- **`app/templates/history.html`**:
  - Metric summary cards (Total, Avg Match Score, Active Market).
  - Live client-side search input (instant filtering of table by role or company).
  - Application cards/rows with:
    - Position, Company, Seniority.
    - Match score color-coded pill.
    - Creation date.
    - Quick actions: View Kit (`/result/{id}`), Download ZIP (`/download-bundle/{id}`), Reuse Template (`/?result_id={id}`), and Delete (`hx-delete`).
  - Empty state with clear CTA button to `/`.

---

## 7. Testing & Verification Plan

### Test Suites to Add / Update (`tests/test_storage.py`):
1. **Database initialization & WAL verification**: Verifies tables, pragmas, and indexes are properly created.
2. **Draft CRUD**: Save, retrieve, and delete drafts.
3. **Application CRUD & Refinement**: Save application, retrieve with Pydantic deserialization, update kit via refinement, list applications ordered by `created_at DESC`, and delete application.
4. **Research Caching & TTL**: Test cache set, cache hit, and cache expiration after 14 days.
5. **Candidate Fact Bank**: Verify adding Q&A pairs, duplicate handling, and retrieving all facts.
6. **Integration / Route Tests**:
   - `GET /history`: Returns 200 and renders applications list.
   - `DELETE /api/applications/{result_id}`: Deletes record and returns 200.
   - Server restart simulation: Write in storage instance A, open storage instance B on same file, confirm data survives.

All existing 61 tests in `pytest` must remain 100% passing.

---

## 8. Operational & Security Considerations

- **Data Privacy**: `data/` is added to `.gitignore`. Personal candidate data and generated PDFs never get tracked in Git.
- **Thread Safety**: SQLite connections use `check_same_thread=False` with timeout and context managers (`with get_db() as conn:`) to ensure safe connection closing.
- **Corrupt DB Graceful Handling**: If SQLite file is locked or temporarily unreadable, appropriate HTTP 500 / 503 errors are returned with logging.
