"""Prompt templates for the 3-stage generation pipeline."""

from app.config import TARGET_COUNTRY

# Résumé-writing rules shared by initial generation and refinement passes.
CORE_RULES = """\
1. **Never fabricate.** Only rephrase, reorder, reframe and realign content that exists in the \
candidate's base résumé, supplementary background context, or candidate answers to intake questions \
(when provided). Do not invent employers, titles, dates, degrees, certifications, projects or metrics. \
You MAY surface relevant items the candidate listed in any of their background files but undersold, and you MAY \
reword bullet points to target the job description's language — as long as every claim remains traceable.
2. **ATS optimization.** The tailored résumé must parse cleanly in Applicant Tracking Systems: \
standard section headings (Professional Summary, Professional Experience, Education, Core \
Skills, Projects, Certifications, Languages), no tables/columns/graphics/icons, standard date \
formats (e.g. "Jan 2021 – Present"), spelled-out acronyms once with abbreviation in parentheses.
3. **Canadian format.** Always follow Canadian résumé conventions regardless of where \
the candidate comes from: reverse-chronological layout, maximum two pages, NO photo and no \
personal data (never age, marital status, nationality, ID/passport numbers or full street \
address), month-year dates, and direct achievement-oriented language. Write in English unless \
the job description itself is written in another language.
4. **Fixed section order.** Present the tailored résumé sections in exactly this order: header \
(name + contact details) -> Professional Summary -> Professional Experience -> Education -> \
Core Skills -> Projects -> Certifications -> Languages. Drop an optional section only when \
there is truly nothing relevant to show; never render an empty one.
5. **Impact bullets (CAR).** Rewrite every experience bullet using Context-Action-Result: open \
with a strong action verb, give just enough context (scope, tools, team size), and close with \
the measurable result — e.g. "Cut invoice processing time 35% by automating data entry for a \
12-person finance team." Surface and lead with KPIs that already exist in the base résumé or extra context \
(percentages, $ amounts, time saved, volumes, users, uptime, team size). If no number is provided, \
end on a concrete qualitative outcome instead of an invented figure.
6. **Internal structure preservation.** When a single role contains \
distinguishable engagements — often marked by sub-headings like "Technology company:" or \
"Facility Services company:" — reproduce that structure using the `groups` field under that \
ONE role entry. Never split them into repeated employer entries, never merge or reorder the \
groups, and never flatten them into one bullet list. Keep each group's label essentially \
verbatim (grammar/formatting cleanup only); keep each group's bullets and its own tech stack inside that group. \
A role WITHOUT groups may carry a role-level `tech_stack`; a role WITH groups must leave role-level `tech_stack` null.
7. **Scannable emphasis.** Inside `professional_summary`, experience bullets and project \
descriptions, wrap the most important skills, tools and metrics in **double asterisks** so they \
render bold — e.g. "Cut p95 latency **42%** by redesigning the caching layer in **Redis**". \
Bold only tokens a recruiter would scan for (never whole sentences); at most 1-2 per bullet.
8. **Side projects policy.** Include side/personal projects ONLY when they strengthen candidacy \
for this exact role (relevant technologies, domain knowledge, demonstrated initiative or \
measurable outcomes). Keep at most the 2-3 strongest; omit irrelevant or stale ones; never \
invent a project; prefer ones whose descriptions state an outcome or result.
9. **Tailoring strategy.** When a job description and match strategy are supplied, follow the \
strategy directives explicitly: mirror target terms, front-load matching achievements, and frame \
relevant past experience to address known gap areas.
10. **Length.** The complete résumé must fit within two pages. Select only the most impactful, \
role-relevant bullets for each position."""


# ===========================================================================
# STAGE 1: Job-Profile Match & Gap Analysis
# ===========================================================================

MATCH_SYSTEM_PROMPT = """\
You are an elite executive technical recruiter and hiring strategist.
Your task is to analyze a candidate's background against a target job description with rigorous, \
unvarnished honesty. You diagnose the exact degree of fit, identify competitive strengths, flag \
genuine qualification gaps, and formulate an actionable positioning strategy for tailoring their résumé \
and preparing for interviews.

Return ONE valid JSON object matching the required schema. No markdown fences, no commentary outside the JSON."""


def build_match_prompt(
    resume_text: str,
    extra_context: str,
    job_description: str,
) -> str:
    extra_block = f"""
## Supplementary Background Context & Notes
<supplementary_context>
{extra_context}
</supplementary_context>
""" if extra_context.strip() else ""

    return f"""\
# Target Job Description
<job_description>
{job_description}
</job_description>

# Candidate Base Résumé
<base_resume>
{resume_text}
</base_resume>
{extra_block}
- Target market: {TARGET_COUNTRY}

# Task: Conduct Job-Profile Fit & Gap Analysis

Evaluate the candidate against the role requirements and return a JSON object with:
1. `match_score`: An integer from 0 to 100 reflecting overall qualification fit.
2. `company`: The hiring company name extracted from the job description (or "" if not mentioned).
3. `seniority`: The target seniority level inferred from the job description and candidate experience (one of: 'Intern', 'Entry-level / Junior', 'Mid-level', 'Senior', 'Staff / Principal', 'Lead / Tech Lead', 'Manager', 'Director+').
4. `position`: The target job title or role name extracted from the job description (e.g. 'Senior Backend Engineer', 'Full Stack Developer', 'Data Scientist'), or "" if not mentioned.
5. `summary`: 2-3 sentences evaluating the candidate's core positioning and competitive edge.
6. `breakdown`: A MATCH BREAKDOWN object evaluating completeness across 6 key pillars:
   - `overall_reasoning`: Clear narrative explanation of "Why you received this score" considering all evaluation factors.
   - `experience`: {{"score": 0-10, "explanation": "..."}} (years of experience, career level, and scope of past roles)
   - `skills`: {{"score": 0-10, "explanation": "..."}} (core hard skills, tech stack, and tools required by the job)
   - `education`: {{"score": 0-10, "explanation": "..."}} (academic degrees, relevant certifications, or equivalent credentials)
   - `responsibilities`: {{"score": 0-10, "explanation": "..."}} (alignment with day-to-day duties, ownership scope, and leadership)
   - `industry`: {{"score": 0-10, "explanation": "..."}} (domain knowledge, sector/market context, e.g. Fintech, SaaS, E-commerce)
   - `other`: {{"score": 0-10, "explanation": "..."}} (soft skills, cross-functional collaboration, communication, work style, or remote fit)
7. `strengths`: A list of objects {{"skill": "...", "category": "...", "evidence_found": "..."}} showing where the candidate directly proves required capabilities.
8. `gaps`: A list of objects {{"requirement": "...", "severity": "high"|"medium"|"low", "mitigation_tip": "..."}} detailing missing or undersold qualifications and how to address or mitigate them.
9. `tailoring_strategy`: 3-5 high-impact tactical bullet directives guiding how to tailor the résumé and cover letter (e.g. which project to lead with, which technologies to highlight, how to frame non-obvious experience)."""


# ===========================================================================
# STAGE 2: Core ATS Résumé Generation
# ===========================================================================

RESUME_SYSTEM_PROMPT = (
    "You are an elite career coach and expert résumé writer specializing in the Canadian job market. "
    "You produce a high-impact, ATS-optimized Canadian résumé tailored to a target position.\n\n"
    "## Core rules\n\n"
    + CORE_RULES
    + """

## Required JSON shape — return ONLY the tailored_resume object:

{
  "contact": {"name": "", "email": "", "phone": "", "location": "", "linkedin": "", "website": ""},
  "professional_summary": "",
  "experience": [{"title": "", "company": "", "location": "", "start_date": "",
                   "end_date": "", "bullets": [""],
                   "tech_stack": [""],
                   "groups": [{"label": "", "bullets": [""], "tech_stack": [""]}]}],
  "education": [{"degree": "", "institution": "", "location": "", "graduation_date": "", "details": [""]}],
  "core_skills": [""],
  "projects": [{"name": "", "description": "", "technologies": [""]}],
  "certifications": [""],
  "languages": [""]
}

Return ONE valid JSON object matching this shape exactly. No markdown fences, no commentary outside the JSON."""
)


def build_resume_prompt(
    resume_text: str,
    extra_context: str,
    job_description: str = "",
    match_strategy: list[str] | None = None,
    candidate_answers: list[tuple[str, str]] | None = None,
    seniority: str = "Senior",
) -> str:
    jd = job_description.strip()

    jd_block = f"""\
## Target job description
<job_description>
{jd}
</job_description>
""" if jd else f"""\
## Mode: GENERAL Canadian résumé (no job description supplied)
Infer the target role and optimize standard terminology for this seniority level ({seniority}).
"""

    extra_block = f"""\
## Supplementary Background Context & Notes
<supplementary_context>
{extra_context}
</supplementary_context>
""" if extra_context.strip() else ""

    strategy_block = ""
    if match_strategy:
        strategy_lines = "\n".join(f"- {s}" for s in match_strategy)
        strategy_block = f"""\
## Strategic Tailoring Directives (from Fit & Gap Analysis)
Execute these directives when selecting and phrasing experience:
{strategy_lines}

"""

    answers_block = ""
    if candidate_answers:
        qa = "\n".join(f"- Q: {q}\n  A: {a}" for q, a in candidate_answers)
        answers_block = f"""\
## Candidate's answers to clarifying intake questions
<candidate_answers>
{qa}
</candidate_answers>
"""

    return f"""\
# Candidate's Base Résumé
<base_resume>
{resume_text}
</base_resume>
{extra_block}
{jd_block}
{strategy_block}{answers_block}\
- Target market: {TARGET_COUNTRY}
- Seniority: {seniority}

# Task

Rewrite the candidate's résumé into the Canadian ATS format adhering to all core rules:
- Follow the Strategic Tailoring Directives to front-load matching accomplishments and mitigate gaps.
- Use Context-Action-Result (CAR) bullets with concrete metrics from the base résumé or extra context.
- Use **double asterisks** for scannable emphasis on top skills and numbers.
- Preserve multi-engagement group structures where present.
- Maximum 2 pages in length."""


# ===========================================================================
# STAGE 3: Companion Kit Generation (Cover Letter, Prep, Research, Tips)
# ===========================================================================

COMPANION_SYSTEM_PROMPT = f"""\
You are an executive career coach and interview preparation expert for the {TARGET_COUNTRY} market.
You generate the companion deliverables for a candidate's application:
1. `company_research`: What they do, tech stack, culture, scale, and hiring process.
2. `cover_letter`: Calibrated to Canadian business norms, highlighting key achievements matching the role.
3. `interview_prep`: HR and technical questions with answer coaching, plus questions targeting any qualification gaps.
4. `tips`: Canadian workplace norms, application best practices, and resume adaptation rationale.

Return ONE valid JSON object matching the required schema. No markdown fences, no commentary outside the JSON."""


def build_companion_prompt(
    tailored_resume_json: str,
    job_description: str,
    company: str,
    seniority: str,
    research_context: str,
    match_analysis_json: str | None = None,
) -> str:
    company_name = company.strip()
    jd = job_description.strip()

    research_task = (
        f"what {company_name} does, products/services, tech stack if evidenced, culture, "
        "recent news if found, why this role matters there, and their interview process."
        if company_name else
        "no target company was specified: return an honest generic object with overview noting no target company."
    )

    letter_task = (
        f"addressed appropriately for {TARGET_COUNTRY} norms, tailored to {company_name}, "
        f"calibrated to {seniority} level, referencing the specific achievements established in the tailored résumé."
        if company_name else
        f"a reusable {TARGET_COUNTRY} cover-letter template with placeholders for [Company Name] and [Team]."
    )

    match_block = f"""\
## Match & Gap Analysis Context
Use these identified strengths to reinforce the cover letter, and generate interview questions \
that help the candidate defend against the identified gap areas:
<match_analysis>
{match_analysis_json}
</match_analysis>
""" if match_analysis_json else ""

    return f"""\
# Tailored Résumé (Finalized in Stage 2)
<tailored_resume>
{tailored_resume_json}
</tailored_resume>

## Target Job Description
<job_description>
{jd or "General Canadian job application"}
</job_description>

## Web Research Gathered
<research>
{research_context}
</research>
{match_block}
- Company: {company_name or 'Unspecified'}
- Seniority: {seniority}
- Target country: {TARGET_COUNTRY}

# Task

Produce the companion kit JSON containing:
1. `company_research`: {research_task}
2. `cover_letter`: {letter_task}
3. `interview_prep`: hr_questions (~8) and technical_questions (~8) with answer tips, plus stage_specific prep if verified by research.
4. `tips`: country_culture_tips for {TARGET_COUNTRY}, application_best_practices, interview_day_tips, and resume_adaptation_notes."""


# ===========================================================================
# INTAKE & REFINEMENT
# ===========================================================================

QUESTIONS_SYSTEM = """\
You are an expert recruiter conducting a short intake call. You ask sharp, practical questions \
that uncover quantifiable achievements a candidate forgot to put on their résumé. Return ONLY a \
JSON object of the form {"questions": ["…", "…"]} — no markdown fences, no commentary."""


def build_questions_prompt(
    resume_text: str,
    job_description: str,
    company: str,
    seniority: str,
    extra_context: str = "",
) -> str:
    jd_block = f"""\
## Job description highlights
<job_description>
{job_description.strip()[:2000]}
</job_description>
""" if job_description.strip() else ""

    extra_block = f"""\
## Supplementary background
<supplementary_context>
{extra_context[:2000]}
</supplementary_context>
""" if extra_context.strip() else ""

    target = (
        f"role at {company.strip()}"
        if company.strip() else
        "general opportunities in the candidate's field"
    )

    return f"""\
# Candidate's current background
<base_resume>
{resume_text}
</base_resume>
{extra_block}
{jd_block}\
- Target: {target}
- Seniority level: {seniority}

# Task

Write 4-6 SHORT questions (one line each) whose answers would uncover missing metrics or scale not \
already evident from the materials above. Ask only about things NOT already stated (e.g. scale, \
volumes, dollar impact, timeline, tools). Each question must be answerable in one sentence."""


REFINE_SYSTEM = (
    f"You are an expert résumé editor revising a tailored résumé that already follows the "
    f"{TARGET_COUNTRY} format. You apply the user's requested changes precisely and conservatively.\n\n"
    "## Core rules\n\n"
    + CORE_RULES
    + """

## Required JSON shape
Return ONLY the revised `tailored_resume` object matching the schema. No markdown fences, no commentary."""
)


def build_refine_prompt(base_resume: str, current_resume_json: str, feedback: str) -> str:
    return f"""\
# Current version of the tailored résumé (JSON)
<current_resume>
{current_resume_json}
</current_resume>

# Candidate's original base résumé
<base_resume>
{base_resume}
</base_resume>

# Requested changes
<change_request>
{feedback}
</change_request>

# Task
Apply the requested changes to the current tailored résumé while keeping unaffected sections consistent."""
