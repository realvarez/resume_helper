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


def test_draft_crud(temp_storage: StorageRepository, sample_generate_inputs: GenerateInputs, sample_match_analysis: ProfileMatchAnalysis):
    questions = ["What was your team size?"]

    # Save
    temp_storage.save_draft("draft_123", sample_generate_inputs, sample_match_analysis, questions)

    # Get
    draft = temp_storage.get_draft("draft_123")
    assert draft is not None
    assert draft["inputs"].resume_text == sample_generate_inputs.resume_text
    assert draft["match_analysis"].company == sample_match_analysis.company
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
    assert app_data["kit"].tailored_resume.contact.name == sample_application_kit.tailored_resume.contact.name
    assert app_data["draft_id"] == "draft_123"

    # List
    apps = temp_storage.list_applications()
    assert len(apps) == 1
    assert apps[0]["result_id"] == "res_456"
    assert apps[0]["company"] == sample_generate_inputs.company

    # Update Kit (Refinement)
    updated_kit = sample_application_kit.model_copy(deep=True)
    updated_kit.tailored_resume.professional_summary = "Refined summary statement."
    assert temp_storage.update_application_kit("res_456", updated_kit) is True

    reloaded = temp_storage.get_application("res_456")
    assert reloaded["kit"].tailored_resume.professional_summary == "Refined summary statement."

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
