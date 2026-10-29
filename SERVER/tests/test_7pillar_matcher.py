import sys
import os
import unittest

# Ensure SERVER directory is in Python path
server_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if server_dir not in sys.path:
    sys.path.insert(0, server_dir)

from services.matcher import (
    _classify_candidate_category,
    _score_pillar_2_experience_and_norms,
    _score_pillar_6_technical_skills,
    match_resume_to_jd,
    FACULTY_WEIGHTS,
    CORPORATE_TEACHING_WEIGHTS,
    FRESHER_WEIGHTS
)
from services.aicte_engine import (
    evaluate_assistant_professor,
    evaluate_associate_professor,
    evaluate_professor,
    evaluate_aicte_eligibility
)


class TestSevenPillarMatcher(unittest.TestCase):

    def test_jd_skills_are_disabled(self):
        """The general faculty evaluation does not compare skills with the JD."""
        pillar = _score_pillar_6_technical_skills()
        self.assertEqual(pillar["score"], 0)
        self.assertEqual(pillar["matched_required"], [])
        self.assertEqual(pillar["missing_required"], [])

    def test_candidate_classification(self):
        """Verify candidate category classification logic."""
        # Faculty profile
        faculty_resume = {"experience": {"teaching_years": 8.0, "industrial_years": 2.0, "total_years": 10.0}}
        self.assertEqual(_classify_candidate_category(faculty_resume), "Faculty")

        # Corporate to Teaching profile
        corp_resume = {"experience": {"teaching_years": 1.0, "industrial_years": 7.0, "total_years": 8.0}}
        self.assertEqual(_classify_candidate_category(corp_resume), "Corporate->Teaching")

        # Fresher profile
        fresher_resume = {"experience": {"teaching_years": 0.5, "industrial_years": 0.5, "total_years": 1.0}}
        self.assertEqual(_classify_candidate_category(fresher_resume), "Fresher")

    def test_weight_sums(self):
        """Verify that weights for each candidate category sum to 100%."""
        self.assertEqual(sum(FACULTY_WEIGHTS.values()), 100)
        self.assertEqual(sum(CORPORATE_TEACHING_WEIGHTS.values()), 100)
        self.assertEqual(sum(FRESHER_WEIGHTS.values()), 100)
        self.assertEqual(FACULTY_WEIGHTS["technical_skills"], 0)
        self.assertEqual(CORPORATE_TEACHING_WEIGHTS["technical_skills"], 0)
        self.assertEqual(FRESHER_WEIGHTS["technical_skills"], 0)

    def test_experience_score_uses_position_norms(self):
        resume = {
            "qualification": {"phd": {"status": "Completed"}},
            "experience": {"total_years": 4, "post_phd_years": 1},
            "total_indexed_publications": 0,
        }
        aicte = evaluate_aicte_eligibility(resume, ["Associate Professor"])
        pillar = _score_pillar_2_experience_and_norms(resume, aicte)
        self.assertEqual(pillar["score"], 50)
        self.assertIn("Post-Ph.D. experience", pillar["detail"])

    def test_aicte_eligibility_norms(self):
        """Verify Assistant, Associate, and Full Professor AICTE norms."""
        # Assistant Professor: Completed M.Tech
        asst_qual_valid = {"ug": {"degree": "B.Tech"}, "pg": {"degree": "M.Tech", "passing_year": "2020"}}
        self.assertTrue(evaluate_assistant_professor(asst_qual_valid, {})["eligible"])

        # Assistant Professor: Ongoing M.Tech (NOT ELIGIBLE)
        asst_qual_ongoing = {"ug": {"degree": "B.Tech"}, "pg": {"degree": "M.Tech", "passing_year": "Ongoing"}}
        self.assertFalse(evaluate_assistant_professor(asst_qual_ongoing, {})["eligible"])

        # Associate Professor: PhD + 8 yrs exp + 6 Scopus papers
        assoc_qual = {"phd": {"status": "Completed"}}
        assoc_exp = {"total_years": 9.0, "post_phd_years": 3.0}
        self.assertTrue(evaluate_associate_professor(assoc_qual, assoc_exp, scopus_count=6)["eligible"])
        self.assertFalse(evaluate_associate_professor(assoc_qual, assoc_exp, scopus_count=4)["eligible"])

        # Professor: PhD + 10 yrs exp + 3 yrs at Associate level +
        # 6 Scopus + 2 PhD guided (relaxed publication path)
        prof_qual = {"phd": {"status": "Completed"}}
        prof_exp = {"total_years": 12.0, "assoc_prof_years": 3.0}
        self.assertTrue(evaluate_professor(prof_qual, prof_exp, scopus_count=6, phd_guided_count=2)["eligible"])
        self.assertFalse(evaluate_professor(prof_qual, prof_exp, scopus_count=6, phd_guided_count=0)["eligible"])

    def test_full_7pillar_match_engine(self):
        """Full end-to-end integration test of match_resume_to_jd."""
        sample_resume = {
            "candidate_name": "Dr. Aditi Sharma",
            "contact_number": "+91-9876543210",
            "email_id": "aditi.sharma@example.com",
            "qualification": {
                "ug": {"degree": "B.Tech", "branch": "Computer Science", "class_obtained": "First Class"},
                "pg": {"degree": "M.Tech", "branch": "Computer Science", "class_obtained": "First Class"},
                "phd": {"status": "Completed", "discipline": "Machine Learning", "university": "IIT Bombay"}
            },
            "scopus_post_phd_publications": 8,
            "patents": "1 Granted, 1 Published",
            "grants_funding": "DST-SERB Project Sanctioned Amount: 25 Lakhs",
            "experience": {
                "teaching_years": 9.0,
                "industrial_years": 1.0,
                "total_years": 10.0,
                "details": "Teaching: 9.0 Yrs, Industry: 1.0 Yrs"
            },
            "extra_academic_fields": {
                "core_domain_specialization": "Artificial Intelligence, Deep Learning, Machine Learning",
                "h_index_citations": "h-index: 12, Citations: 450",
                "phd_guidance_count": 2,
                "accreditation_experience": "NBA SAR Lead, NAAC Steering Committee",
                "administrative_leadership_roles": "Head of Department (HOD) - Computer Engineering",
                "professional_memberships_upskilling": "Senior Member IEEE, ISTE Life Member, NPTEL Elite",
                "sponsored_grants_consultancy": "DST SERB Grant (25 Lakhs) & Consultancy"
            },
            "Skills": {
                "Programming Languages": ["Python", "C++"],
                "Technologies": ["Machine Learning", "Deep Learning", "PyTorch"]
            }
        }

        sample_jd = {
            "job_title": "Associate Professor - Computer Engineering",
            "key_domain": "Computer Science & Artificial Intelligence",
            "experience_required_years": 8,
            "required_skills": ["Python", "Machine Learning", "Deep Learning"],
            "preferred_skills": ["PyTorch", "AWS"]
        }

        result = match_resume_to_jd(sample_resume, sample_jd)

        # Assertions
        self.assertIn("overall_score", result)
        self.assertGreaterEqual(result["overall_score"], 75)
        self.assertEqual(result["candidate_category"], "Faculty")
        self.assertIn("breakdown", result)

        breakdown = result["breakdown"]
        self.assertIn("research_publications", breakdown)
        self.assertIn("experience_position_norms", breakdown)
        self.assertIn("patents_grants", breakdown)
        self.assertIn("leadership_roles", breakdown)
        self.assertIn("professional_dev", breakdown)
        self.assertIn("technical_skills", breakdown)
        self.assertIn("education", breakdown)

        print("\n--- Test Full 7-Pillar Match Result ---")
        print(f"Candidate: {result['candidate_name']}")
        print(f"Category: {result['candidate_category']}")
        print(f"Overall Score: {result['overall_score']}/100 ({result['grade']})")
        print("Breakdown:")
        for k in ["research_publications", "experience_position_norms", "patents_grants",
                  "leadership_roles", "professional_dev", "technical_skills", "education"]:
            p = breakdown[k]
            print(f"  - {k}: Score={p['score']}, Weight={p['weight_pct']}%, WeightedScore={p['weighted_score']}")


if __name__ == "__main__":
    unittest.main()
