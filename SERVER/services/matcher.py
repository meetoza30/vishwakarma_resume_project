import re
from dotenv import load_dotenv
from services.llm_providers.provider_manager import provider_manager
from services.aicte_engine import (evaluate_aicte_eligibility, normalize_positions,
                                   POSITION_NORMS, to_int, profile_experience)

load_dotenv()


PERMANENT_ROLE_CRITERIA = {
    "Assistant Professor": {
        "position": "Assistant Professor",
        "job_title": "Assistant Professor",
        "qualification_norm": (
            "B.E./B.Tech./B.S. and M.E./M.Tech./M.S. or Integrated M.Tech. in relevant "
            "branch with First Class or equivalent in any one of the degrees."
        ),
        "experience_norm": "No minimum experience requirement.",
        "publications_norm": "Desirable / Research aptitude.",
        "education_required": "B.E./B.Tech./B.S. and M.E./M.Tech./M.S. or Integrated M.Tech. with First Class",
        "experience_required_years": 0,
        "min_publications": 0,
    },
    "Associate Professor": {
        "position": "Associate Professor",
        "job_title": "Associate Professor",
        "qualification_norm": (
            "Ph.D. in relevant discipline with First Class or equivalent at "
            "Bachelor's or Master’s level."
        ),
        "experience_norm": "Minimum 8 years of total experience, out of which at least 2 years must be Post-Ph.D.",
        "publications_norm": "Minimum 6 research publications in SCI / UGC Care / AICTE-approved journals.",
        "education_required": "Ph.D. in relevant discipline with First Class at Bachelor's or Master's level",
        "experience_required_years": 8,
        "min_publications": 6,
    },
    "Professor": {
        "position": "Professor",
        "job_title": "Professor",
        "qualification_norm": (
            "Ph.D. in relevant discipline with First Class or equivalent at "
            "Bachelor's or Master’s level."
        ),
        "experience_norm": (
            "Minimum 10 years of total experience, out of which at least 3 years must be "
            "at the level of Associate Professor or equivalent."
        ),
        "publications_norm": (
            "Minimum 10 research publications in SCI / UGC Care / AICTE-approved journals "
            "OR minimum 6 research publications if successfully guided at least 2 Ph.D. candidates."
        ),
        "education_required": "Ph.D. in relevant discipline with First Class at Bachelor's or Master's level",
        "experience_required_years": 10,
        "min_publications": 10,
    },
}


def get_permanent_jd_data(role: str = None) -> dict:
    """Return permanent criteria dictionary for the specified faculty role."""
    r_lower = str(role or '').lower()
    if 'associate' in r_lower:
        return dict(PERMANENT_ROLE_CRITERIA['Associate Professor'])
    elif 'professor' in r_lower and 'assistant' not in r_lower:
        return dict(PERMANENT_ROLE_CRITERIA['Professor'])
    return dict(PERMANENT_ROLE_CRITERIA['Assistant Professor'])


def normalize_selected_role(role: str) -> str | None:
    """Return the canonical role only when one of the supported roles was selected."""
    normalized = _normalize(role)
    for supported in PERMANENT_ROLE_CRITERIA:
        if _normalize(supported) == normalized:
            return supported
    return None


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


def _classify_candidate_category(resume: dict) -> str:
    exp = profile_experience(resume)
    teaching, industrial, total = (exp[k] for k in ("teaching_years", "industrial_years", "total_years"))
    if total < 2.0:
        return "Fresher"
    if industrial >= 2.0 and industrial > teaching:
        return "Corporate->Teaching"
    return "Faculty"


# ---------------------------------------------------------------------------
# SECTION 1 — 7 Pillar Scoring Functions
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


def _score_pillar_2_experience_and_norms(resume: dict, aicte_result: dict) -> dict:
    """Score experience against position norms, without JD/domain matching."""
    normalized_exp = profile_experience(resume)
    target = aicte_result.get("target_position")
    target_result = aicte_result.get("target_result") or {}
    checks = [c for c in target_result.get("checks", []) if c.get("group") == "experience"]

    if checks:
        # Each mandatory criterion contributes its progress ratio from the
        # deterministic eligibility engine (total, post-Ph.D., or Associate-level years).
        score = round(100 * sum(c.get("progress", 0) for c in checks) / len(checks))
        detail = " | ".join(
            f"{c['criterion']}: {c['actual']}/{c['required']} ({c['status']})" for c in checks
        )
    else:
        # Assistant Professor has no minimum experience requirement. Use total
        # experience as a descriptive, capped eight-year scale for desirable experience.
        total_years = normalized_exp["total_years"]
        score = round(min(100, total_years / 8 * 100))
        detail = (
            f"No minimum experience norm for {target or 'this position'}; "
            f"total experience {total_years} yrs (scored against an 8-year scale)"
        )

    return {
        "score": score,
        "detail": detail,
    }


def _score_pillar_3_patents_and_grants(resume: dict) -> dict:
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


def _score_pillar_4_leadership_roles(resume: dict) -> dict:
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


def _score_pillar_5_professional_dev(resume: dict) -> dict:
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


def _score_pillar_6_technical_skills() -> dict:
    """Keep the legacy report field, but do not score skills against this general JD."""
    return {
        "score": 0,
        "matched_required": [],
        "missing_required": [],
        "matched_preferred": [],
        "missing_preferred": [],
        "detail": "Not scored: no JD-specific skill requirements are used",
    }


def _score_pillar_7_education(
    resume: dict,
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

    target_result = aicte_result.get("target_result") or {}
    education_checks = [
        check for check in target_result.get("checks", [])
        if check.get("group") == "education"
    ]
    if education_checks:
        score = round(
            100 * sum(check.get("progress", 0) for check in education_checks)
            / len(education_checks)
        )
        detail = " | ".join(
            f"{check['criterion']}: {check['status']}"
            for check in education_checks
        )
    elif has_phd:
        score, detail = 100, "Ph.D. completed; no target-position norm available"
    elif pursuing_phd:
        score, detail = 85, "Ph.D. pursuing / thesis submitted; no target-position norm available"
    elif has_pg:
        score, detail = 75, f"Master's degree ({pg.get('degree')}); no target-position norm available"
    elif has_ug:
        score, detail = 60, f"Bachelor's degree ({ug.get('degree')}); no target-position norm available"
    else:
        score, detail = 0, "Education details not available"

    return {
        "score": score,
        "has_phd": has_phd,
        "has_pg": has_pg,
        "has_ug": has_ug,
        "detail": detail
    }


# ---------------------------------------------------------------------------
# SECTION 2 — 7 Pillar Weight Allocation Matrix
# ---------------------------------------------------------------------------

FACULTY_WEIGHTS = {
    "research_publications": 25,
    "experience_position_norms": 35,
    "patents_grants": 10,
    "leadership_roles": 5,
    "professional_dev": 5,
    "technical_skills": 0,
    "education": 20,
}

CORPORATE_TEACHING_WEIGHTS = {
    "research_publications": 15,
    "experience_position_norms": 35,
    "patents_grants": 5,
    "leadership_roles": 5,
    "professional_dev": 10,
    "technical_skills": 0,
    "education": 30,
}

FRESHER_WEIGHTS = {
    "research_publications": 10,
    "experience_position_norms": 10,
    "patents_grants": 5,
    "leadership_roles": 5,
    "professional_dev": 15,
    "technical_skills": 0,
    "education": 55,
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


def match_resume_to_jd(resume: dict, jd: dict = None, target_role: str = None) -> dict:
    if jd is None or not isinstance(jd, dict):
        jd = get_permanent_jd_data(target_role)
    elif target_role:
        permanent = get_permanent_jd_data(target_role)
        jd = {**permanent, **jd}
    """
    Norm-focused seven-pillar matching engine.
    1. Evaluates AICTE Faculty Eligibility Norms via deterministic rule engine.
    2. Classifies candidate into category: Faculty, Corporate->Teaching, or Fresher.
    3. Scores candidates across seven general academic pillars without JD skill/domain matching.
    4. Computes final weighted overall score according to category weight matrix.
    5. Generates executive recruiter summary via T.C.R.A.F.T. system prompt.
    """
    # 1. Deterministic AICTE Compliance Engine
    target_positions = normalize_positions(jd.get("position")) or normalize_positions(jd.get("job_title"))
    aicte_result = evaluate_aicte_eligibility(resume, target_positions)

    # 2. Candidate Classification
    category = _classify_candidate_category(resume)

    # 3. 7 Pillar Scoring; JD skill and research-domain matching is disabled.
    p1 = _score_pillar_1_research_and_publications(resume, jd, aicte_result)
    p2 = _score_pillar_2_experience_and_norms(resume, aicte_result)
    p3 = _score_pillar_3_patents_and_grants(resume)
    p4 = _score_pillar_4_leadership_roles(resume)
    p5 = _score_pillar_5_professional_dev(resume)
    p6 = _score_pillar_6_technical_skills()
    p7 = _score_pillar_7_education(resume, aicte_result)

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
        "experience_position_norms": {
            "score": p2["score"],
            "weight_pct": weights["experience_position_norms"],
            "weighted_score": round(p2["score"] * (weights["experience_position_norms"] / 100.0), 2),
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
        for k in ["research_publications", "experience_position_norms", "patents_grants",
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
        "applied_post": aicte_result.get("target_position") or jd.get("position") or jd.get("job_title", "Faculty"),
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
