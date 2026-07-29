"""
extractor.py
=============
Lightweight course data extractor.

Reads a link_compile.pdf (same format as autonomous_course_verifier),
extracts course metadata (name, university, cost, duration, mode, country,
skills, URL, domain band, badges), looks up affiliated university from the
SQLite database, matches logo from CSV, then asks an LLM for a concise
skills description based on the course page.

Does NOT verify anything — no MATCH/MISMATCH, no status field.
Output: extracted_catalog.json in the same schema as course_catalog.json.

Usage:
    python extractor.py link_compile.pdf [--start N] [--end N]
"""

import sys
import os
import re
import csv
import json
import time
import sqlite3
import argparse
from difflib import SequenceMatcher

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

try:
    import requests
except ImportError:
    requests = None

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False
    print("[WARN] undetected-chromedriver not installed. URL extraction will use requests fallback.")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "Untitled spreadsheet - Sheet1.csv")
DB_PATH    = os.path.join(BASE_DIR, "local_database.db")
OUTPUT     = os.path.join(BASE_DIR, "extracted_catalog.json")
ENV_PATH   = os.path.join(BASE_DIR, ".env")

# ── Load .env ─────────────────────────────────────────────────────────────────
def _load_env(path):
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

_load_env(ENV_PATH)

# ── Domain Bands ──────────────────────────────────────────────────────────────
DOMAIN_RANGES = [
    {"label": "Free",                   "min": 1,    "max": 25},
    {"label": "Free to Audit",          "min": 26,   "max": 48},
    {"label": "High Value Low Cost",    "min": 49,   "max": 100},
    {"label": "Foundational",           "min": 101,  "max": 601},
    {"label": "Network Infrastructure", "min": 602,  "max": 1585},
    {"label": "System & Endpoint",      "min": 1586, "max": 1890},
    {"label": "Cyber Forensics",        "min": 1891, "max": 2634},
    {"label": "Data & Application",     "min": 2635, "max": 2965},
    {"label": "Legal & Ethical",        "min": 2966, "max": 3727},
]
FREE_BANDS = {"Free", "Free to Audit", "High Value Low Cost"}

# ── University Aliases (same as build_catalog.py) ─────────────────────────────
ALIASES = {
    "iit kanpur": "Indian Institute of Technology Kanpur",
    "iitk": "Indian Institute of Technology Kanpur",
    "iit bombay": "Indian Institute of Technology Bombay",
    "iitb": "Indian Institute of Technology Bombay",
    "iit delhi": "Indian Institute of Technology Delhi",
    "iitd": "Indian Institute of Technology Delhi",
    "iit madras": "Indian Institute of Technology Madras",
    "iitm": "Indian Institute of Technology Madras",
    "iit roorkee": "Indian Institute of Technology Roorkee",
    "iitr": "Indian Institute of Technology Roorkee",
    "iit kharagpur": "Indian Institute of Technology Kharagpur",
    "iitkgp": "Indian Institute of Technology Kharagpur",
    "iit guwahati": "Indian Institute of Technology Guwahati",
    "iitg": "Indian Institute of Technology Guwahati",
    "iit hyderabad": "Indian Institute of Technology Hyderabad",
    "iith": "Indian Institute of Technology Hyderabad",
    "iit bhubaneswar": "Indian Institute of Technology Bhubaneswar",
    "iit gandhinagar": "Indian Institute of Technology Gandhinagar",
    "iit jodhpur": "Indian Institute of Technology Jodhpur",
    "iit mandi": "Indian Institute of Technology Mandi",
    "iit patna": "Indian Institute of Technology Patna",
    "iit indore": "Indian Institute of Technology Indore",
    "iisc": "Indian Institute of Science",
    "iisc bangalore": "Indian Institute of Science",
    "iim ahmedabad": "Indian Institute of Management Ahmedabad",
    "iima": "Indian Institute of Management Ahmedabad",
    "iim bangalore": "Indian Institute of Management Bangalore",
    "iimb": "Indian Institute of Management Bangalore",
    "iim calcutta": "Indian Institute of Management Calcutta",
    "iimc": "Indian Institute of Management Calcutta",
    "nit trichy": "National Institute of Technology Tiruchirappalli",
    "nit tiruchirappalli": "National Institute of Technology Tiruchirappalli",
    "nit warangal": "National Institute of Technology Warangal",
    "nit calicut": "National Institute of Technology Calicut",
    "nit surathkal": "National Institute of Technology Karnataka",
    "nitk": "National Institute of Technology Karnataka",
    "nit kurukshetra": "National Institute of Technology Kurukshetra",
    "nit rourkela": "National Institute of Technology Rourkela",
    "mnnit": "Motilal Nehru National Institute of Technology Allahabad",
    "mnit": "Malaviya National Institute of Technology",
    "svnit": "Sardar Vallabhbhai National Institute of Technology",
    "bits pilani": "Birla Institute of Technology and Science",
    "bits": "Birla Institute of Technology and Science",
    "vit": "Vellore Institute of Technology",
    "thapar": "Thapar Institute of Engineering and Technology",
    "manipal": "Manipal Academy of Higher Education",
    "mahe": "Manipal Academy of Higher Education",
    "upes": "University of Petroleum and Energy Studies",
    "anna university": "Anna University",
    "vtu": "Visvesvaraya Technological University",
    "mit": "Massachusetts Institute of Technology",
    "stanford": "Stanford University",
    "harvard": "Harvard University",
    "oxford": "University of Oxford",
    "cambridge": "University of Cambridge",
    "ucl": "University College London",
    "imperial": "Imperial College London",
    "nus": "National University of Singapore",
    "ntu singapore": "Nanyang Technological University",
    "eth zurich": "ETH Zurich",
}

_PUNCT = re.compile(r"[^a-z0-9 ]")

def _norm(text):
    return _PUNCT.sub(" ", (text or "").lower()).strip()

_ALIAS_NORM = {_norm(k): _norm(v) for k, v in ALIASES.items()}

# ── PDF ligature normalisation ─────────────────────────────────────────────────────────
_LIGATURES = [
    ("\ufb01", "fi"),  # fi ligature (Shef?eld -> Sheffield)
    ("\ufb02", "fl"),  # fl ligature
    ("\ufb00", "ff"),  # ff ligature
    ("\ufb03", "ffi"), # ffi ligature
    ("\ufb04", "ffl"), # ffl ligature
]

def _clean_uni_name(name):
    """Normalise PDF ligatures, fix missing spaces, strip affiliation parentheticals."""
    if not name:
        return name
    for bad, good in _LIGATURES:
        name = name.replace(bad, good)
    # Fix missing spaces e.g. "University ofWashington"
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Strip parenthetical affiliation: "College (Anna University)" -> "College"
    # Handles: (Anna Uni.) (Jawaharlal Nehru Technological Uni.) (A.P.J. Abdul Kalam Technological University)
    name = re.sub(r"\s*\([^)]*(?:university|uni\.|univ\.)[^)]*\)\s*", " ", name, flags=re.IGNORECASE).strip()
    # Strip trailing location qualifiers: "College, City, State"
    name = re.sub(r",\s+[A-Z][a-zA-Z .]+$", "", name).strip()
    return name.strip()


def resolve_university_name(raw_name: str, logo_map: dict) -> str:
    """
    Normalise abbreviations and return the canonical CSV name.
    Priority: direct alias -> CSV fuzzy match -> raw name.
    """
    if not raw_name or raw_name.lower() in ("unknown", "nan", ""):
        return raw_name
    # First clean ligatures and parentheticals
    cleaned = _clean_uni_name(raw_name)
    n = _norm(cleaned)
    # direct alias
    alias_target = _ALIAS_NORM.get(n)
    if alias_target:
        for csv_norm, url in logo_map.items():
            if _norm(csv_norm) == alias_target or alias_target in _norm(csv_norm):
                return csv_norm.title()
    # fuzzy match to CSV keys
    best, best_name = 0.0, cleaned
    for csv_n in logo_map:
        s = SequenceMatcher(None, n, _norm(csv_n)).ratio()
        if s > best:
            best, best_name = s, csv_n
    if best >= 0.80:
        return best_name.title()
    return cleaned


# ── Logo lookup ───────────────────────────────────────────────────────────────
def load_logo_map(csv_path):
    logo_map = {}
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    logo_map[_norm(row[0].strip())] = row[1].strip()
    except FileNotFoundError:
        print(f"[WARN] Logo CSV not found at {csv_path}")
    return logo_map


def find_logo(uni_name, logo_map):
    if not uni_name:
        return ""
    cleaned = _clean_uni_name(uni_name)
    n = _norm(cleaned)
    if n in logo_map:
        return logo_map[n]
    alias_target = _ALIAS_NORM.get(n)
    if alias_target and alias_target in logo_map:
        return logo_map[alias_target]
    for alias_n, target_n in _ALIAS_NORM.items():
        if alias_n in n:
            if target_n in logo_map:
                return logo_map[target_n]
    best, best_url = 0.0, ""
    for csv_n, url in logo_map.items():
        s = SequenceMatcher(None, n, csv_n).ratio()
        if s > best:
            best, best_url = s, url
    return best_url if best >= 0.72 else ""


# ── Database ──────────────────────────────────────────────────────────────────
def get_affiliated_uni_from_db(course_name: str, university: str) -> str:
    """Look up affiliated university from local SQLite database."""
    if not os.path.exists(DB_PATH):
        return ""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        # Try exact match first
        cur.execute(
            "SELECT affiliated_uni FROM affiliations WHERE LOWER(course_name)=LOWER(?) AND LOWER(university)=LOWER(?)",
            (course_name.strip(), university.strip())
        )
        row = cur.fetchone()
        if row:
            return row["affiliated_uni"]
        # Fallback: university-only match
        cur.execute(
            "SELECT affiliated_uni FROM affiliations WHERE LOWER(university)=LOWER(?)",
            (university.strip(),)
        )
        row = cur.fetchone()
        conn.close()
        return row["affiliated_uni"] if row else ""
    except Exception as e:
        return ""


# ── Domain band ───────────────────────────────────────────────────────────────
def get_domain_band(course_id: int) -> str:
    for band in DOMAIN_RANGES:
        if band["min"] <= course_id <= band["max"]:
            return band["label"]
    return "Uncategorised"


# ── LLM (uses environment API keys, same as verifier) ────────────────────────
def ask_llm_for_description(course_name: str, uni_name: str, page_text: str) -> str:
    """
    Ask an LLM to produce a concise, syllabus-based skills description.
    Falls back to a summary of the page_text if no LLM key is available.
    """
    api_keys = [
        k.strip() for k in
        os.environ.get("GEMINI_API_KEYS", "").split(",") if k.strip()
    ] or [
        k.strip() for k in
        os.environ.get("MISTRAL_API_KEYS", "").split(",") if k.strip()
    ]

    if not api_keys or not page_text.strip():
        # Simple fallback: first 500 chars of skills-related text
        skills_re = re.search(
            r'(curriculum|syllabus|you will learn|skills|topics covered).{0,1000}',
            page_text, re.IGNORECASE | re.DOTALL
        )
        if skills_re:
            return skills_re.group(0)[:400].replace("\n", " ").strip()
        return page_text[:300].replace("\n", " ").strip()

    api_key = api_keys[0]
    prompt = (
        f"You are summarising a course page for a university course catalog.\n"
        f"Course: '{course_name}' at '{uni_name}'.\n\n"
        f"Based on the following extracted page text, write a concise (2-4 sentence) "
        f"professional skills description covering what students will learn, key topics, "
        f"and practical skills gained. Focus on cybersecurity-relevant content. "
        f"Do NOT mention verification, MATCH, or MISMATCH.\n\n"
        f"Page text:\n{page_text[:4000]}"
    )

    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={api_key}"
        body = {"contents": [{"parts": [{"text": prompt}]}]}
        resp = requests.post(url, json=body, timeout=30)
        if resp.ok:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
    except Exception:
        pass
    return ""


# ── Page text fetcher ─────────────────────────────────────────────────────────
def fetch_page_text(url: str) -> str:
    """Fetch course page text using requests (lightweight, no browser)."""
    if not url or url == "Unknown" or not requests:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CourseExtractor/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        text = resp.text
        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:8000]
    except Exception:
        return ""


# ── PDF Extraction ─────────────────────────────────────────────────────────────
def extract_courses_from_pdf(pdf_path: str, start_page: int = 1, end_page: int = None):
    """
    Extract course data from a link_compile.pdf style PDF.
    Mirrors the extract_and_parse logic in autonomous_course_verifier.py.
    Returns list of raw course dicts.
    """
    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    end_page = min(end_page or total_pages, total_pages)
    start_page = max(1, start_page)

    global_domain = "Unknown Domain"
    global_course_type = "Certificate"
    courses = []
    global_idx = 0  # running ID

    COURSE_KEYWORDS = ("Mode:", "Cost:", "Fees:", "Duration:", "http://", "https://", "www.")
    box_labels = ["top-left", "top-right", "bottom-left", "bottom-right"]

    for page_num in range(start_page - 1, end_page):
        page = doc[page_num]
        pw, ph = page.rect.width, page.rect.height
        half_w = pw / 2
        half_h = ph / 2
        y_top = ph * 0.08
        y_bottom = ph * 0.95

        box_rects = [
            fitz.Rect(0, y_top, half_w, half_h),
            fitz.Rect(half_w, y_top, pw, half_h),
            fitz.Rect(0, half_h, half_w, y_bottom),
            fitz.Rect(half_w, half_h, pw, y_bottom),
        ]
        quadrants = [
            {"id": f"Q{i+1}", "label": box_labels[i], "rect": box_rects[i], "blocks": [], "links": []}
            for i in range(4)
        ]

        blocks = page.get_text("blocks")
        text_blocks = [b for b in blocks if b[6] == 0]
        links = page.get_links()

        page_full_text = " ".join(b[4] for b in text_blocks)

        # Detect cover/domain pages (no course data keywords)
        top_texts = []
        for b in text_blocks:
            b_rect = fitz.Rect(b[:4])
            if b_rect.y1 <= y_top:
                tv = b[4].strip()
                if len(tv) > 2 and chr(8224) not in tv:
                    top_texts.append(tv)

        if not any(kw in page_full_text for kw in COURSE_KEYWORDS):
            if len(text_blocks) < 50 and top_texts:
                global_domain = top_texts[0]
                global_course_type = "Certificate"
                print(f"  [Domain] Page {page_num+1}: {global_domain}")
            continue

        if top_texts:
            top_upper = top_texts[0].upper()
            if any(x in top_upper for x in ["FREE COURSE", "FREE TO AUDIT", "HIGH VALUE LOW COST"]):
                global_domain = top_texts[0]
                global_course_type = "Certificate"
            else:
                global_course_type = top_texts[0]

        # Assign blocks/links to quadrants
        for b in text_blocks:
            b_rect = fitz.Rect(b[:4])
            cx = (b_rect.x0 + b_rect.x1) / 2
            cy = (b_rect.y0 + b_rect.y1) / 2
            for q in quadrants:
                if q["rect"].contains(fitz.Point(cx, cy)):
                    q["blocks"].append(b)
                    break

        for lk in links:
            l_rect = lk["from"]
            cx = (l_rect.x0 + l_rect.x1) / 2
            cy = (l_rect.y0 + l_rect.y1) / 2
            for q in quadrants:
                if q["rect"].contains(fitz.Point(cx, cy)):
                    q["links"].append(lk)
                    break

        # Parse each quadrant
        for qi, q in enumerate(quadrants):
            full_text = " ".join(b[4].replace("\n", " ") for b in q["blocks"]).strip()
            if "Mode:" not in full_text and "Cost:" not in full_text and "Fees:" not in full_text:
                continue

            full_text_lower = full_text.lower()
            has_qs   = "qs" in full_text_lower or "stars" in full_text_lower
            has_nirf = "nirf" in full_text_lower
            has_free_box = "free" in full_text_lower
            has_schol = "scholar" in full_text_lower or "financial aid" in full_text_lower

            # Word-level sorted text (mirrors verifier logic)
            words = page.get_text("words")
            q_words = [w for w in words if q["rect"].contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2))]
            q_words.sort(key=lambda w: w[1])
            lines = []
            current_line_words = []
            current_y = None
            for w in q_words:
                y = w[1]
                if current_y is None or abs(y - current_y) < 8:
                    current_line_words.append(w)
                    if current_y is None:
                        current_y = y
                else:
                    current_line_words.sort(key=lambda ww: ww[0])
                    lines.append(" ".join(ww[4] for ww in current_line_words))
                    current_line_words = [w]
                    current_y = y
            if current_line_words:
                current_line_words.sort(key=lambda ww: ww[0])
                lines.append(" ".join(ww[4] for ww in current_line_words))

            fts = "\n".join(lines)
            # Fix ligatures
            for bad, good in [("\ufb02", "fl"), ("\ufb01", "fi"), ("\ufb00", "ff"),
                               ("\u2018", "'"), ("\u2019", "'"), ("\u201c", '"'), ("\u201d", '"'),
                               ("\u2013", "-"), ("\u2014", "-"), ("\u2026", "...")]:
                fts = fts.replace(bad, good)

            # Field extraction (same regex patterns as verifier)
            def field(pattern, text=fts):
                m = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
                return m.group(1).replace("\n", " ").strip() if m else ""

            skills   = field(r"Skills:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Mode:|Country:|Link to|$))")
            cost     = field(r"Cost:\s*(.*?)(?=\s*(?:Duration:|Language:|Mode:|Skills:|Country:|Link to|$))")
            duration = field(r"Duration:\s*(.*?)(?=\s*(?:Cost:|Language:|Mode:|Skills:|Country:|Link to|$))")
            mode     = field(r"Mode:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Skills:|Country:|Link to|$))")
            country  = field(r"Country:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Mode:|Skills:|Link to|$))")
            mode = mode.replace("Offl\uFB02ine", "Offline").replace("Of\uFB02ine", "Offline")

            # Name + uni (lines before first keyword)
            pre_lines = []
            for l in lines:
                if any(l.lower().startswith(k) for k in ["cost:", "duration:", "language:", "skills:", "mode:"]):
                    break
                if l.strip():
                    pre_lines.append(l.strip())
            if len(pre_lines) > 1:
                uni_raw  = pre_lines[-1]
                name_raw = " ".join(pre_lines[:-1])
            elif len(pre_lines) == 1:
                name_raw = pre_lines[0]
                uni_raw  = "Unknown"
            else:
                name_raw = uni_raw = "Unknown"

            # URL
            url = q["links"][0].get("uri", "") if q["links"] else ""

            global_idx += 1
            courses.append({
                "_id":               global_idx,
                "_page":             page_num + 1,
                "_box":              q["label"],
                "name":              name_raw,
                "uni":               uni_raw,
                "domain_raw":        global_domain,
                "course_type_raw":   global_course_type,
                "cost":              cost,
                "duration":          duration,
                "mode":              mode,
                "country":           country,
                "skills_raw":        skills,
                "url":               url,
                "has_qs_badge":      has_qs,
                "has_nirf_badge":    has_nirf,
                "has_free_box":      has_free_box,
                "has_scholarship":   has_schol,
            })

    doc.close()
    print(f"[OK] Extracted {len(courses)} courses from pages {start_page}–{end_page}.")
    return courses


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Lightweight course extractor (no verification)")
    parser.add_argument("pdf", help="Path to link_compile.pdf")
    parser.add_argument("--start", type=int, default=1, help="Start page (1-indexed)")
    parser.add_argument("--end",   type=int, default=None, help="End page (inclusive)")
    parser.add_argument("--output", default=OUTPUT, help="Output JSON path")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM description calls")
    args = parser.parse_args()

    if not os.path.exists(args.pdf):
        print(f"[ERROR] PDF not found: {args.pdf}")
        sys.exit(1)

    logo_map = load_logo_map(CSV_PATH)
    raw_courses = extract_courses_from_pdf(args.pdf, args.start, args.end)

    catalog = []
    for idx, c in enumerate(raw_courses, 1):
        print(f"  [{idx}/{len(raw_courses)}] Processing: {c['name'][:60]}")

        # Resolve canonical university name
        uni_raw = c["uni"]
        affiliated_uni = get_affiliated_uni_from_db(c["name"], uni_raw)
        # Use affiliated uni for IIT/NIT style lookups, else raw
        uni_canonical = resolve_university_name(uni_raw, logo_map)

        # Domain band (use raw global_domain band label if it matches, else "Uncategorised")
        domain_raw = (c.get("domain_raw") or "").strip()
        domain_band = "Uncategorised"
        for band in DOMAIN_RANGES:
            if _norm(band["label"]) in _norm(domain_raw) or _norm(domain_raw) in _norm(band["label"]):
                domain_band = band["label"]
                break
        if domain_band == "Uncategorised":
            domain_band = domain_raw if domain_raw else "Uncategorised"

        course_type_raw = (c.get("course_type_raw") or "").strip()
        if domain_band in FREE_BANDS:
            course_type = "Certificate"
        else:
            course_type = course_type_raw if course_type_raw else "Unknown"

        has_free = domain_band in {"Free", "Free to Audit"}
        logo_url = find_logo(uni_canonical, logo_map)

        # Fetch page & generate description
        page_text = ""
        skills_description = c.get("skills_raw", "")
        if c.get("url") and c["url"] not in ("Unknown", ""):
            page_text = fetch_page_text(c["url"])
            if page_text and not args.no_llm:
                time.sleep(0.3)  # polite delay
                llm_desc = ask_llm_for_description(c["name"], uni_canonical, page_text)
                if llm_desc:
                    skills_description = llm_desc

        entry = {
            "id":                 c["_id"],
            "name":               c["name"],
            "university":         uni_canonical,
            "affiliated_uni":     affiliated_uni,
            "logo_url":           logo_url,
            "domain":             domain_band,
            "course_type":        course_type,
            "country":            c.get("country", ""),
            "cost":               c.get("cost", ""),
            "duration":           c.get("duration", ""),
            "mode":               c.get("mode", ""),
            "url":                c.get("url", ""),
            "skills_description": skills_description,
            "has_qs_badge":       c.get("has_qs_badge", False),
            "has_nirf_badge":     c.get("has_nirf_badge", False),
            "has_scholarship":    c.get("has_scholarship", False),
            "has_free":           has_free,
        }
        catalog.append(entry)

    out_path = args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Wrote {len(catalog)} courses -> {out_path}")


if __name__ == "__main__":
    main()
