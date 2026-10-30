"""Shared report schemas and row mapping for CSV and formatted Excel exports."""

import csv
from datetime import datetime, timedelta, timezone

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, Side
from openpyxl.cell.rich_text import CellRichText, TextBlock
from openpyxl.cell.text import InlineFont


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
    "Research Areas",
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
    ("Education", "education"),
)
REPORT_TIMEZONE = timezone(timedelta(hours=5, minutes=30), name="IST")


def report_now():
    """Current report time in the institute's local timezone."""
    return datetime.now(REPORT_TIMEZONE)


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


def aicte_eligible_role(result):
    """Return the highest AICTE-eligible role, independent of selected role."""
    match = _as_match(result)
    aicte = match.get("aicte_eligibility", {})
    if not isinstance(aicte, dict):
        return "Not Evaluated"

    recommended = str(aicte.get("primary_recommended_status") or "").strip()
    prefix = "Eligible - "
    if recommended.casefold().startswith(prefix.casefold()):
        return recommended[len(prefix):].strip()

    # Fallback for older result payloads without primary_recommended_status.
    for role, key in (
        ("Professor", "professor"),
        ("Associate Professor", "associate_professor"),
        ("Assistant Professor", "assistant_professor"),
    ):
        role_result = aicte.get(key)
        if isinstance(role_result, dict) and role_result.get("eligible") is True:
            return role
    return "Not Eligible" if recommended or aicte else "Not Evaluated"


def dated_report_filename(report_kind, extension, identifier=None, now=None):
    """Build the requested date-first report name, retaining unique batch IDs."""
    date_prefix = (now or report_now()).strftime("%d.%m.%Y")
    suffix = f"_{identifier}" if identifier else ""
    return f"{date_prefix}_match_report_{report_kind}{suffix}.{extension}"


def _score_breakdown_text(breakdown):
    parts = []
    for label, key in _EXCEL_SCORE_PILLARS:
        item = breakdown.get(key, {}) if isinstance(breakdown, dict) else {}
        if key == "experience_position_norms" and not item and isinstance(breakdown, dict):
            item = breakdown.get("experience_domain_alignment", {})
        if not isinstance(item, dict) or item.get("score") is None:
            parts.append(f"\u2022 {label}: Not Scored")
            continue
        short_label = {
            "Experience & Position Norms": "Experience & Norms",
            "Professional Dev": "Professional Development",
        }.get(label, label)
        parts.append(f"\u2022 {short_label}: {item['score']}/100")
    return "\n".join(parts)


def _qualification_rich_text(formatted_string):
    """Return a CellRichText with each UG/PG/Ph.D. segment on its own line,
    the heading part (e.g. 'UG') rendered in bold and the detail in normal weight."""
    if not formatted_string or not isinstance(formatted_string, str):
        return formatted_string or ""

    segments = [seg.strip() for seg in formatted_string.split("|") if seg.strip()]
    if not segments:
        return formatted_string

    bold_font = InlineFont(rFont="Verdana", sz=13, b=True)
    normal_font = InlineFont(rFont="Verdana", sz=13, b=False)

    blocks = []
    for i, segment in enumerate(segments):
        # Each segment looks like "UG: B.Tech (CSE, VIT)" — split on first colon
        if ":" in segment:
            heading, _, detail = segment.partition(":")
            heading = heading.strip()
            detail = detail.strip()
            prefix = "\u2022 "
            blocks.append(TextBlock(bold_font, f"{prefix}{heading}:"))
            if detail:
                blocks.append(TextBlock(normal_font, f" {detail}"))
        else:
            blocks.append(TextBlock(normal_font, f"\u2022 {segment}"))
        # Add newline between segments (not after the last one)
        if i < len(segments) - 1:
            blocks.append(TextBlock(normal_font, "\n"))

    return CellRichText(*blocks)


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
    """Map a match result to the report's data columns."""
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
    eligible_role = aicte_eligible_role(match)
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
        _qualification_rich_text(
            qualification.get("formatted_string", "") if isinstance(qualification, dict) else str(qualification or "")
        ),
        _join_list(match.get("research_areas", [])),
        scopus_count,
        match.get("patents", ""),
        match.get("grants_funding", ""),
        experience.get("details", "") if isinstance(experience, dict) else str(experience or ""),
        employers or "",
        eligible_role,
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
    generated_at = report_now()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = f"Final list {generated_at.strftime('%d.%m.%Y')}"

    # Institution heading and title band mirror the reference sheet's layout.
    last_column = "V"
    sheet.merge_cells(f"D2:{last_column}2")
    sheet["D2"] = "Bansilal Ramnath Agarwal Charitable Trust"
    sheet["D2"].font = Font(name="Comic Sans MS", size=18)
    sheet["D2"].alignment = Alignment(horizontal="center", vertical="top")
    for address, value in (
        ("D3", "Suyog Centre, 7th floor, 34A/1, Market Yard Road, Giridhar Bhavan Chowk, Gultekdi, Pune-411037."),
        ("D4", "Phone: 020 2452 5555"),
    ):
        end_column = last_column
        row = address[1:]
        sheet.merge_cells(f"D{row}:{end_column}{row}")
        sheet[address] = value
        sheet[address].font = Font(name="Verdana", size=13)
        sheet[address].alignment = Alignment(horizontal="center", vertical="top", wrap_text=True)
    sheet.merge_cells("U5:V5")
    sheet["T5"] = f"Date: {generated_at.strftime('%d.%m.%Y')}"
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
        cell = sheet.cell(row=9, column=column, value=label)
        cell.font = header_font
        cell.alignment = header_alignment
        cell.border = cell_border
    sheet.row_dimensions[2].height = 27.6
    sheet.row_dimensions[3].height = 24
    sheet.row_dimensions[4].height = 24
    sheet.row_dimensions[5].height = 31.5
    sheet.row_dimensions[6].height = 24
    sheet.row_dimensions[7].height = 9
    sheet.row_dimensions[8].height = 9
    sheet.row_dimensions[9].height = 53.25

    column_widths = {
        "A": 9.1, "B": 7, "C": 14.1, "D": 24.1, "E": 17, "F": 21.55,
        "G": 25.33, "H": 13, "I": 38, "J": 50.89, "K": 35.33, "L": 30.55,
        "M": 29.11, "N": 32, "O": 47.11, "P": 46, "Q": 39.11, "R": 18.66,
        "S": 15.55, "T": 15.44, "U": 19.55, "V": 14.11,
    }
    for column, width in column_widths.items():
        sheet.column_dimensions[column].width = width

    for row_number, result in enumerate(ordered_results, start=10):
        values = build_excel_report_row(result, row_number - 9)
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
    sheet.print_title_rows = "9:9"
    sheet.print_area = f"B1:V{max(9, 9 + len(ordered_results))}"
    workbook.save(path)
