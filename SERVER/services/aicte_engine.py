"""Deterministic, position-driven AICTE norm engine. Edit POSITION_NORMS to change norms."""
import re
import datetime
from typing import Any, Dict, List, Optional

POSITION_NORMS = {
    "Assistant Professor": {"rank": 1, "phd_required": False, "min_total_exp": 0, "min_post_phd_exp": 0,
                            "min_assoc_exp": 0, "min_pubs": 0, "relaxed_pubs": None, "relaxed_phd_guided": 0},
    "Associate Professor": {"rank": 2, "phd_required": True, "min_total_exp": 8, "min_post_phd_exp": 2,
                            "min_assoc_exp": 0, "min_pubs": 6, "relaxed_pubs": None, "relaxed_phd_guided": 0},
    "Professor":           {"rank": 3, "phd_required": True, "min_total_exp": 10, "min_post_phd_exp": 0,
                            "min_assoc_exp": 3, "min_pubs": 10, "relaxed_pubs": 6, "relaxed_phd_guided": 2},
}
FIRST_CLASS_CGPA = 6.75      # adjust to your university's rule
FIRST_CLASS_PERCENT = 60.0


# ---------- helpers ----------
def to_int(v, default=0) -> int:
    if isinstance(v, (int, float)):
        return int(v)
    m = re.search(r"\d+", str(v or ""))
    return int(m.group()) if m else default


def to_float(v, default=0.0) -> float:
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"\d+(?:\.\d+)?", str(v or ""))
    return float(m.group()) if m else default


def extract_years(value, default=0.0) -> float:
    """Parse a numeric year value without accidentally treating a year as duration.

    Handles values such as ``"8 years"``, ``"8+ yrs"`` and ``"Teaching: 5.5
    years"``.  A four-digit calendar year is not a duration.
    """
    if isinstance(value, (int, float)):
        return max(0.0, float(value))
    text = str(value or "").lower().replace(",", " ")
    matches = re.findall(r"\d+(?:\.\d+)?", text)
    if not matches:
        return default
    numbers = [float(x) for x in matches]
    duration = [x for x in numbers if x < 100]
    return max(duration) if duration else default


def profile_experience(profile: Dict[str, Any]) -> Dict[str, float]:
    """Return normalized experience numbers with safe fallbacks for legacy JSON."""
    exp = profile.get("experience") or {}
    entries = profile.get("experience_entries") or []
    values = {k: extract_years(exp.get(k)) for k in
              ("teaching_years", "industrial_years", "post_phd_years", "assoc_prof_years", "total_years")}
    if not values["total_years"]:
        durations = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            start, end = str(entry.get("start", "")), str(entry.get("end", ""))
            sy = re.search(r"(19|20)\d{2}", start)
            ey = re.search(r"(19|20)\d{2}", end)
            if sy:
                end_year = int(ey.group()) if ey else datetime.date.today().year
                durations.append(max(0.0, end_year - int(sy.group())))
        values["total_years"] = round(sum(durations), 1)
    if not values["total_years"]:
        values["total_years"] = max(values["teaching_years"] + values["industrial_years"], 0.0)
    return values


def normalize_positions(text) -> List[str]:
    """'Assistant / Associate Professor' -> ['Assistant Professor', 'Associate Professor']"""
    t = re.sub(r"[^a-z ]", " ", str(text or "").lower())
    found = []
    if "lecturer" in t or ("assistant" in t and "professor" in t):
        found.append("Assistant Professor")
    if "associate" in t and "professor" in t:
        found.append("Associate Professor")
    rest = re.sub(r"assistant\s+professor|associate\s+professor", " ", t)
    if "professor" in rest:
        found.append("Professor")
    return found


def _blank(v) -> bool:
    return str(v or "").strip().lower() in ("", "none", "not mentioned", "nil", "n/a")


def _is_first_class(deg: dict) -> bool:
    txt = str(deg.get("class_obtained") or "").lower()
    if any(k in txt for k in ("first", "distinction", "honour", "honor")):
        return True
    m = re.search(r"\d+(?:\.\d+)?", txt)
    if not m:
        return False
    val = float(m.group())
    return val >= FIRST_CLASS_CGPA if val <= 10 else val >= FIRST_CLASS_PERCENT


def _first_class_status(qual: dict) -> str:
    known = [d for d in (qual.get("ug") or {}, qual.get("pg") or {}) if not _blank(d.get("class_obtained"))]
    if any(_is_first_class(d) for d in known):
        return "met"
    return "not_met" if known else "unverified"


def _check(group, name, required, actual, status, progress):
    return {"group": group, "criterion": name, "required": required,
            "actual": actual, "status": status, "progress": progress}


def _bool_check(group, name, ok: Optional[bool], actual):
    if ok is None:
        return _check(group, name, "Yes", actual, "unverified", 0.5)
    return _check(group, name, "Yes", actual, "met" if ok else "not_met", 1.0 if ok else 0.0)


def _num_check(group, name, required, actual, unverified=False):
    if actual >= required:
        return _check(group, name, required, actual, "met", 1.0)
    if unverified:
        return _check(group, name, required, actual, "unverified", 0.5)
    return _check(group, name, required, actual, "not_met", round(actual / required, 2))


# ---------- per-position evaluation ----------
def evaluate_position(position: str, profile: Dict[str, Any]) -> Dict[str, Any]:
    norm = POSITION_NORMS[position]
    qual = profile.get("qualification") or {}
    exp = profile.get("experience") or {}
    extras = profile.get("extra_academic_fields") or {}
    ug, pg, phd = (qual.get(k) or {} for k in ("ug", "pg", "phd"))

    pubs = to_int(profile.get("total_indexed_publications")) or to_int(profile.get("scopus_post_phd_publications"))
    guided = to_int(extras.get("phd_guidance_count"))
    phd_done = str(phd.get("status", "")).lower() == "completed"
    checks = []

    # education
    if norm["phd_required"]:
        checks.append(_bool_check("education", "Ph.D. completed", phd_done, phd.get("status") or "None"))
    else:
        ug_text = str(ug.get("degree", "")).lower()
        pg_text = str(pg.get("degree", "")).lower()
        has_ug = any(k in ug_text for k in ("b.e", "b.tech", "b.s", "bachelor"))
        has_pg = any(k in pg_text for k in ("m.e", "m.tech", "m.s", "master"))
        integrated = "integrated" in ug_text or "integrated" in pg_text
        pg_year = str(pg.get("passing_year", "")).lower()
        yr = re.search(r"\d{4}", pg_year)
        pg_ongoing = any(k in pg_year for k in ("pursuing", "ongoing", "expected")) or \
                     (yr and int(yr.group()) > datetime.date.today().year)
        # Assistant Professor accepts the specified UG + PG combination, or an
        # Integrated M.Tech.  Keep the individual facts in the checklist while
        # applying the norm as an OR between valid qualification paths.
        degree_path = (has_ug and has_pg and not pg_ongoing) or (integrated and not pg_ongoing)
        checks.append(_bool_check("education", "B.E./B.Tech/B.S. + M.E./M.Tech/M.S. (or Integrated M.Tech)",
                                  degree_path, f"UG: {ug.get('degree') or 'None'} | PG: {pg.get('degree') or 'None'}"))
    fc = _first_class_status(qual)
    checks.append(_check("education", "First Class in UG or PG", "First Class",
                         f"UG: {ug.get('class_obtained')} | PG: {pg.get('class_obtained')}", fc,
                         {"met": 1.0, "not_met": 0.0, "unverified": 0.5}[fc]))

    # experience
    if norm["min_total_exp"]:
        checks.append(_num_check("experience", "Total experience (yrs)", norm["min_total_exp"],
                                 profile_experience(profile)["total_years"]))
    if norm["min_post_phd_exp"]:
        yr_known = bool(re.search(r"\d{4}", str(phd.get("completion_year", ""))))
        checks.append(_num_check("experience", "Post-Ph.D. experience (yrs)", norm["min_post_phd_exp"],
                                 profile_experience(profile)["post_phd_years"], unverified=(phd_done and not yr_known)))
    if norm["min_assoc_exp"]:
        checks.append(_num_check("experience", "Yrs at Associate Professor level or above", norm["min_assoc_exp"],
                                 profile_experience(profile)["assoc_prof_years"]))

    # publications
    if norm["min_pubs"]:
        relaxed = norm["relaxed_pubs"] and guided >= norm["relaxed_phd_guided"]
        need = norm["relaxed_pubs"] if relaxed else norm["min_pubs"]
        label = "SCI/UGC Care/AICTE journal publications"
        if norm["relaxed_pubs"]:
            label += f" ({norm['min_pubs']}, or {norm['relaxed_pubs']} with {norm['relaxed_phd_guided']} Ph.D. guided)"
        checks.append(_num_check("publications", label, need, pubs))

    failed = [c for c in checks if c["status"] == "not_met"]
    unver = [c for c in checks if c["status"] == "unverified"]
    ratio = round(sum(c["progress"] for c in checks) / len(checks), 2)
    if failed:
        status = "Not Eligible"
        reasons = []
        for c in failed:
            if c["criterion"] == "Ph.D. completed":
                reasons.append("Ph.D. degree not completed")
            elif ("degree" in c["criterion"].lower() or "m.tech" in c["criterion"].lower()) and "ongoing" in str(c["actual"]).lower():
                reasons.append(f"{c['criterion']} is in progress")
            else:
                reasons.append(f"{c['criterion']}: need {c['required']}, found {c['actual']}")
        reason = "; ".join(reasons)
    else:
        status = f"Eligible - {position}"
        reason = f"Meets AICTE norms for {position}"
        if unver:
            reason += " (verify: " + ", ".join(c["criterion"] for c in unver) + ")"
    return {"eligible": not failed, "status": status, "reason": reason,
            "checks": checks, "compliance_ratio": ratio}


def evaluate_assistant_professor(qualification, experience=None, scopus_count=0, phd_guided_count=0):
    profile = {"qualification": qualification or {}, "experience": experience or {},
               "total_indexed_publications": scopus_count,
               "extra_academic_fields": {"phd_guidance_count": phd_guided_count}}
    return evaluate_position("Assistant Professor", profile)


def evaluate_associate_professor(qualification, experience=None, scopus_count=0, phd_guided_count=0):
    profile = {"qualification": qualification or {}, "experience": experience or {},
               "total_indexed_publications": scopus_count,
               "extra_academic_fields": {"phd_guidance_count": phd_guided_count}}
    return evaluate_position("Associate Professor", profile)


def evaluate_professor(qualification, experience=None, scopus_count=0, phd_guided_count=0):
    profile = {"qualification": qualification or {}, "experience": experience or {},
               "total_indexed_publications": scopus_count,
               "extra_academic_fields": {"phd_guidance_count": phd_guided_count}}
    return evaluate_position("Professor", profile)


def evaluate_aicte_eligibility(profile: Dict[str, Any], target_positions: Optional[List[str]] = None) -> Dict[str, Any]:
    results = {p: evaluate_position(p, profile) for p in POSITION_NORMS}
    ranked = sorted(POSITION_NORMS, key=lambda p: -POSITION_NORMS[p]["rank"])
    top = next((p for p in ranked if results[p]["eligible"]), None)

    target = None
    if target_positions:
        target = max(target_positions, key=lambda p: (results[p]["eligible"], results[p]["compliance_ratio"]))

    return {
        "assistant_professor": results["Assistant Professor"],   # back-compat keys
        "associate_professor": results["Associate Professor"],
        "professor": results["Professor"],
        "primary_recommended_status": f"Eligible - {top}" if top else "Not Eligible - Needs Verification",
        "target_position": target,                               # NEW: position from the JD
        "target_result": results[target] if target else None,    # NEW: checklist for that position
        "verification_status": "Verified via Deterministic AICTE Rule Engine",
    }
