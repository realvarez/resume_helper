"""Document formatting and ZIP bundle generation for application deliverables.

Naming standard:
  Zip bundle: {user_initials}_{position}_{company}.zip (e.g. RA_<position>_<company>.zip)
  Each file inside uses the same prefix with a suffix for the file type:
    - _resume.pdf
    - _resume.md
    - _cover_letter.pdf
    - _cover_letter.md
    - _cover_letter.txt
    - _interview_prep.md
    - _tips.md
    - _company_research.md
    - _match_analysis.md
"""
import io
import logging
import re
import zipfile
from datetime import date

from app.config import TARGET_COUNTRY
from app.schemas import (
    ApplicationKit,
    CompanyResearch,
    ContactInfo,
    CoverLetter,
    GenerateInputs,
    InterviewQuestions,
    ProfileMatchAnalysis,
    QuestionAdvice,
    TailoredResume,
    TipsSection,
)

logger = logging.getLogger(__name__)


def extract_initials(name: str) -> str:
    """Extract uppercase initials from candidate name (e.g. 'Ricardo Alvarez' -> 'RA').

    Falls back to 'User' if name is empty or invalid.
    """
    words = re.findall(r"\w+", name or "")
    if not words:
        return "User"
    if len(words) == 1:
        w = words[0]
        return w.upper() if len(w) <= 4 else w
    return "".join(w[0].upper() for w in words)


def sanitize_token(text: str, default: str = "Unknown") -> str:
    """Sanitize a name token (position, company, user) for clean filesystem naming."""
    return re.sub(r"[^\w\-]+|_+", "_", text or "").strip("_") or default


def get_application_filenames(
    kit: ApplicationKit,
    inputs: GenerateInputs | None = None,
) -> dict[str, str]:
    """Calculate the unified base prefix and filenames for all application deliverables.

    Convention:
      Base prefix: {initials}_{position}_{company}
      Example: RA_Senior_Backend_Engineer_Shopify
    """
    candidate_name = kit.tailored_resume.contact.name if kit.tailored_resume.contact else ""
    initials = extract_initials(candidate_name)

    # Resolve position (inputs -> match_analysis -> top experience title -> seniority -> 'Position')
    pos_candidates = [
        getattr(inputs, "position", None),
        getattr(kit.match_analysis, "position", None),
        kit.tailored_resume.experience[0].title if kit.tailored_resume.experience else None,
        f"{inputs.seniority.strip()} Role" if getattr(inputs, "seniority", None) else None,
    ]
    position = next((p.strip() for p in pos_candidates if p and p.strip()), "Position")

    # Resolve company (inputs -> match_analysis -> 'Company')
    co_candidates = [getattr(inputs, "company", None), getattr(kit.match_analysis, "company", None)]
    company = next((c.strip() for c in co_candidates if c and c.strip()), "Company")

    clean_position = sanitize_token(position, "Position")
    clean_company = sanitize_token(company, "Company")
    prefix = f"{initials}_{clean_position}_{clean_company}"

    suffixes = [
        "resume.pdf", "resume.md", "cover_letter.pdf", "cover_letter.md",
        "cover_letter.txt", "interview_prep.md", "tips.md",
        "company_research.md", "match_analysis.md",
    ]
    return {
        "initials": initials,
        "position": position,
        "company": company,
        "clean_position": clean_position,
        "clean_company": clean_company,
        "prefix": prefix,
        "zip_name": f"{prefix}.zip",
        **{f"{s.replace('.', '_')}_name": f"{prefix}_{s}" for s in suffixes},
    }


def render_resume_markdown(resume: TailoredResume) -> str:
    """Format TailoredResume as clean GitHub-style Markdown."""
    lines: list[str] = [f"# {resume.contact.name}"]
    contact_parts = " · ".join(filter(None, [
        resume.contact.email, resume.contact.phone, resume.contact.location,
        resume.contact.linkedin, resume.contact.website,
    ]))
    if contact_parts:
        lines.append(contact_parts)
    lines.extend(["", "## Professional Summary", resume.professional_summary, "", "## Professional Experience"])

    for job in resume.experience:
        company_part = f" — {job.company}" if job.company else ""
        loc_part = f" | {job.location}" if job.location else ""
        lines.append(f"### {job.title}{company_part}")
        lines.append(f"*{job.start_date} – {job.end_date}{loc_part}*\n")
        lines.extend(f"- {b}" for b in job.bullets)
        if job.tech_stack:
            lines.append(f"- **Tech Stack**: {', '.join(job.tech_stack)}")
        for group in (job.groups or []):
            lines.append(f"\n**{group.label}**")
            lines.extend(f"- {gb}" for gb in group.bullets)
            if group.tech_stack:
                lines.append(f"- **Tech Stack**: {', '.join(group.tech_stack)}")
        lines.append("")

    if resume.education:
        lines.append("## Education")
        for edu in resume.education:
            loc = f" | {edu.location}" if edu.location else ""
            date_str = f" ({edu.graduation_date})" if edu.graduation_date else ""
            lines.append(f"### {edu.degree} — {edu.institution}{date_str}{loc}")
            lines.extend(f"- {d}" for d in (edu.details or []))
        lines.append("")

    if resume.core_skills:
        lines.extend(["## Core Skills", ", ".join(resume.core_skills), ""])

    if resume.projects:
        lines.append("## Notable Projects")
        for p in resume.projects:
            lines.extend([f"### {p.name}", p.description])
            if p.technologies:
                lines.append(f"**Technologies**: {', '.join(p.technologies)}")
            lines.append("")

    for title, items in [("Certifications", resume.certifications), ("Languages", resume.languages)]:
        if items:
            lines.append(f"## {title}")
            lines.extend(f"- {c}" for c in items)
            lines.append("")

    return "\n".join(lines).strip() + "\n"


def render_cover_letter_markdown(
    cover_letter: CoverLetter,
    resume: TailoredResume,
    company: str = "",
    position: str = "",
) -> str:
    """Format cover letter as Markdown with formal headers."""
    today = date.today().strftime("%B %d, %Y")
    lines: list[str] = [f"# Cover Letter — {resume.contact.name}", f"**Date**: {today}"]
    if company:
        lines.append(f"**Target Company**: {company}")
    if position:
        lines.append(f"**Position Applied**: {position}")
    lines.extend(["", "**To**: Hiring Team & Recruitment Manager"])
    if company:
        lines.append(company)
    lines.append("")

    target = " at ".join(filter(None, [position, company]))
    if target:
        lines.extend([f"**RE: Application for {target}**", ""])

    lines.extend([cover_letter.greeting, ""])
    for p in cover_letter.body:
        lines.extend([p, ""])
    lines.extend([cover_letter.closing, f"**{resume.contact.name}**", ""])

    contact_parts = " · ".join(filter(None, [resume.contact.email, resume.contact.phone, resume.contact.linkedin]))
    if contact_parts:
        lines.append(contact_parts)

    return "\n".join(lines).strip() + "\n"


def render_cover_letter_text(
    cover_letter: CoverLetter,
    resume: TailoredResume,
    company: str = "",
    position: str = "",
) -> str:
    """Format cover letter as clean plain text suitable for direct copy-paste."""
    today = date.today().strftime("%B %d, %Y")
    lines: list[str] = [resume.contact.name]
    contact_parts = " | ".join(filter(None, [resume.contact.email, resume.contact.phone, resume.contact.location]))
    if contact_parts:
        lines.append(contact_parts)
    lines.extend(["", today, "", "Hiring Team & Recruitment Manager"])
    if company:
        lines.append(company)
    lines.append("")

    target = " at ".join(filter(None, [position, company]))
    if target:
        lines.extend([f"RE: Application for {target}", ""])

    lines.extend([cover_letter.greeting, ""])
    for p in cover_letter.body:
        lines.extend([p, ""])
    lines.extend([cover_letter.closing, resume.contact.name])

    return "\n".join(lines).strip() + "\n"


def render_interview_prep_markdown(
    interview_prep: InterviewQuestions,
    position: str = "",
    company: str = "",
) -> str:
    """Format interview prep questions and STAR tips as Markdown."""
    target = " at ".join(filter(None, [position, company]))
    header = f"Interview Preparation Guide{' — ' + target if target else ''}"
    lines = [
        f"# {header}",
        "",
        "Comprehensive interview question preparation using the STAR method (Situation, Task, Action, Result).",
        "",
    ]

    def _append_qa(title: str, questions: list[QuestionAdvice], prefix: str = "### Q"):
        lines.extend([title, ""])
        for idx, qa in enumerate(questions, 1):
            lines.append(f"{prefix}{idx}: {qa.question}")
            if qa.why_they_ask:
                lines.append(f"**Why they ask**: {qa.why_they_ask}")
            lines.extend([f"**Strategy & Key Points**: {qa.answer_tips}", ""])

    _append_qa("## 1. HR & Behavioral Questions", interview_prep.hr_questions)
    _append_qa("## 2. Technical & Domain Questions", interview_prep.technical_questions)

    if interview_prep.stage_specific:
        lines.extend(["## 3. Stage-Specific Interview Questions", ""])
        for stage in interview_prep.stage_specific:
            _append_qa(f"### Stage: {stage.stage_name}\n", stage.questions, prefix="#### Q")

    return "\n".join(lines).strip() + "\n"


def render_tips_markdown(tips: TipsSection, target_country: str = TARGET_COUNTRY) -> str:
    """Format Canadian workplace, application, and interview tips as Markdown."""
    sections = [
        (f"## 1. Workplace & Cultural Norms ({target_country})", tips.country_culture_tips),
        ("## 2. Application & ATS Best Practices", tips.application_best_practices),
        ("## 3. Interview Day Recommendations", tips.interview_day_tips or []),
        ("## 4. Résumé Adaptation Strategy & Notes", tips.resume_adaptation_notes),
    ]
    lines = [f"# Job Search & Interview Success Guide ({target_country} Market)", ""]
    for title, items in sections:
        if items:
            lines.append(title)
            lines.extend(f"- {t}" for t in items)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def render_company_research_markdown(research: CompanyResearch, company: str = "") -> str:
    """Format company intelligence report as Markdown."""
    lines: list[str] = [
        f"# Company Research & Intelligence: {company or 'Target Organization'}",
        "",
        "## Executive Overview",
        research.overview,
        "",
    ]

    sections = [
        ("## Core Products & Services", research.products_and_services),
        ("## Known Tech Stack & Tooling", research.tech_stack),
        ("## Culture & Corporate Values", research.culture_and_values),
        ("## Recent News & Notable Milestones", research.recent_news),
    ]
    for title, items in sections:
        if items:
            lines.append(title)
            lines.extend(f"- {item}" for item in items)
            lines.append("")

    lines.extend(["## Role Strategic Importance", research.role_importance, ""])

    if research.interview_process and research.interview_process.stages:
        status = (
            "Verified via research"
            if research.interview_process.known_from_research
            else "Industry-typical expectations"
        )
        lines.extend([f"## Interview Process ({status})", ""])
        for idx, stage in enumerate(research.interview_process.stages, 1):
            lines.extend([
                f"### Stage {idx}: {stage.stage_name}",
                f"**Description**: {stage.description}",
                f"**What to expect**: {stage.what_to_expect}",
                "",
            ])

    return "\n".join(lines).strip() + "\n"


def render_match_analysis_markdown(
    match: ProfileMatchAnalysis,
    position: str = "",
    company: str = "",
) -> str:
    """Format 6-pillar match and gap evaluation as Markdown."""
    target = " at ".join(filter(None, [position, company]))
    lines = ["# Profile-Role Match & Gap Analysis"]
    if target:
        lines.append(f"**Target Role**: {target}")
    lines.extend([
        f"**Overall Match Fit Score**: {match.match_score}/100",
        "",
        "## Recruiter Assessment & Verdict",
        match.summary,
        "",
    ])

    if match.breakdown:
        lines.append("## 6-Pillar Completeness Breakdown")
        if match.breakdown.overall_reasoning:
            lines.append(f"**Score Rationale**: {match.breakdown.overall_reasoning}\n")
        for cat in match.breakdown.categories:
            lines.append(f"- **{cat['name']}**: {cat['match'].score}/10 — {cat['match'].explanation}")
        lines.append("")

    if match.strengths:
        lines.append(f"## Verified Strengths ({len(match.strengths)} matches)")
        for s in match.strengths:
            lines.extend([f"### {s.skill} ({s.category})", f"- **Evidence Found**: {s.evidence_found}"])
        lines.append("")

    if match.gaps:
        lines.append(f"## Identified Gaps & Mitigation ({len(match.gaps)} areas)")
        for g in match.gaps:
            lines.extend([f"### {g.requirement} [{g.severity.upper()} impact]", f"- **Mitigation Advice**: {g.mitigation_tip}"])
        lines.append("")

    if match.tailoring_strategy:
        lines.append("## Strategic Tailoring Blueprint")
        lines.extend(f"- {t}" for t in match.tailoring_strategy)
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def generate_application_zip(
    kit: ApplicationKit,
    inputs: GenerateInputs | None = None,
) -> tuple[bytes, str]:
    """Generate complete ZIP bundle of all application documentation.

    Zip file and all internal files strictly follow the naming standard:
      {initials}_{position}_{company}.zip
      {initials}_{position}_{company}_resume.pdf
      {initials}_{position}_{company}_resume.md
      {initials}_{position}_{company}_cover_letter.pdf
      {initials}_{position}_{company}_cover_letter.md
      {initials}_{position}_{company}_cover_letter.txt
      {initials}_{position}_{company}_interview_prep.md
      {initials}_{position}_{company}_tips.md
      {initials}_{position}_{company}_company_research.md
      {initials}_{position}_{company}_match_analysis.md

    Returns:
      tuple of (zip_bytes, zip_filename)
    """
    from app.services.pdf import render_cover_letter_pdf, render_resume_pdf

    filenames = get_application_filenames(kit, inputs)
    pos, comp = filenames["position"], filenames["company"]

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        for name, fn in [
            (filenames["resume_pdf_name"], lambda: render_resume_pdf(kit)),
            (filenames["cover_letter_pdf_name"], lambda: render_cover_letter_pdf(kit, company=comp, position=pos)),
        ]:
            try:
                zf.writestr(name, fn())
            except Exception as exc:
                logger.warning("Could not render %s for zip: %s", name, exc)

        docs = [
            (filenames["resume_md_name"], render_resume_markdown(kit.tailored_resume)),
            (filenames["cover_letter_md_name"], render_cover_letter_markdown(kit.cover_letter, kit.tailored_resume, company=comp, position=pos)),
            (filenames["cover_letter_txt_name"], render_cover_letter_text(kit.cover_letter, kit.tailored_resume, company=comp, position=pos)),
            (filenames["interview_prep_md_name"], render_interview_prep_markdown(kit.interview_prep, position=pos, company=comp)),
            (filenames["tips_md_name"], render_tips_markdown(kit.tips, target_country=TARGET_COUNTRY)),
        ]
        if kit.company_research and kit.company_research.overview.strip():
            docs.append((filenames["company_research_md_name"], render_company_research_markdown(kit.company_research, company=comp)))
        if kit.match_analysis:
            docs.append((filenames["match_analysis_md_name"], render_match_analysis_markdown(kit.match_analysis, position=pos, company=comp)))

        for fname, content in docs:
            zf.writestr(fname, content)

    return buffer.getvalue(), filenames["zip_name"]
