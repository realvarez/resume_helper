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
    res_id = _store_result(sample_generate_inputs, sample_application_kit, draft_id="draft_abc")
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

