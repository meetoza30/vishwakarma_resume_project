"""Shared tabular report schema and row mapping.

The frontend downloads CSV, which Excel opens directly. Keeping the headers and
row construction in one module prevents the API and background-worker exports
from drifting out of alignment.
"""

import csv


TABULAR_REPORT_HEADERS = [
    "target_position",
    "candidate_name",
    "contact_number",
    "email_id",
    "overall_score",
    "Research & Publications",
    "Experience & Domain",
    "Patents & Grants",
    "Leadership Roles",
    "Professional Dev",
    "Education",
    "experience_data.details",
    "qualification.formatted_string",
    "research_areas",
    "total_publications",
    "total_indexed_publications",
    "patents",
    "grants_funding",
]


def _breakdown_score(breakdown, key):
    value = breakdown.get(key, {}) if isinstance(breakdown, dict) else {}
    return value.get("score", "") if isinstance(value, dict) else ""


def _join_list(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)


def build_tabular_report_row(result):
    """Return one row with exactly the same length/order as the headers."""
    if not isinstance(result, dict):
        return [""] * len(TABULAR_REPORT_HEADERS)

    if not result.get("success", True):
        return [
            "",
            f"Error: {result.get('error', 'Candidate processing failed')}",
            "",
            "",
            0,
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
            "",
        ]

    breakdown = result.get("breakdown", {})
    experience = result.get("experience_data", {})
    qualification = result.get("qualification", {})
    aicte = result.get("aicte_eligibility", {})

    target_position = result.get("target_position")
    if not target_position and isinstance(aicte, dict):
        target_position = aicte.get("target_position")

    experience_details = (
        experience.get("details", "")
        if isinstance(experience, dict)
        else str(experience or "")
    )
    qualification_string = (
        qualification.get("formatted_string", "")
        if isinstance(qualification, dict)
        else str(qualification or "")
    )

    return [
        target_position or "",
        result.get("candidate_name", ""),
        result.get("contact_number", ""),
        result.get("email_id", ""),
        result.get("overall_score", ""),
        _breakdown_score(breakdown, "research_publications"),
        _breakdown_score(breakdown, "experience_domain_alignment"),
        _breakdown_score(breakdown, "patents_grants"),
        _breakdown_score(breakdown, "leadership_roles"),
        _breakdown_score(breakdown, "professional_dev"),
        _breakdown_score(breakdown, "education"),
        experience_details,
        qualification_string,
        _join_list(result.get("research_areas", [])),
        result.get("total_publications", 0),
        result.get("total_indexed_publications", 0),
        result.get("patents", ""),
        result.get("grants_funding", ""),
    ]


def write_tabular_report(path, results):
    """Write an Excel-compatible UTF-8 CSV with a stable schema."""
    with open(path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(TABULAR_REPORT_HEADERS)
        writer.writerows(build_tabular_report_row(result) for result in results)
