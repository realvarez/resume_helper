import pytest
from app.schemas import (
    ApplicationKit,
    CategoryMatch,
    CompanyResearch,
    ContactInfo,
    CoverLetter,
    EducationItem,
    ExperienceGroup,
    ExperienceItem,
    GapDetail,
    GenerateInputs,
    InterviewProcess,
    InterviewQuestions,
    InterviewStage,
    MatchBreakdown,
    ProfileMatchAnalysis,
    ProjectItem,
    QuestionAdvice,
    SkillMatch,
    StagePrep,
    TailoredResume,
    TipsSection,
)


@pytest.fixture
def sample_contact_info() -> ContactInfo:
    return ContactInfo(
        name="Ricardo Alvarez",
        email="ricardo@example.com",
        phone="+1 555-0199",
        location="Toronto, ON",
        linkedin="https://linkedin.com/in/ricardo",
        website="https://ricardo.dev",
    )


@pytest.fixture
def sample_experience_item() -> ExperienceItem:
    return ExperienceItem(
        title="Senior Software Engineer",
        company="TechCorp Inc.",
        location="Toronto, ON",
        start_date="2022",
        end_date="Present",
        bullets=[
            "Architected high-throughput microservices using Python and FastAPI, reducing latency by 40%.",
            "Led team of 5 engineers to deliver cloud-native data pipelines.",
        ],
        tech_stack=["Python", "FastAPI", "Docker", "PostgreSQL"],
    )


@pytest.fixture
def sample_grouped_experience_item() -> ExperienceItem:
    return ExperienceItem(
        title="Lead Consultant",
        company="Consulting Partners",
        location="Remote",
        start_date="2020",
        end_date="2022",
        groups=[
            ExperienceGroup(
                label="Enterprise Banking Client",
                bullets=["Built real-time fraud detection engine handling 10k TPS."],
                tech_stack=["Python", "Kafka"],
            ),
            ExperienceGroup(
                label="Retail Client",
                bullets=["Automated order fulfillment reducing manual labor by 30%."],
                tech_stack=["FastAPI", "Redis"],
            ),
        ],
    )


@pytest.fixture
def sample_tailored_resume(sample_contact_info, sample_experience_item) -> TailoredResume:
    return TailoredResume(
        contact=sample_contact_info,
        professional_summary="Results-driven Senior Software Engineer with 8+ years building distributed backend systems in Canadian tech.",
        experience=[sample_experience_item],
        education=[
            EducationItem(
                degree="B.S. in Computer Science",
                institution="University of Toronto",
                location="Toronto, ON",
                graduation_date="2018",
                details=["Dean's List", "Specialization in Distributed Systems"],
            )
        ],
        core_skills=["Python", "FastAPI", "PostgreSQL", "Docker", "AWS", "CI/CD"],
        projects=[
            ProjectItem(
                name="CloudQueue",
                description="Distributed message broker built in Python.",
                technologies=["Python", "Redis", "Asyncio"],
            )
        ],
        certifications=["AWS Certified Solutions Architect"],
        languages=["English (Fluent)", "Spanish (Native)"],
    )


@pytest.fixture
def sample_company_research() -> CompanyResearch:
    return CompanyResearch(
        overview="Shopify is a leading global commerce platform empowering millions of merchants.",
        products_and_services=["Online storefronts", "Shopify POS", "Shopify Payments"],
        tech_stack=["Ruby on Rails", "Python", "React", "Kafka", "Google Cloud"],
        culture_and_values=["Be a constant learner", "Default to open", "Make commerce better"],
        recent_news=["Expanded AI merchant tools and enterprise offerings."],
        role_importance="Critical role to enhance platform scalability and merchant checkout speed.",
        interview_process=InterviewProcess(
            known_from_research=True,
            stages=[
                InterviewStage(
                    stage_name="Life Story Screening",
                    description="45-minute recruiter conversation on career trajectory and values.",
                    what_to_expect="Focus on self-reflection, motivations, and impact.",
                ),
                InterviewStage(
                    stage_name="Technical Deep Dive",
                    description="System design and coding session with senior engineering peers.",
                    what_to_expect="Pair programming in your language of choice.",
                ),
            ],
        ),
    )


@pytest.fixture
def sample_cover_letter() -> CoverLetter:
    return CoverLetter(
        greeting="Dear Shopify Hiring Team,",
        body=[
            "I am excited to apply for the Senior Backend Engineer position at Shopify.",
            "With over 8 years of engineering experience developing high-scale systems in Canada, I bring deep expertise in cloud architectures.",
            "I look forward to discussing how my background aligns with Shopify's mission.",
        ],
        closing="Sincerely,",
    )


@pytest.fixture
def sample_interview_questions() -> InterviewQuestions:
    return InterviewQuestions(
        hr_questions=[
            QuestionAdvice(
                question="Why Shopify?",
                why_they_ask="To assess alignment with commerce mission and merchant empathy.",
                answer_tips="Emphasize admiration for merchant empowerment and scale.",
            )
        ],
        technical_questions=[
            QuestionAdvice(
                question="How do you handle distributed transactions across microservices?",
                why_they_ask="Evaluates distributed systems architecture knowledge.",
                answer_tips="Discuss Saga pattern, two-phase commits, and idempotency keys.",
            )
        ],
        stage_specific=[
            StagePrep(
                stage_name="Life Story Screening",
                questions=[
                    QuestionAdvice(
                        question="Tell me about your career journey and biggest turning point.",
                        answer_tips="Follow chronological arc highlighting intentional career decisions.",
                    )
                ],
            )
        ],
    )


@pytest.fixture
def sample_tips_section() -> TipsSection:
    return TipsSection(
        country_culture_tips=[
            "Canadian workplaces value collaborative consensus and egalitarian communication.",
            "Avoid listing personal details like photo, marital status, or age.",
        ],
        application_best_practices=[
            "Submit ATS-friendly single-column format.",
            "Quantify results using Canadian spelling conventions where applicable.",
        ],
        interview_day_tips=["Test webcam lighting and prepare questions about team culture."],
        resume_adaptation_notes=[
            "Restructured experience bullets to emphasize measurable metrics and CAR framework."
        ],
    )


@pytest.fixture
def sample_match_analysis() -> ProfileMatchAnalysis:
    return ProfileMatchAnalysis(
        match_score=88,
        company="Shopify",
        seniority="Senior",
        position="Senior Backend Engineer",
        summary="Candidate shows strong alignment with Shopify's high-throughput backend needs.",
        breakdown=MatchBreakdown(
            overall_reasoning="Strong technical alignment with Python and distributed architectures.",
            experience=CategoryMatch(score=9, explanation="8+ years exceeding 5+ year requirement."),
            skills=CategoryMatch(score=9, explanation="Strong Python and cloud data systems experience."),
            responsibilities=CategoryMatch(score=8, explanation="Proven tech leadership and architecture."),
            industry=CategoryMatch(score=8, explanation="Solid e-commerce and fintech adjacency."),
            education=CategoryMatch(score=9, explanation="BS in Computer Science aligns with criteria."),
            other=CategoryMatch(score=9, explanation="Canadian market experience and strong communication."),
        ),
        strengths=[
            SkillMatch(
                skill="Python & Microservices",
                category="Core Skill",
                evidence_found="Built high-throughput services reducing latency by 40%.",
            )
        ],
        gaps=[
            GapDetail(
                requirement="Ruby on Rails",
                severity="low",
                mitigation_tip="Highlight quick mastery of backend languages and OOP frameworks.",
            )
        ],
        tailoring_strategy=[
            "Emphasize distributed systems scalability and latency reduction metrics.",
            "Frame backend experience around high-volume transaction processing.",
        ],
    )


@pytest.fixture
def sample_application_kit(
    sample_match_analysis,
    sample_tailored_resume,
    sample_company_research,
    sample_cover_letter,
    sample_interview_questions,
    sample_tips_section,
) -> ApplicationKit:
    return ApplicationKit(
        match_analysis=sample_match_analysis,
        tailored_resume=sample_tailored_resume,
        company_research=sample_company_research,
        cover_letter=sample_cover_letter,
        interview_prep=sample_interview_questions,
        tips=sample_tips_section,
    )


@pytest.fixture
def sample_generate_inputs() -> GenerateInputs:
    return GenerateInputs(
        resume_text="Ricardo Alvarez\nSoftware Engineer with 8 years experience building backend systems in Python.",
        extra_context="Won company hackathon in 2023 for AI developer tooling.",
        job_description="Seeking a Senior Backend Engineer to build scalable microservices.",
        company="Shopify",
        seniority="Senior",
        position="Senior Backend Engineer",
    )
