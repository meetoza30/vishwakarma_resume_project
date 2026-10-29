import json
import re
import requests
import os
import time
from dotenv import load_dotenv
from services.llm_providers.provider_manager import provider_manager
from services.aicte_engine import evaluate_aicte_eligibility
import re
from services.llm_providers.provider_manager import provider_manager
from services.aicte_engine import (evaluate_aicte_eligibility, normalize_positions,
                                   POSITION_NORMS, to_int, to_float, profile_experience)

load_dotenv()


# ---------------------------------------------------------------------------
# SECTION 1 — Skill Taxonomy & Exact Token-Boundary Matching Engine
# ---------------------------------------------------------------------------

SKILL_TAXONOMY = {
    "ml": ["machine learning"],
    "machine learning": ["ml"],
    "ai": ["artificial intelligence"],
    "artificial intelligence": ["ai"],
    "dl": ["deep learning"],
    "deep learning": ["dl"],
    "nlp": ["natural language processing"],
    "natural language processing": ["nlp"],
    "cv": ["computer vision"],
    "computer vision": ["cv"],
    "aws": ["amazon web services"],
    "amazon web services": ["aws"],
    "k8s": ["kubernetes"],
    "kubernetes": ["k8s"],
    "ci/cd": ["continuous integration", "continuous deployment", "cicd"],
    "cicd": ["ci/cd", "continuous integration"],
    "continuous integration": ["ci/cd", "cicd"],
    "dbms": ["database management system", "sql", "relational database"],
    "database management system": ["dbms", "sql"],
    "iot": ["internet of things"],
    "internet of things": ["iot"],
    "vlsi": ["very large scale integration"],
    "very large scale integration": ["vlsi"],
    "cybersecurity": ["cyber security", "information security"],
    "cyber security": ["cybersecurity", "information security"],
    "cloud": ["cloud computing"],
    "cloud computing": ["cloud"],
    "ds": ["data science"],
    "data science": ["ds"],
    "qa": ["quality assurance"],
}


def _normalize(text) -> str:
    """Lowercase, strip punctuation for normalized comparison."""
    if not isinstance(text, str):
        if isinstance(text, dict):
            text = " ".join(str(v) for v in text.values())
        elif isinstance(text, (list, tuple, set)):
            text = " ".join(str(v) for v in text)
        else:
            text = str(text or "")
    return re.sub(r'[^a-z0-9\s]', '', text.lower()).strip()


# def _is_academic_role(jd: dict) -> bool:
#     """Check if the JD is for an academic, faculty, teaching, or research position."""
#     text = (_normalize(jd.get("job_title", "")) + " " + _normalize(jd.get("key_domain", ""))).lower()
#     academic_keywords = [
#         "professor", "faculty", "lecturer", "dean", "hod", "academic",
#         "teacher", "teaching", "researcher", "scientist", "instructor", "postdoc", "visiting faculty"
#     ]
#     return any(k in text for k in academic_keywords)


def _classify_candidate_category(resume: dict) -> str:
    exp = profile_experience(resume)
    teaching, industrial, total = (exp[k] for k in ("teaching_years", "industrial_years", "total_years"))
    if total < 2.0:
        return "Fresher"
    if industrial >= 2.0 and industrial > teaching:
        return "Corporate->Teaching"
    return "Faculty"


def _skills_from_resume(resume: dict) -> list[str]:
    """
    Collect every skill/technology/domain from the resume:
    - Skills section (all categories)
    - Technologies listed in project blocks
    - Core technical domain & specialization
    - Academic qualification branches
    """
    skills = []

    # From dedicated Skills section
    skills_section = resume.get("Skills", {})
    if isinstance(skills_section, dict):
        for category, skill_list in skills_section.items():
            if isinstance(skill_list, list):
                skills.extend(skill_list)

    # # From experience project technologies
    # for exp in resume.get("Experience", {}).get("experiences", []):
    #     if isinstance(exp, dict):
    #         for proj in exp.get("projects", []):
    #             if isinstance(proj, dict):
    #                 for tech in proj.get("technologies", []):
    #                     skills.append(tech)

    # From extra academic fields
    extras = resume.get("extra_academic_fields", {})
    if isinstance(extras, dict):
        core_domain = extras.get("core_domain_specialization", "")
        if core_domain and isinstance(core_domain, str):
            skills.extend([s.strip() for s in re.split(r'[,/|;]', core_domain) if s.strip()])

    # From qualification branches
    qual = resume.get("qualification", {})
    if isinstance(qual, dict):
        for deg in ["ug", "pg", "phd"]:
            deg_obj = qual.get(deg, {})
            if isinstance(deg_obj, dict):
                branch = deg_obj.get("branch") or deg_obj.get("discipline")
                if branch and isinstance(branch, str) and branch.lower() not in ["none", "not mentioned"]:
                    skills.append(branch)

    ra = resume.get("research_areas", [])
    if isinstance(ra, list):
        skills.extend(str(x) for x in ra if x)

    return list(set(s for s in skills if s))


def _match_skill_token(jd_skill: str, resume_skills: list[str]) -> bool:
    """
    Precision Token-Boundary & Taxonomy Skill Matcher.
    - Uses regex word boundary \\b to prevent 'java' from matching 'javascript'.
    - Uses SKILL_TAXONOMY map to match 'ml' with 'machine learning'.
    """
    jd_norm = _normalize(jd_skill)
    if not jd_norm:
        return False

    synonyms = {jd_norm}
    if jd_norm in SKILL_TAXONOMY:
        synonyms.update(_normalize(s) for s in SKILL_TAXONOMY[jd_norm])

    for r_skill in resume_skills:
        r_norm = _normalize(r_skill)
        if not r_norm:
            continue

        if jd_norm == r_norm or r_norm in synonyms:
            return True

        for syn in synonyms:
            pattern = r'\b' + re.escape(syn) + r'\b'
            if re.search(pattern, r_norm):
                return True
            r_pattern = r'\b' + re.escape(r_norm) + r'\b'
            if len(r_norm) > 2 and re.search(r_pattern, syn):
                return True

    return False


def _is_department_only_term(term: str, jd: dict) -> bool:
    """Return True when a term is only a broad department label.

    A JD such as "Assistant Professor - Department of Information Technology"
    has a department but no research specialization. That label should not be
    treated as a mandatory research match unless the JD explicitly names it as
    a required technical domain.
    """
    normalized = _normalize(term)
    key_domain = _normalize(jd.get("key_domain", ""))
    broad_departments = {
        "information technology",
        "computer science",
        "computer engineering",
        "electronics and communication",
        "electronics engineering",
        "engineering",
        "technology",
    }
    return (
        normalized in broad_departments
        and (not key_domain or normalized == key_domain)
    )


# ---------------------------------------------------------------------------
# SECTION 2 — 7 Pillar Scoring Functions
# ---------------------------------------------------------------------------

def _score_pillar_1_research_and_publications(resume: dict, jd: dict, aicte_result: dict) -> dict:
    extras = resume.get("extra_academic_fields") or {}
    total_pubs = to_int(resume.get("total_indexed_publications")) or to_int(resume.get("scopus_post_phd_publications"))
    guided = to_int(extras.get("phd_guidance_count"))
    h_index = to_int(extras.get("h_index"))
    details_str = str(resume.get("scopus_publication_details", "")).strip()

    target = aicte_result.get("target_position")
    norm = POSITION_NORMS.get(target) if target else None
    need = 0
    if norm and norm["min_pubs"]:
        need = norm["relaxed_pubs"] if (norm["relaxed_pubs"] and guided >= norm["relaxed_phd_guided"]) else norm["min_pubs"]
        ratio = total_pubs / need
        pub_score = round(ratio * 75) if ratio < 1 else min(100, 75 + round((ratio - 1) * 25))
    else:  # Assistant Professor / unknown post: no publication norm, so just reward output
        pub_score = 90 if total_pubs >= 10 else 78 if total_pubs >= 6 else 65 if total_pubs >= 3 else 50 if total_pubs >= 1 else 20

    jd_min = to_int(jd.get("min_publications"))
    if jd_min and total_pubs < jd_min:
        pub_score = max(20, round(pub_score * total_pubs / jd_min))

    h_bonus = 10 if h_index >= 10 else 6 if h_index >= 5 else 3 if h_index >= 1 else 0
    g_bonus = 10 if guided >= 2 else 5 if guided == 1 else 0
    score = min(100, pub_score + h_bonus + g_bonus)

    details = [f"{total_pubs} indexed journal publications" + (f" (norm for {target}: {need})" if need else "")]
    if details_str.lower() not in ("", "nil", "none", "not mentioned"):
        details.append(details_str)
    if h_index:
        details.append(f"h-index {h_index}, citations {to_int(extras.get('citation_count'))}")
    if guided:
        details.append(f"Guided {guided} Ph.D. scholars")
    if jd_min:
        details.append(f"JD minimum {jd_min}: {'Met' if total_pubs >= jd_min else 'Not met'}")
    return {"score": score, "detail": " | ".join(details)}


def _domain_alignment_score(resume: dict, jd: dict) -> int:

    required_terms = [
        str(s)
        for s in jd.get("required_skills", [])
        if s and not _is_department_only_term(str(s), jd)
    ]

    research_terms = [
        str(s)
        for s in jd.get("research_domains", [])
        if s
    ]

    resume_terms = _skills_from_resume(resume)

    if not required_terms and not research_terms:
        return 70

    # Mandatory JD skills
    required_hits = sum(
        1 for term in required_terms
        if _match_skill_token(term, resume_terms)
    )

    required_score = (
        100 * required_hits / len(required_terms)
        if required_terms else 100
    )

    # Preferred research domains
    research_hits = sum(
        1 for term in research_terms
        if _match_skill_token(term, resume_terms)
    )

    research_score = (
        100 * research_hits / len(research_terms)
        if research_terms else 100
    )

    # Required skills matter more than preferred research areas
    return round(
        0.70 * required_score +
        0.30 * research_score
    )


def _score_pillar_2_experience_and_domain(
    resume: dict,
    jd: dict,
    aicte_result: dict
) -> dict:

    exp = resume.get("experience") or {}

    normalized_exp = profile_experience(resume)
    teaching = normalized_exp["teaching_years"]
    industrial = normalized_exp["industrial_years"]
    total = normalized_exp["total_years"]

    required = to_float(jd.get("experience_required_years"))
    target = aicte_result.get("target_position")
    norm_required = to_float((POSITION_NORMS.get(target) or {}).get("min_total_exp"))
    # A faculty JD may omit years even though the institute norm requires them.
    # Use the stricter of the explicit JD requirement and the selected position norm.
    required = max(required, norm_required)

    # 1. JD experience fit
    if required <= 0:
        years_score = 85
    elif total >= required:
        # Meets JD requirement, small bonus for extra experience
        years_score = min(
            100,
            round(85 + min(15, (total - required) * 2))
        )
    else:
        years_score = round(
            max(0, min(100, (total / required) * 100))
        )

    # 2. Domain fit
    domain_score = _domain_alignment_score(resume, jd)

    # 3. Final pillar score
    final = round(
        0.70 * years_score +
        0.30 * domain_score
    )

    return {
        "score": final,
        "detail": (
            f"{total} yrs total "
            f"({teaching} teaching/research, {industrial} industry) "
            f"vs {required} yrs required | "
            f"JD experience fit: {years_score}% | "
            f"Domain fit: {domain_score}%"
        )
    }


def _score_pillar_3_patents_and_grants(resume: dict, jd: dict) -> dict:
    """
    Pillar 3: Patents & Grants
    Evaluates patents filed/published/granted and sponsored research grants, industrial consultancy, and commercialized patents.
    """
    patents = str(resume.get("patents", "")).lower()
    has_patents = patents not in ["nil", "none", "not mentioned", "", "0"]
    if "granted" in patents:
        patent_score = 90
    elif has_patents or "published" in patents or "filed" in patents:
        patent_score = 70
    else:
        patent_score = 30

    extras = resume.get("extra_academic_fields", {}) if isinstance(resume.get("extra_academic_fields"), dict) else {}
    grants = str(extras.get("sponsored_grants_consultancy") or resume.get("grants_funding") or "").lower()
    has_grants = grants not in ["nil", "none", "not mentioned", "", "0"]

    if has_grants:
        grants_bonus = 25 if any(k in grants for k in ["dst", "serb", "aicte", "isro", "lakh", "crore"]) else 15
    else:
        grants_bonus = 0

    total_score = min(100, patent_score + grants_bonus)

    details = []
    if has_patents:
        details.append(f"Patents: {resume.get('patents')}")
    if has_grants:
        details.append(f"Grants & Consultancy: {extras.get('sponsored_grants_consultancy') or resume.get('grants_funding')}")
    if not details:
        details.append("No patents or external research grants stated")

    return {
        "score": total_score,
        "detail": " | ".join(details)
    }


def _score_pillar_4_leadership_roles(resume: dict, jd: dict) -> dict:
    """
    Pillar 4: Administrative Leadership Roles
    Evaluates HOD, Dean, Controller of Examinations, Training & Placement Officer, Committee leadership.
    """
    extras = resume.get("extra_academic_fields", {}) if isinstance(resume.get("extra_academic_fields"), dict) else {}
    leadership = str(extras.get("administrative_leadership_roles", "")).lower()

    if leadership in ["none", "not mentioned", "nil", "", "0"]:
        # Check experience designations fallback
        designations = " ".join([
            _normalize(exp.get("designation", ""))
            for exp in resume.get("experience_entries", [])
            if isinstance(exp, dict)
        ])
        if any(role in designations for role in ["head", "hod", "dean", "director", "principal", "controller", "tpo", "lead"]):
            leadership = designations

    if any(role in leadership for role in ["dean", "principal", "director"]):
        score = 95
        detail = f"Senior Academic Executive Leadership ({extras.get('administrative_leadership_roles') or leadership})"
    elif any(role in leadership for role in ["hod", "head of department", "controller"]):
        score = 85
        detail = f"Departmental / Administrative Leadership ({extras.get('administrative_leadership_roles') or leadership})"
    elif any(role in leadership for role in ["tpo", "placement", "coordinator", "committee", "lead"]):
        score = 70
        detail = f"Institutional Committee / Administrative Role ({extras.get('administrative_leadership_roles') or leadership})"
    else:
        score = 40
        detail = "No major administrative leadership roles stated"

    return {
        "score": score,
        "detail": detail
    }


def _score_pillar_5_professional_dev(resume: dict, jd: dict) -> dict:
    """
    Pillar 5: Professional Development
    Evaluates Accreditation & Quality Assurance (NBA SAR, NAAC, IQAC) + Professional Memberships & Up-skilling (IEEE/ACM, ISTE, NPTEL, FDPs).
    """
    extras = resume.get("extra_academic_fields", {}) if isinstance(resume.get("extra_academic_fields"), dict) else {}

    accreditation = str(extras.get("accreditation_experience", "")).lower()
    has_accreditation = accreditation not in ["none", "not mentioned", "nil", "", "0"]

    memberships = str(extras.get("professional_memberships_upskilling", "")).lower()
    has_memberships = memberships not in ["none", "not mentioned", "nil", "", "0"]

    score = 35
    details = []

    if has_accreditation:
        score += 35
        details.append(f"Accreditation: {extras.get('accreditation_experience')}")
    if has_memberships:
        score += 30
        details.append(f"Up-skilling & Memberships: {extras.get('professional_memberships_upskilling')}")

    if not details:
        details.append("No NBA/NAAC/IQAC accreditation or IEEE/NPTEL memberships stated")

    return {
        "score": min(100, score),
        "detail": " | ".join(details)
    }


def _score_pillar_6_technical_skills(resume: dict, jd: dict) -> dict:
    """
    Pillar 6: Technical Skills
    Compares JD required and preferred skills against candidate skills using Exact Token-Boundary & Taxonomy Matcher.
    """
    resume_skills = _skills_from_resume(resume)

    required = [
        str(s) for s in jd.get("required_skills_normalized", [])
        if s and not _is_department_only_term(str(s), jd)
    ]
    if not required:
        required = [
            _normalize(s) for s in jd.get("required_skills", [])
            if s and not _is_department_only_term(str(s), jd)
        ]
    preferred = [
        str(s) for s in jd.get("preferred_skills_normalized", [])
        if s and not _is_department_only_term(str(s), jd)
    ]
    if not preferred:
        preferred = [
            _normalize(s) for s in jd.get("preferred_skills", [])
            if s and not _is_department_only_term(str(s), jd)
        ]

    matched_required = [s for s in required if _match_skill_token(s, resume_skills)]
    missing_required = [s for s in required if not _match_skill_token(s, resume_skills)]
    matched_preferred = [s for s in preferred if _match_skill_token(s, resume_skills)]
    missing_preferred = [s for s in preferred if not _match_skill_token(s, resume_skills)]

    req_score = (len(matched_required) / len(required) * 100) if required else 100
    pref_score = (len(matched_preferred) / len(preferred) * 100) if preferred else 100
    final_score = round(req_score * 0.80 + pref_score * 0.20)

    detail = f"{len(matched_required)}/{len(required)} required skills matched"
    if preferred:
        detail += f", {len(matched_preferred)}/{len(preferred)} preferred"

    return {
        "score": final_score,
        "matched_required": matched_required,
        "missing_required": missing_required,
        "matched_preferred": matched_preferred,
        "missing_preferred": missing_preferred,
        "detail": detail
    }


def _score_pillar_7_education(
    resume: dict,
    jd: dict,
    aicte_result: dict
) -> dict:

    qual = (
        resume.get("qualification", {})
        if isinstance(resume.get("qualification"), dict)
        else {}
    )

    ug = qual.get("ug", {})
    pg = qual.get("pg", {})
    phd = qual.get("phd", {})

    phd_status = str(
        phd.get("status", "")
    ).lower()

    has_phd = phd_status == "completed"
    pursuing_phd = phd_status in ("pursuing", "ongoing")

    has_pg = bool(
        pg.get("degree")
        and str(pg.get("degree")).lower()
        not in ("none", "not mentioned", "")
    )

    has_ug = bool(
        ug.get("degree")
        and str(ug.get("degree")).lower()
        not in ("none", "not mentioned", "")
    )

    if has_phd:
        score = 100
        detail = "Ph.D. completed"
    elif pursuing_phd:
        score = 85
        detail = "Ph.D. pursuing / thesis submitted"
    elif has_pg:
        score = 75
        detail = f"Master's degree ({pg.get('degree')})"
    elif has_ug:
        score = 60
        detail = f"Bachelor's degree ({ug.get('degree')})"
    else:
        score = 0
        detail = "Education details not available"

    return {
        "score": score,
        "has_phd": has_phd,
        "has_pg": has_pg,
        "has_ug": has_ug,
        "detail": detail
    }


# ---------------------------------------------------------------------------
# SECTION 3 — 7 Pillar Weight Allocation Matrix
# ---------------------------------------------------------------------------

FACULTY_WEIGHTS = {
    "research_publications": 25,
    "experience_domain_alignment": 40,
    "patents_grants": 15,
    "leadership_roles": 5,
    "professional_dev": 5,
    "technical_skills": 0,
    "education": 10,
}

CORPORATE_TEACHING_WEIGHTS = {
    "research_publications": 10,
    "experience_domain_alignment": 40,
    "patents_grants": 5,
    "leadership_roles": 5,
    "professional_dev": 10,
    "technical_skills": 20,
    "education": 10,
}

FRESHER_WEIGHTS = {
    "research_publications": 15,
    "experience_domain_alignment": 20,
    "patents_grants": 5,
    "leadership_roles": 10,
    "professional_dev": 10,
    "technical_skills": 30,
    "education": 10,
}


def _score_to_grade(score: int) -> str:
    if score >= 80:
        return "Strong Match"
    elif score >= 65:
        return "Good Match"
    elif score >= 50:
        return "Moderate Match"
    elif score >= 35:
        return "Weak Match"
    else:
        return "Poor Match"


def _score_to_color(score: int) -> str:
    if score >= 80:
        return "green"
    elif score >= 65:
        return "blue"
    elif score >= 50:
        return "amber"
    else:
        return "red"


def _generate_summary(resume, jd, category, overall_score, breakdown, aicte_result) -> str:
    name = resume.get("candidate_name") or "The candidate"
    title = jd.get("job_title", "this role")
    target = aicte_result.get("target_position") or "Not specified in JD"
    tr = aicte_result.get("target_result")
    norm_line = "n/a" if not tr else (f"MEETS AICTE norms for {target}" if tr["eligible"]
                                      else f"DOES NOT MEET AICTE norms for {target} ({tr['reason']})")
    pillar_lines = "\n".join(f"- {k}: {v['score']}/100 ({v['detail']})"
                             for k, v in breakdown.items() if isinstance(v, dict) and "weight_pct" in v)
    prompt = f"""
Candidate: {name} | Category: {category} | Target role: {title} | Position norms: {norm_line}
{pillar_lines}
- Overall Weighted Score: {overall_score}/100

Write a concise 2-3 sentence recruiter summary starting with '{name}'. State clearly whether the AICTE norms for the position are met
(and the main gap if not), then the key research / leadership strengths. Do not invent facts.
Respond ONLY with JSON: {{"summary": "<text>"}}
"""
    try:
        res = provider_manager.execute_with_fallback(
            "You are a Senior Faculty Recruitment Specialist. Return valid JSON only.", prompt)
        if isinstance(res, dict) and res.get("summary"):
            return str(res["summary"]).strip()
    except Exception as e:
        print(f"LLM Summary warning: {e}")
    return (f"{name} is a {category} candidate scoring {overall_score}/100 for {title}. "
            f"Norm check: {norm_line}.")


def match_resume_to_jd(resume: dict, jd: dict) -> dict:
    """
    Master 7-Pillar Matching Engine.
    1. Evaluates AICTE Faculty Eligibility Norms via deterministic rule engine.
    2. Classifies candidate into category: Faculty, Corporate->Teaching, or Fresher.
    3. Scores candidate across 7 distinct pillars incorporating all 7 Extra Academic Fields.
    4. Computes final weighted overall score according to category weight matrix.
    5. Generates executive recruiter summary via T.C.R.A.F.T. system prompt.
    """
    # 1. Deterministic AICTE Compliance Engine
    target_positions = normalize_positions(jd.get("position")) or normalize_positions(jd.get("job_title"))
    aicte_result = evaluate_aicte_eligibility(resume, target_positions)

    # 2. Candidate Classification
    category = _classify_candidate_category(resume)

    # 3. 7 Pillar Scoring
    p1 = _score_pillar_1_research_and_publications(resume, jd, aicte_result)
    p2 = _score_pillar_2_experience_and_domain(resume, jd, aicte_result)
    p3 = _score_pillar_3_patents_and_grants(resume, jd)
    p4 = _score_pillar_4_leadership_roles(resume, jd)
    p5 = _score_pillar_5_professional_dev(resume, jd)
    p6 = _score_pillar_6_technical_skills(resume, jd)
    p7 = _score_pillar_7_education(resume, jd, aicte_result)

    # 4. Weight Selection based on Candidate Category
    if category == "Corporate->Teaching":
        weights = CORPORATE_TEACHING_WEIGHTS
    elif category == "Fresher":
        weights = FRESHER_WEIGHTS
    else:
        weights = FACULTY_WEIGHTS

    # Compute weighted scores for each pillar
    breakdown = {
        "research_publications": {
            "score": p1["score"],
            "weight_pct": weights["research_publications"],
            "weighted_score": round(p1["score"] * (weights["research_publications"] / 100.0), 2),
            "detail": p1["detail"]
        },
        "experience_domain_alignment": {
            "score": p2["score"],
            "weight_pct": weights["experience_domain_alignment"],
            "weighted_score": round(p2["score"] * (weights["experience_domain_alignment"] / 100.0), 2),
            "detail": p2["detail"]
        },
        "patents_grants": {
            "score": p3["score"],
            "weight_pct": weights["patents_grants"],
            "weighted_score": round(p3["score"] * (weights["patents_grants"] / 100.0), 2),
            "detail": p3["detail"]
        },
        "leadership_roles": {
            "score": p4["score"],
            "weight_pct": weights["leadership_roles"],
            "weighted_score": round(p4["score"] * (weights["leadership_roles"] / 100.0), 2),
            "detail": p4["detail"]
        },
        "professional_dev": {
            "score": p5["score"],
            "weight_pct": weights["professional_dev"],
            "weighted_score": round(p5["score"] * (weights["professional_dev"] / 100.0), 2),
            "detail": p5["detail"]
        },
        "technical_skills": {
            "score": p6["score"],
            "weight_pct": weights["technical_skills"],
            "weighted_score": round(p6["score"] * (weights["technical_skills"] / 100.0), 2),
            "detail": p6["detail"],
            "matched_required": p6.get("matched_required", []),
            "missing_required": p6.get("missing_required", []),
            "matched_preferred": p6.get("matched_preferred", []),
            "missing_preferred": p6.get("missing_preferred", [])
        },
        "education": {
            "score": p7["score"],
            "weight_pct": weights["education"],
            "weighted_score": round(p7["score"] * (weights["education"] / 100.0), 2),
            "detail": p7["detail"]
        },
        # Backwards compatibility legacy keys
        "research": p1,
        "skills": p6,
        "experience": p2,
        "role_alignment": {"score": p2["score"], "detail": p2["detail"]}
    }

    # Sum of weighted scores
    overall_score = round(sum(
        breakdown[k]["weighted_score"]
        for k in ["research_publications", "experience_domain_alignment", "patents_grants",
                  "leadership_roles", "professional_dev", "technical_skills", "education"]
    ))
    overall_score = max(0, min(100, overall_score))

    target_res = aicte_result.get("target_result")
    eligible_for_target = target_res["eligible"] if target_res else None

    # 5. LLM Recruiter Summary & Role Alignment
    summary = _generate_summary(resume, jd, category, overall_score, breakdown, aicte_result)

    grade = _score_to_grade(overall_score)
    color = _score_to_color(overall_score)

    all_missing = p6.get("missing_required", []) + p6.get("missing_preferred", [])

    # Compute total_publications: prefer scopus_post_phd_publications, else parse pub details string
    _post_phd_pubs = 0
    try:
        _post_phd_pubs = int(resume.get("scopus_post_phd_publications") or 0)
    except (ValueError, TypeError):
        _post_phd_pubs = 0
    if _post_phd_pubs == 0:
        _pub_str = str(resume.get("scopus_publication_details", "") or "").strip()
        if _pub_str and _pub_str.lower() not in ["nil", "none", "not mentioned", ""]:
            import re as _re
            _nums = [int(n) for n in _re.findall(r'\b(\d+)\b', _pub_str)]
            _post_phd_pubs = sum(_nums) if _nums else 0
    total_publications = _post_phd_pubs
    if resume.get('total_publications'):
        try: total_publications = int(resume.get('total_publications'))
        except: pass
    elif resume.get('total_indexed_publications'):
        try: total_publications = int(resume.get('total_indexed_publications'))
        except: pass

    # research_areas — up to 7 from the resume (extracted by LLM under research_areas key)
    raw_research_areas = resume.get("research_areas", [])
    if not isinstance(raw_research_areas, list):
        raw_research_areas = []
    research_areas = [str(a).strip() for a in raw_research_areas if a][:7]

    return {
        "overall_score": overall_score,
        "candidate_category": category,
        "grade": grade,
        "color": color,
        "summary": summary,
        "breakdown": breakdown,
        "missing_skills": all_missing,
        "matched_skills": p6.get("matched_required", []),
        "candidate_name": resume.get("candidate_name") or resume.get("Name", "Unknown"),
        "job_title": jd.get("job_title", ""),
        "weights_used": weights,
        # "applied_post": resume.get("applied_post") or jd.get("job_title", "Faculty"),
        "contact_number": resume.get("contact_number", "Not Mentioned"),
        "email_id": resume.get("email_id", "Not Mentioned"),
        "qualification": resume.get("qualification", {}),
        "total_publications": total_publications,
        "total_indexed_publications": resume.get("total_indexed_publications", 0),
        "scopus_post_phd_publications": resume.get("scopus_post_phd_publications", 0),
        "scopus_publication_details": resume.get("scopus_publication_details", ""),
        "research_areas": research_areas,
        "patents": resume.get("patents", "Nil"),
        "grants_funding": resume.get("grants_funding", "Nil"),
        "experience_data": resume.get("experience", {}),
        "previous_employers": resume.get("previous_employers", []),
        "aicte_eligibility": aicte_result,
        "extra_academic_fields": resume.get("extra_academic_fields", {}),
        "raw_resume_data": resume,
        "target_position": aicte_result.get("target_position"),
        "eligible_for_target": eligible_for_target,
        "norm_checks": (target_res or {}).get("checks", []),
    }
