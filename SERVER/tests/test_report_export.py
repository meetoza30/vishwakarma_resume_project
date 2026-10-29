import csv
import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from services.report_export import (  # noqa: E402
    TABULAR_REPORT_HEADERS,
    build_tabular_report_row,
    write_tabular_report,
)


def _result():
    return {
        "success": True,
        "target_position": "Assistant Professor",
        "candidate_name": "Anuradha Rai",
        "contact_number": "+91-9118062299",
        "email_id": "anuradha2002rai@gmail.com",
        "overall_score": 44,
        "breakdown": {
            "research_publications": {"score": 65},
            "experience_domain_alignment": {"score": 72},
            "patents_grants": {"score": 30},
            "leadership_roles": {"score": 40},
            "professional_dev": {"score": 55},
            "education": {"score": 80},
        },
        "experience_data": {"details": "Teaching/Research: 3.3 Yrs, Industry: 0 Yrs (Total: 3.3 Yrs)"},
        "qualification": {"formatted_string": "UG: B.Tech | PG: M.Tech | Ph.D.: None"},
        "research_areas": ["Deep Learning", "Intrusion Detection"],
        "total_publications": 3,
        "total_indexed_publications": 2,
        "patents": "Nil",
        "grants_funding": "Nil",
    }


def test_report_row_matches_requested_schema_and_order():
    row = build_tabular_report_row(_result())
    assert len(row) == len(TABULAR_REPORT_HEADERS)
    assert row == [
        "Assistant Professor",
        "Anuradha Rai",
        "+91-9118062299",
        "anuradha2002rai@gmail.com",
        44,
        65,
        72,
        30,
        40,
        55,
        80,
        "Teaching/Research: 3.3 Yrs, Industry: 0 Yrs (Total: 3.3 Yrs)",
        "UG: B.Tech | PG: M.Tech | Ph.D.: None",
        "Deep Learning, Intrusion Detection",
        3,
        2,
        "Nil",
        "Nil",
    ]


def test_csv_header_and_row_have_identical_column_count(tmp_path):
    output = tmp_path / "faculty_report.csv"
    write_tabular_report(output, [_result()])

    with output.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.reader(stream))

    assert rows[0] == TABULAR_REPORT_HEADERS
    assert len(rows[0]) == 18
    assert len(rows[1]) == len(rows[0])
    assert rows[1][0] == "Assistant Professor"
    assert rows[1][15] == "2"


def test_failed_result_still_has_stable_column_count():
    row = build_tabular_report_row({"success": False, "error": "Failed processing"})
    assert len(row) == len(TABULAR_REPORT_HEADERS)
    assert row[1] == "Error: Failed processing"
