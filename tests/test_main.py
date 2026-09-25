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
