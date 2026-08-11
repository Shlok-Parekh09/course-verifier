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
import re
import argparse
from difflib import SequenceMatcher
from dotenv import load_dotenv

load_dotenv()

def sanitize_filename(name):
    """Remove non-alphanumeric characters, replace spaces with underscores, convert to lowercase."""
    safe_name = "".join([c if c.isalnum() else "_" for c in name.lower()])
    return re.sub(r'_+', '_', safe_name).strip('_')

def _norm(x):
    s = str(x).lower().replace('&', 'and')
    return re.sub(r'[^a-z0-9]', '', s)

# ── Optional deps ─────────────────────────────────────────────────────────────
try:
    import fitz  # PyMuPDF
except ImportError:
    print("[ERROR] PyMuPDF not installed. Run: pip install pymupdf")
    sys.exit(1)

try:
    import cv2
    import numpy as np
except ImportError:
    print("[WARN] opencv-python or numpy not installed. Visual badge detection will be disabled.")
    cv2 = None

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

# ── Domain Bands ──────────────────────────────────────────────────────────────
DOMAIN_RANGES = [
    {"label": "Free"},
    {"label": "Free to Audit"},
    {"label": "High Value Low Cost"},
    {"label": "Foundational"},
    {"label": "Network Infrastructure"},
    {"label": "System & Endpoint"},
    {"label": "Cyber Forensics"},
    {"label": "Data & Application"},
    {"label": "Legal & Ethical"},
]

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
CSV_PATH   = os.path.join(BASE_DIR, "Untitled spreadsheet - Sheet1.csv")
DB_PATH    = os.path.join(BASE_DIR, "backend", "local_database.db")
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
R2_PUBLIC_URL = os.environ.get("R2_PUBLIC_URL", "").rstrip("/")

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
    "indian institute of science bangalore": "Indian Institute of Science",
    "iiitm kancheepuram": "Indian Institute of Information Technology Design and Manufacturing Kancheepuram",
    "atal bihari vajpayee indian institute of information technology and management gwalior": "IIITM Gwalior",
    "iiitm gwalior": "IIITM Gwalior",
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
    t = _PUNCT.sub(" ", (text or "").lower())
    return " ".join(t.split())

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
    
    # Expand abbreviations automatically
    name = re.sub(r"\bEngg\.?\b", "Engineering", name, flags=re.IGNORECASE)
    name = re.sub(r"\bEng\.?\b", "Engineering", name, flags=re.IGNORECASE)
    name = re.sub(r"\bMgmt\.?\b", "Management", name, flags=re.IGNORECASE)
    name = re.sub(r"\bTech\.?\b", "Technology", name, flags=re.IGNORECASE)
    name = re.sub(r"\bInst\.?\b", "Institute", name, flags=re.IGNORECASE)
    name = re.sub(r"\bUniv\.?\b", "University", name, flags=re.IGNORECASE)
    
    # Fix missing spaces e.g. "University ofWashington"
    name = re.sub(r"([a-z])([A-Z])", r"\1 \2", name)
    # Strip parenthetical affiliation: "College (Anna University)" -> "College"
    name = re.sub(r"\s*\([^)]*(?:university|uni\.|univ\.)[^)]*\)\s*", " ", name, flags=re.IGNORECASE).strip()
    # Strip trailing location qualifiers: "College, City, State"
    name = re.sub(r",\s+[A-Z][a-zA-Z .]+$", "", name).strip()
    return name.strip()


def _title_case(name):
    acronyms = {"Iit", "Iiit", "Nit", "Iim", "Aiims", "Bits", "Srm", "Vit", "Mit", "Ucl", "Nus", "Ntu", "Svkm'S", "Nmims", "Iiser", "Niser"}
    words = name.title().split()
    for i, w in enumerate(words):
        if w in acronyms:
            words[i] = w.upper()
        # Handle cases like Svkm's -> SVKM's
        elif w == "Svkm'S":
            words[i] = "SVKM's"
    return " ".join(words)

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
                return _title_case(csv_norm)
    # fuzzy match to CSV keys
    best, best_name = 0.0, cleaned
    for csv_n in logo_map:
        s = SequenceMatcher(None, n, _norm(csv_n)).ratio()
        if s > best:
            best, best_name = s, csv_n
    if best >= 0.80:
        return _title_case(best_name)
    return _title_case(cleaned)


# ── Logo lookup ───────────────────────────────────────────────────────────────
def _get_extension(url):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    ext = os.path.splitext(parsed.path)[1].lower()
    if not ext or ext not in ['.png', '.jpg', '.jpeg', '.svg', '.gif', '.webp']:
        return '.png'
    return ext

def load_logo_map(csv_path):
    logo_map = {}
    
    # 1. Try to load from the logos directory directly
    logos_dir = os.path.join(BASE_DIR, "logos")
    if os.path.exists(logos_dir):
        for f in os.listdir(logos_dir):
            if "." in f:
                base = os.path.splitext(f)[0]
                logo_map[_norm(base.replace("_", " "))] = f
                
    # 2. Then try to load from CSV (overrides directory if present, ensuring precise mapping)
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)
            for row in reader:
                if len(row) >= 2 and row[0].strip() and row[1].strip():
                    uni = row[0].strip()
                    url = row[1].strip()
                    safe_name = "".join([c if c.isalnum() else "_" for c in uni.lower()])
                    safe_name = re.sub(r'_+', '_', safe_name).strip('_')
                    filename = safe_name + _get_extension(url)
                    logo_map[_norm(_clean_brackets(uni))] = filename
    except FileNotFoundError:
        pass
        
    return logo_map


_TOKEN_MAP = {
    'inst': 'institute',
    'tech': 'technology',
    'engg': 'engineering',
    'uni': 'university',
    'univ': 'university',
    'mgmt': 'management',
    'sci': 'science',
    'national': 'natl',
}

_GENERIC = {'university', 'institute', 'college', 'school', 'engineering', 'technology', 'management', 'science', 'sciences', 'centre', 'center', 'academy', 'education'}

def _clean_brackets(s):
    return re.sub(r"\(.*?\)", "", s).strip()

def _get_tokens(s):
    words = [w for w in re.split(r'[^a-z0-9]', s.lower()) if len(w) > 2 and w not in ('the', 'and', 'for', 'of', 'at')]
    normalized = set()
    for w in words:
        normalized.add(_TOKEN_MAP.get(w, w))
    return normalized

def _is_valid_match(uni, base):
    uni_clean = _clean_brackets(uni)
    sanitized_uni = _norm(_clean_uni_name(uni_clean))
    
    if sanitized_uni == base:
        return True
        
    stripped_uni = re.sub(r"[^a-z0-9]", "", uni_clean.lower())
    stripped_base = re.sub(r"[^a-z0-9]", "", base.lower())
    
    if len(stripped_base) > 8 and stripped_base in stripped_uni:
        return True
        
    uni_tokens = _get_tokens(uni_clean)
    base_tokens = _get_tokens(base)
    inter = uni_tokens.intersection(base_tokens)
    
    non_generic = inter - _GENERIC
    if len(non_generic) > 0:
        m = max(len(uni_tokens), len(base_tokens))
        if m > 0 and len(inter) / m >= 0.75:
            return True
            
    ratio = SequenceMatcher(None, stripped_uni, stripped_base).ratio()
    if ratio >= 0.85:
        return True
            
    return False

def find_logo(uni_name, logo_map):
    if not uni_name:
        return ""
        
    uni_clean = _clean_brackets(uni_name)
    cleaned = _clean_uni_name(uni_clean)
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
                
    best_score = 0
    best_match = None
    stripped_uni = re.sub(r"[^a-z0-9]", "", uni_clean.lower())
    
    valid_candidates = []
    for csv_n, url in logo_map.items():
        if _is_valid_match(uni_name, csv_n):
            valid_candidates.append((csv_n, url))
            
    if valid_candidates:
        for csv_n, url in valid_candidates:
            stripped_base = re.sub(r"[^a-z0-9]", "", csv_n.lower())
            ratio = SequenceMatcher(None, stripped_uni, stripped_base).ratio()
            if ratio > best_score:
                best_score = ratio
                best_match = url
        return best_match
            
    return ""


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
        if row and row["affiliated_uni"] and "not found" not in row["affiliated_uni"].lower():
            conn.close()
            return row["affiliated_uni"]
            
        # Fallback: university-only match
        cur.execute(
            "SELECT affiliated_uni FROM affiliations WHERE LOWER(university)=LOWER(?)",
            (university.strip(),)
        )
        row = cur.fetchone()
        if row and row["affiliated_uni"] and "not found" not in row["affiliated_uni"].lower():
            conn.close()
            return row["affiliated_uni"]
            
        conn.close()
        return ""
    except Exception as e:
        return ""

_GLOBAL_QS = None
_GLOBAL_NIRF = None

def check_rankings_in_db(uni1: str, uni2: str = ""):
    """Check if either university name exists in QS or NIRF tables using fuzzy match."""
    global _GLOBAL_QS, _GLOBAL_NIRF
    has_qs, has_nirf = False, False
    
    if not os.path.exists(DB_PATH):
        return False, False
        
    try:
        if _GLOBAL_QS is None or _GLOBAL_NIRF is None:
            conn = sqlite3.connect(DB_PATH)
            cur = conn.cursor()
            cur.execute("SELECT university FROM qs_ranking")
            _GLOBAL_QS = [r[0].strip().lower() for r in cur.fetchall() if r[0]]
            cur.execute("SELECT university FROM nirf_ranking")
            _GLOBAL_NIRF = [r[0].strip().lower() for r in cur.fetchall() if r[0]]
            conn.close()
            
        candidates = [u.strip().lower() for u in [uni1, uni2] if u.strip()]
        if not candidates:
            return False, False
            
        try:
            from rapidfuzz import fuzz
            def is_match(c, u_list):
                if c in ["university", "institute", "college", "school"]: return False
                for u in u_list:
                    if u in ["university", "institute", "college", "school", "results"]: continue
                    if c == u or c in u or u in c:
                        return True
                    if fuzz.token_set_ratio(c, u) >= 90:
                        return True
                return False
        except ImportError:
            def is_match(c, u_list):
                if c in ["university", "institute", "college", "school"]: return False
                for u in u_list:
                    if u in ["university", "institute", "college", "school", "results"]: continue
                    if c == u or c in u or u in c:
                        return True
                return False

        for cand in candidates:
            if not has_qs and is_match(cand, _GLOBAL_QS):
                has_qs = True
            if not has_nirf and is_match(cand, _GLOBAL_NIRF):
                has_nirf = True
                
    except Exception as e:
        pass
    return has_qs, has_nirf



# ── LLM (uses environment API keys, same as verifier) ────────────────────────
def ask_llm_for_description(course_name: str, uni_name: str, page_text: str, country_raw: str = "") -> dict:
    """
    Ask an LLM to produce a concise, syllabus-based skills description, identify the university's state,
    and correct the country name if it is suspicious or abbreviated.
    Returns a dict with 'description', 'uni_state', and 'country'.
    """
    api_keys = [
        k.strip() for k in
        [os.environ.get("MISTRAL_API_KEY_1", "")] if k.strip()
    ]

    if not api_keys or not page_text.strip():
        # Simple fallback: first 500 chars of skills-related text
        fallback_desc = page_text[:300].replace("\n", " ").strip()
        skills_re = re.search(
            r'(curriculum|syllabus|you will learn|skills|topics covered).{0,1000}',
            page_text, re.IGNORECASE | re.DOTALL
        )
        if skills_re:
            fallback_desc = skills_re.group(0)[:400].replace("\n", " ").strip()
        return {"description": fallback_desc, "uni_state": "", "country": country_raw}

    api_key = api_keys[0]
    prompt = (
        f"You are summarising a course curriculum for a university course catalog.\n"
        f"Course: '{course_name}' at '{uni_name}'.\n\n"
        f"Based on the following extracted web page text (which contains the curriculum/syllabus), "
        f"generate an extremely concise, punchy description (MAXIMUM 150 characters) of the cybersecurity topics taught. "
        f"CRITICAL: Write in full, cohesive sentences. Do NOT output a comma-separated list of keywords! Get straight to the point and fit as much fine detail as possible into this short space.\n"
        f"CRITICAL: Vary your vocabulary and sentence structure for every course! Do NOT always start with the same word. Use highly diverse action verbs (e.g. 'Dive into', 'Build skills in', 'Explore', 'Study', 'Analyze').\n"
        f"FORBIDDEN WORD: You are absolutely FORBIDDEN from using the word 'Master' or 'Mastering' anywhere in the description.\n"
        f"If the text contains unrelated web errors like '403 Forbidden', 'Access Denied', or 'Cloudflare', COMPLETELY IGNORE them. Do NOT include them in the description.\n"
        f"Do NOT mention verification, MATCH, or MISMATCH.\n"
        f"Also, deduce the geographical state or province where the university '{uni_name}' is located (e.g. 'California', 'Maharashtra'). If unknown, leave empty.\n"
        f"Additionally, the parsed country name is '{country_raw}'. If this is suspicious, dirty (e.g. 'English, UK, UK'), or a code (e.g. 'US', 'UK'), fix it to the actual full country name (e.g. 'United Kingdom', 'United States'). If it's already a valid country name, keep it. If unknown, infer it from the university location or leave empty.\n"
        f"Return ONLY a raw JSON object with exactly three keys: \"description\" (the 3-liner), \"uni_state\" (the state), and \"country\" (the fixed country name). Do NOT wrap in markdown block.\n\n"
        f"Text:\n{page_text[:4000]}"
    )

    try:
        url = "https://api.mistral.ai/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        body = {
            "model": "mistral-small-latest",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"}
        }
        resp = requests.post(url, headers=headers, json=body, timeout=30)
        if resp.ok:
            data = resp.json()
            text_resp = data["choices"][0]["message"]["content"].strip()
            text_resp = re.sub(r"^```json|```$", "", text_resp, flags=re.MULTILINE).strip()
            import json
            return json.loads(text_resp)
    except Exception as e:
        print(f"[WARN] LLM API Error: {e}")
        pass
    return {"description": "", "uni_state": "", "country": country_raw}


# ── Page text fetcher ─────────────────────────────────────────────────────────
import urllib.parse

def fetch_page_text(url: str) -> str:
    """Fetch course page text and any linked syllabus PDFs."""
    if not url or url == "Unknown" or not requests:
        return ""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; CourseExtractor/1.0)"}
        resp = requests.get(url, headers=headers, timeout=15)
        text = resp.text
        
        pdf_text = ""
        # Look for PDF links in the webpage (syllabus, curriculum, etc.)
        import re
        pdf_links = re.findall(r'href=["\']([^"\']+\.pdf)["\']', text, re.IGNORECASE)
        if pdf_links:
            pdf_url = urllib.parse.urljoin(url, pdf_links[0])
            try:
                import fitz
                pdf_resp = requests.get(pdf_url, headers=headers, timeout=15)
                if pdf_resp.status_code == 200:
                    pdf_doc = fitz.open(stream=pdf_resp.content, filetype="pdf")
                    for page in pdf_doc:
                        pdf_text += page.get_text() + "\n"
                    pdf_doc.close()
            except Exception as e:
                print(f"[WARN] Failed to read PDF {pdf_url}: {e}")

        # Strip HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        
        combined_text = text
        if pdf_text:
            pdf_text = re.sub(r"\s+", " ", pdf_text).strip()
            combined_text += "\n\n--- PDF CONTENT ---\n\n" + pdf_text
            
        return combined_text[:12000]
    except Exception:
        return ""

_global_driver = None

def get_driver():
    global _global_driver
    if not SELENIUM_OK: return None
    if _global_driver is None:
        try:
            options = uc.ChromeOptions()
            options.add_argument('--headless')
            options.add_argument('--no-sandbox')
            options.add_argument('--disable-dev-shm-usage')
            options.add_argument('--window-size=1920,1080')
            _global_driver = uc.Chrome(options=options)
            _global_driver.set_page_load_timeout(30)
            
            # Monkey-patch __del__ to prevent WinError 6 on teardown
            def silent_del(self):
                pass
            _global_driver.__class__.__del__ = silent_del
            
        except Exception as e:
            print(f"[WARN] Failed to start undetected_chromedriver: {e}")
            _global_driver = None
    return _global_driver

def close_driver():
    global _global_driver
    if _global_driver:
        try:
            _global_driver.quit()
        except Exception:
            pass
        _global_driver = None

def fetch_page_text_selenium(url: str) -> str:
    """Fetch course page text using Selenium, clicking syllabus if present."""
    if not url or url == "Unknown": return ""
    driver = get_driver()
    if not driver:
        return fetch_page_text(url) # fallback to requests
    try:
        driver.get(url)
        time.sleep(3)
        body = driver.find_element(By.TAG_NAME, 'body')
        page_text = body.text
        
        # Check for syllabus
        try:
            links = driver.find_elements(By.TAG_NAME, 'a')
            for link in links:
                if link.is_displayed():
                    text = link.text.lower()
                    if 'syllabus' in text or 'curriculum' in text:
                        href = link.get_attribute('href')
                        if href and href.startswith('http'):
                            driver.execute_script("window.open('');")
                            driver.switch_to.window(driver.window_handles[-1])
                            driver.get(href)
                            time.sleep(3)
                            syllabus_text = driver.find_element(By.TAG_NAME, 'body').text
                            page_text += "\n\n--- SYLLABUS ---\n" + syllabus_text
                            driver.close()
                            driver.switch_to.window(driver.window_handles[0])
                        else:
                            driver.execute_script("arguments[0].click();", link)
                            time.sleep(3)
                            page_text = driver.find_element(By.TAG_NAME, 'body').text
                        break
        except Exception:
            pass
            
        return page_text[:12000]
    except Exception as e:
        print(f"[WARN] Selenium fetch failed for {url}: {e}")
        close_driver()
        return fetch_page_text(url)


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

        # Detect cover/domain pages and headers (top 15% of page)
        y_top_band = ph * 0.15
        top_texts = []
        for b in text_blocks:
            b_rect = fitz.Rect(b[:4])
            if b_rect.y1 <= y_top_band:
                tv = b[4].strip()
                if len(tv) > 2 and chr(8224) not in tv:
                    top_texts.append(tv)

        is_cover_page = not any(kw in page_full_text for kw in COURSE_KEYWORDS)

        # 1. Process Headers for Domain or Course Category Changes
        if top_texts:
            found_domain = False
            # Sort domains by length descending so "Free to Audit" is checked before "Free"
            sorted_domains = sorted(DOMAIN_RANGES, key=lambda x: len(x["label"]), reverse=True)
            for tv in top_texts:
                tv_norm = _norm(tv)
                for band in sorted_domains:
                    band_norm = _norm(band["label"])
                    # Special check: "Free Course" matches "Free"
                    if band_norm in tv_norm or tv_norm in band_norm or "freecourse" in tv_norm:
                        # Extra logic to distinguish Free vs Free to Audit if relying on "freecourse"
                        if "audit" in tv_norm:
                            global_domain = "Free to Audit"
                        elif "highvaluelowcost" in tv_norm:
                            global_domain = "High Value Low Cost"
                        elif band_norm == "free" and "freecourse" in tv_norm:
                            global_domain = "Free"
                        else:
                            global_domain = band["label"]
                        
                        found_domain = True
                        break
                if found_domain:
                    break

            if found_domain:
                if global_domain in ["Free", "Free to Audit", "High Value Low Cost"]:
                    global_course_type = "Certificate"
                # Else wait for the next course category banner
            else:
                # If no domain found, check if it's a Course Category banner
                categories = ["DIPLOMA", "BACHELORS", "MASTERS", "PG DIPLOMA", "CERTIFICATE", "PG CERT"]
                matched_cat = False
                for tv in top_texts:
                    tv_upper = tv.upper()
                    for cat in categories:
                        if cat in tv_upper or tv_upper in cat:
                            global_course_type = cat
                            matched_cat = True
                            break
                    if matched_cat:
                        break
                
                # If it's a cover page and we STILL didn't find a domain or category, fallback to literal text
                if not matched_cat and is_cover_page and len(text_blocks) < 50:
                    global_domain = top_texts[0] if top_texts else global_domain
                    if not global_course_type:
                        global_course_type = "Certificate"

        if is_cover_page:
            print(f"  [Cover Page] Page {page_num+1} | Domain: {global_domain}")
            continue

        # Extract image of the page for OpenCV if cv2 is available
        page_img = None
        if cv2 is not None:
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
            if pix.n == 4:
                page_img = cv2.cvtColor(img_data, cv2.COLOR_RGBA2BGR)
            else:
                page_img = cv2.cvtColor(img_data, cv2.COLOR_RGB2BGR)

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
            
            # Badge detection logic
            has_free_box = False
            has_schol = False
            
            if page_img is not None:
                # Find quadrant boundaries in the rendered image
                img_h, img_w = page_img.shape[:2]
                q_rect = q["rect"]
                x0 = int(q_rect.x0 / pw * img_w)
                y0 = int(q_rect.y0 / ph * img_h)
                x1 = int(q_rect.x1 / pw * img_w)
                y1 = int(q_rect.y1 / ph * img_h)
                
                roi = page_img[max(0, y0):min(img_h, y1), max(0, x0):min(img_w, x1)]
                if roi.size > 0:
                    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
                    
                    # yellow (Scholarship): H=22-36, S>107, V>127
                    sch_mask = cv2.inRange(hsv, np.array([22, 107, 127]), np.array([36, 255, 255]))
                    
                    # blue (Free): H=89-102, S>89, V>114
                    free_mask = cv2.inRange(hsv, np.array([89, 89, 114]), np.array([102, 255, 255]))
                    
                    def square_like(w, h, area):
                        if area < 300: return False
                        if not (15 <= w <= 100 and 15 <= h <= 100): return False
                        if not (0.55 <= w / max(1, h) <= 1.75): return False
                        fill = area / (w * h)
                        return fill >= 0.70

                    # Find Scholarship
                    contours, _ = cv2.findContours(sch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for c in contours:
                        area = cv2.contourArea(c)
                        x, y, bw, bh = cv2.boundingRect(c)
                        if square_like(bw, bh, area):
                            has_schol = True
                            break

                    # Find Free
                    contours, _ = cv2.findContours(free_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
                    for c in contours:
                        area = cv2.contourArea(c)
                        x, y, bw, bh = cv2.boundingRect(c)
                        if square_like(bw, bh, area):
                            has_free_box = True
                            break
            else:
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
            language = field(r"Language:\s*(.*?)(?=\s*(?:Cost:|Duration:|Mode:|Skills:|Country:|Link to|$))")
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
                "language":          language,
                "mode":              mode,
                "country":           country,
                "skills_raw":        skills,
                "url":               url,
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

    grouped_catalog = {}
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
        
        # Determine Logo URL
        GITHUB_USERNAME = "tbot21998-alt"
        GITHUB_REPO = "logos"
        
        logo_url = ""
        logo_filename = logo_map.get(_norm(uni_canonical))
        if not logo_filename:
            logo_filename = sanitize_filename(uni_canonical) + ".png"
            
        if GITHUB_USERNAME and GITHUB_REPO:
            logo_url = f"https://cdn.jsdelivr.net/gh/{GITHUB_USERNAME}/{GITHUB_REPO}@main/logos/{logo_filename}"
        # Check DB for QS/NIRF Rankings
        has_qs_db, has_nirf_db = check_rankings_in_db(uni_canonical, affiliated_uni)

        course_name = c["name"].strip()
        uni_name_key = uni_canonical.strip().lower()
        course_key = (course_name.lower(), uni_name_key)

        if course_key not in grouped_catalog:
            # Fetch page & generate description ONLY ONCE per unique course
            page_text = ""
            skills_description = c.get("skills_raw", "")
                
            uni_state = ""
            if not args.no_llm:
                if c.get("url") and c["url"] not in ("Unknown", ""):
                    page_text = fetch_page_text_selenium(c["url"])
                
                time.sleep(0.3)  # polite delay
                # If page_text is empty, we fall back to PDF skills inside ask_llm_for_description
                llm_res = ask_llm_for_description(c["name"], uni_canonical, page_text if page_text else c.get("skills_raw", ""), c.get("country", ""))
                if isinstance(llm_res, dict):
                    if llm_res.get("description"):
                        skills_description = llm_res["description"]
                    if llm_res.get("uni_state"):
                        uni_state = llm_res["uni_state"]
                    if llm_res.get("country"):
                        c["country"] = llm_res["country"]

            entry = {
                "id":                 [c["_id"]],
                "name":               course_name,
                "university":         uni_canonical,
                "affiliated_uni":     affiliated_uni,
                "uni_state":          uni_state,
                "logo_url":           logo_url,
                "domains":            [domain_band] if domain_band else [],
                "course_type":        course_type,
                "country":            c.get("country", ""),
                "cost":               c.get("cost", ""),
                "duration":           c.get("duration", ""),
                "language":           c.get("language", ""),
                "mode":               c.get("mode", ""),
                "url":                c.get("url", ""),
                "skills_description": skills_description,
                "has_qs_badge":       has_qs_db,
                "has_nirf_badge":     has_nirf_db,
                "has_scholarship":    c.get("has_scholarship", False),
                "has_free":           c.get("has_free_box", False) or has_free,
                "banner_url":         ""
            }
            grouped_catalog[course_key] = entry
        else:
            if c["_id"] not in grouped_catalog[course_key]["id"]:
                grouped_catalog[course_key]["id"].append(c["_id"])
            if domain_band and domain_band not in grouped_catalog[course_key]["domains"]:
                grouped_catalog[course_key]["domains"].append(domain_band)
            if course_type == "Certificate":
                grouped_catalog[course_key]["course_type"] = "Certificate"
            if c.get("has_free_box") or has_free:
                grouped_catalog[course_key]["has_free"] = True
            if has_qs_db: grouped_catalog[course_key]["has_qs_badge"] = True
            if has_nirf_db: grouped_catalog[course_key]["has_nirf_badge"] = True
            if c.get("has_scholarship"): grouped_catalog[course_key]["has_scholarship"] = True

    catalog = list(grouped_catalog.values())
    out_path = args.output
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, ensure_ascii=False, indent=2)

    print(f"\n[OK] Wrote {len(catalog)} deduplicated courses -> {out_path}")
    close_driver()


if __name__ == "__main__":
    main()
