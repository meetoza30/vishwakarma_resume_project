from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class UGQualification(BaseModel):
    degree: str = Field(default="Not Mentioned")
    branch: str = Field(default="Not Mentioned")
    university: str = Field(default="Not Mentioned")
    passing_year: str = Field(default="Not Mentioned")
    class_obtained: str = Field(default="Not Mentioned")


class PGQualification(BaseModel):
    degree: str = Field(default="Not Mentioned")
    branch: str = Field(default="Not Mentioned")
    university: str = Field(default="Not Mentioned")
    passing_year: str = Field(default="Not Mentioned")
    class_obtained: str = Field(default="Not Mentioned")


class PhdQualification(BaseModel):
    status: str = Field(default="None")  # Completed, Pursuing, None
    discipline: str = Field(default="Not Mentioned")
    university: str = Field(default="Not Mentioned")
    completion_year: str = Field(default="Not Mentioned")


class QualificationSummary(BaseModel):
    ug: UGQualification = Field(default_factory=UGQualification)
    pg: PGQualification = Field(default_factory=PGQualification)
    phd: PhdQualification = Field(default_factory=PhdQualification)
    formatted_string: str = Field(default="Not Mentioned")


class ExperienceSummary(BaseModel):
    teaching_years: float = Field(default=0.0)
    industrial_years: float = Field(default=0.0)
    total_years: float = Field(default=0.0)
    details: str = Field(default="Teaching: 0 Yrs, Industry: 0 Yrs (Total: 0 Yrs)")


class AICTEPostEligibility(BaseModel):
    eligible: bool = Field(default=False)
    status: str = Field(default="Not Eligible")
    reason: str = Field(default="Does not meet criteria")


class AICTEEligibilitySummary(BaseModel):
    assistant_professor: AICTEPostEligibility = Field(default_factory=AICTEPostEligibility)
    associate_professor: AICTEPostEligibility = Field(default_factory=AICTEPostEligibility)
    professor: AICTEPostEligibility = Field(default_factory=AICTEPostEligibility)
    primary_recommended_status: str = Field(default="Unverified")
    verification_status: str = Field(default="Unverified")


class ExtraAcademicFields(BaseModel):
    core_domain_specialization: str = Field(default="Not Mentioned")
    h_index_citations: str = Field(default="Not Mentioned")
    phd_guidance_count: int = Field(default=0)
    accreditation_experience: str = Field(default="Not Mentioned")
    administrative_leadership_roles: str = Field(default="Not Mentioned")
    professional_memberships_upskilling: str = Field(default="Not Mentioned")
    sponsored_grants_consultancy: str = Field(default="Not Mentioned")


class PillarScore(BaseModel):
    score: int = Field(default=0)
    weight_pct: int = Field(default=0)
    weighted_score: float = Field(default=0.0)
    detail: str = Field(default="")


class SevenPillarBreakdown(BaseModel):
    research_publications: PillarScore = Field(default_factory=PillarScore)
    experience_domain_alignment: PillarScore = Field(default_factory=PillarScore)
    patents_grants: PillarScore = Field(default_factory=PillarScore)
    leadership_roles: PillarScore = Field(default_factory=PillarScore)
    professional_dev: PillarScore = Field(default_factory=PillarScore)
    technical_skills: PillarScore = Field(default_factory=PillarScore)
    education: PillarScore = Field(default_factory=PillarScore)


class CandidateAcademicProfile(BaseModel):
    sr_no: int = Field(default=1)
    candidate_name: str = Field(default="Not Mentioned")
    candidate_category: str = Field(default="Faculty")  # Faculty, Corporate->Teaching, Fresher
    # applied_post: str = Field(default="Faculty Position")
    contact_number: str = Field(default="Not Mentioned")
    email_id: str = Field(default="Not Mentioned")
    qualification: QualificationSummary = Field(default_factory=QualificationSummary)
    scopus_post_phd_publications: int = Field(default=0)
    scopus_publication_details: str = Field(default="Nil")
    patents: str = Field(default="Nil")
    grants_funding: str = Field(default="Nil")
    experience: ExperienceSummary = Field(default_factory=ExperienceSummary)
    previous_employers: List[str] = Field(default_factory=list)
    aicte_eligibility: AICTEEligibilitySummary = Field(default_factory=AICTEEligibilitySummary)
    extra_academic_fields: ExtraAcademicFields = Field(default_factory=ExtraAcademicFields)
    pillar_breakdown: SevenPillarBreakdown = Field(default_factory=SevenPillarBreakdown)


class MatchJobStatusResponse(BaseModel):
    job_id: str
    status: str  # QUEUED, PROCESSING, COMPLETED, FAILED
    total_resumes: int
    processed_resumes: int
    report_pdf_url: Optional[str] = None
    report_csv_url: Optional[str] = None
    results: List[Dict[str, Any]] = Field(default_factory=list)
