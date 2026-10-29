from concurrent.futures import ThreadPoolExecutor
from services.matcher import match_resume_to_jd
from core.config import settings

def test_parallel_resume_matching():
    mock_jd = {
        "job_title": "Assistant Professor in Computer Science",
        "required_skills_normalized": ["python", "machine learning"],
        "preferred_skills_normalized": ["fastapi", "docker"],
        "responsibilities": ["Teach CS courses", "Research in ML"],
        "experience_required": {"teaching_years": 2.0, "total_years": 2.0},
        "education_required": "Master's Degree"
    }

    mock_candidates = [
        {
            "candidate_name": f"Dr. Candidate {i}",
            "contact_number": f"+91 987654321{i}",
            "email_id": f"candidate{i}@example.com",
            "qualification": {
                "ug": {"degree": "B.Tech", "branch": "CSE"},
                "pg": {"degree": "M.Tech", "branch": "AI"},
                "formatted_string": "B.Tech (CSE) | M.Tech (AI)"
            },
            "scopus_post_phd_publications": 3 + i,
            "patents": "1 Filed",
            "grants_funding": "Nil",
            "experience": {
                "teaching_years": 3.0 + i,
                "industrial_years": 1.0,
                "total_years": 4.0 + i,
                "details": f"Teaching: {3.0+i} Yrs"
            },
            "previous_employers": ["Pune University"],
            "Skills": {
                "Programming Languages": ["Python"],
                "Technologies": ["Machine Learning", "FastAPI"]
            },
            "Experience": {
                "total_experience_years": 4.0 + i,
                "experiences": [
                    {
                        "company": "Pune University",
                        "designation": "Assistant Professor",
                        "duration": "2022 - Present",
                        "projects": [
                            {
                                "project_name": "AI Lab",
                                "technologies": ["Python", "FastAPI"],
                                "description": ["Taught ML courses"]
                            }
                        ]
                    }
                ]
            }
        }
        for i in range(1, 4)
    ]

    worker_count = min(settings.MAX_CONCURRENT_RESUME_WORKERS, len(mock_candidates))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        results = list(executor.map(lambda c: match_resume_to_jd(c, mock_jd), mock_candidates))

    assert len(results) == len(mock_candidates)
    for res in results:
        assert "overall_score" in res
        assert "grade" in res
        assert "summary" in res
        assert "breakdown" in res
        assert "research" in res["breakdown"]
        assert "education" in res["breakdown"]
        assert "skills" in res["breakdown"]
        assert "experience" in res["breakdown"]
        assert "role_alignment" in res["breakdown"]
        assert res["overall_score"] > 60
