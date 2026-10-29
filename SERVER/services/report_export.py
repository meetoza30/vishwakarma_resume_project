"""Shared report schemas and row mapping for CSV and formatted Excel exports."""

import csv
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side


TABULAR_REPORT_HEADERS = [
    "target_position",
    "candidate_name",
    "contact_number",
    "email_id",
    "overall_score",
    "Research & Publications",
    "Experience & Position Norms",
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

# The column order and wording follow the supplied Candidate Information Sheet.
EXCEL_REPORT_HEADERS = [
    "Sr. No.",
    "Timing",
    "Name of Candidate",
    "Applied for Post",
    "Contact No.",
    "Email ID",
    "Overall Score",
    "Score Breakdown",
    "Qualification (UG/PG/Ph.D.)",
    "Scopus Publications after Ph.D.",
    "Patent (Filed/Published/Granted)",
    "Grants/Funding Received",
    "Experience (Teaching / Industry)",
    "Previous Employers",
    "Eligibility as per AICTE Norms",
    "Present Salary",
    "Expected Salary",
    "Expected Joining",
    "Interviewed By",
    "Remarks",
]

_EXCEL_SCORE_PILLARS = (
    ("Research & Publications", "research_publications"),
    ("Experience & Position Norms", "experience_position_norms"),
    ("Patents & Grants", "patents_grants"),
    ("Leadership Roles", "leadership_roles"),
    ("Professional Dev", "professional_dev"),
    ("Technical Skills", "technical_skills"),
    ("Education", "education"),
)


def _breakdown_score(breakdown, key):
    value = breakdown.get(key, {}) if isinstance(breakdown, dict) else {}
    if key == "experience_position_norms" and not value and isinstance(breakdown, dict):
        value = breakdown.get("experience_domain_alignment", {})
    return value.get("score", "") if isinstance(value, dict) else ""


def _join_list(value):
    if isinstance(value, list):
        return ", ".join(str(item) for item in value if item is not None)
    return "" if value is None else str(value)


def _as_match(result):
    """Accept either a flat API result or the internal {match: ...} shape."""
    if not isinstance(result, dict):
        return {}
    match = result.get("match") if isinstance(result, dict) else None
    return match if isinstance(match, dict) else result


def _score_value(result):
    match = _as_match(result)
    try:
        return float(match.get("overall_score") or 0)
    except (TypeError, ValueError):
        return 0.0


def sort_results_by_score(results):
    """Stable descending sort; equal scores retain their original order."""
    return [item for _, item in sorted(
        enumerate(results or []), key=lambda pair: (-_score_value(pair[1]), pair[0])
    )]


def _score_breakdown_text(breakdown):
    """Return score breakdown as bullet-pointed text with bold factor names."""
    parts = []
    for label, key in _EXCEL_SCORE_PILLARS:
        item = breakdown.get(key, {}) if isinstance(breakdown, dict) else {}
        if key == "experience_position_norms" and not item and isinstance(breakdown, dict):
            item = breakdown.get("experience_domain_alignment", {})
        short_label = {
            "Experience & Position Norms": "Experience & Norms",
            "Professional Dev": "Professional Development",
        }.get(label, label)
        if not isinstance(item, dict) or item.get("score") is None:
            parts.append(f"• {short_label}: Not Scored")
            continue
        parts.append(f"• {short_label}: {item['score']}/100")
    return "\n".join(parts)


def _format_qualification_bullets(formatted_string):
    """Parse 'UG: X | PG: Y | Ph.D.: Z' into newline-separated bullet points."""
    if not formatted_string:
        return ""
    # Split by the pipe separator used in formatted_string
    segments = [seg.strip() for seg in str(formatted_string).split("|")]
    lines = []
    for seg in segments:
        if seg:
            lines.append(f"• {seg}")
    # If no pipe separators found, return as-is with a single bullet
    if not lines:
        return f"• {formatted_string}"
    return "\n".join(lines)


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
        _breakdown_score(breakdown, "experience_position_norms"),
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


def build_excel_report_row(result, serial_number):
    """Map a match result to the 20 data columns in the supplied template."""
    if not isinstance(result, dict):
        return [serial_number] + [""] * (len(EXCEL_REPORT_HEADERS) - 1)

    match = _as_match(result)
    if not isinstance(match, dict):
        match = {}
    if not result.get("success", True):
        error_name = f"Error: {result.get('error', 'Candidate processing failed')}"
        return [serial_number, "", error_name] + [""] * (len(EXCEL_REPORT_HEADERS) - 3)

    breakdown = match.get("breakdown", {})
    experience = match.get("experience_data", {})
    qualification = match.get("qualification", {})
    aicte = match.get("aicte_eligibility", {})
    position = match.get("target_position") or (aicte.get("target_position") if isinstance(aicte, dict) else "")
    primary_status = aicte.get("primary_recommended_status", "") if isinstance(aicte, dict) else ""
    employers = match.get("previous_employers", [])
    if isinstance(employers, list):
        employers = "\n".join(f"• {employer}" for employer in employers if employer)
    contact_number = match.get("contact_number", "")
    if contact_number not in (None, ""):
        contact_number = str(contact_number)
    try:
        overall_score = int(round(float(match.get("overall_score") or 0)))
    except (TypeError, ValueError):
        overall_score = 0
    scopus_count = match.get("scopus_post_phd_publications", "")
    if isinstance(scopus_count, str) and scopus_count.strip().isdigit():
        scopus_count = int(scopus_count.strip())

    return [
        serial_number,
        "",  # interview timing is reserved for official scheduling
        match.get("candidate_name", ""),
        position or "",
        contact_number,
        match.get("email_id", ""),
        overall_score,
        _score_breakdown_text(breakdown),
        _format_qualification_bullets(
            qualification.get("formatted_string", "") if isinstance(qualification, dict) else str(qualification or "")
        ),
        scopus_count,
        match.get("patents", ""),
        match.get("grants_funding", ""),
        experience.get("details", "") if isinstance(experience, dict) else str(experience or ""),
        employers or "",
        primary_status,
        "",  # present salary is official-use information, not resume scoring data
        "",  # expected salary
        "",  # expected joining
        "",  # interviewer
        "",  # official remarks
    ]


def write_tabular_report(path, results):
    """Write an Excel-compatible UTF-8 CSV with a stable schema."""
    with open(path, mode="w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(TABULAR_REPORT_HEADERS)
        writer.writerows(build_tabular_report_row(result) for result in sort_results_by_score(results))


def write_excel_report(path, results):
    """Write a formatted XLSX following the supplied Candidate Information Sheet."""
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"Final list {datetime.now().strftime('%d.%m.%Y')}"

    # Institution heading and title band mirror the reference sheet's layout.
    sheet.merge_cells("D2:U2")
    sheet["D2"] = "Bansilal Ramnath Agarwal Charitable Trust"
    sheet["D2"].font = Font(name="Comic Sans MS", size=18)
    sheet["D2"].alignment = Alignment(horizontal="center", vertical="top")
    for address, value in (
        ("D3", "Suyog Centre, 7th floor, 34A/1, Market Yard Road, Giridhar Bhavan Chowk, Gultekdi, Pune-411037."),
        ("D4", "Phone: 020 2452 5555"),
    ):
        end_column = "U"
        row = address[1:]
        sheet.merge_cells(f"D{row}:{end_column}{row}")
        sheet[address] = value
        sheet[address].font = Font(name="Verdana", size=13)
        sheet[address].alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
    sheet.merge_cells("T5:U5")
    sheet["T5"] = f"Date: {datetime.now().strftime('%d.%m.%Y')}"
    sheet["T5"].font = Font(name="Verdana", size=13)
    sheet["T5"].alignment = Alignment(horizontal="right", vertical="center")

    sheet["B6"] = "Candidate Information Sheet (ranked by overall score)"
    sheet["B6"].font = Font(name="Verdana", size=13)
    sheet["B6"].alignment = Alignment(vertical="center")
    ordered_results = sort_results_by_score(results)

    thin_black = Side(style="thin", color="000000")
    cell_border = Border(left=thin_black, right=thin_black, top=thin_black, bottom=thin_black)
    header_font = Font(name="Verdana", size=13, bold=True)
    body_font = Font(name="Verdana", size=13)
    header_alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    body_alignment = Alignment(vertical="top", wrap_text=True)

    for column, label in enumerate(EXCEL_REPORT_HEADERS, start=2):
        cell = sheet.cell(row=8, column=column, value=label)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = cell_border
    sheet.row_dimensions[2].height = 27.6
    sheet.row_dimensions[3].height = 24
    sheet.row_dimensions[4].height = 24
    sheet.row_dimensions[5].height = 31.5
    sheet.row_dimensions[6].height = 24
    sheet.row_dimensions[7].height = 9
    sheet.row_dimensions[8].height = 53.25

    column_widths = {
        "A": 9.1, "B": 7, "C": 14.1, "D": 24.1, "E": 17, "F": 21.55,
        "G": 25.33, "H": 13, "I": 38, "J": 50.89, "K": 35.33, "L": 30.55,
        "M": 29.11, "N": 47.11, "O": 46, "P": 39.11, "Q": 18.66,
        "R": 15.55, "S": 15.44, "T": 19.55, "U": 14.11,
    }
    for column, width in column_widths.items():
        sheet.column_dimensions[column].width = width

    for row_number, result in enumerate(ordered_results, start=9):
        values = build_excel_report_row(result, row_number - 8)
        for column, value in enumerate(values, start=2):
            cell = sheet.cell(row=row_number, column=column, value=value)
            cell.font = body_font
            cell.alignment = body_alignment
            cell.border = cell_border
        sheet.cell(row=row_number, column=2).alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        sheet.cell(row=row_number, column=3).alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
        sheet.cell(row=row_number, column=8).number_format = "0"
        sheet.row_dimensions[row_number].height = 154.5

    sheet.sheet_view.showGridLines = True
    sheet.page_setup.orientation = "landscape"
    sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
    # Keep the template's non-scaled print behavior; forcing all 20 fields onto
    # one page would make the text illegibly small.
    sheet.page_setup.fitToWidth = None
    sheet.page_setup.fitToHeight = 0
    sheet.print_title_rows = "8:8"
    sheet.print_area = f"B1:U{max(8, 8 + len(ordered_results))}"
    workbook.save(path)
