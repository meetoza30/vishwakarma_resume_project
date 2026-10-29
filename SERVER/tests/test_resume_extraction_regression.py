"""Regression benchmarks for deterministic resume extraction normalization.

These tests deliberately do not call an external LLM. They exercise the
post-processing boundary that must remain correct regardless of provider,
model, or provider retry behavior.
"""

import sys
from pathlib import Path


SERVER_ROOT = Path(__file__).resolve().parents[1]
if str(SERVER_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVER_ROOT))

from services.resume_extraction import (  # noqa: E402
    _declared_experience,
    _explicit_indexed_publication_count,
    _publication_entries_from_text,
    extract_text_preserving_layout,
    normalize_extracted_resume,
    reconcile_publication_counts,
)


RESUMES = {
    "nlp": Path(r"C:\Resumes\3. Professor - Academic\NLP_resume.docx"),
    "anuradha": Path(r"C:\Resumes\3. Professor - Academic\Anuradha_Pandit_3pg.pdf"),
    "dipali": Path(r"C:\Resumes\3. Professor - Academic\Dipali_Kakade_Satarkar_2pg.pdf"),
    "shivam": Path(r"C:\Resumes\2. Corporate - Industry Professional\ShivamDattaPurkayastha_Resume_2pg.pdf"),
    "vidhi": Path(r"C:\Resumes\2. Corporate - Industry Professional\VidhiRaghvani_Academic_CV_2pg.pdf"),
    "shlok": Path(r"C:\Resumes\1. Fresher - College Passout\Shlok_Tiwari_Assistant Professor_2pg.pdf"),
    "aman": Path(r"C:\Resumes\1. Fresher - College Passout\AmanSagarCV26++_2pg.pdf"),
}


def _text(key):
    path = RESUMES[key]
    if not path.exists():
        raise AssertionError(f"Benchmark input is missing: {path}")
    return extract_text_preserving_layout(str(path))


def _empty_provider_result():
    return {
        "candidate_name": "Fixture",
        "qualification": {"phd": {"status": "None"}},
        "total_publications": 0,
        "total_indexed_publications": 0,
        "scopus_post_phd_publications": 0,
        "experience_entries": [],
        "declared_experience_years": {},
        "extra_academic_fields": {},
    }


def test_publication_benchmark_catches_previous_under_counts():
    expected = {
        "nlp": (6, 6),
        "anuradha": (4, 3),
        "vidhi": (2, 1),
        "shlok": (2, 1),
    }
    for key, (total, indexed) in expected.items():
        entries = _publication_entries_from_text(_text(key))
        assert entries is not None, key
        assert len(entries) == total, key
        assert sum(1 for entry in entries if entry["indexed"]) == indexed, key


def test_resumes_without_publication_sections_preserve_zero_counts():
    for key in ("dipali", "shivam", "aman"):
        entries = _publication_entries_from_text(_text(key))
        assert entries is None, key
        result = normalize_extracted_resume(_empty_provider_result(), _text(key))
        assert result["total_publications"] == 0, key
        assert result["total_indexed_publications"] == 0, key


def test_normalizer_replaces_provider_publication_under_count():
    result = normalize_extracted_resume(
        {**_empty_provider_result(), "total_publications": 1, "total_indexed_publications": 1},
        _text("anuradha"),
    )
    assert result["total_publications"] == 4
    assert result["total_indexed_publications"] == 3
    assert len(result["publication_entries"]) == 4


def test_provider_entries_are_aggregated_when_text_has_no_publication_heading():
    result = reconcile_publication_counts(
        {
            **_empty_provider_result(),
            "total_publications": 5,
            "total_indexed_publications": 0,
            "publication_entries": [
                {"title": "A", "indexed": "true"},
                {"title": "B", "indexed": True},
                {"title": "C", "indexed": "yes"},
                {"title": "D", "indexed": 1},
                {"title": "E", "indexed": False},
            ],
        },
        "Candidate profile with publications listed in a table.",
    )
    assert result["total_publications"] == 5
    assert result["total_indexed_publications"] == 4


def test_large_cv_explicit_scopus_count_overrides_collapsed_entry_array():
    # Use the actual large CV as a separate benchmark below; this fixture
    # verifies the invariant independently of provider output shape.
    large_cv = Path(r"C:\Resumes\3. Professor - Academic\1 AnupkumarBongale_CV_15pg.pdf")
    large_text = extract_text_preserving_layout(str(large_cv))
    assert _explicit_indexed_publication_count(large_text) == 76

    result = reconcile_publication_counts(
        {
            **_empty_provider_result(),
            "scopus_post_phd_publications": 75,
            "total_publications": 1,
            "total_indexed_publications": 1,
            "publication_entries": [{"title": "collapsed CV section", "indexed": True}],
        },
        large_text,
    )
    assert result["total_indexed_publications"] == 76
    assert result["total_publications"] == 76


def test_large_resume_pipeline_keeps_original_text_for_final_normalization(monkeypatch):
    import services.resume_extraction as resume_extraction

    source = (
        _text("nlp")
        + ("\nAdditional CV text for large-resume routing." * 500)
        + "\nNumber of publications indexed in Scopus: 76\n"
    )
    calls = []
    provider_outputs = [
        {"summary": "intermediate summary"},
        {
            **_empty_provider_result(),
            "scopus_post_phd_publications": 75,
            "total_indexed_publications": 1,
            "publication_entries": [{"title": "collapsed", "indexed": True}],
        },
    ]

    def fake_provider(system_prompt, user_content):
        calls.append(user_content)
        return provider_outputs.pop(0)

    monkeypatch.setattr(
        resume_extraction.provider_manager,
        "execute_with_fallback",
        fake_provider,
    )
    result = resume_extraction.extract_resume_json(source)

    assert len(calls) == 2
    assert "FULL ORIGINAL RESUME TEXT (AUTHORITATIVE SOURCE)" in calls[1]
    assert result["total_indexed_publications"] == 76


def test_production_llm_service_reconciles_publication_entries(monkeypatch):
    import services.llm_service as llm_service

    provider_payload = {
        **_empty_provider_result(),
        "publication_entries": [
            {"title": "A", "indexed": True},
            {"title": "B", "indexed": True},
            {"title": "C", "indexed": True},
            {"title": "D", "indexed": True},
            {"title": "E", "indexed": False},
        ],
    }
    monkeypatch.setattr(llm_service, "call_openrouter_api", lambda *args: provider_payload.copy())
    monkeypatch.setattr(llm_service.settings, "PRIMARY_LLM_MODEL", "test-model")
    monkeypatch.setattr(llm_service.settings, "FALLBACK_LLM_MODELS", [])
    monkeypatch.setattr(llm_service.settings, "LLM_MAX_RETRIES", 1)

    result = llm_service.extract_resume_with_resilient_llm(
        "Candidate profile with publications listed in a table."
    )
    assert result["total_publications"] == 5
    assert result["total_indexed_publications"] == 4


def test_explicit_industry_claim_is_not_lost_to_incomplete_dates():
    text = _text("vidhi")
    declared = _declared_experience(text)
    assert declared["total_years"] == 2.5
    assert declared["industrial_years"] == 2.5
    result = normalize_extracted_resume(
        {
            **_empty_provider_result(),
            "experience_entries": [
                {"type": "Industry", "start": "2021-08", "end": "2023-05"}
            ],
        },
        text,
    )
    assert result["experience"]["date_derived_total_years"] == 1.8
    assert result["experience"]["stated_total_years"] == 2.5
    assert result["experience"]["total_years"] == 2.5


def test_university_teaching_claim_is_parsed_as_numeric_experience():
    declared = _declared_experience(_text("nlp"))
    assert declared["total_years"] == 10.0
    assert declared["teaching_years"] == 10.0


def test_normalizer_keeps_indexed_count_distinct_from_total_count():
    result = normalize_extracted_resume(_empty_provider_result(), _text("shlok"))
    assert result["total_publications"] == 2
    assert result["total_indexed_publications"] == 1
    assert {entry["type"] for entry in result["publication_entries"]} == {"book", "journal"}
