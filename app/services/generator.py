"""Pipeline orchestration: 3-stage modular pipeline (Match Analysis -> Core Resume -> Companion Kit)."""
import json
import logging
import re

import litellm
from fastapi import HTTPException
from pydantic import ValidationError

from app.config import get_settings
from app.prompts import (
    COMPANION_SYSTEM_PROMPT,
    MATCH_SYSTEM_PROMPT,
    QUESTIONS_SYSTEM,
    REFINE_SYSTEM,
    RESUME_SYSTEM_PROMPT,
    build_companion_prompt,
    build_match_prompt,
    build_questions_prompt,
    build_refine_prompt,
    build_resume_prompt,
)
from app.schemas import (
    ApplicationKit,
    ClarifyingQuestions,
    CompanionKit,
    GenerateInputs,
    ProfileMatchAnalysis,
    TailoredResume,
)

logger = logging.getLogger(__name__)
litellm.suppress_debug_info = True


def _extract_json(content: str) -> dict:
    """Parse model output as JSON, tolerating stray markdown fences."""
    text = content.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.rstrip().endswith("```"):
            text = text.rstrip()[:-3]
    return json.loads(text)


def _validation_feedback(error: Exception) -> str:
    if isinstance(error, ValidationError):
        problems = "\n".join(f"- {'.'.join(str(p['loc']))}: {p['msg']}" for p in error.errors()[:12])
        return (
            f"Your JSON was parseable but did not match the required schema:\n{problems}\n\n"
            "Return the corrected COMPLETE JSON object using EXACTLY the field names from the "
            "schema in the system prompt. Do not rename, nest or omit fields."
        )
    return ("Your previous answer could not be parsed as JSON. "
            "Return ONLY the corrected JSON object matching the schema.")


async def _call_llm(messages: list[dict], response_format: type) -> str:
    settings = get_settings()
    kwargs = {}
    if settings.llm_api_key:
        kwargs["api_key"] = settings.llm_api_key
    try:
        response = await litellm.acompletion(
            model=settings.llm_model,
            messages=messages,
            temperature=settings.llm_temperature,
            response_format=response_format,
            timeout=settings.request_timeout,
            num_retries=1,
            **kwargs,
        )
    except Exception as exc:  # noqa: BLE001 — surfaced to the UI with context
        logger.exception("LLM call failed")
        if isinstance(exc, litellm.exceptions.AuthenticationError):
            raise HTTPException(
                status_code=502,
                detail=f"Authentication failed for '{settings.llm_model}'. "
                       f"Check that LLM_API_KEY is set correctly in your .env file.",
            ) from exc
        hint = ""
        if not settings.llm_api_key and not settings.llm_model.startswith("ollama/"):
            hint = " No LLM_API_KEY is configured — set it in your .env file."
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}.{hint}") from exc

    return response.choices[0].message.content or ""


_LIST_LINE_RE = re.compile(r"^\s*(?:\d+[.)]|[-*•])\s*(.+)$")


def _parse_questions(content: str) -> list[str]:
    """Parse intake questions from JSON, or from a plain numbered/bulleted list."""
    try:
        data = _extract_json(content)
    except ValueError:
        data = None
    if isinstance(data, dict):
        try:
            return ClarifyingQuestions.model_validate(data).questions
        except ValidationError:
            pass
    elif isinstance(data, list):
        questions = [str(q).strip() for q in data if str(q).strip()]
        if questions:
            return questions

    questions = []
    for line in content.splitlines():
        m = _LIST_LINE_RE.match(line)
        if m and len(m.group(1).strip()) >= 10:  # skip stray fragments
            questions.append(m.group(1).strip().strip('`"'))
    return questions[:8]


async def generate_clarifying_questions(inputs: GenerateInputs) -> list[str]:
    """Short intake questions about missing KPIs/scope."""
    messages = [
        {"role": "system", "content": QUESTIONS_SYSTEM},
        {"role": "user", "content": build_questions_prompt(
            resume_text=inputs.resume_text,
            job_description=inputs.job_description,
            company=inputs.company,
            seniority=inputs.seniority,
            extra_context=inputs.extra_context,
        )},
    ]
    try:
        content = await _call_llm(messages, response_format=ClarifyingQuestions)
    except Exception as exc:  # noqa: BLE001 — optional step must never break generation
        logger.warning("Questions LLM call failed (%s); skipping questions step", exc)
        return []
    questions = _parse_questions(content)
    if not questions:
        logger.warning("Unparseable questions output (%.120r); skipping questions step", content)
    return questions


async def _validated_llm_call(
    messages: list[dict],
    model_cls: type,
    *,
    label: str = "model output",
) -> object:
    """LLM call validated into ``model_cls``; one corrective retry, then 502."""
    content = await _call_llm(messages, response_format=model_cls)

    try:
        return model_cls.model_validate(_extract_json(content))
    except (ValueError, ValidationError) as first_error:
        logger.warning("Invalid %s (%s), retrying once", label, type(first_error).__name__)
        messages.append({"role": "assistant", "content": content[:4000]})
        messages.append({"role": "user", "content": _validation_feedback(first_error)})
        content = await _call_llm(messages, response_format=model_cls)
        try:
            return model_cls.model_validate(_extract_json(content))
        except (ValueError, ValidationError) as second_error:
            logger.warning("Retry failed too: %s", second_error)
            raise HTTPException(
                status_code=502,
                detail=f"The model returned a non-conforming answer twice "
                       f"({str(second_error)[:300]}). Try again or switch model via LLM_MODEL.",
            ) from second_error


# ===========================================================================
# STAGE 1: Match & Gap Analysis
# ===========================================================================

async def analyze_job_match(inputs: GenerateInputs) -> ProfileMatchAnalysis:
    """Stage 1: Evaluate candidate profile against target job description."""
    messages = [
        {"role": "system", "content": MATCH_SYSTEM_PROMPT},
        {"role": "user", "content": build_match_prompt(
            resume_text=inputs.resume_text,
            extra_context=inputs.extra_context,
            job_description=inputs.job_description,
        )},
    ]
    return await _validated_llm_call(messages, ProfileMatchAnalysis, label="match analysis output")


# ===========================================================================
# STAGE 2: Core Tailored Résumé
# ===========================================================================

async def generate_tailored_resume(
    inputs: GenerateInputs,
    match_analysis: ProfileMatchAnalysis | None = None,
    candidate_answers: list[tuple[str, str]] | None = None,
) -> TailoredResume:
    """Stage 2: Generate Canadian ATS-format résumé guided by match strategy."""
    match_strategy = match_analysis.tailoring_strategy if match_analysis else None
    user_prompt = build_resume_prompt(
        resume_text=inputs.resume_text,
        extra_context=inputs.extra_context,
        job_description=inputs.job_description,
        match_strategy=match_strategy,
        candidate_answers=candidate_answers,
        seniority=inputs.seniority,
    )
    messages = [
        {"role": "system", "content": RESUME_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return await _validated_llm_call(messages, TailoredResume, label="tailored resume output")


# ===========================================================================
# STAGE 3: Companion Kit
# ===========================================================================

async def generate_companion_kit(
    inputs: GenerateInputs,
    tailored_resume: TailoredResume,
    match_analysis: ProfileMatchAnalysis | None,
    research_context: str,
) -> CompanionKit:
    """Stage 3: Generate cover letter, company research, interview prep and tips."""
    match_json = match_analysis.model_dump_json(indent=2) if match_analysis else None
    user_prompt = build_companion_prompt(
        tailored_resume_json=tailored_resume.model_dump_json(indent=2),
        job_description=inputs.job_description,
        company=inputs.company,
        seniority=inputs.seniority,
        research_context=research_context,
        match_analysis_json=match_json,
    )
    messages = [
        {"role": "system", "content": COMPANION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    return await _validated_llm_call(messages, CompanionKit, label="companion kit output")


async def refine_tailored_resume(
    inputs: GenerateInputs,
    current_resume: TailoredResume,
    feedback: str,
) -> TailoredResume:
    """Rewrite only the tailored résumé per user's change request."""
    messages = [
        {"role": "system", "content": REFINE_SYSTEM},
        {"role": "user", "content": build_refine_prompt(
            base_resume=inputs.resume_text,
            current_resume_json=current_resume.model_dump_json(indent=2),
            feedback=feedback,
        )},
    ]
    return await _validated_llm_call(messages, TailoredResume, label="refined resume output")


# ===========================================================================
# Orchestrator
# ===========================================================================

async def generate_kit_from_match(
    inputs: GenerateInputs,
    match_analysis: ProfileMatchAnalysis | None = None,
    candidate_answers: list[tuple[str, str]] | None = None,
) -> tuple[ApplicationKit, str]:
    """Stages 2 & 3: Generate Tailored Resume + Companion Kit using confirmed match context."""
    from app.services.research import build_research_context

    inferred_company = match_analysis.company if match_analysis and match_analysis.company else ""
    inferred_seniority = match_analysis.seniority if match_analysis and match_analysis.seniority else "Mid-level"
    inferred_position = match_analysis.position if match_analysis and match_analysis.position else ""

    effective_company = inputs.company.strip() if inputs.company.strip() else inferred_company
    effective_seniority = inputs.seniority.strip() if inputs.seniority.strip() else inferred_seniority
    effective_position = inputs.position.strip() if inputs.position.strip() else inferred_position

    effective_inputs = inputs.model_copy(update={
        "company": effective_company,
        "seniority": effective_seniority,
        "position": effective_position,
    })

    # Web research (Tavily search)
    research_context = await build_research_context(
        company=effective_inputs.company,
        job_description=effective_inputs.job_description,
    )

    # Stage 2: Core ATS Résumé
    logger.info(
        "Stage 2/3: Generating Canadian ATS tailored résumé (%s, %s)...",
        effective_inputs.seniority, effective_inputs.company or "general",
    )
    tailored_resume = await generate_tailored_resume(effective_inputs, match_analysis, candidate_answers)

    # Stage 3: Companion Kit
    logger.info("Stage 3/3: Generating companion deliverables (cover letter, interview prep, tips)...")
    companion = await generate_companion_kit(effective_inputs, tailored_resume, match_analysis, research_context)

    kit = ApplicationKit(
        match_analysis=match_analysis,
        tailored_resume=tailored_resume,
        company_research=companion.company_research,
        cover_letter=companion.cover_letter,
        interview_prep=companion.interview_prep,
        tips=companion.tips,
    )
    return kit, research_context


async def run_pipeline(
    inputs: GenerateInputs,
    candidate_answers: list[tuple[str, str]] | None = None,
) -> tuple[ApplicationKit, str]:
    """Full 3-stage pipeline: Match Analysis -> Core Resume -> Companion Kit."""
    match_analysis: ProfileMatchAnalysis | None = None
    if inputs.job_description.strip():
        logger.info("Stage 1/3: Analyzing job-profile match and gaps...")
        try:
            match_analysis = await analyze_job_match(inputs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Match analysis failed (%s); proceeding with direct resume tailoring", exc)

    return await generate_kit_from_match(inputs, match_analysis, candidate_answers)
