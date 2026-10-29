import pytest
from services.aicte_engine import evaluate_aicte_eligibility, evaluate_assistant_professor, evaluate_associate_professor, evaluate_professor


def test_assistant_professor_eligible():
    qual = {
        "ug": {"degree": "B.E. Computer Engineering"},
        "pg": {"degree": "M.E. Computer Engineering", "passing_year": "2018"}
    }
    exp = {"total_years": 4.0}
    res = evaluate_assistant_professor(qual, exp)
    assert res["eligible"] is True
    assert "Assistant Professor" in res["status"]


def test_assistant_professor_ongoing_pg():
    qual = {
        "ug": {"degree": "B.Tech Computer Science"},
        "pg": {"degree": "M.Tech Ongoing", "passing_year": "Expected June 2026"}
    }
    exp = {"total_years": 1.0}
    res = evaluate_assistant_professor(qual, exp)
    assert res["eligible"] is False
    assert "in progress" in res["reason"] or "Missing" in res["reason"]


def test_associate_professor_no_phd():
    qual = {
        "ug": {"degree": "B.E. IT"},
        "pg": {"degree": "M.Tech CSE"},
        "phd": {"status": "None"}
    }
    exp = {"total_years": 12.0}
    res = evaluate_associate_professor(qual, exp, scopus_count=10)
    assert res["eligible"] is False
    assert "Ph.D. degree not completed" in res["reason"]


def test_associate_professor_eligible():
    qual = {
        "ug": {"degree": "B.E. IT"},
        "pg": {"degree": "M.Tech CSE"},
        "phd": {"status": "Completed"}
    }
    exp = {"total_years": 9.0, "post_phd_years": 3.0}
    res = evaluate_associate_professor(qual, exp, scopus_count=8)
    assert res["eligible"] is True
    assert "Associate Professor" in res["status"]


def test_professor_norms_relaxation():
    qual = {
        "ug": {"degree": "B.E. E&TC"},
        "pg": {"degree": "M.Tech Electronics"},
        "phd": {"status": "Completed"}
    }
    exp = {"total_years": 11.0, "assoc_prof_years": 4.0}
    # 6 papers + 2 Ph.D. supervisions satisfies relaxed Professor norm
    res = evaluate_professor(qual, exp, scopus_count=6, phd_guided_count=2)
    assert res["eligible"] is True
    assert "Professor" in res["status"]
