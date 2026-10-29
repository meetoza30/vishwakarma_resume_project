import pdfplumber
import json
import re
import datetime
from dateutil import parser
from dotenv import load_dotenv
import os
from services.llm_providers.provider_manager import provider_manager
from services.aicte_engine import to_int, extract_years
import time

load_dotenv()

def _parse_date(s, now):
    s = str(s or "").strip()
    if not s:
        return None
    if s.lower() in ("present", "current", "till date", "today", "now", "ongoing"):
        return now
    s = re.sub(r"['’](\d{2})\b", r" 20\1", s)
    try:
        return parser.parse(s, default=datetime.datetime(now.year, 1, 1))
    except Exception:
        return None


def _months(a, b):
    return (b.year - a.year) * 12 + (b.month - a.month)


def _union_years(intervals):
    """Years covered by the union of intervals, so overlapping jobs aren't double counted."""
    total, cs, ce = 0, None, None
    for s, e in sorted(intervals):
        if ce is None or s > ce:
            if ce is not None:
                total += _months(cs, ce)
            cs, ce = s, e
        else:
            ce = max(ce, e)
    if ce is not None:
        total += _months(cs, ce)
    return round(total / 12.0, 1)


def compute_experience(entries, phd_completion_year=None):
    now = datetime.datetime.now()
    m = re.search(r"(19|20)\d{2}", str(phd_completion_year or ""))
    phd_dt = datetime.datetime(int(m.group()), 7, 1) if m else None

    allv, academic, industry, post_phd, senior = [], [], [], [], []
    for e in entries or []:
        if not isinstance(e, dict):
            continue
        s, en = _parse_date(e.get("start"), now), _parse_date(e.get("end"), now)
        if not s or not en or en <= s:
            continue
        iv = (s, en)
        allv.append(iv)
        is_acad = str(e.get("type", "")).lower() in ("teaching", "research")
        (academic if is_acad else industry).append(iv)
        # The norm asks for post-Ph.D. experience, regardless of whether the
        # post-award role is teaching, research, or industry.
        if phd_dt and en > phd_dt:
            post_phd.append((max(s, phd_dt), en))
        d = str(e.get("designation", "")).lower()
        # Associate Professor level OR ABOVE (Professor counts, Assistant/Adjunct/Visiting don't)
        if is_acad and "professor" in d and not any(x in d for x in ("assistant", "adjunct", "visiting")):
            senior.append(iv)

    t, i, tot = _union_years(academic), _union_years(industry), _union_years(allv)
    return {"teaching_years": t, "industrial_years": i, "post_phd_years": _union_years(post_phd),
            "assoc_prof_years": _union_years(senior), "total_years": tot,
            "details": f"Teaching/Research: {t} Yrs, Industry: {i} Yrs (Total: {tot} Yrs)"}


def _declared_experience(text):
    """Extract explicit experience claims so they can be reconciled with dates."""
    clean = re.sub(r"\s+", " ", str(text or "")).lower()

    def find(pattern):
        m = re.search(pattern, clean)
        return extract_years(m.group(1)) if m else 0.0

    total = find(r"(?:total|overall|รวม)\s+(?:professional\s+)?experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)")
    if not total:
        total = find(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s+(?:of\s+)?(?:total\s+)?experience")
    if not total:
        total = find(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s+of\s+(?:professional|industry|industrial|work)\s+experience")
    if not total:
        total = find(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s+of\s+(?:university\s+)?(?:teaching|professional|industry|industrial|work).*?experience")
    teaching = find(r"(?:teaching|academic)\s+experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)")
    if not teaching:
        teaching = find(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s+of\s+(?:university\s+)?teaching\b")
    industry = find(r"(?:industrial|industry|corporate)\s+experience\s*[:\-]?\s*(\d+(?:\.\d+)?)\s*(?:years?|yrs?)")
    if not industry:
        industry = find(r"(\d+(?:\.\d+)?)\s*(?:\+\s*)?(?:years?|yrs?)\s+of\s+(?:industrial|industry|corporate)\s+experience")
    return {"total_years": total, "teaching_years": teaching, "industrial_years": industry}


_PUBLICATION_HEADINGS = re.compile(
    r"^\s*(?:(?:research|selected)\s+)?publications?\s*$",
    re.IGNORECASE,
)
_SECTION_HEADINGS = re.compile(
    r"^\s*(?:education|academics?|experience|professional experience|"
    r"teaching|research projects?|certifications?|skills?|patents?|"
    r"projects?|awards?|references?|additional information|positions? of responsibility|"
    r"sponsored research.*|consultancy.*|professional memberships.*|memberships.*|"
    r"continuous? up[- ]skilling.*|research supervision.*|academic service.*|"
    r"research leadership.*|research projects?.*|technical skills.*|languages?|achievements?)\s*$",
    re.IGNORECASE,
)


def _publication_entries_from_text(text):
    """Extract publication blocks and conservatively classify indexed journals.

    LLMs frequently under-count compact CV publication sections or count books and
    conference papers as journals. This pass uses only visible section structure
    and explicit venue/indexing cues; it never invents a publication.
    """
    lines = [re.sub(r"\s+", " ", line).strip() for line in str(text or "").splitlines()]
    start = next((i + 1 for i, line in enumerate(lines) if _PUBLICATION_HEADINGS.match(line)), None)
    if start is None:
        return None

    section = []
    for line in lines[start:]:
        if _SECTION_HEADINGS.match(line) and not re.search(r"publication", line, re.IGNORECASE):
            break
        if line:
            section.append(line)

    blocks = []
    current = []
    current_kind = ""
    for line in section:
        lower = line.lower().strip(" .:")
        if lower in {"book publication", "book publications"}:
            # A heading can follow the previous block (for example a book
            # publication list followed by a journal publication list). Flush
            # it before changing the classification for the next block.
            if current:
                blocks.append((current_kind or "other", " ".join(current)))
                current = []
            current_kind = "book"
            continue
        if lower in {"journal publication", "journal publications"}:
            if current:
                blocks.append((current_kind or "other", " ".join(current)))
                current = []
            current_kind = "journal"
            continue

        starts_entry = bool(
            re.match(r"^(?:[•●▪*-]\s+|(?:19|20)\d{2}\s*[|:,-])", line)
            or (re.search(r"\b\d{1,2}/\d{1,2}/\d{4}\b", line) and len(line) > 25)
        )
        # Ignore explanatory prose before the first publication record. It is
        # not itself a publication and otherwise becomes a false entry.
        if not starts_entry and not current and re.search(
            r"\b(?:journal|research) publications?\b|paper records?|listed below",
            line,
            re.IGNORECASE,
        ):
            continue
        if starts_entry and current:
            blocks.append((current_kind, " ".join(current)))
            current = []
        if starts_entry:
            current_kind = current_kind or "other"
        current.append(line)
    if current:
        blocks.append((current_kind, " ".join(current)))

    # A short sentence such as "6 journal publications listed below" may be
    # the only count signal for a compact academic CV.
    if not blocks:
        count_match = re.search(r"(\d+)\s+(?:indexed\s+)?journal publications?", " ".join(section), re.IGNORECASE)
        if count_match:
            count = int(count_match.group(1))
            return [{"title": "", "venue": "", "type": "journal", "indexed": True} for _ in range(count)]
        return None

    # Some CVs use a title/venue/date layout without bullets or numbering. In
    # that layout the line containing the venue is the most reliable record
    # boundary. Use only explicit venue-like lines and only when the normal
    # block parser collapsed multiple records into one.
    if len(blocks) == 1:
        venue_lines = [
            line for line in section
            if re.match(r"^(?:ACM\b|International Journal\b|IEEE\b|Springer\b|Elsevier\b|"
                        r"Journal of\b|International Conference\b)", line, re.IGNORECASE)
        ]
        if len(venue_lines) > 1:
            return [{
                "title": "",
                "venue": line,
                "type": "conference" if re.search(r"conference|autoui", line, re.IGNORECASE) else "journal",
                "indexed": bool(re.search(r"international journal|journal of|scie|scopus|ugc|aicte", line, re.IGNORECASE)),
            } for line in venue_lines]

    indexed_cues = (
        "scie", "scopus", "ugc", "aicte", "journal", "volume", "issue", "issn",
        "international journal", "expert systems with applications", "aibi research",
        "ijrte", "ijca", "information sciences", "applied soft computing",
        "ieee access", "knowledge-based systems", "information processing & management",
    )
    excluded_cues = ("book", "conference", "proceedings", "symposium", "autoui")
    entries = []
    for kind, block in blocks:
        lower = block.lower()
        is_indexed = kind == "journal" or any(cue in lower for cue in indexed_cues)
        if any(cue in lower for cue in excluded_cues) and not any(cue in lower for cue in ("scie", "scopus", "ugc", "aicte")):
            is_indexed = False
        entries.append({
            "title": re.sub(r"^[•●▪*-]\s*", "", block).strip(),
            "venue": "",
            "type": kind or ("journal" if is_indexed else "other"),
            "indexed": bool(is_indexed),
        })
    return entries


def _coerce_publication_indexed(value):
    """Convert provider booleans such as ``true``/``"true"`` safely."""
    if isinstance(value, bool):
        return value
    return str(value or "").strip().lower() in {"true", "1", "yes", "y"}


def _explicit_indexed_publication_count(text):
    """Read an explicitly stated indexed-publication count from the CV.

    Large academic CVs commonly provide a reliable summary count near the
    profile section even when their detailed publication list is too long for
    a provider to reproduce as individual JSON records.
    """
    clean = re.sub(r"\s+", " ", str(text or "")).lower()
    patterns = (
        r"(?:number|no\.?)[\s-]+of\s+publications?\s+indexed\s+in\s+scopus\s*[:\-]?\s*(\d+)",
        r"(\d+)\s*\+?\s+scopus[- ]indexed\s+(?:research\s+)?(?:articles?|papers?|publications?)",
    )
    counts = []
    for pattern in patterns:
        counts.extend(int(value) for value in re.findall(pattern, clean))
    return max(counts) if counts else 0


def reconcile_publication_counts(parsed_json, resume_text=""):
    """Make publication totals agree with per-publication entries.

    The application has two extraction paths. One can identify publications
    directly from the source text; the other may receive a provider-generated
    ``publication_entries`` array without a recognizable publication heading.
    In either case, the aggregate fields used by AICTE and matching must be
    calculated from the entries rather than trusted from an LLM-provided
    default of zero.
    """
    if not isinstance(parsed_json, dict):
        raise ValueError("Resume extraction provider did not return an object")

    text_entries = _publication_entries_from_text(resume_text) if resume_text else None
    provider_entries = parsed_json.get("publication_entries")
    entries = text_entries if text_entries is not None else provider_entries

    if isinstance(entries, list):
        normalized_entries = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            normalized = dict(entry)
            normalized["indexed"] = _coerce_publication_indexed(normalized.get("indexed"))
            normalized_entries.append(normalized)
        parsed_json["publication_entries"] = normalized_entries
        parsed_json["total_publications"] = len(normalized_entries)
        parsed_json["total_indexed_publications"] = sum(
            1 for entry in normalized_entries if entry["indexed"]
        )
    else:
        parsed_json["total_publications"] = to_int(parsed_json.get("total_publications"))
        parsed_json["total_indexed_publications"] = to_int(
            parsed_json.get("total_indexed_publications")
        )

    # Preserve explicit summary counts when a long CV's detailed records were
    # collapsed by the LLM. A post-Ph.D. indexed count is a subset of the
    # all-career indexed count, so it is also a safe lower bound when the
    # provider emitted an inconsistent aggregate.
    explicit_indexed = _explicit_indexed_publication_count(resume_text)
    post_phd_indexed = to_int(parsed_json.get("scopus_post_phd_publications"))
    parsed_json["total_indexed_publications"] = max(
        to_int(parsed_json.get("total_indexed_publications")),
        explicit_indexed,
        post_phd_indexed,
    )
    parsed_json["total_publications"] = max(
        to_int(parsed_json.get("total_publications")),
        explicit_indexed,
    )
    return parsed_json


def normalize_extracted_resume(parsed_json, resume_text):
    """Normalize LLM output before it reaches AICTE and matching logic."""
    if not isinstance(parsed_json, dict):
        raise ValueError("Resume extraction provider did not return an object")
    parsed_json["candidate_name"] = parsed_json.get("candidate_name") or parsed_json.get("Name") or "Unknown Candidate"

    for key in ("scopus_post_phd_publications", "total_indexed_publications", "total_publications"):
        parsed_json[key] = to_int(parsed_json.get(key))
    extras = parsed_json.setdefault("extra_academic_fields", {})
    for key in ("phd_guidance_count", "phd_guidance_ongoing", "h_index", "citation_count"):
        extras[key] = to_int(extras.get(key))

    reconcile_publication_counts(parsed_json, resume_text)

    phd = (parsed_json.get("qualification") or {}).get("phd") or {}
    phd_year = phd.get("completion_year") if str(phd.get("status", "")).lower() == "completed" else None
    computed = compute_experience(parsed_json.get("experience_entries"), phd_year)
    stated = parsed_json.get("declared_experience_years") or {}
    detected = _declared_experience(resume_text)
    stated = {
        key: extract_years(stated.get(key) or detected.get(key))
        for key in ("total_years", "teaching_years", "industrial_years")
    }
    computed["date_derived_total_years"] = computed.get("total_years", 0.0)
    computed["stated_total_years"] = stated["total_years"]
    for key in ("total_years", "teaching_years", "industrial_years"):
        # An explicit bounded claim such as "2.5+ years of industry experience"
        # should not be discarded merely because the CV's dates are incomplete.
        if 0 < stated[key] <= 50:
            computed[key] = max(computed.get(key, 0.0), stated[key])
    if not computed.get("total_years"):
        computed["total_years"] = round(computed.get("teaching_years", 0) + computed.get("industrial_years", 0), 1)
    computed["details"] = (f"Teaching/Research: {computed['teaching_years']} Yrs, "
                            f"Industry: {computed['industrial_years']} Yrs (Total: {computed['total_years']} Yrs)")
    parsed_json["experience"] = computed
    return parsed_json


def calculate_total_experience(experiences):
    total_months = 0
    now = datetime.datetime.now()
    
    for exp in experiences:
        duration_str = exp.get("duration", "")
        if not duration_str:
            continue
            
        # Clean up formats like "Aug'25" or "Aug’25" to "Aug 2025"
        duration_str = re.sub(r'[\'’](\d{2})\b', r' 20\1', duration_str)
            
        parts = re.split(r'\s*(?:-|to|–)\s*', duration_str, flags=re.IGNORECASE)
        if len(parts) == 2:
            start_str, end_str = parts[0].strip(), parts[1].strip()
            if not start_str or not end_str:
                continue
                
            try:
                start_date = parser.parse(start_str, default=datetime.datetime(now.year, 1, 1))
                if end_str.lower() in ["present", "current", "till date", "today", "now"]:
                    end_date = now
                else:
                    end_date = parser.parse(end_str, default=datetime.datetime(now.year, 1, 1))
                
                months = (end_date.year - start_date.year) * 12 + (end_date.month - start_date.month)
                if months > 0:
                    total_months += months
            except Exception:
                pass
                
    return round(total_months / 12.0, 1)

# 1. TEXT EXTRACTION — HELPERS

def _clean_cid(text):
    """Clean (cid:NNN) tokens produced by unembedded fonts and map common ligatures."""
    if not text:
        return text
    replacements = [
        ("(cid:14)", "ffi"),
        ("(cid:11)", "ff"),
        ("(cid:12)", "fi"),
        ("(cid:13)", "fl"),
    ]
    for bad, good in replacements:
        text = text.replace(bad, good)
    return re.sub(r'\(cid:\d+\)', '', text)


def _fix_mojibake(text):
    """Fix Windows-1252 characters that were double-encoded as UTF-8 (mojibake).
    Applies before text is sent to the LLM so descriptions render cleanly.
    """
    if not text:
        return text
    replacements = [
        ('\u00e2\u20ac\u201c', '\u2013'),   # â€" → en-dash
        ('\u00e2\u20ac\u201d', '\u2014'),   # â€" → em-dash
        ('\u00e2\u20ac\u2122', '\u2019'),   # â€™ → right single quote / apostrophe
        ('\u00e2\u20ac\u0153', '\u201c'),   # â€œ → left double quote
        ('\u00e2\u20ac\x9d',   '\u201d'),   # â€  → right double quote
        ('\u00e2\u20ac\xa2',   '\u2022'),   # â€¢ → bullet
        ('\u00e2\u20ac\xa6',   '\u2026'),   # â€¦ → ellipsis
        ('\u00e2\u20ac\xb0',   '\u2030'),   # â€° → per mille
        # Literal string forms that survive the decode
        ('â\u20acâ\u20ac',    '\u2013'),
        ('â\u20ac™',          "'"),
        ('â\u20ac"',          '\u2013'),
    ]
    for bad, good in replacements:
        text = text.replace(bad, good)
    return text


def _detect_column_bands(page):
    """
    Detect multi-column layout by analysing where words START horizontally (x0).

    Algorithm:
    1. Collect x0 (left edge) of every word on the page.
    2. Sort and find the largest gap between consecutive x0 values.
    3. If that gap is wide enough (>= 8% of page width AND >= 40pt), treat
       it as a column gutter and split the page there.

    Returns:
        List of (x0, x1) crop bands, one per column, left-to-right.
        None if the page is single-column.
    """
    words = page.extract_words()
    if not words or len(words) < 6:
        return None

    page_width = page.width
    if page_width < 200:
        return None

    # Collect all word left-edge positions
    x0_values = sorted(set(round(w["x0"], 1) for w in words))

    if len(x0_values) < 4:
        return None

    # Find the largest gap between consecutive x0 values
    best_gap = 0
    best_gap_left = 0
    best_gap_right = 0

    for i in range(1, len(x0_values)):
        gap = x0_values[i] - x0_values[i - 1]
        if gap > best_gap:
            best_gap = gap
            best_gap_left = x0_values[i - 1]
            best_gap_right = x0_values[i]

    # Thresholds: gap must be meaningful relative to the page
    min_gap_abs = 40          # at least 40pt wide
    min_gap_pct = 0.08        # at least 8% of page width

    if best_gap < min_gap_abs or best_gap < page_width * min_gap_pct:
        return None

    # Split point is the midpoint of the gutter
    split_x = (best_gap_left + best_gap_right) / 2.0

    # Balance check: the smaller side must contain real column content,
    # not just margin annotations (dates, links, icons).
    # Rule: minor side needs ≥ 25 words AND those words must span ≥ 40%
    # of the page height (true columns run most of the page; scattered
    # annotations don't).
    total = len(words)
    left_count = sum(1 for w in words if w["x0"] < split_x)
    right_count = total - left_count

    if left_count <= right_count:
        minor_words = [w for w in words if w["x0"] < split_x]
    else:
        minor_words = [w for w in words if w["x0"] >= split_x]

    minor_count = len(minor_words)
    if minor_count < 25:
        return None

    y_vals = [w["top"] for w in minor_words]
    y_span = max(y_vals) - min(y_vals)
    if y_span < page.height * 0.40:
        return None

    return [(0, split_x), (split_x, page_width)]


def _chars_to_lines(chars):
    """
    Group characters into lines by Y-coordinate, preserving PDF stream order.
    Returns list of (first_x0, line_text) tuples.

    - Characters within 3pt vertically are considered the same line.
    - A space is inserted when the horizontal gap exceeds 2pt.
    - first_x0 is the x0 of the very first character in the line
      (used for column assignment in multi-column pages).
    """
    if not chars:
        return []

    lines_data = []
    curr_line = []
    curr_top = None
    prev_x1 = None
    first_x0 = None

    for c in chars:
        top = c.get("top", 0)
        x0 = c.get("x0", 0)
        x1 = c.get("x1", x0)
        text = c.get("text", "")
        size = c.get("size", 10.0)

        if curr_top is None or abs(top - curr_top) <= 3.0:
            # Same line — insert space if there is a horizontal gap
            if prev_x1 is not None and (x0 - prev_x1) > 0.15 * size:
                curr_line.append(" ")
            curr_line.append(text)
            curr_top = top
            prev_x1 = max(prev_x1, x1) if prev_x1 is not None else x1
            if first_x0 is None:
                first_x0 = x0
        else:
            # New line — flush previous
            lines_data.append((first_x0, "".join(curr_line)))
            curr_line = [text]
            curr_top = top
            prev_x1 = x1
            first_x0 = x0

    if curr_line:
        lines_data.append((first_x0, "".join(curr_line)))
    return lines_data


def _extract_page_text(page):
    """
    Smart per-page extractor:
    - Auto-detects multi-column layout via word-start positions.
    - For multi-column: extracts ALL characters in stream order from the full
      page, groups them into lines, and assigns each line to left/right column
      based on where its first character starts.  This avoids crop-based word
      truncation that occurs when words straddle the column boundary.
    - For single-column: uses stream-order extraction directly.
    - Cleans (cid:NNN) tokens and ligatures.
    """
    chars = getattr(page, "chars", None)
    if not chars:
        text = page.extract_text(x_tolerance=2, y_tolerance=3)
        return _clean_cid(text) if text else ""

    bands = _detect_column_bands(page)

    if bands is None:
        # Single-column — stream-order extraction
        lines_data = _chars_to_lines(chars)
        text = "\n".join(t for _, t in lines_data)
        return _clean_cid(text)

    # Multi-column — assign each line to its column based on first_x0
    split_x = bands[0][1]       # boundary between left and right columns
    lines_data = _chars_to_lines(chars)

    left_lines = [t for fx0, t in lines_data if fx0 < split_x]
    right_lines = [t for fx0, t in lines_data if fx0 >= split_x]

    combined = "\n".join(left_lines) + "\n" + "\n".join(right_lines)
    return _clean_cid(combined.strip())


# 1. TEXT EXTRACTION

def extract_text_preserving_layout(file_path):
    """Extracts text from PDF or DOCX with auto multi-column support."""
    full_text = ""
    if file_path.lower().endswith('.docx') or file_path.lower().endswith('.doc'):
        try:
            import docx
            doc = docx.Document(file_path)
            for para in doc.paragraphs:
                if para.text.strip():
                    full_text += para.text + "\n"
            for table in doc.tables:
                for row in table.rows:
                    row_text = " | ".join([cell.text.strip() for cell in row.cells if cell.text.strip()])
                    if row_text:
                        full_text += row_text + "\n"
        except Exception as e:
            print(f"Error reading DOCX: {e}")
            return ""
    else:
        try:
            with pdfplumber.open(file_path) as pdf:
                for page in pdf.pages:
                    page_text = _extract_page_text(page)
                    if page_text:
                        full_text += page_text + "\n"
        except Exception as e:
            print(f"Error reading PDF: {e}")
            return ""
    return _fix_mojibake(full_text)

# 2. LLM EXTRACTION VIA OPENROUTER WITH T.C.R.A.F.T. SYSTEM PROMPT

def extract_big_resume_summary(resume_text):
    """
    Multi-stage high-capacity pre-extraction pass for Big / Long Resumes (>10,000 characters).
    Uses provider_manager with a 128k-context large LLM (Llama 3.3 70B / Qwen 2.5 72B / Gemma)
    to summarize all extensive sections without character truncation.
    """
    print(f"Big academic resume detected ({len(resume_text)} chars). Running high-capacity pre-extraction pass...")
    system_prompt = (
        "You are an expert Academic Resume Pre-Processor. "
        "Extract and summarize every key section accurately into structured text without omitting any publications, grants, patents, or qualifications."
    )

    prompt = f"""
    Thoroughly analyze and summarize the following extensive academic curriculum vitae.
    Preserve ALL exact facts, counts, titles, numbers, and dates without hallucinating:
    1. Candidate Full Name, Email, Phone Number, Links
    2. Educational Qualifications (UG, PG, PhD degrees with exact Branch, College/University, Passing Year, Class/CGPA/Percentage obtained)
    3. Teaching Experience (years & subjects taught) and Industrial Experience (years, company names, designations, dates)
    4. Exact Count and details of Research Publications: SCI, Scopus, UGC Care indexed papers, conference proceedings, and post-PhD publication count
    5. Patents (status: Filed, Published, or Granted with titles)
    6. Sponsored Research Grants, AICTE/DST/SERB/Govt funding (Grant agency, project title, sanctioned amount in Lakhs)
    7. Doctoral Guidance / PhD Supervision Count (awarded vs ongoing)
    8. Administrative Leadership Roles (Dean, HOD, TPO, Controller of Examinations) & Accreditation Work (NBA SAR, NAAC SSR)
    9. Core Technical Domains & Specializations (e.g. AI/ML, Cyber Security, Cloud, VLSI, Robotics)
    10. Key Projects & Technical Skills

    CURRICULUM VITAE TEXT:
    {resume_text[:60000]}
    """

    try:
        result = provider_manager.execute_with_fallback(system_prompt, prompt)
        if result and isinstance(result, dict):
            tokens_used = result.get("_llm_metadata", {}).get("total_tokens", 0)
            print(f"\n==============================================")
            print(f"Tokens consumed for Big Resume Pre-extraction: {tokens_used}")
            print(f"==============================================\n")
            return json.dumps(result, indent=2)
    except Exception as e:
        print(f"Big resume stage 1 warning: {e}")

    return resume_text


def extract_resume_json(resume_text, model="qwen/qwen3-32b"):
    """
    Sends the resume text to OpenRouter using T.C.R.A.F.T. prompt and returns structured JSON dictionary.
    Supports Big Resumes via multi-stage extraction pass.
    """
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    current_year = datetime.date.today().year
    current_month = datetime.date.today().strftime("%B")

    # Keep the original text separate from the intermediate summary. The
    # summary is useful for organization, but it must not replace publication
    # pages that occur after the first excerpt of a long CV.
    source_resume_text = resume_text
    if len(source_resume_text) > 10000:
        summary_text = extract_big_resume_summary(source_resume_text)
        if summary_text == source_resume_text:
            resume_text = source_resume_text
        else:
            resume_text = (
                summary_text
                + "\n\nFULL ORIGINAL RESUME TEXT (AUTHORITATIVE SOURCE):\n"
                + source_resume_text
            )

    start = time.perf_counter()

    system_prompt = f"""
T.C.R.A.F.T. INSTRUCTION FOR ACADEMIC & FACULTY RESUME EXTRACTION

T - TASK:
You are a faculty-resume EXTRACTION engine. Copy structured facts from the resume into the JSON schema below.
You are NOT an evaluator: do NOT judge AICTE eligibility, do NOT recommend a post, do NOT add up years of experience. Downstream Python code does that.
Never infer or fabricate. If a text field is absent write "Not Mentioned"; if a numeric field is absent write 0.

C - CONTEXT:
Evaluation Date: {current_month} {current_year}

R - ROLE: Faculty Resume Data Extraction Specialist.
A - AUDIENCE: A deterministic rule engine. Its input must be exact and machine-readable.
F - FORMAT: Output ONLY a raw valid JSON object. No markdown, no preamble.

T - RULES:
1. contact_number / email_id: "Not Mentioned" if absent.
2. total_publications, total_indexed_publications, scopus_post_phd_publications, phd_guidance_count, phd_guidance_ongoing, h_index, citation_count MUST be plain integers, never text (write 2, not "2 awarded").
3. total_publications counts all distinct publication records. total_indexed_publications counts only journal papers in SCI/SCIE/SSCI/Scopus/UGC Care/AICTE-approved journals over the WHOLE career. Exclude conference papers and book chapters. When a venue is not explicitly indexed, do not classify it as indexed.
4. scopus_post_phd_publications = the subset published AFTER the Ph.D. was awarded. 0 if the Ph.D. is not completed.
5. experience_entries: ONE object per position held (a promotion inside the same institute = a separate entry).
   - start / end: "YYYY-MM" (or "YYYY" if no month is given); end = "Present" if current.
   - type: "Teaching" (faculty roles), "Research" (research fellow / post-doc / scientist) or "Industry" (everything else).
   - designation: exactly as written (e.g. "Associate Professor").
   - Do NOT calculate durations or totals.
6. class_obtained: copy as written (First Class / Distinction / 8.2 CGPA / 68%). phd.completion_year = year the Ph.D. was AWARDED, or "Ongoing" if pursuing.
7. phd_guidance_count = Ph.D. scholars already AWARDED under this candidate. phd_guidance_ongoing = currently supervised.
8. research_areas: 3-10 short atomic terms (1-3 words) from the Ph.D. topic, stated specialization and publication topics (e.g. "Machine Learning", "VLSI").
9. HOD / Dean / COE / TPO / Director roles go into administrative_leadership_roles.
RESEARCH AREA RULE:

Only include a research area if it is explicitly supported by:
1. Research Interests / Research Areas section
2. Ph.D. topic
3. Publication title/topic
4. Explicit specialization statement

Do NOT infer "Artificial Intelligence", "Machine Learning",
"Data Science", "Cyber Security", etc. from general technical skills,
coursework, or broad job responsibilities.

OUTPUT SCHEMA (return strictly this JSON object):
{{
  "candidate_name": "Full Name or 'Not Mentioned'",
  "contact_number": "Phone or 'Not Mentioned'",
  "email_id": "Email or 'Not Mentioned'",
  "qualification": {{
    "ug":  {{"degree": "B.E. / B.Tech / B.S. / B.Sc / None", "branch": "", "university": "", "passing_year": "Year or 'Not Mentioned'", "class_obtained": ""}},
    "pg":  {{"degree": "M.E. / M.Tech / M.S. / M.Sc / MCA / None", "branch": "", "university": "", "passing_year": "Year / Ongoing / 'Not Mentioned'", "class_obtained": ""}},
    "phd": {{"status": "Completed / Pursuing / None", "discipline": "", "university": "", "completion_year": "Year / Ongoing / 'Not Mentioned'"}},
    "formatted_string": "UG: ... | PG: ... | Ph.D.: ..."
  }},
  "total_indexed_publications": 0,
  "total_publications": 0,
  "scopus_post_phd_publications": 0,
  "scopus_publication_details": "Short description of publications",
  "publication_entries": [
    {{"title": "", "venue": "", "type": "journal / book / conference / other", "indexed": false}}
  ],
  "patents": "Filed / Published / Granted details or 'Nil'",
  "grants_funding": "Agency + amount or 'Nil'",
  "experience_entries": [
    {{"designation": "", "organization": "", "type": "Teaching / Research / Industry", "start": "YYYY-MM", "end": "YYYY-MM or Present"}}
  ],
  "declared_experience_years": {{"total_years": 0, "teaching_years": 0, "industrial_years": 0}},
  "previous_employers": [],
  "research_areas": [],
  "extra_academic_fields": {{
    "core_domain_specialization": "AI/ML, Cyber Security, VLSI, ...",
    "h_index": 0,
    "citation_count": 0,
    "h_index_citations": "text as written or 'Not Mentioned'",
    "phd_guidance_count": 0,
    "phd_guidance_ongoing": 0,
    "accreditation_experience": "NBA SAR / NAAC / IQAC work or 'Not Mentioned'",
    "administrative_leadership_roles": "HOD / Dean / COE / TPO or 'Not Mentioned'",
    "professional_memberships_upskilling": "IEEE / ACM / ISTE / NPTEL / FDPs or 'Not Mentioned'",
    "sponsored_grants_consultancy": "DST / SERB / AICTE / industry or 'Not Mentioned'"
  }},
  "Skills": {{"Programming Languages": [], "Tools": [], "Technologies": []}}
}}
"""

    user_content = f"Extract this academic resume according to T.C.R.A.F.T. instructions. Return ONLY valid JSON:\n\n{resume_text}"

    parsed_json = provider_manager.execute_with_fallback(system_prompt, user_content)
    
    if parsed_json and isinstance(parsed_json, dict):
        tokens_used = parsed_json.get("_llm_metadata", {}).get("total_tokens", 0)
        print(f"\n==============================================")
        print(f"Tokens consumed for Resume Extraction: {tokens_used}")
        print(f"==============================================\n")
        
    return normalize_extracted_resume(parsed_json, source_resume_text)

# 3. MAIN RUNNER

def process_resume(file_path):
    print(f"Reading file: {file_path}...")
    
    full_text = extract_text_preserving_layout(file_path)
    if not full_text:
        print("Empty or unreadable file")
        return
    # print("text", full_text)
    print("Extracting data via LLM...")
    # extracted_data = "meet"
    extracted_data = extract_resume_json(full_text)
    
    if extracted_data:
        print("\n--- EXTRACTION RESULT ---")
        # print(json.dumps(extracted_data, indent=4, ensure_ascii=False))
        
        # Generate the PDF (Uncomment when ready)
        # candidate_name = extracted_data.get("Name", "Unknown")
        # pdf_name = candidate_name.replace(" ", "_") + "_NcircleCV.pdf"
        # generate_resume_pdf(extracted_data, pdf_name)
        # print(f"Generated PDF: {pdf_name}")

if __name__ == "__main__":
    resume_paths = [
        # "./Resumes/2pg2.pdf",
        # "./Resumes/1quarter.pdf",
        # "./Resumes/03_Data_Scientist_Rahul_Mehta.pdf",
        # "./Resumes/Aman_Babu_s_Resume__Copy_ (1).pdf",
        # "./Resumes/civil.pdf",
        # "./Resumes/icons_resume.pdf",
        # "./Resumes/1manyinfo2.pdf",
        # "./Resumes/1_2cols_pic.pdf",
        # "./Resumes/1_page_many_info.pdf",
        # "./Resumes/3_page.pdf",
    ]

    for pdf_path in resume_paths:
        process_resume(pdf_path)
