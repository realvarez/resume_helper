"""Resume Worker — FastAPI application and routes."""
import logging
import re
import uuid
from collections import OrderedDict

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import TARGET_COUNTRY, get_settings
from app.jinja_filters import bold
from app.schemas import ApplicationKit, GenerateInputs, ProfileMatchAnalysis
from app.services.generator import (
    analyze_job_match,
    generate_clarifying_questions,
    generate_kit_from_match,
    refine_tailored_resume,
    run_pipeline,
)
from app.services.export import generate_application_zip, get_application_filenames
from app.services.parser import build_extra_context, extract_text
from app.services.storage import get_storage

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("resume_worker")

app = FastAPI(title="Resume Worker", docs_url=None, redoc_url=None)
templates = Jinja2Templates(directory="app/templates")
templates.env.filters["bold"] = bold
app.mount("/static", StaticFiles(directory="app/static"), name="static")


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


@app.post("/api/parse-preview")
async def parse_preview(request: Request):
    """Instant drag-and-drop parsing feedback for PDF/DOCX/MD/TXT.
    Extracts text, calculates metrics, and detects resume section structure."""
    form = await request.form()
    upload = form.get("file")
    if not upload or not getattr(upload, "filename", ""):
        return JSONResponse({"ok": False, "error": "No file provided."}, status_code=400)

    filename = upload.filename
    try:
        text = extract_text(upload, min_chars=0)
    except HTTPException as e:
        return JSONResponse({"ok": False, "error": e.detail, "filename": filename}, status_code=400)
    except Exception as e:
        logger.exception("Failed to parse uploaded file: %s", filename)
        return JSONResponse(
            {"ok": False, "error": f"Failed to parse file: {str(e)}", "filename": filename},
            status_code=400,
        )

    if not text.strip():
        return JSONResponse(
            {
                "ok": False,
                "error": "Could not extract readable text. The document may be a scanned image.",
                "filename": filename,
            },
            status_code=422,
        )

    char_count = len(text)
    words = re.findall(r"\b\w+\b", text)
    word_count = len(words)

    # Detect common résumé sections
    sections = []
    if re.search(r"(?i)(email|phone|linkedin|github|contact|location)", text):
        sections.append("Contact Info")
    if re.search(r"(?i)(experience|employment|work history|career history|professional background)", text):
        sections.append("Experience")
    if re.search(r"(?i)(education|university|college|degree|bachelor|master|phd)", text):
        sections.append("Education")
    if re.search(r"(?i)(skills|technologies|proficiencies|languages|competencies|tools)", text):
        sections.append("Skills")
    if re.search(r"(?i)(projects|portfolio|certifications|awards)", text):
        sections.append("Projects/Certs")

    preview = (text[:220] + "…") if len(text) > 220 else text

    return JSONResponse({
        "ok": True,
        "filename": filename,
        "char_count": char_count,
        "word_count": word_count,
        "sections": sections,
        "snippet": preview,
        "ats_ready": char_count >= 80,
    })


@app.get("/")
async def index(request: Request, draft_id: str | None = None, result_id: str | None = None):
    settings = get_settings()
    inputs = None
    if draft_id:
        draft = get_storage().get_draft(draft_id)
        if draft:
            inputs = draft.get("inputs")
    elif result_id:
        app_data = get_storage().get_application(result_id)
        if app_data:
            inputs = app_data.get("inputs")

    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "has_tavily": bool(settings.tavily_api_key),
            "llm_model": settings.llm_model,
            "llm_ready": bool(settings.llm_api_key or settings.llm_model.startswith("ollama/")),
            "inputs": inputs,
            "draft_id": draft_id,
            "result_id": result_id,
            "active_step": 1,
        },
    )


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Render friendly HTML for browser/HTMX requests; JSON elsewhere."""
    wants_html = request.headers.get("HX-Request") or "text/html" in request.headers.get("accept", "")
    if wants_html and exc.status_code != 303:
        return templates.TemplateResponse(
            request,
            "_error.html",
            {"detail": exc.detail},
            status_code=exc.status_code,
        )
    return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)


@app.post("/match")
async def match(request: Request):
    """Step 1 endpoint: Evaluates Job Fit & Gaps, auto-infers Company and Seniority,
    and returns an interactive review screen for user confirmation."""
    form = await request.form()
    resume_text = str(form.get("resume_text") or "")
    job_description = str(form.get("job_description") or "").strip()
    position = str(form.get("position") or "").strip()

    # Supporting context: extracted from uploads & notes
    extra_context = str(form.get("extra_context") or "")
    if not extra_context:
        extra_notes = str(form.get("extra_notes") or "").strip()
        supporting_files = [
            f for f in form.getlist("supporting_files")
            if f is not None and getattr(f, "filename", "")
        ]
        extra_context = build_extra_context(supporting_files, extra_notes)

    # Résumé source: uploaded file wins over pasted text.
    text = ""
    upload = form.get("resume_file")
    if upload is not None and getattr(upload, "filename", ""):
        text = extract_text(upload)
    elif resume_text.strip():
        text = resume_text.strip()
    if len(text) < 80:
        raise HTTPException(
            status_code=422,
            detail="Provide your résumé (upload a file or paste at least a few lines).",
        )

    # If no job description is provided: run general Canadian résumé mode directly!
    if not job_description:
        inputs = GenerateInputs(
            resume_text=text,
            extra_context=extra_context,
            job_description="",
            company="",
            seniority="Mid-level",
            position=position,
        )
        kit, research_context = await run_pipeline(inputs)
        result_id = _store_result(inputs, kit)
        logger.info("Generated general kit %s (%s mode)", result_id, TARGET_COUNTRY)
        if request.headers.get("HX-Request"):
            return Response(status_code=200, headers={"HX-Redirect": f"/result/{result_id}"})
        return RedirectResponse(f"/result/{result_id}", status_code=303)

    # Targeted mode: Run Stage 1 (Match & Gap Analysis)
    inputs = GenerateInputs(
        resume_text=text,
        extra_context=extra_context,
        job_description=job_description,
        company="",
        seniority="",
        position=position,
    )

    match_analysis = await analyze_job_match(inputs)

    # Optional clarifying questions to display on the review screen
    questions = []
    if form.get("ask_questions"):
        inputs_with_inferred = inputs.model_copy(update={
            "company": match_analysis.company,
            "seniority": match_analysis.seniority,
            "position": position or match_analysis.position,
        })
        questions = await generate_clarifying_questions(inputs_with_inferred)

    draft_id = _store_draft(inputs, match_analysis, questions)
    logger.info(
        "Analyzed match for draft %s: score=%s, company=%r, seniority=%r",
        draft_id, match_analysis.match_score, match_analysis.company, match_analysis.seniority,
    )

    if request.headers.get("HX-Request"):
        return Response(status_code=200, headers={"HX-Redirect": f"/match-review/{draft_id}"})
    return RedirectResponse(f"/match-review/{draft_id}", status_code=303)


@app.get("/match-review/{draft_id}")
async def match_review(request: Request, draft_id: str):
    draft = _get_draft(draft_id)
    context = {
        "draft_id": draft_id,
        "inputs": draft["inputs"],
        "match_analysis": draft["match_analysis"],
        "questions": draft.get("questions", []),
        "target_country": TARGET_COUNTRY,
        "has_tavily": bool(get_settings().tavily_api_key),
        "active_step": 2,
    }
    return templates.TemplateResponse(request, "match_review.html", context)


@app.post("/generate-from-match/{draft_id}")
async def generate_from_match(request: Request, draft_id: str):
    """Step 2 endpoint: User confirms or edits inferred company & seniority,
    then executes Stage 2 (Core Résumé) and Stage 3 (Companion Kit)."""
    draft = _get_draft(draft_id)
    form = await request.form()

    company = str(form.get("company") or "").strip()
    seniority = str(form.get("seniority") or "").strip()
    position = str(form.get("position") or "").strip()

    inputs: GenerateInputs = draft["inputs"].model_copy(update={
        "company": company,
        "seniority": seniority,
        "position": position,
    })
    match_analysis: ProfileMatchAnalysis | None = draft.get("match_analysis")
    if match_analysis and (company or seniority or position):
        match_analysis = match_analysis.model_copy(update={
            "company": company or match_analysis.company,
            "seniority": seniority or match_analysis.seniority,
            "position": position or match_analysis.position,
        })

    candidate_answers = [
        (str(q).strip(), str(a).strip())
        for q, a in zip(form.getlist("question"), form.getlist("answer"))
        if str(q).strip() and str(a).strip()
    ] or None

    if candidate_answers:
        get_storage().add_candidate_facts(candidate_answers)

    kit, research_context = await generate_kit_from_match(inputs, match_analysis, candidate_answers)
    result_id = _store_result(inputs, kit, draft_id=draft_id)
    logger.info(
        "Generated kit %s from match %s for %s (%s, %s)",
        result_id, draft_id, inputs.company or "no company", TARGET_COUNTRY, inputs.seniority,
    )

    if request.headers.get("HX-Request"):
        return Response(status_code=200, headers={"HX-Redirect": f"/result/{result_id}"})
    return RedirectResponse(f"/result/{result_id}", status_code=303)


@app.get("/result/{result_id}")
async def result(request: Request, result_id: str):
    stored = _get_result(result_id)
    filenames = get_application_filenames(stored["kit"], stored.get("inputs"))
    return templates.TemplateResponse(
        request,
        "result.html",
        {
            "result_id": result_id,
            "draft_id": stored.get("draft_id"),
            "target_country": TARGET_COUNTRY,
            "active_step": 3,
            "filenames": filenames,
            **stored,
        },
    )


@app.post("/refine/{result_id}")
async def refine(request: Request, result_id: str):
    """Iterate on the résumé of an existing kit using a free-text change request."""
    stored = _get_result(result_id)
    form = await request.form()
    feedback = str(form.get("feedback") or "").strip()
    if len(feedback) < 3:
        raise HTTPException(status_code=422, detail="Describe the change you want (a few words is enough).")

    new_resume = await refine_tailored_resume(
        inputs=stored["inputs"],
        current_resume=stored["kit"].tailored_resume,
        feedback=feedback,
    )
    stored["kit"] = stored["kit"].model_copy(update={"tailored_resume": new_resume})
    stored["last_feedback"] = feedback
    get_storage().update_application_kit(result_id, stored["kit"])
    logger.info("Refined résumé for kit %s: %.80r", result_id, feedback)

    filenames = get_application_filenames(stored["kit"], stored.get("inputs"))

    context = {"result_id": result_id, "target_country": TARGET_COUNTRY, "filenames": filenames, **stored}
    if request.headers.get("HX-Request"):  # HTMX submit: swap content in-place
        return templates.TemplateResponse(request, "_result_content.html", context)
    return RedirectResponse(f"/result/{result_id}", status_code=303)


@app.get("/download/{result_id}")
async def download(result_id: str):
    """Download single tailored ATS résumé PDF."""
    stored = _get_result(result_id)
    from app.services.pdf import render_resume_pdf  # deferred: heavy WeasyPrint import

    pdf_bytes = render_resume_pdf(stored["kit"])
    filenames = get_application_filenames(stored["kit"], stored.get("inputs"))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filenames["resume_pdf_name"]}"'},
    )


@app.get("/download-cover-letter/{result_id}")
async def download_cover_letter(result_id: str):
    """Download single tailored cover letter PDF."""
    stored = _get_result(result_id)
    from app.services.pdf import render_cover_letter_pdf

    filenames = get_application_filenames(stored["kit"], stored.get("inputs"))
    pdf_bytes = render_cover_letter_pdf(
        stored["kit"],
        company=filenames["company"],
        position=filenames["position"],
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filenames["cover_letter_pdf_name"]}"'},
    )


@app.get("/download-bundle/{result_id}")
@app.get("/download/{result_id}/zip")
async def download_bundle(result_id: str):
    """Download full application package as a ZIP bundle."""
    stored = _get_result(result_id)
    zip_bytes, zip_filename = generate_application_zip(stored["kit"], stored.get("inputs"))
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{zip_filename}"'},
    )


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


