from dotenv import load_dotenv
from services.llm_providers.provider_manager import provider_manager
from services.aicte_engine import to_int, to_float, normalize_positions

load_dotenv()

def normalize_position(raw: str, fallback_text: str = "") -> str:
    t = f"{raw} {fallback_text}".lower()
    if "associate" in t:
        return "Associate Professor"
    if "assistant" in t:
        return "Assistant Professor"
    if "professor" in t:
        return "Professor"
    return ""

def extract_jd_with_llm(jd_text: str) -> dict | None:
    """
    Sends a raw Job Description text to the Multi-Provider LLM Engine and returns a structured JSON dict.
    Extracts both Technical/Industry and Academic/Faculty requirements.
    """
    system_prompt = """
    You are a professional Job Description & Faculty Requirement Extraction Engine.
    You ONLY output raw, valid JSON. No markdown, no explanation, no preamble.

    Your task is to parse a Job Description (JD) or Faculty Opening into a structured JSON object.

    RULES:
    - Extract ONLY what is explicitly stated in the JD. Do NOT infer or invent.
    - For skills/technologies, separate "required" (must-have, mandatory) from "preferred" (nice-to-have, bonus, plus).
    - If the JD does not differentiate required vs preferred, put all skills under "required_skills" and leave "preferred_skills" empty.
    - For experience, extract the minimum years mentioned (e.g. "3+ years" -> 3). If a range is given (e.g. "3-5 years"), use the lower bound.
    - For education, extract the minimum degree level mentioned (e.g. "Ph.D.", "M.Tech / Master's", "B.Tech / Bachelor's", "Any Graduate").
    - If it is an academic faculty role, extract the position, the research domain(s) required, and any stated requirements for teaching experience, SCI/UGC Care/AICTE-approved publications, PhD guidance and research grants.
    - Treat a department name (for example, "Information Technology" in "Department of Information Technology") as organizational context, not as a research domain or mandatory technical skill, unless the JD explicitly requires expertise in it.
    - "position": Choose from "Assistant Professor", "Associate Professor", "Professor". If the JD lists several posts, join them with " / " (e.g. "Assistant Professor / Associate Professor"). If none is stated, "Not Specified". Never infer the post from years of experience.
    - "required_skills" / "preferred_skills": ATOMIC terms of 1-3 words each (e.g. "Machine Learning", "VLSI", "Cyber Security"), never sentences. For faculty JDs these are explicit research / teaching domains or technologies, not department names copied from the title.
    - "min_publications": integer, the minimum research publications the JD states, else 0.

    OUTPUT SCHEMA (use this exact structure):
    {
        "job_title": "Exact job title from JD",
        "company": "Company / Institute name if mentioned, else ''",
        "key_domain": "Industry or academic domain (e.g. Computer Science, AI/ML, VLSI, FinTech)",
        "position": "Assistant Professor | Associate Professor | Professor | ''",
        "research_domains": ["Research areas the JD wants, e.g. Deep Learning, VLSI, IoT"],
        "min_publications": 0,
        "experience_required_years": 0,
        "education_required": "e.g. Ph.D. in Computer Science / Master's / Bachelor's",
        "required_skills": [
            "Skill or domain that is mandatory"
        ],
        "preferred_skills": [
            "Skill or domain that is nice-to-have"
        ],
        "responsibilities": [
            "Responsibility bullet point copied from JD"
        ],
        "other_requirements": [
            "Any other requirements like Scopus papers, PhD guidance, certifications, location"
        ]
    }
    """

    user_content = f"Parse this Job Description and return ONLY a valid JSON object:\n\n{jd_text}"

    try:
        parsed = provider_manager.execute_with_fallback(system_prompt, user_content)
        if parsed and isinstance(parsed, dict) and "job_title" in parsed:
            tokens_used = parsed.get("_llm_metadata", {}).get("total_tokens", 0)
            print(f"\n==============================================")
            print(f"Tokens consumed for JD Extraction: {tokens_used}")
            print(f"==============================================\n")
            
            parsed.setdefault("company", "")
            parsed.setdefault("key_domain", "")
            parsed.setdefault("experience_required_years", 0)
            parsed.setdefault("education_required", "")
            parsed.setdefault("required_skills", [])
            parsed.setdefault("preferred_skills", [])
            parsed.setdefault("responsibilities", [])
            parsed.setdefault("other_requirements", [])
            parsed.setdefault("research_domains", [])
            parsed.setdefault("position", "Not Specified")
            parsed["min_publications"] = to_int(parsed.get("min_publications"))
            parsed["experience_required_years"] = to_float(parsed.get("experience_required_years"))
            positions = normalize_positions(parsed.get("position"))
            parsed["position"] = " / ".join(positions) if positions else ""

            # Normalize skills for consistent matching
            parsed["required_skills_normalized"] = [str(s).lower().strip() for s in parsed["required_skills"] if s]
            parsed["preferred_skills_normalized"] = [str(s).lower().strip() for s in parsed["preferred_skills"] if s]

            print(f"JD extracted successfully via Multi-Provider LLM: {parsed['job_title']}")
            print(parsed)
            return parsed
    except Exception as e:
        print(f"JD extraction exception: {e}")

    # Fallback default structure
    lines = [l.strip() for l in jd_text.splitlines() if l.strip()]
    first_line = lines[0][:50] if lines else "Faculty Post / Job Opening"
    return {
        "job_title": first_line,
        "company": "Vishwakarma Institute",
        "key_domain": "Engineering / Technology",
        "experience_required_years": 0.0,
        "education_required": "Bachelor's / Master's / Ph.D.",
        "required_skills": [],
        "preferred_skills": [],
        "responsibilities": lines[:5],
        "position": "Not Specified",
        "min_publications": 0,
        "research_domains": [],
        "other_requirements": [],
        "required_skills_normalized": [],
        "preferred_skills_normalized": []
    }
