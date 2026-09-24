"""Request forms and the structured LLM output schema.

``ApplicationKit`` is the single JSON object the LLM must return; every
deliverable shown in the UI / PDF is a field of this model.
"""
import re

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Form inputs (POST /generate)
# ---------------------------------------------------------------------------

class GenerateInputs(BaseModel):
    resume_text: str
    extra_context: str = ""  # Consolidated text from supporting files and notes
    # Empty job description => general Canadian-format résumé (no targeting).
    # Empty company => skip company research; cover letter becomes a reusable template.
    job_description: str = ""
    company: str = ""
    seniority: str = ""
    position: str = ""


# ---------------------------------------------------------------------------
# Tailored résumé
# ---------------------------------------------------------------------------

class ContactInfo(BaseModel):
    name: str
    email: str | None = None
    phone: str | None = None
    location: str | None = None
    linkedin: str | None = None
    website: str | None = None


class ExperienceGroup(BaseModel):
    """One distinguishable engagement inside a single role (e.g. per-client work)."""

    label: str = Field(
        description="Engagement/client/division label taken from the base résumé, "
                    "e.g. 'Technology company'"
    )
    bullets: list[str] = Field(
        description="CAR-format bullets (Context, Action, Result): strong action verb, "
                    "brief context, quantified impact/KPI drawn from the base résumé"
    )
    tech_stack: list[str] | None = None


class ExperienceItem(BaseModel):
    title: str
    company: str
    location: str | None = None
    start_date: str
    end_date: str = Field(description="'Present' if current role")
    bullets: list[str] = Field(
        default_factory=list,
        description="Role-level bullets outside any group; empty when the role is "
                    "entirely grouped",
    )
    tech_stack: list[str] | None = Field(
        default=None,
        description="Role-wide tech stack (from the base résumé's Stack line); "
                    "MUST be null when the role has groups — each group carries its own",
    )
    groups: list[ExperienceGroup] | None = None

    @model_validator(mode="after")
    def _validate_role(self) -> "ExperienceItem":
        if not self.bullets and not (self.groups and any(g.bullets for g in self.groups)):
            raise ValueError("an experience entry needs bullets or groups with bullets")
        # Models sometimes echo a group's bullets at role level too, rendering them
        # twice; drop flat bullets that duplicate a group bullet (normalized compare).
        if self.groups and self.bullets:
            group_bullets = {
                re.sub(r"\s+", " ", b).strip().lower()
                for g in self.groups for b in g.bullets
            }
            self.bullets = [
                b for b in self.bullets
                if re.sub(r"\s+", " ", b).strip().lower() not in group_bullets
            ]
        # A role-level stack next to per-group stacks would render duplicate
        # information; grouped roles keep their stacks inside the groups only.
        if self.groups and self.tech_stack:
            self.tech_stack = None
        return self


class EducationItem(BaseModel):
    degree: str
    institution: str
    location: str | None = None
    graduation_date: str | None = None
    details: list[str] | None = None


class ProjectItem(BaseModel):
    name: str
    description: str = Field(
        description="What it does, technologies used and the concrete outcome/impact; "
                    "include only role-relevant side projects"
    )
    technologies: list[str] | None = None


# Field order mirrors the fixed Canadian section order:
# header/contact -> summary -> experience -> education -> skills -> projects
# -> certifications -> languages.
class TailoredResume(BaseModel):
    contact: ContactInfo
    professional_summary: str = Field(description="2-3 sentences aligned to the target role")
    experience: list[ExperienceItem]
    education: list[EducationItem] | None = None
    core_skills: list[str]
    projects: list[ProjectItem] | None = None
    certifications: list[str] | None = None
    languages: list[str] | None = None


# ---------------------------------------------------------------------------
# Company research
# ---------------------------------------------------------------------------

class InterviewStage(BaseModel):
    stage_name: str
    description: str
    what_to_expect: str


class InterviewProcess(BaseModel):
    known_from_research: bool = Field(
        description="True only if based on real findings about THIS company, "
                    "False if industry-typical assumption"
    )
    stages: list[InterviewStage] = Field(default_factory=list)


class CompanyResearch(BaseModel):
    overview: str = Field(description="What the company does, market, scale")
    products_and_services: list[str] = Field(default_factory=list)
    tech_stack: list[str] | None = None
    culture_and_values: list[str] | None = None
    recent_news: list[str] | None = None
    role_importance: str = Field(description="Why this role matters to the company's goals")
    interview_process: InterviewProcess | None = None


# ---------------------------------------------------------------------------
# Cover letter & interview prep
# ---------------------------------------------------------------------------

class CoverLetter(BaseModel):
    greeting: str
    body: list[str] = Field(description="Letter paragraphs in order")
    closing: str


class QuestionAdvice(BaseModel):
    question: str
    why_they_ask: str | None = None
    answer_tips: str


class StagePrep(BaseModel):
    """Per-stage question set used when a real interview process is known."""
    stage_name: str
    questions: list[QuestionAdvice]


class InterviewQuestions(BaseModel):
    hr_questions: list[QuestionAdvice]
    technical_questions: list[QuestionAdvice]
    stage_specific: list[StagePrep] | None = Field(
        default=None,
        description="Fill ONLY when interview_process.known_from_research is true; "
                    "one entry per real interview stage",
    )


# ---------------------------------------------------------------------------
# Tips
# ---------------------------------------------------------------------------

class TipsSection(BaseModel):
    country_culture_tips: list[str] = Field(description="Workplace/country-specific norms")
    application_best_practices: list[str]
    interview_day_tips: list[str] | None = None
    resume_adaptation_notes: list[str] = Field(
        description="How and why the résumé was adapted from the original"
    )


# ---------------------------------------------------------------------------
# Match & Gap Analysis (Stage 1)
# ---------------------------------------------------------------------------

class SkillMatch(BaseModel):
    skill: str = Field(description="Skill, tool, or qualification matched")
    category: str = Field(description="Category: 'Core Skill', 'Tool / Tech', 'Domain', 'Leadership'")
    evidence_found: str = Field(description="Specific evidence or metric found in the candidate background")


class GapDetail(BaseModel):
    requirement: str = Field(description="Job requirement missing or undersold in candidate background")
    severity: str = Field(description="'high', 'medium', or 'low'")
    mitigation_tip: str = Field(description="Concrete advice on how candidate should address or frame this in resume/interviews")


class CategoryMatch(BaseModel):
    score: int = Field(ge=0, le=10, description="Completeness score out of 10 (e.g. 5 for 5/10, 8 for 8/10)")
    explanation: str = Field(description="Why the candidate received this score, citing what matched vs what is missing")


class MatchBreakdown(BaseModel):
    overall_reasoning: str = Field(
        description="Comprehensive summary explaining 'Why you received this score' based on all factors"
    )
    experience: CategoryMatch = Field(
        description="Score and evaluation for years of experience, career level, and scope of past roles"
    )
    skills: CategoryMatch = Field(
        description="Score and evaluation for core technical skills, hard skills, tools, and methodologies"
    )
    education: CategoryMatch = Field(
        description="Score and evaluation for degrees, academic background, or equivalent credentials"
    )
    responsibilities: CategoryMatch = Field(
        description="Score and evaluation for demonstrated responsibilities, scope of ownership, and day-to-day deliverables"
    )
    industry: CategoryMatch = Field(
        description="Score and evaluation for domain/industry alignment (e.g. Fintech, E-commerce, SaaS, Healthcare)"
    )
    other: CategoryMatch = Field(
        description="Score and evaluation for other requirements: soft skills, cultural fit, language proficiency, remote/location fit"
    )

    @property
    def categories(self) -> list[dict]:
        return [
            {"name": "Experience", "match": self.experience, "icon": "💼"},
            {"name": "Skills", "match": self.skills, "icon": "🛠️"},
            {"name": "Responsibilities", "match": self.responsibilities, "icon": "📋"},
            {"name": "Industry", "match": self.industry, "icon": "🏢"},
            {"name": "Education", "match": self.education, "icon": "🎓"},
            {"name": "Other", "match": self.other, "icon": "✨"},
        ]


class ProfileMatchAnalysis(BaseModel):
    match_score: int = Field(description="Overall fit score from 0 to 100")
    company: str = Field(default="", description="Target company name inferred from the job description, or empty string if not detected")
    seniority: str = Field(default="Mid-level", description="Inferred target seniority level, e.g. 'Intern', 'Junior', 'Mid-level', 'Senior', 'Lead', 'Staff', 'Director'")
    position: str = Field(default="", description="Target job title or position inferred from the job description, e.g. 'Senior Backend Engineer', 'Full Stack Developer'")
    summary: str = Field(description="Executive recruiter verdict on candidate fit and positioning strategy")
    breakdown: MatchBreakdown | None = Field(
        default=None,
        description="Breakdown of match completeness across Experience, Skills, Education, Responsibilities, Industry, and Other, each rated out of 10",
    )
    strengths: list[SkillMatch] = Field(description="Key strengths matching the job requirements")
    gaps: list[GapDetail] = Field(description="Identified gaps or missing qualifications and mitigation advice")
    tailoring_strategy: list[str] = Field(
        description="Key strategic guidelines for how the tailored resume and cover letter should position the candidate"
    )


# ---------------------------------------------------------------------------
# Companion Kit (Stage 3)
# ---------------------------------------------------------------------------

class CompanionKit(BaseModel):
    company_research: CompanyResearch
    cover_letter: CoverLetter
    interview_prep: InterviewQuestions
    tips: TipsSection


# ---------------------------------------------------------------------------
# Complete Application Kit Deliverable
# ---------------------------------------------------------------------------

class ApplicationKit(BaseModel):
    match_analysis: ProfileMatchAnalysis | None = None
    tailored_resume: TailoredResume
    company_research: CompanyResearch
    cover_letter: CoverLetter
    interview_prep: InterviewQuestions
    tips: TipsSection


# ---------------------------------------------------------------------------
# Optional pre-generation intake
# ---------------------------------------------------------------------------

class ClarifyingQuestions(BaseModel):
    """Short questions shown before generation to surface missing KPIs/scope."""

    questions: list[str] = Field(
        description="4-6 short, specific questions about responsibilities, scale and "
                    "measurable outcomes NOT already evident from the résumé"
    )
