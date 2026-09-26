"""SQLite storage repository for application kits, drafts, research cache, and candidate facts."""
from __future__ import annotations

import json
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
        if str(self.db_path) != ":memory:":
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
