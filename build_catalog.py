"""
build_catalog.py
=================
Builds frontend/course_catalog.json from:
  1. frontend/1.json        — all verified course data
  2. Sheet1.csv             — university logo URLs

Output fields per course:
  id, name, university, affiliated_uni, logo_url,
  domain (ID-based band), course_type (academic level),
  country, cost, duration, mode, url,
  skills_description, has_qs_badge, has_nirf_badge,
  has_scholarship, has_free
"""

import json
import csv
import re
import os
from difflib import SequenceMatcher

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
INPUT_JSON = os.path.join(BASE_DIR, "frontend", "1.json")
CSV_PATH   = os.path.join(BASE_DIR, "Untitled spreadsheet - Sheet1.csv")
OUTPUT     = os.path.join(BASE_DIR, "frontend", "course_catalog.json")

# ── Domain Bands (same as app.js DOMAIN_RANGES) ───────────────────────────────
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

# Free/Audit/HVLC bands => course_type = "Certificate"
FREE_BANDS = {"Free", "Free to Audit", "High Value Low Cost"}

# ── Known University Aliases ──────────────────────────────────────────────────
# normalised lowercase alias => exact CSV university name
ALIASES = {
    # IITs
    "iit kanpur":          "Indian Institute of Technology Kanpur",
    "iitk":                "Indian Institute of Technology Kanpur",
    "iit bombay":          "Indian Institute of Technology Bombay",
    "iitb":                "Indian Institute of Technology Bombay",
    "iit delhi":           "Indian Institute of Technology Delhi",
    "iitd":                "Indian Institute of Technology Delhi",
    "iit madras":          "Indian Institute of Technology Madras",
    "iitm":                "Indian Institute of Technology Madras",
    "iit roorkee":         "Indian Institute of Technology Roorkee",
    "iitr":                "Indian Institute of Technology Roorkee",
    "iit kharagpur":       "Indian Institute of Technology Kharagpur",
    "iitkgp":              "Indian Institute of Technology Kharagpur",
    "iit guwahati":        "Indian Institute of Technology Guwahati",
    "iitg":                "Indian Institute of Technology Guwahati",
    "iit hyderabad":       "Indian Institute of Technology Hyderabad",
    "iith":                "Indian Institute of Technology Hyderabad",
    "iit bhubaneswar":     "Indian Institute of Technology Bhubaneswar",
    "iit gandhinagar":     "Indian Institute of Technology Gandhinagar",
    "iit jodhpur":         "Indian Institute of Technology Jodhpur",
    "iit mandi":           "Indian Institute of Technology Mandi",
    "iit patna":           "Indian Institute of Technology Patna",
    "iit indore":          "Indian Institute of Technology Indore",
    "iit tirupati":        "Indian Institute of Technology Tirupati",
    "iit palakkad":        "Indian Institute of Technology Palakkad",
    "iit dharwad":         "Indian Institute of Technology Dharwad",
    "iit bhilai":          "Indian Institute of Technology Bhilai",
    "iit jammu":           "Indian Institute of Technology Jammu",
    # IISc
    "iisc":                "Indian Institute of Science",
    "iisc bangalore":      "Indian Institute of Science",
    "indian institute of science bangalore": "Indian Institute of Science",
    # IIMs
    "iim ahmedabad":       "Indian Institute of Management Ahmedabad",
    "iima":                "Indian Institute of Management Ahmedabad",
    "iim bangalore":       "Indian Institute of Management Bangalore",
    "iimb":                "Indian Institute of Management Bangalore",
    "iim calcutta":        "Indian Institute of Management Calcutta",
    "iimc":                "Indian Institute of Management Calcutta",
    # NITs
    "nit trichy":          "National Institute of Technology Tiruchirappalli",
    "nit tiruchirappalli": "National Institute of Technology Tiruchirappalli",
    "nit warangal":        "National Institute of Technology Warangal",
    "nit calicut":         "National Institute of Technology Calicut",
    "nit surathkal":       "National Institute of Technology Karnataka",
    "nitk":                "National Institute of Technology Karnataka",
    "nit kurukshetra":     "National Institute of Technology Kurukshetra",
    "nit rourkela":        "National Institute of Technology Rourkela",
    "nit allahabad":       "Motilal Nehru National Institute of Technology Allahabad",
    "mnnit":               "Motilal Nehru National Institute of Technology Allahabad",
    "mnit jaipur":         "Malaviya National Institute of Technology",
    "mnit":                "Malaviya National Institute of Technology",
    "nit surat":           "Sardar Vallabhbhai National Institute of Technology",
    "svnit":               "Sardar Vallabhbhai National Institute of Technology",
    # IIITs
    "indian institute of information technology kota":     "IIIT Kota",
    "indian institute of information technology allahabad": "IIIT Allahbad",
    "indian institute of information technology hyderabad": "IIIT Hyderabad",
    "indian institute of information technology bangalore": "IIIT Bangalore",
    "indian institute of information technology gwalior":  "IIITM Gwalior",
    "indian institute of information technology bhopal":   "IIIT Bhopal",
    "indian institute of information technology vadodara": "IIIT Vadodara",
    "indian institute of information technology tiruchirappalli": "IIIT Tiruchirappalli",
    "indian institute of information technology una":     "IIIT, Una",
    "indian institute of information technology surat":   "IIIT, Surat",
    "iiit kota":           "IIIT Kota",
    "iiit allahabad":      "IIIT Allahbad",
    "iiit hyderabad":      "IIIT Hyderabad",
    "iiit bangalore":      "IIIT Bangalore",
    # NIELIT
    "national institute of electronics & it":  "NIELIT",
    "national institute of electronics and information technology": "NIELIT",
    "nielit":              "NIELIT",
    # Anna University (used as fallback for affiliated colleges)
    "anna university":     "Anna University",
    # Common
    "bits pilani":         "Birla Institute of Technology and Science",
    "bits":                "Birla Institute of Technology and Science",
    "vit":                 "Vellore Institute of Technology",
    "vit vellore":         "Vellore Institute of Technology",
    "thapar":              "Thapar Institute of Engineering and Technology",
    "manipal":             "Manipal Academy of Higher Education",
    "mahe":                "Manipal Academy of Higher Education",
    "upes":                "University of Petroleum and Energy Studies",
    "du":                  "University of Delhi",
    "delhi university":    "University of Delhi",
    "jadavpur":            "Jadavpur University",
    "uoh":                 "University of Hyderabad",
    "vtu":                 "Visvesvaraya Technological University",
    # International
    "mit":                 "Massachusetts Institute of Technology",
    "stanford":            "Stanford University",
    "harvard":             "Harvard University",
    "oxford":              "University of Oxford",
    "cambridge":           "University of Cambridge",
    "ucl":                 "University College London",
    "imperial":            "Imperial College London",
    "nus":                 "National University of Singapore",
    "ntu singapore":       "Nanyang Technological University",
    "ntu":                 "Nanyang Technological University",
    "hkust":               "Hong Kong University of Science and Technology",
    "eth zurich":          "ETH Zurich",
    "epfl":                "Ecole Polytechnique Federale de Lausanne",
}


# ── Normalisation helpers ─────────────────────────────────────────────────────
_PUNCT = re.compile(r"[^a-z0-9 ]")

def _norm(text):
    return _PUNCT.sub(" ", (text or "").lower()).strip()


def _token_ratio(a, b):
    na, nb = _norm(a), _norm(b)
    if na == nb:
        return 1.0
    ta = set(na.split())
    tb = set(nb.split())
    if not ta or not tb:
        return 0.0
    jaccard = len(ta & tb) / len(ta | tb)
    seq = SequenceMatcher(None, na, nb).ratio()
    return 0.5 * jaccard + 0.5 * seq


# ── Load CSV logo map ─────────────────────────────────────────────────────────
def load_logo_map(csv_path):
    logo_map = {}
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < 2:
                continue
            name = row[0].strip()
            url  = row[1].strip()
            if name and url:
                logo_map[_norm(name)] = url
    print(f"[OK] Loaded {len(logo_map)} logo entries from CSV.")
    return logo_map


_ALIAS_NORM = {_norm(k): _norm(v) for k, v in ALIASES.items()}


def find_logo(uni_name, logo_map):
    if not uni_name or uni_name.lower() in ("unknown", "nan", ""):
        return ""

    # Strip parenthetical affiliation suffixes: "College X (Anna University)" -> "College X"
    clean_name = re.sub(r"\s*\([^)]*university[^)]*\)\s*", " ", uni_name, flags=re.IGNORECASE).strip()
    # Also strip trailing location qualifiers like ", Mandore" if present after a college name
    clean_name = re.sub(r",\s*[A-Z][a-z].*$", "", clean_name).strip()

    def _lookup(name):
        n = _norm(name)
        # 1. Exact
        if n in logo_map:
            return logo_map[n]
        # 2. Alias exact
        alias_target = _ALIAS_NORM.get(n)
        if alias_target and alias_target in logo_map:
            return logo_map[alias_target]
        # 3. Alias substring
        for alias_n, target_n in _ALIAS_NORM.items():
            if alias_n in n or n.startswith(alias_n):
                if target_n in logo_map:
                    return logo_map[target_n]
        # 4. Fuzzy
        best_score, best_url = 0.0, ""
        for csv_n, url in logo_map.items():
            score = _token_ratio(n, csv_n)
            if score > best_score:
                best_score, best_url = score, url
        if best_score >= 0.72:
            return best_url
        return ""

    # Try with cleaned name first, fall back to original
    result = _lookup(clean_name)
    if not result and clean_name != uni_name:
        result = _lookup(uni_name)
    return result


# ── Domain band lookup ────────────────────────────────────────────────────────
def get_domain_band(course_id):
    for band in DOMAIN_RANGES:
        if band["min"] <= course_id <= band["max"]:
            return band["label"]
    return "Uncategorised"


# ── Skills description ────────────────────────────────────────────────────────
def extract_skills_description(course):
    """Pull the best AI-generated skills text from pdf_table Skills row."""
    for row in (course.get("pdf_table") or []):
        if isinstance(row, dict) and row.get("attribute", "").lower() == "skills":
            verified = (row.get("verified") or "").strip()
            if verified and len(verified) > 10:
                return verified
    return (course.get("skills") or "").strip()


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(f"[*] Loading {INPUT_JSON}...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        courses = json.load(f)
    print(f"    {len(courses)} courses loaded.")

    logo_map = load_logo_map(CSV_PATH)

    catalog = []
    matched = 0
    unmatched_unis = []

    for c in courses:
        cid = c.get("id", 0)

        domain_band = get_domain_band(cid)
        raw_domain  = c.get("domain", "")

        if domain_band in FREE_BANDS:
            course_type = "Certificate"
        else:
            course_type = raw_domain if raw_domain else "Unknown"

        uni_name = c.get("university") or c.get("uni") or ""
        logo_url = find_logo(uni_name, logo_map)
        if logo_url:
            matched += 1
        else:
            unmatched_unis.append(uni_name)

        has_free = domain_band in {"Free", "Free to Audit"}

        entry = {
            "id":                 cid,
            "name":               c.get("name", ""),
            "university":         uni_name,
            "affiliated_uni":     c.get("affiliated_uni", ""),
            "logo_url":           logo_url,
            "domain":             domain_band,
            "course_type":        course_type,
            "country":            c.get("country", ""),
            "cost":               c.get("cost", ""),
            "duration":           c.get("duration", ""),
            "mode":               c.get("mode", ""),
            "url":                c.get("url", ""),
            "skills_description": extract_skills_description(c),
            "has_qs_badge":       bool(c.get("has_qs_badge")),
            "has_nirf_badge":     bool(c.get("has_nirf_badge")),
            "has_scholarship":    bool(c.get("scholarship_match")),
            "has_free":           has_free,
        }
        catalog.append(entry)

    print(f"\n[*] Logo match rate: {matched}/{len(courses)} ({100*matched//len(courses)}%)")

    print(f"\n[*] Writing {OUTPUT}...")
    with open(OUTPUT, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)
    print(f"[OK] Wrote {len(catalog)} courses -> {OUTPUT}")

    unique_unmatched = list(dict.fromkeys(unmatched_unis))[:25]
    if unique_unmatched:
        print(f"[!] Sample unmatched universities ({len(unique_unmatched)} shown):")
        for u in unique_unmatched:
            safe_u = u.encode("ascii", errors="replace").decode("ascii")
            print(f"    - {safe_u}")


if __name__ == "__main__":
    main()
