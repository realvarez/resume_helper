import pytest
from pydantic import ValidationError
from app.schemas import (
    CategoryMatch,
    ExperienceGroup,
    ExperienceItem,
    GenerateInputs,
    MatchBreakdown,
    ProfileMatchAnalysis,
)


def test_generate_inputs_defaults():
    inputs = GenerateInputs(resume_text="My Resume")
    assert inputs.resume_text == "My Resume"
    assert inputs.extra_context == ""
    assert inputs.job_description == ""
    assert inputs.company == ""
    assert inputs.seniority == ""
    assert inputs.position == ""


def test_experience_item_deduplicates_bullets():
    group = ExperienceGroup(
        label="Client A",
        bullets=["Led development of cloud pipeline.", "Optimized SQL queries by 30%."],
    )
    # Role-level bullets contain an exact duplicate (with varied whitespace/casing) and a unique bullet
    role = ExperienceItem(
        title="Software Engineer",
        company="Acme Corp",
        start_date="2021",
        end_date="Present",
        bullets=[
            "  LED DEVELOPMENT OF CLOUD PIPELINE.  ",
            "Mentored junior engineers.",
        ],
        groups=[group],
    )
    # The duplicate should be stripped, keeping only the unique bullet
    assert len(role.bullets) == 1
    assert role.bullets[0] == "Mentored junior engineers."


def test_experience_item_clears_role_tech_stack_when_grouped():
    group = ExperienceGroup(
        label="Client A",
        bullets=["Engineered API."],
        tech_stack=["Python", "FastAPI"],
    )
    role = ExperienceItem(
        title="Consultant",
        company="Acme Corp",
        start_date="2021",
        end_date="Present",
        groups=[group],
        tech_stack=["Python", "Docker"],  # Should be cleared because groups exist
    )
    assert role.tech_stack is None


def test_experience_item_requires_bullets_or_groups():
    with pytest.raises(ValidationError, match="an experience entry needs bullets or groups with bullets"):
        ExperienceItem(
            title="Dev",
            company="Acme",
            start_date="2020",
            end_date="2021",
            bullets=[],
            groups=[],
        )


def test_match_breakdown_categories_property():
    cat = CategoryMatch(score=8, explanation="Solid performance")
    breakdown = MatchBreakdown(
        overall_reasoning="Good match",
        experience=cat,
        skills=cat,
        education=cat,
        responsibilities=cat,
        industry=cat,
        other=cat,
    )
    cats = breakdown.categories
    assert len(cats) == 6
    names = [c["name"] for c in cats]
    assert names == ["Experience", "Skills", "Responsibilities", "Industry", "Education", "Other"]
    assert all("icon" in c and "match" in c for c in cats)


def test_profile_match_analysis_defaults():
    analysis = ProfileMatchAnalysis(
        match_score=85,
        summary="Great candidate",
        strengths=[],
        gaps=[],
        tailoring_strategy=[],
    )
    assert analysis.seniority == "Mid-level"
    assert analysis.company == ""
    assert analysis.position == ""


def test_application_kit_full_validation(sample_application_kit):
    assert sample_application_kit.tailored_resume.contact.name == "Ricardo Alvarez"
    assert sample_application_kit.match_analysis.match_score == 88
    assert len(sample_application_kit.company_research.products_and_services) > 0
    assert sample_application_kit.cover_letter.greeting.startswith("Dear")
    assert len(sample_application_kit.interview_prep.hr_questions) > 0
    assert len(sample_application_kit.tips.country_culture_tips) > 0
