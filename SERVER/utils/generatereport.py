"""
Generates a branded PDF report for bulk resume-to-JD match results.

Layout per page/section:
- Cover: nCircle logo, report title, JD details
- One section per candidate: overall score, grade, summary paragraph, metrics table
"""

from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether
)
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from services.report_export import report_now, sort_results_by_score, aicte_eligible_role

# ---------------------------------------------------------------------------
# Brand constants (Vishwakarma Group Theme)
# ---------------------------------------------------------------------------
BRAND_BLUE    = colors.HexColor("#0073cb")
BRAND_LIGHT   = colors.HexColor("#e6f2fb")
GRADE_COLORS = {
    "Strong Match":   colors.HexColor("#1A7F37"),   # green
    "Good Match":     colors.HexColor("#0073cb"),   # blue
    "Moderate Match": colors.HexColor("#B45309"),   # amber
    "Weak Match":     colors.HexColor("#B91C1C"),   # red
    "Poor Match":     colors.HexColor("#7C3AED"),   # purple
}
LOGO_PATH = "./ncircle_tech_logo.jpg"

# ---------------------------------------------------------------------------
# Paragraph styles
# ---------------------------------------------------------------------------
report_title_style = ParagraphStyle(
    "report_title",
    fontSize=20,
    textColor=BRAND_BLUE,
    fontName="Helvetica-Bold",
    spaceAfter=12,
    spaceBefore=6,
    leading=24,
)

subtitle_style = ParagraphStyle(
    "subtitle",
    fontSize=11,
    textColor=colors.HexColor("#555555"),
    fontName="Helvetica",
    spaceAfter=2,
)

section_header_style = ParagraphStyle(
    "section_header",
    fontSize=13,
    textColor=BRAND_BLUE,
    fontName="Helvetica-Bold",
    spaceAfter=4,
    spaceBefore=10,
)

candidate_name_style = ParagraphStyle(
    "candidate_name",
    fontSize=14,
    textColor=colors.white,
    fontName="Helvetica-Bold",
    spaceAfter=0,
)

body_style = ParagraphStyle(
    "body",
    fontSize=10,
    textColor=colors.HexColor("#222222"),
    leading=15,
    spaceAfter=4,
)

label_style = ParagraphStyle(
    "label",
    fontSize=10,
    textColor=BRAND_BLUE,
    fontName="Helvetica-Bold",
    leading=14,
)

small_gray = ParagraphStyle(
    "small_gray",
    fontSize=9,
    textColor=colors.HexColor("#666666"),
    leading=13,
)

official_remarks_style = ParagraphStyle(
    "official_remarks",
    fontSize=12,
    textColor=BRAND_BLUE,
    fontName="Helvetica-Bold",
    leading=16,
    spaceBefore=3,
    spaceAfter=4,
)


# ---------------------------------------------------------------------------
# Page templates (canvas callbacks)
# ---------------------------------------------------------------------------

def _first_page(canvas, doc):
    canvas.saveState()
    width, height = A4

    # Blue title bar
    canvas.setFillColor(BRAND_BLUE)
    canvas.setFont("Helvetica-Bold", 14)
    canvas.drawString(20 * mm, height - 18 * mm, "VISHWAKARMA GROUP")
    canvas.setFont("Helvetica", 9)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawString(20 * mm, height - 23 * mm, "One Vishwakarma, One Family")

    # Blue underline
    canvas.setStrokeColor(BRAND_BLUE)
    canvas.setLineWidth(1.5)
    canvas.line(20 * mm, height - 26 * mm, 190 * mm, height - 26 * mm)

    # Page number
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")

    canvas.restoreState()


def _later_pages(canvas, doc):
    canvas.saveState()
    width, height = A4

    # Thin blue bar at top
    canvas.setStrokeColor(BRAND_BLUE)
    canvas.setLineWidth(1.5)
    canvas.line(20 * mm, height - 13 * mm, 190 * mm, height - 13 * mm)

    # Label top-right
    canvas.setFillColor(BRAND_BLUE)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawRightString(190 * mm, height - 10 * mm, "Vishwakarma Group - Faculty Resume Screening Report")

    # Page number
    canvas.setFillColor(colors.HexColor("#888888"))
    canvas.setFont("Helvetica", 9)
    canvas.drawRightString(190 * mm, 10 * mm, f"Page {doc.page}")

    canvas.restoreState()


# ---------------------------------------------------------------------------
# Report sections
# ---------------------------------------------------------------------------

def _cover_section(jd_data: dict) -> list:
    """Report title, selected faculty role, and generation timestamp."""
    elements = []

    elements.append(Spacer(1, 4 * mm))
    elements.append(Paragraph("Match Report", report_title_style))
    elements.append(Paragraph(
        f"Role: {jd_data.get('position') or 'Not Mentioned'}",
        body_style,
    ))
    elements.append(Paragraph(
        f"Generated on {report_now().strftime('%d %B %Y, %I:%M %p')}",
        small_gray,
    ))
    elements.append(Spacer(1, 4 * mm))
    elements.append(Spacer(1, 6 * mm))
    elements.append(HRFlowable(width="100%", thickness=1, color=BRAND_BLUE, spaceAfter=6))
    return elements


def _score_bar(score: int) -> str:
    """Return a simple text-based bar for score visualisation inside paragraph."""
    filled  = round(score / 10)
    empty   = 10 - filled
    bar     = "█" * filled + "░" * empty
    return f"{bar}  {score}/100"


def _candidate_section(rank: int, result: dict) -> list:
    """Build a per-candidate block with header strip, summary, and metric table."""
    elements = []

    match = result.get("match", {})
    overall_score   = match.get("overall_score", 0)
    grade           = match.get("grade", "N/A")
    summary         = match.get("summary", "")
    breakdown       = match.get("breakdown", {})
    eligible_role = aicte_eligible_role(match)
    candidate_name  = match.get("candidate_name") or result.get("filename", f"Candidate {rank}")
    filename        = result.get("filename", "")

    grade_color = GRADE_COLORS.get(grade, colors.gray)

    # --- Header banner table (blue strip) ---
    header_data = [[
        Paragraph(f"#{rank}  {candidate_name}", candidate_name_style),
        Paragraph(grade, ParagraphStyle(
            "grade_pill",
            fontSize=11,
            fontName="Helvetica-Bold",
            textColor=colors.white,
            alignment=2,  # right
        )),
    ]]
    header_table = Table(header_data, colWidths=[120 * mm, 50 * mm])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, -1), BRAND_BLUE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING",  (0, 0), (0, 0),  8),
        ("RIGHTPADDING", (1, 0), (1, 0),  8),
        ("TOPPADDING",   (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 7),
        ("ROUNDEDCORNERS", [4]),
    ]))

    # Overall score strip
    score_bar_text = _score_bar(overall_score)
    score_para = Paragraph(
        f'<font color="#0B6FA4"><b>Overall Score:</b></font>  '
        f'<font face="Courier">{score_bar_text}</font>',
        ParagraphStyle("score_line", fontSize=10, leading=14, spaceAfter=4),
    )
    eligibility_para = Paragraph(
        f'<font color="#0B6FA4"><b>AICTE Eligibility:</b></font> {eligible_role}',
        ParagraphStyle("aicte_role", fontSize=10, leading=14, spaceAfter=4),
    )

    # File label (small)
    file_para = Paragraph(f"File: {filename}", small_gray) if filename != candidate_name else Spacer(1, 1)

    # Summary
    summary_para = Paragraph(summary, body_style) if summary else Spacer(1, 2)

    # --- Metrics table ---
    metrics_header = [
        Paragraph("Evaluation Pillar",  ParagraphStyle("th", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white)),
        Paragraph("Weight", ParagraphStyle("th", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white)),
        Paragraph("Score",   ParagraphStyle("th", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white)),
        Paragraph("Details", ParagraphStyle("th", fontSize=10, fontName="Helvetica-Bold", textColor=colors.white)),
    ]

    def _metric_row(label: str, key: str) -> list:
        data = breakdown.get(key, {})
        score = data.get("score", 0)
        weight = data.get("weight_pct", 0)
        detail = data.get("detail", "—")

        # Colour-code the score cell
        if score >= 80:
            s_color = colors.HexColor("#1A7F37")
        elif score >= 65:
            s_color = colors.HexColor("#0B6FA4")
        elif score >= 50:
            s_color = colors.HexColor("#B45309")
        else:
            s_color = colors.HexColor("#B91C1C")

        return [
            Paragraph(label, body_style),
            Paragraph(f"{weight}%", small_gray),
            Paragraph(
                f'<font color="{s_color.hexval() if hasattr(s_color, "hexval") else "#000000"}"><b>{score}/100</b></font>',
                ParagraphStyle("score_cell", fontSize=10, fontName="Helvetica-Bold", alignment=1),
            ),
            Paragraph(detail, small_gray),
        ]

    metrics_rows = [
        metrics_header,
        _metric_row("1. Research & Publications", "research_publications"),
        _metric_row("2. Experience & Position Norms", "experience_position_norms"),
        _metric_row("3. Patents & Grants",        "patents_grants"),
        _metric_row("4. Leadership Roles",        "leadership_roles"),
        _metric_row("5. Professional Dev",        "professional_dev"),
        _metric_row("6. Education",               "education"),
    ]

    col_widths = [45 * mm, 18 * mm, 22 * mm, 85 * mm]
    metrics_table = Table(metrics_rows, colWidths=col_widths)
    metrics_table.setStyle(TableStyle([
        # Header row
        ("BACKGROUND",   (0, 0), (-1, 0), BRAND_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), colors.white),
        # Alternating data rows
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [colors.white, BRAND_LIGHT]),
        ("GRID",         (0, 0), (-1, -1), 0.4, colors.HexColor("#CFE2F3")),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",        (1, 0), (1, -1), "CENTER"),
        ("LEFTPADDING",  (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING",   (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 5),
    ]))

    # Wrap the whole section so it doesn't split awkwardly across pages
    block = KeepTogether([
        header_table,
        Spacer(1, 3 * mm),
        eligibility_para,
        file_para,
        score_para,
        Spacer(1, 2 * mm),
        Paragraph("<b>Summary</b>", label_style),
        summary_para,
        Spacer(1, 3 * mm),
        Paragraph("<b>Detailed Metrics</b>", label_style),
        Spacer(1, 2 * mm),
        metrics_table,
        Spacer(1, 3 * mm),
        Paragraph("Comments / Remarks (For Official Use)", official_remarks_style),
        Spacer(1, 8 * mm),
        HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#CCCCCC"), spaceAfter=4),
    ])
    elements.append(block)
    return elements


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_match_report_pdf(
    results: list[dict],
    jd_data: dict,
    output_path: str,
) -> None:
    """
    Generate a PDF match report for a bulk resume-screening session.

    Args:
        results:     List of per-candidate result dicts from /match-bulk.
                     Each dict must have keys: filename, success, match.
        jd_data:     Stored criteria for the selected faculty position.
        output_path: Full filesystem path for the output PDF.
    """
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=35 * mm,
        bottomMargin=20 * mm,
    )

    story = []

    # Cover / JD summary
    successful = sort_results_by_score([r for r in results if r.get("success")])
    story.extend(_cover_section(jd_data))

    # One block per successful candidate
    for rank, result in enumerate(successful, start=1):
        story.extend(_candidate_section(rank, result))

    # Failed candidates note (if any)
    failed = [r for r in results if not r.get("success")]
    if failed:
        story.append(Paragraph("Failed to process the following files:", section_header_style))
        for f in failed:
            story.append(Paragraph(
                f'• {f["filename"]} — {f.get("error", "Unknown error")}',
                body_style,
            ))

    doc.build(story, onFirstPage=_first_page, onLaterPages=_later_pages)
    print(f"Match report generated: {output_path}")
