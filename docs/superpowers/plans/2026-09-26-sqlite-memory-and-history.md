# SQLite Memory, Persistence, and History Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace ephemeral in-memory dictionary caching with a persistent, zero-dependency SQLite storage repository that preserves drafts, kits, web research, and candidate fact memory across server restarts, and provide an application history dashboard (`/history`).

**Architecture:** A dedicated `StorageRepository` class (`app/services/storage.py`) backed by Python's standard library `sqlite3` using WAL mode and JSON serialization. It encapsulates `drafts`, `applications`, `company_research_cache`, and `candidate_facts` tables. FastAPI endpoints and background services (`generator.py`, `research.py`, `main.py`) call the repository directly, and a new `/history` route renders a dashboard for reviewing and managing past applications.

**Tech Stack:** Python 3.12, SQLite 3 (stdlib `sqlite3`), FastAPI, Pydantic v2, Jinja2, TailwindCSS, HTMX, Pytest.

**Spec:** [docs/superpowers/specs/2026-09-26-sqlite-memory-and-history-design.md](file:///home/realvarez/projects/resume_worker/docs/superpowers/specs/2026-09-26-sqlite-memory-and-history-design.md)

## Global Constraints

- Zero new dependencies in `requirements.txt`: use Python's built-in `sqlite3`.
- Database file must default to `data/resume_worker.db` and `data/` must be gitignored in `.gitignore`.
- SQLite must always be initialized with `PRAGMA journal_mode = WAL;`, `PRAGMA synchronous = NORMAL;`, and `PRAGMA foreign_keys = ON;`.
- Existing Pydantic models (`GenerateInputs`, `ProfileMatchAnalysis`, `TailoredResume`, `ApplicationKit`) must serialize/deserialize via `.model_dump_json()` and `.model_validate_json()`.
- Backward compatibility: All existing routes (`/`, `/match`, `/match-review/{id}`, `/generate-from-match/{id}`, `/result/{id}`, `/refine/{id}`, `/download/{id}`, `/download-bundle/{id}`) must preserve their existing contracts.

## Review Focus

- Malformed or corrupt JSON in database: When reading stored JSON payloads, handle `ValidationError` or `json.JSONDecodeError` gracefully with HTTP 500/404 instead of unhandled crashes.
- Concurrent read/write race condition: WAL mode and `check_same_thread=False` with appropriate busy timeout (5000ms) to prevent `sqlite3.OperationalError: database is locked`.
- Stale or expired research cache: Cache entries older than 14 days must be treated as cache misses and refreshed from Tavily.
- Empty state in `/history`: Clean UI rendering when zero applications exist without template errors.
- Case-insensitivity in company research: Querying for "Shopify" vs "shopify" vs "  shopify  " must map to the same cached company record.

---

### Task 1: Core Storage Repository (`app/services/storage.py`) & Tests

**Files:**
- Create: `app/services/storage.py`
- Test: `tests/test_storage.py`

**Interfaces:**
- Consumes: `GenerateInputs`, `ProfileMatchAnalysis`, `ApplicationKit` from `app/schemas.py`.
- Produces: `StorageRepository` class and `get_storage(db_path=None) -> StorageRepository` singleton helper.

- [ ] **Step 1: Write the failing tests for StorageRepository**

Write `tests/test_storage.py` covering database initialization, WAL pragmas, drafts CRUD, application CRUD, research cache with TTL, and candidate facts bank.

```python
"""Tests for SQLite StorageRepository."""
import time
from pathlib import Path
import pytest
from app.schemas import ApplicationKit, GenerateInputs, ProfileMatchAnalysis
from app.services.storage import StorageRepository


@pytest.fixture
def temp_storage(tmp_path: Path):
    db_file = tmp_path / "test_resume_worker.db"
    return StorageRepository(db_path=db_file)


def test_storage_initialization_and_tables(temp_storage: StorageRepository):
    with temp_storage._connect() as conn:
        tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        assert "drafts" in tables
        assert "applications" in tables
        assert "company_research_cache" in tables
        assert "candidate_facts" in tables

        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == "wal"


def test_draft_crud(temp_storage: StorageRepository, sample_generate_inputs: GenerateInputs):
    match_analysis = ProfileMatchAnalysis(
        match_score=85,
        company="Acme Corp",
        position="Senior Backend Engineer",
        seniority="Senior",
        role_summary="Great fit",
    )
    questions = ["What was your team size?"]

    # Save
    temp_storage.save_draft("draft_123", sample_generate_inputs, match_analysis, questions)

    # Get
    draft = temp_storage.get_draft("draft_123")
    assert draft is not None
    assert draft["inputs"].resume_text == sample_generate_inputs.resume_text
    assert draft["match_analysis"].company == "Acme Corp"
    assert draft["questions"] == questions

    # Not found
    assert temp_storage.get_draft("non_existent") is None

    # Delete
    assert temp_storage.delete_draft("draft_123") is True
    assert temp_storage.get_draft("draft_123") is None


def test_application_crud(temp_storage: StorageRepository, sample_generate_inputs: GenerateInputs, sample_application_kit: ApplicationKit):
    # Save
    temp_storage.save_application("res_456", sample_generate_inputs, sample_application_kit, draft_id="draft_123")

    # Get
    app_data = temp_storage.get_application("res_456")
    assert app_data is not None
    assert app_data["inputs"].resume_text == sample_generate_inputs.resume_text
    assert app_data["kit"].tailored_resume.header.name == sample_application_kit.tailored_resume.header.name
    assert app_data["draft_id"] == "draft_123"

    # List
    apps = temp_storage.list_applications()
    assert len(apps) == 1
    assert apps[0]["result_id"] == "res_456"
    assert apps[0]["company"] == sample_generate_inputs.company

    # Update Kit (Refinement)
    updated_kit = sample_application_kit.model_copy(deep=True)
    updated_kit.tailored_resume.summary = "Refined summary statement."
    assert temp_storage.update_application_kit("res_456", updated_kit) is True

    reloaded = temp_storage.get_application("res_456")
    assert reloaded["kit"].tailored_resume.summary == "Refined summary statement."

    # Delete
    assert temp_storage.delete_application("res_456") is True
    assert temp_storage.get_application("res_456") is None
    assert len(temp_storage.list_applications()) == 0


def test_company_research_cache_ttl(temp_storage: StorageRepository):
    temp_storage.cache_research("Shopify", "# Shopify Research Context")

    # Cache hit (case-insensitive and trimmed)
    cached = temp_storage.get_cached_research("  shopify  ", max_age_days=14)
    assert cached == "# Shopify Research Context"

    # Cache miss on non-existent
    assert temp_storage.get_cached_research("Unknown Corp") is None

    # Cache expiration simulation
    with temp_storage._connect() as conn:
        conn.execute("UPDATE company_research_cache SET fetched_at = datetime('now', '-15 days') WHERE company_normalized = 'shopify'")
    assert temp_storage.get_cached_research("Shopify", max_age_days=14) is None


def test_candidate_facts_accumulation(temp_storage: StorageRepository):
    temp_storage.add_candidate_facts([
        ("What was your team size?", "Led 8 engineers."),
        ("What cloud did you use?", "AWS and GCP."),
    ])

    facts = temp_storage.get_all_candidate_facts()
    assert len(facts) == 2
    assert facts[0] == ("What was your team size?", "Led 8 engineers.")

    # Adding duplicate question-answer should not create duplicates
    temp_storage.add_candidate_facts([
        ("What was your team size?", "Led 8 engineers."),
    ])
    assert len(temp_storage.get_all_candidate_facts()) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_storage.py -v`  
Expected: FAIL with `ModuleNotFoundError: No module named 'app.services.storage'`

- [ ] **Step 3: Implement StorageRepository in `app/services/storage.py`**

Create `app/services/storage.py` with standard library `sqlite3`, thread safety, WAL pragmas, schema initialization, and typed CRUD methods.

```python
"""SQLite storage repository for application kits, drafts, research cache, and candidate facts."""
from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Generator

from app.schemas import ApplicationKit, GenerateInputs, ProfileMatchAnalysis

logger = logging.getLogger(__name__)

DEFAULT_DB_PATH = Path("data/resume_worker.db")


class StorageRepository:
    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if self.db_path != Path(":memory:"):
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    @contextmanager
    def _connect(self) -> Generator[sqlite3.Connection, None, None]:
        conn = sqlite3.connect(
            str(self.db_path),
            timeout=5.0,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("PRAGMA foreign_keys = ON;")

            conn.execute("""
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
            """)

            conn.execute("""
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
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_created ON applications(created_at DESC);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_applications_company ON applications(company);")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS company_research_cache (
                    company_normalized TEXT PRIMARY KEY,
                    company_display TEXT NOT NULL,
                    research_markdown TEXT NOT NULL,
                    fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS candidate_facts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question TEXT NOT NULL,
                    answer TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(question, answer)
                );
            """)

    # -----------------------------------------------------------------------
    # Drafts
    # -----------------------------------------------------------------------

    def save_draft(
        self,
        draft_id: str,
        inputs: GenerateInputs,
        match_analysis: ProfileMatchAnalysis | None,
        questions: list[str] | None = None,
    ) -> None:
        inputs_json = inputs.model_dump_json()
        match_json = match_analysis.model_dump_json() if match_analysis else None
        import json
        questions_json = json.dumps(questions or [])
        company = (inputs.company or (match_analysis.company if match_analysis else "")).strip()
        position = (inputs.position or (match_analysis.position if match_analysis else "")).strip()
        seniority = (inputs.seniority or (match_analysis.seniority if match_analysis else "")).strip()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO drafts (
                    draft_id, company, position, seniority, inputs_json, match_analysis_json, questions_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?);
                """,
                (draft_id, company, position, seniority, inputs_json, match_json, questions_json),
            )

    def get_draft(self, draft_id: str) -> dict | None:
        import json
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM drafts WHERE draft_id = ?", (draft_id,)).fetchone()
            if not row:
                return None
            inputs = GenerateInputs.model_validate_json(row["inputs_json"])
            match_analysis = (
                ProfileMatchAnalysis.model_validate_json(row["match_analysis_json"])
                if row["match_analysis_json"]
                else None
            )
            questions = json.loads(row["questions_json"]) if row["questions_json"] else []
            return {
                "draft_id": row["draft_id"],
                "inputs": inputs,
                "match_analysis": match_analysis,
                "questions": questions,
                "created_at": row["created_at"],
            }

    def delete_draft(self, draft_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM drafts WHERE draft_id = ?", (draft_id,))
            return cursor.rowcount > 0

    # -----------------------------------------------------------------------
    # Applications
    # -----------------------------------------------------------------------

    def save_application(
        self,
        result_id: str,
        inputs: GenerateInputs,
        kit: ApplicationKit,
        draft_id: str | None = None,
    ) -> None:
        company = (inputs.company or (kit.match_analysis.company if kit.match_analysis else "") or "General").strip()
        position = (inputs.position or (kit.match_analysis.position if kit.match_analysis else "") or kit.tailored_resume.target_role or "Professional").strip()
        seniority = (inputs.seniority or (kit.match_analysis.seniority if kit.match_analysis else "") or "Mid-level").strip()
        match_score = kit.match_analysis.match_score if kit.match_analysis else None

        inputs_json = inputs.model_dump_json()
        kit_json = kit.model_dump_json()

        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO applications (
                    result_id, draft_id, company, position, seniority, match_score, inputs_json, kit_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?);
                """,
                (result_id, draft_id, company, position, seniority, match_score, inputs_json, kit_json),
            )

    def get_application(self, result_id: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM applications WHERE result_id = ?", (result_id,)).fetchone()
            if not row:
                return None
            inputs = GenerateInputs.model_validate_json(row["inputs_json"])
            kit = ApplicationKit.model_validate_json(row["kit_json"])
            return {
                "result_id": row["result_id"],
                "draft_id": row["draft_id"],
                "company": row["company"],
                "position": row["position"],
                "seniority": row["seniority"],
                "match_score": row["match_score"],
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
                "inputs": inputs,
                "kit": kit,
            }

    def update_application_kit(self, result_id: str, kit: ApplicationKit) -> bool:
        kit_json = kit.model_dump_json()
        with self._connect() as conn:
            cursor = conn.execute(
                "UPDATE applications SET kit_json = ?, updated_at = CURRENT_TIMESTAMP WHERE result_id = ?",
                (kit_json, result_id),
            )
            return cursor.rowcount > 0

    def list_applications(self, limit: int = 100) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT result_id, draft_id, company, position, seniority, match_score, created_at, updated_at
                FROM applications
                ORDER BY created_at DESC
                LIMIT ?;
                """,
                (limit,),
            ).fetchall()
            return [dict(row) for row in rows]

    def delete_application(self, result_id: str) -> bool:
        with self._connect() as conn:
            cursor = conn.execute("DELETE FROM applications WHERE result_id = ?", (result_id,))
            return cursor.rowcount > 0

    # -----------------------------------------------------------------------
    # Company Research Cache
    # -----------------------------------------------------------------------

    def get_cached_research(self, company: str, max_age_days: int = 14) -> str | None:
        normalized = company.strip().lower()
        if not normalized:
            return None
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT research_markdown, fetched_at
                FROM company_research_cache
                WHERE company_normalized = ?
                  AND fetched_at >= datetime('now', ? || ' days');
                """,
                (normalized, f"-{max_age_days}"),
            ).fetchone()
            return row["research_markdown"] if row else None

    def cache_research(self, company: str, research_markdown: str) -> None:
        normalized = company.strip().lower()
        if not normalized or not research_markdown.strip():
            return
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO company_research_cache (
                    company_normalized, company_display, research_markdown, fetched_at
                ) VALUES (?, ?, ?, CURRENT_TIMESTAMP);
                """,
                (normalized, company.strip(), research_markdown),
            )

    # -----------------------------------------------------------------------
    # Candidate Facts
    # -----------------------------------------------------------------------

    def add_candidate_facts(self, qa_pairs: list[tuple[str, str]]) -> None:
        valid_pairs = [
            (q.strip(), a.strip()) for q, a in qa_pairs if q.strip() and a.strip()
        ]
        if not valid_pairs:
            return
        with self._connect() as conn:
            conn.executemany(
                "INSERT OR IGNORE INTO candidate_facts (question, answer) VALUES (?, ?);",
                valid_pairs,
            )

    def get_all_candidate_facts(self) -> list[tuple[str, str]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT question, answer FROM candidate_facts ORDER BY id ASC").fetchall()
            return [(r["question"], r["answer"]) for r in rows]


_global_storage: StorageRepository | None = None


def get_storage(db_path: Path | str | None = None) -> StorageRepository:
    global _global_storage
    if db_path is not None:
        return StorageRepository(db_path)
    if _global_storage is None:
        _global_storage = StorageRepository()
    return _global_storage
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_storage.py -v`  
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/storage.py tests/test_storage.py
git commit -m "feat: implement SQLite StorageRepository with drafts, applications, cache, and facts"
```

---

### Task 2: Web Research Cache Integration (`app/services/research.py`)

**Files:**
- Modify: `app/services/research.py:70-130`
- Test: `tests/test_research.py`

**Interfaces:**
- Consumes: `get_storage` from `app.services.storage`.
- Produces: Updated `build_research_context(company, job_description)` with transparent caching.

- [ ] **Step 1: Write failing test in `tests/test_research.py`**

Add tests checking that `build_research_context` returns cached research without invoking Tavily, and caches new results upon successful search.

```python
@pytest.mark.asyncio
async def test_build_research_context_uses_cache(monkeypatch, tmp_path):
    from app.services.storage import StorageRepository
    test_storage = StorageRepository(tmp_path / "research_cache.db")
    test_storage.cache_research("Acme Corp", "Cached Acme Dossier")
    monkeypatch.setattr("app.services.research.get_storage", lambda: test_storage)

    # Calling with cached company should NOT call tavily
    called_tavily = False
    def fake_tavily(*args, **kwargs):
        nonlocal called_tavily
        called_tavily = True
        return {}

    monkeypatch.setattr("tavily.TavilyClient", fake_tavily)
    result = await build_research_context("Acme Corp", "Some JD")
    assert result == "Cached Acme Dossier"
    assert called_tavily is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_research.py::test_build_research_context_uses_cache -v`  
Expected: FAIL

- [ ] **Step 3: Modify `app/services/research.py` to check and set storage cache**

In `app/services/research.py`, import `get_storage` and wrap Tavily queries with `storage.get_cached_research` and `storage.cache_research`.

```python
async def build_research_context(company: str, job_description: str) -> str:
    company_name = company.strip()
    if not company_name:
        return ""

    from app.services.storage import get_storage
    storage = get_storage()
    cached = storage.get_cached_research(company_name, max_age_days=14)
    if cached:
        logger.info("Using cached company research for %r", company_name)
        return cached

    # ... existing Tavily search code ...
    # Once context is built:
    if context:
        storage.cache_research(company_name, context)
    return context
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_research.py -v`  
Expected: All tests in `test_research.py` PASS.

- [ ] **Step 5: Commit**

```bash
git add app/services/research.py tests/test_research.py
git commit -m "feat: cache company web research in SQLite storage"
```

---

### Task 3: Candidate Fact Memory & Pipeline Integration (`app/services/generator.py`)

**Files:**
- Modify: `app/services/generator.py:170-220`
- Test: `tests/test_generator.py`

**Interfaces:**
- Consumes: `storage.get_all_candidate_facts` from `app.services.storage`.
- Produces: Updated `generate_tailored_resume` that injects accumulated facts into the candidate answers block.

- [ ] **Step 1: Write failing test in `tests/test_generator.py`**

Add a test verifying that `generate_tailored_resume` incorporates historical candidate facts from storage alongside current answers.

```python
@pytest.mark.asyncio
async def test_generate_tailored_resume_merges_stored_candidate_facts(monkeypatch, tmp_path, sample_generate_inputs):
    from app.services.storage import StorageRepository
    test_storage = StorageRepository(tmp_path / "facts.db")
    test_storage.add_candidate_facts([("Prior KPI", "Increased throughput 40%")])
    monkeypatch.setattr("app.services.generator.get_storage", lambda: test_storage)

    captured_prompt = None
    async def fake_validated_call(messages, model_cls, label):
        nonlocal captured_prompt
        captured_prompt = messages[1]["content"]
        from app.schemas import TailoredResume, ResumeHeader
        return TailoredResume(
            header=ResumeHeader(name="Jane Doe", email="j@d.com", phone="123", location="Toronto, ON"),
            target_role="Developer",
            summary="Experienced dev",
            skills=["Python"],
            experience=[],
            education=[],
        )

    monkeypatch.setattr("app.services.generator._validated_llm_call", fake_validated_call)
    await generate_tailored_resume(sample_generate_inputs, candidate_answers=[("Current Q", "Current Ans")])

    assert "Prior KPI" in captured_prompt
    assert "Increased throughput 40%" in captured_prompt
    assert "Current Q" in captured_prompt
    assert "Current Ans" in captured_prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_generator.py::test_generate_tailored_resume_merges_stored_candidate_facts -v`  
Expected: FAIL

- [ ] **Step 3: Modify `generate_tailored_resume` in `app/services/generator.py`**

In `app/services/generator.py`, fetch stored candidate facts and combine them with `candidate_answers` before calling `build_resume_prompt`.

```python
async def generate_tailored_resume(
    inputs: GenerateInputs,
    match_analysis: ProfileMatchAnalysis | None = None,
    candidate_answers: list[tuple[str, str]] | None = None,
) -> TailoredResume:
    from app.services.storage import get_storage
    storage = get_storage()
    stored_facts = storage.get_all_candidate_facts()

    # Combine historical facts with current answers, preserving order and eliminating exact dupes
    combined_answers: list[tuple[str, str]] = list(stored_facts)
    if candidate_answers:
        existing_set = set(combined_answers)
        for pair in candidate_answers:
            if pair not in existing_set:
                combined_answers.append(pair)
                existing_set.add(pair)

    # Pass combined_answers to build_resume_prompt
    user_prompt = build_resume_prompt(
        resume_text=inputs.resume_text,
        extra_context=inputs.extra_context,
        job_description=inputs.job_description,
        match_strategy=match_analysis.tailoring_strategy if match_analysis else None,
        candidate_answers=combined_answers or None,
        seniority=inputs.seniority or "Senior",
    )
    # ... rest of call
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_generator.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app/services/generator.py tests/test_generator.py
git commit -m "feat: inject accumulated candidate fact memory into tailored resume prompt"
```

---

### Task 4: Main Application & Storage Migration (`app/main.py`)

**Files:**
- Modify: `app/main.py:34-78, 140-250`
- Modify: `.gitignore`
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `get_storage` from `app.services.storage`.
- Produces: Replaces `_results` and `_drafts` with SQLite repository; stores candidate answers into facts table.

- [ ] **Step 1: Write failing test in `tests/test_main.py`**

Test that stored drafts and applications persist to SQLite, and that `/api/parse-preview` and download endpoints continue to function as expected.

```python
def test_persistence_survives_new_storage_instance(tmp_path, monkeypatch, sample_generate_inputs, sample_application_kit):
    from app.services.storage import StorageRepository
    db_file = tmp_path / "persistence_test.db"
    storage1 = StorageRepository(db_file)
    storage1.save_application("persisted_1", sample_generate_inputs, sample_application_kit)

    # Instance 2 reading from same file
    storage2 = StorageRepository(db_file)
    reloaded = storage2.get_application("persisted_1")
    assert reloaded is not None
    assert reloaded["kit"].tailored_resume.header.name == sample_application_kit.tailored_resume.header.name
```

- [ ] **Step 2: Run test to verify it passes**

Run: `uv run pytest tests/test_main.py -v`

- [ ] **Step 3: Update `app/main.py` and `.gitignore`**

1. Add `data/` and `*.db` to `.gitignore`.
2. In `app/main.py`:
   - Replace in-memory dictionaries with `storage = get_storage()`.
   - Update `_store_result`, `_get_result`, `_store_draft`, `_get_draft` to call `storage`.
   - In `generate_from_match`: call `storage.add_candidate_facts(candidate_answers)` when candidate answers are submitted.
   - In `refine`: call `storage.update_application_kit(result_id, stored["kit"])`.

```python
# In app/main.py:
from app.services.storage import get_storage

def _store_result(inputs: GenerateInputs, kit: ApplicationKit, draft_id: str | None = None) -> str:
    result_id = uuid.uuid4().hex[:12]
    get_storage().save_application(result_id, inputs, kit, draft_id=draft_id)
    return result_id

def _get_result(result_id: str) -> dict:
    app_data = get_storage().get_application(result_id)
    if not app_data:
        raise HTTPException(status_code=404, detail="Result expired or not found. Generate it again.")
    return app_data

def _store_draft(
    inputs: GenerateInputs,
    match_analysis: ProfileMatchAnalysis | None,
    questions: list[str] | None = None,
) -> str:
    draft_id = uuid.uuid4().hex[:12]
    get_storage().save_draft(draft_id, inputs, match_analysis, questions)
    return draft_id

def _get_draft(draft_id: str) -> dict:
    draft = get_storage().get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="Draft expired or not found. Please start over from the home page.")
    return draft
```

- [ ] **Step 4: Run test suite to verify existing routes continue passing**

Run: `uv run pytest tests/test_main.py -v`  
Expected: All 6 tests in `test_main.py` PASS.

- [ ] **Step 5: Commit**

```bash
git add app/main.py .gitignore tests/test_main.py
git commit -m "refactor: replace in-memory cache with SQLite storage in main routes"
```

---

### Task 5: History Dashboard UI & Management Endpoints

**Files:**
- Create: `app/templates/history.html`
- Modify: `app/templates/base.html:20-60`
- Modify: `app/main.py` (add `GET /history` and `DELETE /api/applications/{result_id}`)
- Test: `tests/test_main.py`

**Interfaces:**
- Consumes: `storage.list_applications` and `storage.delete_application`.
- Produces: `/history` UI page with search and action buttons; HTMX delete endpoint.

- [ ] **Step 1: Write failing tests for `/history` and `DELETE /api/applications/{id}`**

In `tests/test_main.py`:

```python
def test_history_page_empty(client):
    response = client.get("/history")
    assert response.status_code == 200
    assert "Past Applications" in response.text
    assert "No past applications recorded yet" in response.text


def test_history_page_with_data_and_delete(client, sample_generate_inputs, sample_application_kit):
    from app.services.storage import get_storage
    storage = get_storage()
    storage.save_application("test_app_1", sample_generate_inputs, sample_application_kit)

    # GET /history
    response = client.get("/history")
    assert response.status_code == 200
    assert "test_app_1" in response.text
    assert sample_generate_inputs.company in response.text

    # DELETE /api/applications/{id}
    del_resp = client.delete("/api/applications/test_app_1")
    assert del_resp.status_code == 200

    # Ensure deleted
    assert storage.get_application("test_app_1") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_main.py::test_history_page_empty -v`  
Expected: FAIL with 404 Not Found

- [ ] **Step 3: Implement `app/templates/history.html` and endpoints in `app/main.py`**

1. Add endpoints in `app/main.py`:
```python
@app.get("/history")
async def history(request: Request):
    storage = get_storage()
    applications = storage.list_applications(limit=100)
    total_apps = len(applications)
    scores = [a["match_score"] for a in applications if a.get("match_score") is not None]
    avg_score = round(sum(scores) / len(scores)) if scores else None
    
    return templates.TemplateResponse(
        request,
        "history.html",
        {
            "applications": applications,
            "total_apps": total_apps,
            "avg_score": avg_score,
            "target_country": TARGET_COUNTRY,
        },
    )

@app.delete("/api/applications/{result_id}")
async def delete_application_endpoint(result_id: str):
    storage = get_storage()
    deleted = storage.delete_application(result_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Application not found")
    return Response(status_code=200)
```

2. Create `app/templates/history.html` with Tailwind styling matching `base.html`:
   - Metric summary cards (Total Applications, Average Match Score, Active Market).
   - Live client-side search input (`oninput` filtering table rows).
   - Application list with company, position, match score badge, creation date.
   - Action links: **View Kit** (`/result/{id}`), **Download Bundle** (`/download-bundle/{id}`), **Reuse** (`/?result_id={id}`), and **Delete** button with `hx-delete="/api/applications/{{ app.result_id }}" hx-target="closest tr" hx-swap="outerHTML swap:300ms"`.

3. Update `app/templates/base.html`:
   - Add a "Past Applications" link in the top header navigation bar.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_main.py -v`  
Expected: All tests PASS.

- [ ] **Step 5: Commit**

```bash
git add app/templates/history.html app/templates/base.html app/main.py tests/test_main.py
git commit -m "feat: add application history dashboard and delete endpoint"
```

---

### Task 6: Full Verification & Integration Test Run

**Files:**
- Test: Full test suite (`tests/`)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -v`  
Expected: All test modules pass (65+ tests, 100% success).

- [ ] **Step 2: Commit any cleanups or formatting**

```bash
git status
```
Ensure working tree is clean.
