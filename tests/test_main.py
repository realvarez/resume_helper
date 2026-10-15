import io
from unittest.mock import patch
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from app.main import (
    _get_draft,
    _get_result,
    _store_draft,
    _store_result,
    app,
)
from app.schemas import GenerateInputs


@pytest.fixture
def client():
    return TestClient(app)


def test_storage_persistence_and_retrieval(sample_generate_inputs, sample_application_kit, sample_match_analysis):
    res_id = _store_result(sample_generate_inputs, sample_application_kit)
    retrieved_res = _get_result(res_id)
    assert retrieved_res is not None
    assert retrieved_res["inputs"].resume_text == sample_generate_inputs.resume_text
    assert retrieved_res["kit"].tailored_resume.contact.name == sample_application_kit.tailored_resume.contact.name

    draft_id = _store_draft(sample_generate_inputs, sample_match_analysis, questions=["Q1?"])
    retrieved_draft = _get_draft(draft_id)
    assert retrieved_draft is not None
    assert retrieved_draft["inputs"].resume_text == sample_generate_inputs.resume_text
    assert retrieved_draft["questions"] == ["Q1?"]


def test_persistence_survives_new_storage_instance(tmp_path, sample_generate_inputs, sample_application_kit):
    from app.services.storage import StorageRepository
    db_file = tmp_path / "persistence_test.db"
    storage1 = StorageRepository(db_file)
    storage1.save_application("persisted_1", sample_generate_inputs, sample_application_kit)

    # Instance 2 reading from the exact same file
    storage2 = StorageRepository(db_file)
    reloaded = storage2.get_application("persisted_1")
    assert reloaded is not None
    assert reloaded["kit"].tailored_resume.contact.name == sample_application_kit.tailored_resume.contact.name


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


def test_failed_generation_does_not_store_candidate_facts(client, monkeypatch, sample_generate_inputs, sample_match_analysis):
    from app.services.storage import get_storage

    draft_id = _store_draft(sample_generate_inputs, sample_match_analysis)

    async def failing_kit(*args, **kwargs):
        raise HTTPException(status_code=502, detail="Generation failed")

    monkeypatch.setattr("app.main.generate_kit_from_match", failing_kit)
    response = client.post(
        f"/generate-from-match/{draft_id}",
        data={"question": "Do you have a PMP?", "answer": "No"},
    )

    assert response.status_code == 502
    assert get_storage().get_all_candidate_facts() == []


def test_generation_deletes_the_draft_and_keeps_the_kit(
    client, monkeypatch, sample_generate_inputs, sample_match_analysis, sample_application_kit
):
    from app.services.storage import get_storage

    draft_id = _store_draft(sample_generate_inputs, sample_match_analysis)

    async def fake_kit(*args, **kwargs):
        return sample_application_kit, "Research notes"

    monkeypatch.setattr("app.main.generate_kit_from_match", fake_kit)
    response = client.post(f"/generate-from-match/{draft_id}", data={}, follow_redirects=False)

    assert response.status_code == 303
    result_id = response.headers["location"].rsplit("/", 1)[-1]
    assert get_storage().get_draft(draft_id) is None
    assert get_storage().get_application(result_id) is not None

    result_page = client.get(f"/result/{result_id}")
    assert result_page.status_code == 200
    assert "Back to Step 2" not in result_page.text


def test_delete_missing_application_returns_404(client):
    # History rows delete via HTMX (hx-delete), so the status code drives what the user sees.
    response = client.delete("/api/applications/does_not_exist")
    assert response.status_code == 404
    assert response.json()["detail"] == "Application not found"


def test_history_shows_only_the_newest_100_applications(client, sample_generate_inputs, sample_application_kit):
    """Documents the accepted 100-row cap: rows past 100 are unreachable and the metric
    cards cover only the newest 100. Not a bug — personal use, 100 is enough."""
    from app.services.storage import get_storage
    storage = get_storage()
    for i in range(101):
        storage.save_application(f"app_{i:03d}", sample_generate_inputs, sample_application_kit)

    # Distinct ascending timestamps so newest-first ordering is deterministic.
    with storage._connect() as conn:
        for i in range(101):
            conn.execute(
                "UPDATE applications SET created_at = datetime('now', ?) WHERE result_id = ?",
                (f"-{101 - i} minutes", f"app_{i:03d}"),
            )

    response = client.get("/history")
    assert response.status_code == 200
    assert "Showing 100 kits" in response.text
    # newest 100 kept, oldest dropped
    assert "ID: app_100" in response.text
    assert "ID: app_001" in response.text
    assert "ID: app_000" not in response.text
    # newest first
    assert response.text.index("ID: app_100") < response.text.index("ID: app_099")

