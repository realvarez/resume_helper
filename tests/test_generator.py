import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi import HTTPException
from pydantic import BaseModel, Field
from app.services.generator import (
    _call_llm,
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


def test_validation_feedback():
    try:
        SimpleModel.model_validate({"name": "Test", "score": -10})
    except Exception as exc:
        feedback = _validation_feedback(exc)
        assert "score" in feedback
        assert "greater than or equal to 0" in feedback

    generic_feedback = _validation_feedback(ValueError("bad json"))
    assert "could not be parsed as JSON" in generic_feedback


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


@pytest.mark.asyncio
async def test_generate_tailored_resume_merges_stored_candidate_facts(monkeypatch, tmp_path, sample_generate_inputs, sample_tailored_resume):
    from app.services.storage import StorageRepository
    from app.services.generator import generate_tailored_resume

    test_storage = StorageRepository(tmp_path / "facts.db")
    test_storage.add_candidate_facts([("Prior KPI", "Increased throughput 40%")])
    monkeypatch.setattr("app.services.generator.get_storage", lambda: test_storage)

    captured_prompt = None

    async def fake_validated_call(messages, model_cls, label):
        nonlocal captured_prompt
        captured_prompt = messages[1]["content"]
        return sample_tailored_resume

    monkeypatch.setattr("app.services.generator._validated_llm_call", fake_validated_call)
    await generate_tailored_resume(sample_generate_inputs, candidate_answers=[("Current Q", "Current Ans")])

    assert "Prior KPI" in captured_prompt
    assert "Increased throughput 40%" in captured_prompt
    assert "Current Q" in captured_prompt
    assert "Current Ans" in captured_prompt

