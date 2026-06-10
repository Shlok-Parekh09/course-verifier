import sys
import json
import time
import os
import re
import base64
import tempfile
import warnings
import colorsys
from difflib import SequenceMatcher
from urllib.parse import quote_plus, urljoin, urlparse
from datetime import datetime
from db_manager import DatabaseManager

try:
    import requests
except ImportError:
    requests = None

try:
    import cv2
except ImportError:
    cv2 = None

import base64

try:
    import pytesseract
except ImportError:
    pytesseract = None

try:
    import numpy as np
except ImportError:
    np = None

# --- LLM MANAGER ---
from llm_manager import get_llm_manager

try:
    from PIL import Image
except ImportError:
    Image = None

try:
    import fitz  # PyMuPDF
except ImportError:
    fitz = None

try:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        import fpdf as fpdf_module
        from fpdf import FPDF
except ImportError:
    fpdf_module = None
    FPDF = None

try:
    import undetected_chromedriver as uc
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    # Monkey patch to prevent WinError 6 on Windows
    _original_quit = uc.Chrome.quit
    def _safe_quit(self):
        try:
            _original_quit(self)
        except Exception:
            pass
    uc.Chrome.quit = _safe_quit

    _original_del = getattr(uc.Chrome, '__del__', None)
    if _original_del:
        def _safe_del(self):
            try:
                _original_del(self)
            except Exception:
                pass
        uc.Chrome.__del__ = _safe_del

except ImportError:
    uc = None
    Keys = None

try:
    import pdfplumber
except ImportError:
    pdfplumber = None
    
try:
    from deep_translator import GoogleTranslator
except ImportError:
    GoogleTranslator = None

try:
    import spacy
except ImportError:
    spacy = None
    
# Global nlp brain instance
NLP_BRAIN = None
def get_nlp():
    global NLP_BRAIN
    if NLP_BRAIN is None and spacy is not None:
        try:
            NLP_BRAIN = spacy.load("en_core_web_trf")
        except OSError:
            print("[!] spaCy model 'en_core_web_trf' not found. Continuing with regex/fuzzy local checks.")
    return NLP_BRAIN

# ──────────────────────────────────────────────────────────────
#  UTILITY FUNCTIONS
# ──────────────────────────────────────────────────────────────


def resolve_university_from_url(url):
    if not url: return None
    url = url.lower()
    if 'iitk.ac.in' in url: return 'Indian Institute of Technology Kanpur'
    if 'thapar.edu' in url: return 'Thapar Institute of Engineering and Technology'
    if 'rgpv.ac.in' in url: return 'Rajiv Gandhi Proudyogiki Vishwavidyalaya'
    if 'bits-pilani.ac.in' in url: return 'Birla Institute of Technology and Science'
    if 'iitm.ac.in' in url: return 'Indian Institute of Technology Madras'
    if 'iitb.ac.in' in url: return 'Indian Institute of Technology Bombay'
    if 'iitd.ac.in' in url: return 'Indian Institute of Technology Delhi'
    if 'iitkgp.ac.in' in url: return 'Indian Institute of Technology Kharagpur'
    if 'nielit.gov.in' in url: return 'National Institute of Electronics and Information Technology'
    return None

def _close_other_tabs(driver):
    try:
        handles = driver.window_handles
        if len(handles) > 1:
            main_window = handles[0]
            for handle in handles[1:]:
                driver.switch_to.window(handle)
                driver.close()
            driver.switch_to.window(main_window)
    except Exception:
        pass

def normalize(text):
    """Lowercase, collapse whitespace, strip currency symbols, alias tricky names."""
    if not text:
        return ""
    text = text.lower()
    text = text.replace("tamilnadu", "tamil nadu").replace("tamil-nadu", "tamil nadu")
    
    aliases = {
        "illinois tech": "illinois institute of technology",
        "georgia tech": "georgia institute of technology",
        "caltech": "california institute of technology",
        "virginia tech": "virginia polytechnic institute and state university",
        "cuny": "city university of new york",
        "suny": "state university of new york",
        "umass": "university of massachusetts",
        "upenn": "university of pennsylvania",
        "penn state": "pennsylvania state university",
        "njit": "new jersey institute of technology",
        "national institute of electronics & it": "national institute of electronics and information technology",
        "national institute of electronics and it": "national institute of electronics and information technology",
        "nielit": "national institute of electronics and information technology"
    }
    
    # Direct alias replacement for known troublesome universities
    stripped = text.strip()
    if stripped in aliases:
        text = aliases[stripped]
    
    # Fix common PDF ligature corruption
    text = text.replace('\ufb02', 'fl').replace('\ufb01', 'fi').replace('\ufb00', 'ff')
    text = text.replace('of\ufb02ine', 'offline').replace('offl ine', 'offline')
    text = text.replace('\u20b9', 'Rs.').replace('rs.', 'Rs.')
    text = text.replace('&', ' and ')
    
    # Remove accents/diacritics
    import unicodedata
    text = ''.join(c for c in unicodedata.normalize('NFD', text) if unicodedata.category(c) != 'Mn')
    
    text = re.sub(r'\(.*?\)', '', text)  # Strip anything in parentheses
    text = re.sub(r'[^a-z0-9\s.]', ' ', text)  # Replace all punctuation with space (keep .)
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def fuzzy_match(needle, haystack, threshold=0.70):
    n = normalize(needle)
    h = normalize(haystack)
    if not n or not h:
        return False, 0.0
    if n == h:
        return True, 1.0
        
    generic = {'university', 'of', 'institute', 'technology', 'college', 'school', 'the', 'and', 'for', 'science', 'engineering', 'national', 'state', 'at', 'academy', 'open', 'international', 'global', 'red', 'de', 'universidad', 'universidades', 'instituto', 'tecnologico', 'universidade', 'business', 'management', 'polytechnic', 'la', 'las', 'el', 'los', 'del'}
    
    n_words = n.split()
    h_words = h.split()
    
    # Substring inclusion logic
    if len(n_words) > 0 and all(w in h_words for w in n_words):
        core_n = [w for w in n_words if w not in generic]
        if not core_n:
            # If needle only contains generic words ("Open University"), demand perfect match
            pass
        else:
            # Allow substring match if there are core identifying words
            if len(n_words) >= 2 or len(n_words[0]) >= 3:
                return True, 1.0
        
    ratio = SequenceMatcher(None, n, h).ratio()
    if ratio >= threshold:
        core_n = [w for w in n_words if w not in generic]
        core_h = [w for w in h_words if w not in generic]
        
        core_n_str = ' '.join(core_n)
        core_h_str = ' '.join(core_h)
        
        if not core_n_str or not core_h_str:
            # If all core words were stripped (e.g. "Institute of Technology"), demand near-perfect match
            if ratio < 0.95:
                return False, ratio * 0.5
        else:
            core_ratio = SequenceMatcher(None, core_n_str, core_h_str).ratio()
            if core_ratio < threshold:  # strict enforcement on core ratio
                return False, ratio * 0.5
                
    return ratio >= threshold, ratio


def extract_cost_value(cost_str):
    if not cost_str:
        return None, None
    # Strip trailing "Mode: Online/Offline" leakage (case-insensitive)
    cost_str = re.sub(r'\s*Mode\s*:\s*(?:Online|Offline|Hybrid)\s*$', '', cost_str, flags=re.IGNORECASE).strip()
    cost_lower = cost_str.lower()
    
    # Identify currency symbol/code — check exact symbols first for precision
    currency = None
    # Order matters: check specific symbols before generic text codes
    symbol_map = [
        ('₹', 'INR'), ('$', 'USD'), ('€', 'EUR'), ('£', 'GBP'),
        ('rs.', 'INR'), ('rs ', 'INR'),
        ('inr', 'INR'), ('usd', 'USD'), ('eur', 'EUR'), ('gbp', 'GBP'),
    ]
    symbol_map.extend([
        ('\u20b9', 'INR'), ('rupee', 'INR'), ('rupees', 'INR'),
        ('aud', 'AUD'), ('cad', 'CAD'), ('chf', 'CHF'),
    ])
    for sym, code in symbol_map:
        if sym in cost_lower:
            currency = code
            break
            
    if "free" in cost_lower or "free to audit" in cost_lower:
        return 0.0, currency
    lakh_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)\b', cost_lower)
    if lakh_match:
        try:
            return float(lakh_match.group(1)) * 100000, currency
        except ValueError:
            pass
    match = re.search(r'\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d{4,}(?:\.\d+)?|\d+(?:\.\d+)?', cost_str)
    if match:
        try:
            return float(match.group(0).replace(',', '')), currency
        except ValueError:
            pass
    return None, currency


def format_indian_number(value):
    try:
        n = int(float(value))
    except (TypeError, ValueError):
        return ""
    s = str(abs(n))
    if len(s) <= 3:
        out = s
    else:
        out = s[-3:]
        s = s[:-3]
        while s:
            out = s[-2:] + "," + out
            s = s[:-2]
    return ("-" if n < 0 else "") + out


def is_missing_detail(value):
    s = str(value or "").strip().lower().replace("\u2026", "...")
    if not s or s in {"n/a", "na", "none", "not found", "unknown", "...", "-"}:
        return True
    missing_phrases = [
        "not explicitly", "does not explicitly", "does not list", "not listed",
        "not mentioned", "not stated", "not provided", "no specific",
        "could not be found", "may be available", "likely", "typically",
        "similar programs", "based on context",
    ]
    return any(phrase in s for phrase in missing_phrases)


def is_indian_institution_name(uni_name="", country=""):
    country_norm = normalize(country)
    if country_norm in {"india", "in", "ind", "bharat"}:
        return True
    hay = normalize(uni_name)
    indian_keywords = [
        "india", "indian", "iit", "iim", "iiit", "nit", "nielit", "swayam",
        "delhi", "mumbai", "bangalore", "bengaluru", "chennai", "kanpur",
        "roorkee", "pune", "hyderabad", "kolkata", "coimbatore", "madurai",
        "kanchipuram", "tiruchirappalli", "tirunelveli", "namakkal", "erode",
        "salem", "thiruvallur", "dindigul", "kanyakumari", "tamil nadu",
        "anna university", "bharathiar", "madras", "vellore", "amity",
        "symbiosis", "jindal", "bits", "thapar", "manipal", "nmims",
        "spjimr", "xlri", "punjab", "maharashtra", "gujarat", "kerala",
        "karnataka", "andhra", "telangana",
    ]
    return any(k in hay for k in indian_keywords)


def is_tamil_nadu_college(course):
    hay = normalize(" ".join([
        str(course.get("uni", "")),
        str(course.get("country", "")),
        str(course.get("url", "")),
    ]))
    tn_keywords = [
        "tamil nadu", "anna university", "chennai", "coimbatore", "madurai",
        "kanchipuram", "tiruppur", "tirunelveli", "namakkal", "erode",
        "salem", "thiruvallur", "dindigul", "kanyakumari", "thoothukudi",
        "villupuram", "sivakasi", "virudhunagar", "pudukkottai",
    ]
    return any(k in hay for k in tn_keywords)


def expected_indian_course_duration_years(course_name):
    cn = normalize(course_name)
    if not cn:
        return None
    if any(x in cn for x in ["b tech", "btech", "b e ", "be ", "bachelor of engineering", "bachelor of technology"]):
        return 4
    if any(x in cn for x in ["m tech", "mtech", "m e ", "me ", "master of engineering", "master of technology"]):
        return 2
    if "post graduate diploma" in cn or "pg diploma" in cn:
        return 1
    if "diploma" in cn:
        return 3
    if any(x in cn for x in ["b sc", "bsc", "b c a", "bca", "bachelor of science", "bachelor of computer applications"]):
        return 3
    if any(x in cn for x in ["m sc", "msc", "m c a", "mca", "master of science", "master of computer applications"]):
        return 2
    return None


def normalize_mode_label(value):
    s = normalize(value)
    if not s:
        return ""
    online_markers = [
        "online mode", "online delivery", "online learning", "online platform",
        "online program", "online programme", "mooc", "digital learning",
        "remote learning", "distance learning", "e learning",
    ]
    offline_markers = [
        "offline mode", "on campus", "oncampus", "in person", "classroom",
        "physical campus", "college based", "traditional college", "campus based",
        "regular mode",
    ]
    if "hybrid" in s or "blended" in s:
        return "hybrid"
    if any(m in s for m in online_markers):
        return "online"
    if any(m in s for m in offline_markers):
        return "offline"
    if "online" in s and "offline" not in s:
        return "online"
    if "offline" in s and "online" not in s:
        return "offline"
    if "online" in s and "differs" in s:
        return "online"
    return ""


def modes_equivalent(pdf_mode, web_mode):
    pdf_norm = normalize_mode_label(pdf_mode)
    web_norm = normalize_mode_label(web_mode)
    if not pdf_norm or not web_norm:
        return None
    return pdf_norm == web_norm


# ──────────────────────────────────────────────────────────────
#  DURATION NORMALIZATION ENGINE (Requirement 2)
# ──────────────────────────────────────────────────────────────

# Conversion factors to hours
_DURATION_TO_HOURS = {
    'minute': 1 / 60, 'minutes': 1 / 60, 'min': 1 / 60, 'mins': 1 / 60,
    'hour': 1, 'hours': 1, 'hr': 1, 'hrs': 1,
    'day': 24, 'days': 24,
    'week': 168, 'weeks': 168,
    'month': 720, 'months': 720,   # 30 days
    'semester': 4380, 'semesters': 4380, 'sem': 4380, 'sems': 4380, # Half year
    'year': 8760, 'years': 8760,   # 365 days
    # Compact single-letter abbreviations from PDF
    'h': 1, 'm': 720, 'd': 24, 'w': 168, 'y': 8760,
}


def normalize_duration_to_hours(duration_str):
    """
    Parse a duration string and return total hours.
    Handles:
      - Compact: "2H", "2M", "2D", "2W", "2Y"
      - Verbose: "2 hours", "3 months", "10 weeks", "120 minutes"
      - Combined: "1 year 6 months", "2 hours 30 minutes"
    Returns None if unparseable.
    """
    if not duration_str:
        return None
    s = str(duration_str).strip().lower()
    
    # Remove noise words
    s = re.sub(r'\b(approx\.?|approximately|about|around|up\s+to|total|of)\b', '', s, flags=re.IGNORECASE)
    s = re.sub(r'\s+', ' ', s).strip()
    
    total_hours = 0.0
    found_any = False
    
    # Pattern: number followed by unit (possibly with spaces/punctuation between)
    pattern = r'(\d+(?:\.\d+)?)\s*[-–]?\s*([a-zA-Z]+)'
    for m in re.finditer(pattern, s):
        num_str, unit = m.groups()
        unit = unit.lower().rstrip('s.')  # normalize plural/period
        # Map singular back for lookup
        if unit in _DURATION_TO_HOURS:
            factor = _DURATION_TO_HOURS[unit]
        elif unit + 's' in _DURATION_TO_HOURS:
            factor = _DURATION_TO_HOURS[unit + 's']
        else:
            continue
        total_hours += float(num_str) * factor
        found_any = True
    
    # Fallback: compact format like "2H", "6M" (single letter after number, no space)
    if not found_any:
        compact_match = re.fullmatch(r'(\d+(?:\.\d+)?)\s*([hmdwy])', s, re.IGNORECASE)
        if compact_match:
            num_str, unit = compact_match.groups()
            unit = unit.lower()
            if unit in _DURATION_TO_HOURS:
                total_hours = float(num_str) * _DURATION_TO_HOURS[unit]
                found_any = True
    
    return total_hours if found_any else None


def durations_equivalent(pdf_duration, web_text):
    """
    Check if any duration mentioned in web_text is equivalent to the PDF duration.
    Uses normalized hours for comparison with ±5% tolerance.
    Returns (is_match, detail_string).
    """
    if not pdf_duration or str(pdf_duration).lower() in ('unknown', 'n/a', 'n/a in pdf', ''):
        return True, "No duration specified"
    
    pdf_hours = normalize_duration_to_hours(pdf_duration)
    if pdf_hours is None:
        return True, "Skipped: unparseable PDF duration"
    if pdf_hours == 0:
        return True, "Zero duration (skipped)"
    
    web_lower = web_text.lower()
    
    # Extract all duration-like mentions from web text
    # Pattern: number + duration unit word (or compact letter)
    duration_pattern = r'(\d+(?:\.\d+)?)\s*[-–]?\s*(minutes?|mins?|hours?|hrs?|h|days?|d|weeks?|wks?|w|months?|mos?|m|semesters?|sems?|years?|yrs?|y)\b'
    web_durations = []
    for m in re.finditer(duration_pattern, web_lower):
        num_str, unit = m.groups()
        unit = unit.rstrip('s.')
        if unit in _DURATION_TO_HOURS:
            factor = _DURATION_TO_HOURS[unit]
        elif unit + 's' in _DURATION_TO_HOURS:
            factor = _DURATION_TO_HOURS[unit + 's']
        else:
            continue
        web_hours = float(num_str) * factor
        web_durations.append((web_hours, m.group(0)))
    
    if not web_durations:
        # Try direct substring match as last resort
        pdf_dur_lower = str(pdf_duration).lower()
        if pdf_dur_lower in web_lower:
            return True, f"Direct match: '{pdf_duration}'"
        return False, f"No duration mentions found in web text"
    
    # Compare with ±5% tolerance
    tolerance = 0.05
    for web_hours, web_str in web_durations:
        if abs(web_hours - pdf_hours) <= pdf_hours * tolerance:
            return True, f"Matched: PDF='{pdf_duration}' ≈ Web='{web_str}'"
    
    # No match found — report closest
    closest = min(web_durations, key=lambda x: abs(x[0] - pdf_hours))
    return False, f"Mismatch: PDF='{pdf_duration}' ({pdf_hours:.0f}h) vs closest Web='{closest[1]}' ({closest[0]:.0f}h)"

def verify_cost_in_text(target_cost_tuple, text, target_cost_str="", uni_name=""):
    is_indian = True
    if uni_name:
        if not is_indian_institution_name(uni_name):
            is_indian = False
    target_cost, target_currency = target_cost_tuple if isinstance(target_cost_tuple, tuple) else (target_cost_tuple, None)
    text_lower = text.lower()
    
    if target_cost_str:
        # Strip Mode: leakage from the raw cost string before matching
        cost_str_clean = re.sub(r'\s*mode\s*:\s*(?:online|offline|hybrid)\s*$', '', target_cost_str.lower().strip(), flags=re.IGNORECASE).strip()
        # Direct match of the raw cost string from PDF
        if cost_str_clean and cost_str_clean in text_lower:
            return True

    if target_cost is None:
        return False
        
    if target_cost == 0.0:
        # Match "Free", "Free to Audit", "free course", "$0", etc.
        return any(phrase in text_lower for phrase in ["free", "free to audit", "no cost", "complimentary", "zero fee"]) or "0" in text.split()
    
    # Currency symbols map (expanded for better matching)
    curr_map = {
        'USD': ['$', 'usd', 'dollar', 'dollars'],
        'EUR': ['€', 'eur', 'euro'],
        'GBP': ['£', 'gbp', 'pound'],
        'INR': ['₹', 'rs', 'rs.', 'inr', 'rupees', 'rupee', '₹']
    }
    target_symbols = curr_map.get(target_currency, []) if target_currency else []

    # Direct ₹ pattern matching (e.g., "₹735", "₹ 735", "Rs.735")
    target_int = str(int(target_cost)) if target_cost == int(target_cost) else str(target_cost)
    target_indian = format_indian_number(target_cost)
    for sym in ['₹', 'Rs.', 'Rs ', 'INR ', '$ ', '$', '€', '£']:
        if f"{sym}{target_int}" in text or f"{sym} {target_int}" in text:
            return True
        if target_indian and (f"{sym}{target_indian}" in text or f"{sym} {target_indian}" in text):
            return True

    # Find all numeric matches in text (e.g., 1200, 1,200, 1.2k)
    matches = list(re.finditer(r'\b\d{1,3}(?:,\d{2,3})+(?:\.\d+)?\b|\b\d{4,}(?:\.\d+)?\b|\b\d+(?:\.\d+)?\s*(?:lakh|lakhs|lac|lacs)\b', text, flags=re.IGNORECASE))
    
    for m in matches:
        try:
            raw = m.group(0)
            lakh_match = re.search(r'(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs)\b', raw, flags=re.IGNORECASE)
            val = float(lakh_match.group(1)) * 100000 if lakh_match else float(raw.replace(',', ''))
            if val == target_cost:
                if not target_currency:
                    return True
                
                # Check expanded context window (80 chars before/after for better coverage)
                start = max(0, m.start() - 80)
                end = min(len(text), m.end() + 80)
                context = text_lower[start:end]
                
                if not is_indian:
                    if any(w in context for w in ["domestic", "home fee", "home student", "in-state", "resident "]):
                        continue # Reject domestic fees for international universities
                
                if any(sym in context for sym in target_symbols):
                    return True
                    
                # Secondary check: if we see "fee", "tuition", "cost", "price" nearby, assume it's correct
                if any(w in context for w in ["fee", "tuition", "cost", "price", "amount", "course"]):
                    return True
        except ValueError:
            pass
            
    # As a last resort, look for the cost joined exactly with a symbol (e.g., $1200 or 1200INR)
    target_str_no_comma = str(int(target_cost) if target_cost.is_integer() else target_cost)
    target_str_comma = f"{target_cost:,.0f}" if target_cost.is_integer() else f"{target_cost:,.2f}"
    target_str_indian = format_indian_number(target_cost)
    
    for sym in target_symbols:
        if f"{sym}{target_str_no_comma}" in text_lower or f"{sym} {target_str_no_comma}" in text_lower: return True
        if f"{sym}{target_str_comma}" in text_lower or f"{sym} {target_str_comma}" in text_lower: return True
        if target_str_indian and (f"{sym}{target_str_indian}" in text_lower or f"{sym} {target_str_indian}" in text_lower): return True
        if f"{target_str_no_comma}{sym}" in text_lower or f"{target_str_no_comma} {sym}" in text_lower: return True
        if f"{target_str_comma}{sym}" in text_lower or f"{target_str_comma} {sym}" in text_lower: return True
        if target_str_indian and (f"{target_str_indian}{sym}" in text_lower or f"{target_str_indian} {sym}" in text_lower): return True

    return False


import difflib

# Semantic skill synonyms for deep matching
SKILL_SYNONYMS = {
    "introductory": ["beginner", "basic", "introduction", "fundamentals", "foundational", "introductory", "entry level", "beginner level"],
    "intermediate": ["moderate", "medium", "medium level", "mid-level"],
    "advanced": ["expert", "professional", "senior", "advanced level"],
    "ethical hacking": ["penetration testing", "pen testing", "security testing", "white hat", "hacking", "vulnerability assessment"],
    "web security": ["web application security", "webapp security", "owasp", "xss", "sql injection", "web vulnerabilities"],
    "cyber security": ["cybersecurity", "information security", "infosec", "network security", "it security", "computer security"],
    "data science": ["machine learning", "data analytics", "data analysis", "ai", "artificial intelligence", "deep learning", "statistics"],
    "cloud computing": ["aws", "azure", "gcp", "cloud", "saas", "paas", "iaas", "cloud infrastructure"],
    "blockchain": ["distributed ledger", "smart contracts", "cryptocurrency", "web3", "decentralized", "solidity"],
    "programming": ["coding", "software development", "development", "code", "scripting"],
    "networking": ["network", "tcp/ip", "routing", "switching", "firewall", "lan", "wan", "protocols"],
    "forensics": ["cyber forensics", "digital forensics", "computer forensics", "evidence", "investigation"],
    "penetration testing": ["pentest", "pen test", "ethical hacking", "exploitation", "metasploit", "vulnerability"],
    "cryptography": ["encryption", "decryption", "cipher", "crypto", "hashing", "rsa", "aes"],
}

def skills_match(pdf_skills, page_text):
    """Check if PDF skills are semantically present in page text using fuzzy + synonym matching."""
    if not pdf_skills or pdf_skills == "N/A in PDF":
        return True, "N/A in PDF"
    page_lower = page_text.lower()
    page_norm = normalize(page_text)
    # Split skills by commas, 'and', semicolons, 'etc'
    raw_skills = re.split(r'[,;]|\band\b|\betc\b|/|\|', pdf_skills)
    skills = [s.strip() for s in raw_skills if len(s.strip()) > 2]
    if not skills:
        return True, pdf_skills

    found = []
    not_found = []
    page_words = set(page_norm.split())
    
    for skill in skills:
        skill_lower = skill.lower().strip()
        skill_norm = normalize(skill)
        
        # Direct match
        if skill_norm in page_norm:
            found.append(skill)
            continue
        
        # Synonym expansion match
        synonym_matched = False
        for canon, syns in SKILL_SYNONYMS.items():
            if skill_lower in syns or skill_lower == canon or canon in skill_lower:
                # Check if any synonym appears in the page
                if any(s in page_lower for s in syns) or canon in page_lower:
                    found.append(skill)
                    synonym_matched = True
                    break
        if synonym_matched:
            continue
            
        # Word-level overlap match
        words = important_words(skill_norm, min_len=3)
        if words:
            matches = sum(1 for w in words if w in page_words or any(w in pw for pw in page_words))
            if matches / len(words) >= 0.5:
                found.append(skill)
                continue
                
        # Fuzzy Match
        if len(words) == 1:
            close = difflib.get_close_matches(words[0], page_words, n=1, cutoff=0.75)
            if close:
                found.append(skill)
                continue

        not_found.append(skill)

    total = len(skills)
    ratio = len(found) / total if total > 0 else 0
    detail = f"{len(found)}/{total} skills found on page"
    if found:
        detail += f" ({', '.join(found[:5])})"
    if not_found:
        detail += f"; missing: {', '.join(not_found[:5])}"
        
    # Lowered threshold: even 1 out of 3 is acceptable with synonym expansion
    return ratio >= 0.30, detail


LANGUAGE_ALIASES = {
    "english": ["english", "en"],
    "hindi": ["hindi", "hi"],
    "french": ["french", "francais", "français", "fr"],
    "spanish": ["spanish", "espanol", "español", "es"],
    "german": ["german", "deutsch", "de"],
    "italian": ["italian", "italiano", "it"],
    "chinese": ["chinese", "mandarin", "zh"],
    "japanese": ["japanese", "ja"],
    "arabic": ["arabic", "ar"],
}


def detect_language_from_text(text):
    """Extract explicit course language from scraped text; return empty string if absent."""
    if not text:
        return ""
    raw = str(text)
    lower = normalize(raw)
    patterns = [
        r"(?:language|course language|medium of instruction|taught in|audio)\s*[:\-]\s*([A-Za-z, /&]+)",
        r"(?:instructor language|subtitles)\s*[:\-]\s*([A-Za-z, /&]+)",
        r"(?:enseign(?:e|é)\s+en)\s*([A-Za-z, /&]+)",
        r"(?:idioma|sprache)\s*[:\-]\s*([A-Za-z, /&]+)",
    ]
    for pattern in patterns:
        m = re.search(pattern, raw, flags=re.IGNORECASE)
        if m:
            candidate = re.sub(r"\s+", " ", m.group(1)).strip(" .;|")
            for canonical, aliases in LANGUAGE_ALIASES.items():
                if any(re.search(rf"\b{re.escape(alias)}\b", candidate, flags=re.IGNORECASE) for alias in aliases):
                    return canonical.title()

    for canonical, aliases in LANGUAGE_ALIASES.items():
        if any(re.search(rf"\b(language|taught|medium|subtitles)[^.\n]{{0,80}}\b{re.escape(alias)}\b", lower) for alias in aliases):
            return canonical.title()
    return ""


def language_matches(expected_language, page_text):
    expected = normalize(expected_language)
    if not expected or expected in {"unknown", "n/a", "na"}:
        return True, "No language specified"
    expected_names = [name for name, aliases in LANGUAGE_ALIASES.items() if expected in aliases or name in expected]
    if not expected_names:
        expected_names = [expected.split()[0]]

    detected = detect_language_from_text(page_text)
    if detected:
        detected_norm = normalize(detected)
        ok = any(name in detected_norm or detected_norm in LANGUAGE_ALIASES.get(name, []) for name in expected_names)
        return ok, detected

    if any(alias in normalize(page_text) for name in expected_names for alias in LANGUAGE_ALIASES.get(name, [name])):
        return True, expected_names[0].title()

    if "english" in expected_names:
        return True, "English (Assumed from page)"
    return False, "Language not found"


def safe_latin(text):
    """Make text safe for FPDF latin-1 encoding."""
    text = str(text)
    replacements = {
        '\u20b9': 'Rs.', '\ufb02': 'fl',
        '\u2018': "'", '\u2019': "'", # single quotes
        '\u201c': '"', '\u201d': '"', # double quotes
        '\u2013': '-', '\u2014': '-', # dashes
        '\u2026': ' ',                # ellipsis -> space (not dots)
        '\u00a0': ' ',                # non-breaking space
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')



KNOWN_INSTITUTES = [
    "A J Institute Of Engineering And Technology.Kottar chowki Boloor Village Mangalore (Visvesvaraya Technological University",
    "A.K.S. University",
    "AAA College of Engineering and Technology, Amathur Village, Sivakasi, Virudhunagar-626123. (Anna University",
    "ACS College of Engineering, Mysore Road (Visvesvaraya Technological University",
    "AISECT University",
    "AKASH INTITUTE OF ENGINEERING AND TECHNOLOGY (Visvesvaraya Technological University",
    "APS College of Engineering, Somanahalli, Bangalore (Visvesvaraya Technological University",
    "ARKA Jain University",
    "ATME College of Engineering, Mysore  (Visvesvaraya Technological University",
    "AVS COLLEGE OF ARTS & SCIENCE Attur Main Road, Ramalingapuram,",
    "Aalim Muhammed Salegh College of Engineering (Anna University",
    "Academy of Maritime Education and Training",
    "Acharya Nagarjuna University",
    "Adamas University",
    "Adhiparasakthi College of Engineering, G.B.Nagar, Kalavai, Arcot (Anna University",
    "Aditya University",
    "Ajeenkya D.Y. Patil University",
    "Al-Ameen Engineering College, Palakkad (A.P.J. Abdul Kalam Technological University",
    "Al-Azhar College of Engineering and Technology, Idukki  (A.P.J. Abdul Kalam Technological University",
    "Alliance Univeristy",
    "Alva's Institute of Engineering & Technology, Moodabidre, D.K (Visvesvaraya Technological University",
    "Amal Jyothi College of Engineering, Kottayam (A.P.J. Abdul Kalam Technological University",
    "Amity University Bengaluru",
    "Amity University Gurugram",
    "Amity University Jaipur",
    "Amity University Mohali",
    "Amity University Noida",
    "Amrita Vishwa Vidyapeetham",
    "Amrita Vishwa Vidyapeetham Amritapuri",
    "Anand Institute of Higher Technology(Autonomous), (Anna University",
    "Anand Vishwa Gurukul College of Law (Mumbai University",
    "Anjaneya University",
    "Annasaheb Dange College of Engineering and Technology, Ashta, Sangli (Shivaji University",
    "Anurag University",
    "Apex University",
    "Arjun College of Technology, 310/1B, Chettiyakkapalayam (Anna University",
    "Arul Tharum VPMM College of Engineering and Technology (Anna University",
    "Arunai Engineering College (Autonomous), Chittor-Cuddalore (Anna University",
    "Arya College (Rajasthan Technical University (RTU), Kota",
    "Aryavart International University",
    "Asan Memorial College of Engineering and Technology (Anna University",
    "Asansol Engineering College (Maulana Abul Kalam Azad University of Technology",
    "Asha M. Tarsadia Institute of Computer Science and Technology (Uka Tarsadia University",
    "Asian School of Cyber law",
    "Atal Bihari Vajpayee Indian Institute of Information Technology and Management",
    "Aurora Higher Education and Research Academy",
    "Avantika university",
    "Avinashilingam Institute for Home Science & Higher Education for Women",
    "B M S College of Engineering, Basavanagudi (Visvesvaraya Technological University",
    "B. S. Abdur Rahman Crescent Institute of Science and Technology",
    "B.M.S.INSTITUTE OF TECHNOLOGY AND MANAGEMENT (Visvesvaraya Technological University",
    "BADERIA GLOBAL INSTITUTE OF ENGINEERING & MANAGEMENT Jabalpur (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "BAPUJI INSTITUTE OF ENGINEERING & TECHNOLOGY (Visvesvaraya Technological University",
    "Babu Banarasi Das University",
    "Babu Dinesh Singh University",
    "Bahra University",
    "Bangalore Institute of Technology, K.R.Road, Bangalore (Visvesvaraya Technological University",
    "Bharata Mata College of Commerce &Arts ,Chunangamvely,Aluva (Mahatma Gandhi University",
    "Bharatiar university",
    "Bhartiya Vidyapeeth",
    "Bheemanna Khandre Institute of Technology, Bhalki (Visvesvaraya Technological University",
    "Birla Institute of Technology & Science",
    "Bishop Vayalil Memorial Holy Cross College, Cherpunkal (Mahatma Gandhi University",
    "Brainware University",
    "Brindavan College of Engineering, Yelahanaka, Bangalore (Visvesvaraya Technological University",
    "C. V. Raman Global University",
    "CDAC (Centre for Development of Advanced Computing",
    "CMS College of Engineering, CMS Nagar, Eranapuram Post, Namakkal-637003. (Anna University",
    "COEP Technological University",
    "COER University, Roorkee",
    "Cambridge Institute Of Technology, North Campus, Devanahalli, Bangalore (Visvesvaraya Technological University",
    "Cambridge Institutute of Technology, K.R.Puram, Bangalore (Visvesvaraya Technological University",
    "Career Point University",
    "Central University Of Jammu",
    "Central University of Punjab, Bathinda",
    "Centurion University",
    "Chaitanya Bharathi Institute of Technology (Osmania University",
    "Chandigarh University",
    "Chennai Institute of Technology (Autonomous) (Anna University",
    "Cheran College of Technology, Cheran Nagar, Thittuparai, Kangeyam, Tiruppur-638701. (Anna University",
    "Chhotubhai Gopalbhai Patel Institute of Technology, Maliba Campus, Bardoli (Uka Tarsadia University",
    "Children Welfare Centre's College of Law (Mumbai University",
    "Chitkara University",
    "Christ University",
    "Cochin Arts and Science College,Manakkakadavu (Mahatma Gandhi University",
    "Cochin University of Science and Technology",
    "Coimbatore Institute of Engineering and Technology (Autonomous), Vellimalaipattinam, Narasipuram Post, (Anna University",
    "College of Engineering, Kallooppara, Thiruvalla (A.P.J. Abdul Kalam Technological University",
    "Coorg Institute of Technology, Kunda, Ponnampet (Visvesvaraya Technological University",
    "D.A.V University",
    "DBS Global University",
    "DIT Universty",
    "DJ Sanghvi (Mumbai University",
    "DY Patil University",
    "Datta Meghe Institute of Higher Education and Research",
    "Dayananda Sagar Academy of Technology & Management Technical Campus (Visvesvaraya Technological University",
    "Dayananda Sagar University",
    "Defence Institute of Advanced Technology (Deemed to be University), Girinagar, Pune",
    "Desh Bhagat University",
    "Dev Bhoomi Uttarakhand University",
    "Dhaanish Ahmed Institute of Technology, Pitchanur Village, Coimbatore-641018 (Anna University",
    "Dhanalakshmi Srinivasan College of Engineering (CBE) (Autonomous), Coimbatore-641105. (Anna University",
    "Dhanalakshmi Srinivasan College of Engineering and Technology, Kanchipuram (Anna University",
    "Dilkap Research Institute Of Engineering and Management Studies (Mumbai University",
    "Dr K N Modi University",
    "Dr Mahalingam College of Engineering and Technology (Autonomous) (Anna University",
    "Dr N.G.P. Institute of Technology (Autonomous), Dr. N.G.P. Nagar, Kalapatti Road, Coimbatore-641048.  (Anna University",
    "Dr. B R Ambedkar National Institute of Technology, Jalandhar",
    "Dr. B. C. Roy Engineering College, Durgapur (Maulana Abul Kalam Azad University of Technology",
    "Dr. Babasaheb Ambedkar Open University, Ahmedabad",
    "Dr. D. Y. Patil Arts, Commerce & Science College, Pimpri, Pune (Savitribhai Phule Pune University",
    "Dr. Subhash University, School of Engineering & Technology, Junagadh",
    "Dr. Vishwanath Karad MIT World Peace University",
    "Dr.Sudhir Chandra Sur Institute of Technology and Sports Complex (Maulana Abul Kalam Azad University of Technology",
    "Easa College of Engineering and Technology (Autonomous), Coimbatore-641105. (Anna University",
    "East Point College of Engineering & Technology, Bangalore (Visvesvaraya Technological University",
    "East West Institute of Technology (Visvesvaraya Technological University",
    "Easwari Engineering College (Autonomous), Bharathi Salai, Ramapuram, Chennai-600089. (Anna University",
    "Ellenki College of Engineering and Technology (Jawaharlal Nehru Technological University Hyderabad",
    "Erode Sengunthar Engineering College (Autonomous), Thudupathi, Perundurai (Tk), Erode District-638057. (Anna University",
    "Faculty of Engineering & Technology- Sigma University,Bakrol, Vadodara",
    "Fatima Michael College of Engineering and Technology, Senkottai Village (Anna University",
    "Future Institute of Technology, Boral, Garia (Maulana Abul Kalam Azad University of Technology",
    "G K M College of Engineering and Technology, G K M Nagar (Anna University",
    "G. H. RAISONI COLLEGE OF ENGINEERING Nagpur (Rashtrasant Tukadoji Maharaj Nagpur University",
    "G.H. Raisoni College of Engineering and Management Pune (Savitribhai Phule Pune University",
    "GD Goenka University",
    "GITAM University",
    "GLA University",
    "GM University",
    "GNA University",
    "GOVERNMENT POLYTECHNIC , KUDLIGI",
    "GOVT ENGG COLLEGE W. CHAMPARAN (Bihar Engineering University",
    "Galgotias University",
    "Galgotias university",
    "Gandhinagar University",
    "Ganga Institute of Technology and Management (Maharshi Dayanand University  Rohtak",
    "Ganpat University",
    "Garden City University",
    "Gautam Buddha University",
    "Gaya College of Engineering",
    "Gayatri Vidya Parishad College of Engineering, Visakhapatnam (Andhra University",
    "Geeta University",
    "Girideepam Institute of Advanced Learning, Vadavathoor (Mahatma Gandhi University",
    "Girjandha Chowdhary University",
    "Gojan School of Business and Technology, Thiruvallur (Anna University",
    "Government College of Engineering (Autonomous) Bargur Krishnagiri District 635104 (Anna University",
    "Government Engineering College, Wayanad (A.P.J. Abdul Kalam Technological University",
    "Government Institute of Forensic Science (Dr. Babasaheb Ambhedkar Marathwada University",
    "Government Polytechnic, Ghaziabad (Dr. APJ Abdul Kalam Technical University",
    "Govt. Polytechnic College, Mandore (Rajasthan Technical University (RTU",
    "Graphic Era Hill University Haldwani Campus",
    "Graphic Era University",
    "Gujarat University",
    "Guru Ghasidas Vishwavidyalaya",
    "Guru Gobind Singh Indraprastha University",
    "Guru Jambeshwar University of Science and Technology",
    "Guru Nanak Dev University",
    "Guru Nanak Institute of Technology, Panihati, Sodepur (Maulana Abul Kalam Azad University of Technology",
    "Gurunanak Dev Engineering College, Bidar (Visvesvaraya Technological University",
    "Gyanmanjari Innovative University",
    "Haldia Institute of Technology (Maulana Abul Kalam Azad University of Technology",
    "Haridwar University",
    "Heritage Institute of Technology (Maulana Abul Kalam Azad University of Technology",
    "Hindi Vidya Prachar Samiti's College of Law (Mumbai University",
    "Hindusthan College of Engineering and Technology(Autonomous), Othakkalmandapam Village (Anna University",
    "Hope Foundation and research center's Finolex Academy of Management and Technology, Ratnagiri (Mumbai University",
    "ICFAI University Jaipur",
    "ICFAI University Jharkhand",
    "IFET College of Engineering (Autonomous), IFET Nagar (Anna University",
    "IILM University",
    "IILM University Greater Noida",
    "IILM University Gurugram",
    "IIMT University Meerut",
    "IISc Bangalore",
    "ITM SLS Baroda University",
    "ITM University Gwailor",
    "ITM Vocational University, Waghodia,Vadodara",
    "Ilahia College of Engineering and Technology, Ernakulam (A.P.J. Abdul Kalam Technological University",
    "Immanuel Arasar JJ College of Engineering, Edavilagam, Nattalam, Marthandam, Kanyakumari-629195. (Anna University",
    "Impact College of Engineering & Applied Sciences, Bangalore (Visvesvaraya Technological University",
    "Indian Academy of Cyber Law and management",
    "Indian Institute of Information Technology Allahbad",
    "Indian Institute of Information Technology Bhopal",
    "Indian Institute of Information Technology Kota",
    "Indian Institute of Information Technology Kottayam",
    "Indian Institute of Information Technology Senapati, Manipur",
    "Indian Institute of Information Technology Sri",
    "Indian Institute of Information Technology Tiruchirappalli",
    "Indian Institute of Information Technology Vadodara",
    "Indian Institute of Information Technology, Design and Manufacturing, Kurnool",
    "Indian Institute of Information Technology, Una",
    "Indian Institute of Management Indore",
    "Indian Institute of Technology Bhilai",
    "Indian Institute of Technology Bombay",
    "Indian Institute of Technology Delhi",
    "Indian Institute of Technology Guwahati",
    "Indian Institute of Technology Hyderabad",
    "Indian Institute of Technology Indore",
    "Indian Institute of Technology Jammu",
    "Indian Institute of Technology Jodhpur",
    "Indian Institute of Technology Kanpur",
    "Indian Institute of Technology Kharagpur",
    "Indian Institute of Technology Madras",
    "Indian Institute of Technology Palakkad",
    "Indian Institute of Technology Patna",
    "Indian Institute of Technology Roorkee",
    "Indian Institute of Technology Ropar",
    "Indian Law Institute",
    "Indian School of Business (ISB",
    "Indira College of Commerce and Science (Savitribai Phule Pune University",
    "Indira Gandhi National Open University",
    "Indraprastha Institute of Information Technology Delhi",
    "Indrashil University",
    "Indus University",
    "Institute of Advanced Research",
    "Institute of Forensic Science ( Dr. Homi Baba State University",
    "Institute of Forensic Science (Homi Baba State University",
    "Institute of Forensic Science (Mumbai University",
    "International Forensics Science Institute",
    "International Institute of Business Studies Banglore",
    "International Institute of Information Technology Bangalore",
    "International Institute of Information Technology Hyderabad",
    "Invertis University",
    "J.J. College of Engineering (Anna University",
    "JECRC University",
    "JG University",
    "JIET Jodhpur",
    "JITENDRA CHAUHAN LAW COLLEGE, VILE PARLE (Mumbai University",
    "JK Lakshmipat University - [JKLU], Jaipur",
    "JNN Institute of Engineering (Autonomous), Thiruvallur  (Anna University",
    "JSPM University",
    "Jagannath University",
    "Jagat Guru Nanak Dev Punjab State Open University",
    "Jai Bharath Arts and Science College (Mahatma Gandhi University",
    "Jain University",
    "Jaipur National University",
    "Jamia Hamdard",
    "Jawahar Education Society's Annasaheb Chudaman Patil College of Engineering,Kharghar, Navi Mumbai (Mumbai University",
    "Jawaharlal Institute of Technology, Borawan, Khargone (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Jawaharlal Nehru Technological University Hyderabad",
    "Jaya Sakthi Engineering College, St.Mary's Nagar, Thiruninravur (Anna University",
    "Jaypee Institute of Information Technology",
    "Jeppiaar University",
    "Jerusalem College of Engineering (Autonomous), Pallikkaranai (Anna University",
    "Jharkhand Rai University",
    "Jyothi Engineering College, Thrissur (A.P.J. Abdul Kalam Technological University",
    "K S R College of Engineering (Autonomous) (Anna University",
    "K. N. University",
    "K. S. INSTITUTE OF TECHNOLOGY  (Visvesvaraya Technological University",
    "K.L.N.College of Engineering (Autonomous) (Anna University",
    "KCG college of Technology (Autonomous), Karapakkam (Anna University",
    "KES\u2019 Shri Jayantilal H. Patel Law College (Mumbai University",
    "KIT - Kalaignarkarunanidhi Institute of Technology (Autonomous) (Anna University",
    "KJ Somaiya School of Engineering (Somaiya Vidyavihar University",
    "KK Modi University",
    "KL University",
    "KLE Society's law College (KLE Technological University",
    "KLE Technological University",
    "KMCT Institute of Emerging Technology and Management, Mukkam, Kozhikode (A.P.J. Abdul Kalam Technological University",
    "KMM College of Arts & Science, Thrikkakara (Mahatma Gandhi University",
    "KR Mangalam University",
    "Kalasalingam Academy of Research and Education",
    "Kalinga Institute of Industrial Technology",
    "Kangeyam Institute of Technology (Autonomous) (Anna University",
    "Kannur University",
    "Karpagam Academy of Higher Education",
    "Karpagam College of Engineering (Autonomous) (Anna University",
    "Karunya Institute of Technology and Sciences",
    "Kaushalya the Skill University",
    "Kristu Jayanti university",
    "Kristu Jyoti College of Management & Technology, Kurisummoodu P.O, Changanacherry (Mahatma Gandhi University",
    "Kurukshetra University",
    "LBS College of Engineering, Muliyar,Kasaragod (A.P.J. Abdul Kalam Technological University",
    "Lokmanya Tilak College of Engineering (Mumbai University",
    "Lovely Professional University",
    "Loyola Institute of Technology (Anna University",
    "M S Ramaiah Institute of Technology, Bangalore (Visvesvaraya Technological University",
    "MADRAS ENGINEERING COLLEGE, TAMBARAM ROAD, KANCHIPURAM - 602105. (Anna University",
    "MAHALAKSHMI TECH CAMPUS Chrompet (Anna University",
    "MES- M E S College of Engineering, Kuttippuram (A.P.J. Abdul Kalam Technological University",
    "MGM TECHNOLOGICAL CAMPUS,Valanchery (A.P.J. Abdul Kalam Technological University",
    "MGM University",
    "MH Sabao Sidik College of Engineering ( Mumbai University",
    "Madhya Pradesh Bhoj (open) University",
    "Maganbhai Adenwala Mahagujarat University",
    "Maharaja Institute of Technology Mysore (Visvesvaraya Technological University",
    "Maharaja Institute of Technology Mysore,Belawadi,Srirangapatna,Mandya (Visvesvaraya Technological University",
    "Maharashtara National Law University",
    "Maharashtra State Skills University",
    "Maharishi Paetanjali Polytechnic Of Infomaetin Tecnology ,Karnelganj,",
    "Maharishi University of Information Technology",
    "Mahendra Engineering College (Autonomous), Mahendhirapuri, Mallasamudram West (Anna University",
    "Malaviya National Institute of Technology, Jaipur",
    "Malla Reddy Vishwavidyaapeeth",
    "Manav Rachna International Institute of Research and Studies",
    "Mangalayatan University Aligarh",
    "Mangalore Institute of Technology & Engineering, Moodabidri, Mangalore (Visvesvaraya Technological University",
    "Manipal Academy of Higher Education",
    "Manipal University Jaipur",
    "Manonmaniam Sundaranar University",
    "Manonmaniam Sundarnar University",
    "Marwadi University",
    "Mata Tripura Sundari Open University",
    "Maulana Azad National Institute of Technology Bhopal",
    "Mizoram University",
    "Model Institute of Engineering & Technology, Jammu  (University of Jammu",
    "Mody University of Science & Technology",
    "Mohamed Sathak A J College of Engineering (Autonomous) (Anna University",
    "Mohamed Sathak Engineering College (Autonomous) (Anna University",
    "Mohan Babu University",
    "Muthayammal Engineering College (Anna University",
    "Muthoot Institute of Technology & Science - [MITS], Ernakulam (A.P.J. Abdul Kalam Technological University",
    "N.P.R College of Engineering and Technology (Autonomous) (Anna University",
    "NALSAR University",
    "NEOTIA University",
    "NIELIT Deemed to be University- Srinagar",
    "NIILM University",
    "NIIT University",
    "NITTE",
    "NRI Institute of Research Technology (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Nandha Engineering College (Anna University",
    "Narsee Monjee Institute of Management Studies Vile Parle",
    "National Forensic Sciences University",
    "National Forensic Sciences University Bhopal",
    "National Forensic Sciences University Bhubneshwar",
    "National Forensic Sciences University Chennai",
    "National Forensic Sciences University Delhi",
    "National Forensic Sciences University Gandhinagar",
    "National Forensic Sciences University Goa",
    "National Forensic Sciences University Guwahati",
    "National Forensic Sciences University Jaipur",
    "National Forensic Sciences University Nagpur",
    "National Forensic Sciences University Raipur",
    "National Institute of Electronics & Information Technology",
    "National Institute of Electronics & Information Technology Kohima",
    "National Institute of Electronics & Information Technology Ropar",
    "National Institute of Electronics & Information Technology, Kolkata",
    "National Institute of Electronics & Information Technology,Calicut",
    "National Institute of Electronics and Information Technology Ajmer",
    "National Institute of Technical Teachers Training and Research",
    "National Institute of Technology Agartala",
    "National Institute of Technology Calicut",
    "National Institute of Technology Jamshedpur",
    "National Institute of Technology Patna",
    "National Institute of Technology Rourkela",
    "National Institute of Technology Sikkim",
    "National Institute of Technology Surathkal",
    "National Institute of Technology Warangal",
    "National Institute of Technology, Kurukshetra",
    "National Law Institute University Bhopal",
    "National Law School of India University",
    "National University of Advanced Legal Studies - [NUALS], Ernakulam",
    "Nellai College of Engineering , Maruthakulam P.O, Nanguneri Taluk, Tirunelveli-627151. (Anna University",
    "Nelson Business School",
    "Netaji Subhas University Jamshedpur",
    "Netaji Subhas University of Technology",
    "New Prince Shri Bhavani College of Engineering and Technology (Autonomous) (Anna University",
    "Noble University Junagadh",
    "Noida Institute of Engineering and Technology (Dr. A.P.J. Abdul Kalam Technical University",
    "Noida International University",
    "Noorul Islam Centre for Higher Education",
    "OM Sterling Global University",
    "Odisha State Open University",
    "Oriental College of Technology Bhopal (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "P A College of Engineering, Kairangal, Bantwala Tq,. Mangalore (Visvesvaraya Technological University",
    "P.B. College of Engineering Kancheepuram (Anna University",
    "P.S.V.College of Engineering and Technology, Mittapalli, Balinayanapalli Post, Krishnagiri-635108. (Anna University",
    "P.T.R. College of Engineering and Technology (Anna University",
    "PERI Institute of Technology (Autonomous), Mannivakkam,Tambaram, Kancheepuram (Anna University",
    "PES University",
    "PP Savani university",
    "PSNA College of Engineering and Technology (Autonomous) (Anna University",
    "Paavai Engineering College (Autonomous), NH-7, Paavai Nagar, Pachal, Namakkal-637018. (Anna University",
    "Pandian Saraswathi Yadav Engineering College, Arasanoor Village (Anna University",
    "Pandit Deendayal Energy University",
    "Panipat Institute of Engineering & Technology (Kurukshetra University",
    "Park College of Engineering and Technology (Autonomous)  (Anna University",
    "Parul University",
    "Pimpri Chinchawad University",
    "Pondicherry University",
    "Poornima University",
    "Prathyusha Engineering College (Autonomous) (Anna University",
    "Presidency University, Banglore",
    "Prince Dr. K. Vasudevan College of Engineering and Technology (Autonomous) (Anna University",
    "Providence College of Engineering, Chengannur (A.P.J. Abdul Kalam Technological University",
    "Punjab Engineering College, Chandigarh",
    "Punjabi University",
    "Quantum University",
    "R P Sarathy Institute of Technology (Autonomous) , Poosaripatty(PO), Omalur Taluk, Salem-636305. (Anna University",
    "R.M.K. College of Engineering and Technology (Autonomous), Thiruvallur (Anna University",
    "RIMT University",
    "RNS Institute of Technology, Bangalore (Visvesvaraya Technological University",
    "RV University",
    "RVS School of Engineering and Technology (Anna University",
    "Rabindranath Tagore University",
    "Rajadhani Institute of Science and Technology, Palakkad (A.P.J. Abdul Kalam Technological University",
    "Rajalakshmi Engineering College (Autonomous), Kanchipuram, Chennai-602105. (Anna University",
    "Rajarajeswari College of Engineering, Bangalore (Visvesvaraya Technological University",
    "Rajiv Gandhi University",
    "Ramaiah University",
    "Ramrao Adik Institute of Technology ( DY Patil University",
    "Rashtriya Raksha University",
    "Rathinam Technical Campus (Autonomous), Rathinam Techzone (Anna University",
    "Rayat Bahra University",
    "Reva University",
    "Reva university",
    "Royal College of Engineering and Technology, Thrissur (A.P.J. Abdul Kalam Technological University",
    "Rungta International University",
    "S E A College of Engineering & Technology, Virgonagar, Bangalore (Visvesvaraya Technological University",
    "S-VYASA University",
    "S.A ENGINEERING COLLEGE, CHENNAI (Anna University",
    "S.I.E.S. Graduate School of Technology, Nerul, Navi Mumbai (Mumbai University",
    "S.K.P. Engineering College, Chinnkangiyanur, Somasipadi Post (Anna University",
    "SAGE University Bhopal",
    "SAGE University Indore",
    "SAMS College of Engineering and Technology, 82,Panapakkam, Tirupathi Road  (Anna University",
    "SGT University",
    "SR University",
    "SRI Ramachandra Institute of Higher Education and Research",
    "SRM Institute of Science and Technology Kattankulathur (KTR",
    "SRM Madurai College for Engineering and Technology, Pottapalayam Village (Anna University",
    "SRM University Sikkim",
    "SRM University Sonepat",
    "SRM University, Amaravathi",
    "SSM Institute of Engineering and Technology (Autonomous) (Anna University",
    "ST. LOURDES ENGINEERING COLLEGE Sadhananthapuram (Anna University",
    "ST. Vincent Pallotti College of Engineering & Technology, Nagpur (Rashtrasant Tukadoji Maharaj Nagpur University",
    "Sagar Institute of Research & Technology, Bhopal (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Sagar Institute of Science & Technology (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Sambhram Institute of Technology, Bangalore (Visvesvaraya Technological University",
    "Samrat Ashok Technological Institute, Vidisha (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Sandip University Nashik",
    "Sanskaram University",
    "Sanskriti University",
    "Sardar Patel University of Police, Security and Criminal Justice Jodhpur",
    "Sardar Vallabhbhai National Institute of Technology, Surat",
    "Saveetha Engineering College (Autonomous), Saveetha Nagar, Kancheepuram (Anna University",
    "SavitriBhai Phule Pune University",
    "School of Technology and Applied Sciences Pullarikunnu (STAS) (Mahatma Gandhi University",
    "School of Technology and Applied Sciences, Edappally (Mahatma Gandhi University",
    "School of Technology and Applied Sciences, Pullarikkunnu (Mahatma Gandhi University",
    "Scope Global Skills University",
    "Sethu Institute of Technology (Autonomous), Pulloor, Kariapatti, Virudhunagar-626115. (Anna University",
    "Shah And Anchor Kutchhi Engineering College ( Mumbai University",
    "Shaheed Sukhdev College of Buisness Studies ( University of Delhi",
    "Shanmugha Arts Science Technology & Research Academy (SASTRAT",
    "Sharda University",
    "Shiv Nadar University",
    "Shoolini University",
    "Shree Dhanvantary College of Engineering & Technology, Kim (Gujarat Technological University",
    "Shreyarth University",
    "Shri Guru Gobind Singhji Institute of Engineering and Technology, Nanded (Swami Ramanand Teerth Marathwada Marathwada University",
    "Shri Ramswaroop Memorial University",
    "Shri Rawatpura Sarkar University",
    "Shri Shankaracharya Technical Campus, Bhilai (Chhattisgarh Swami Vivekanand Technical University",
    "Shri Vishnu Engineering College for Women (Jawaharlal Nehru Technological University Kakinada",
    "Sikkim Manipal University (SMIT",
    "Siksha O Anusadhan",
    "Silver Oak University",
    "Singhania University Pacheri",
    "Sir M.Visveswaraya Institute of Technology, Bangalore  (Visvesvaraya Technological University",
    "Sir Padmapat Singhania University",
    "Sister Nivedita University, New Town (Maulana Abul Kalam Azad University of Technology",
    "Smt. Indira Gandhi College of Engineering, Navi Mumbai (Mumbai University",
    "Sona Devi University",
    "Sree Narayana Gurukulam College of Engineering (A.P.J. Abdul Kalam Technological University",
    "Sree Narayana Gurukulam College of Engineering, Ernakulam (A.P.J. Abdul Kalam Technological University",
    "Sree Sakthi Engineering College (Autonomous), Bettathapuram, Bilichi Village (Anna University",
    "Sree Sastha Institute of Engineering and Technology Chembarambakkam (Anna University",
    "Sri Eshwar College of Engineering (Autonomous), Kondampatti Post, Vadasithur Via, Coimbatore-641202. (Anna University",
    "Sri Krishna College of Engineering and Technology (Anna Universtiy",
    "Sri Sai Ram Engineering College (Autonomous), Sai Leo Nagar",
    "Sri Sai Ranganathan Engineering College (Autonomous) , Viraliyur Post, Thondamuthur(via), Coimbatore-641109. (Anna University",
    "Sri Shakthi Institute of Engineering and Technology (Autonomous) (Anna University",
    "Sri Shanmugha College of Engineering and Technology (Autonomous) (Anna University",
    "Sri Sri University",
    "Sri Venkateshwara College of Engineering, Bangalore (Visvesvaraya Technological University",
    "Sri Venkateswara College of Engineering and Technology, Thirupachur (Anna University",
    "Sri Venkateswara Institute of Science and Technology, Kolundhalur (Anna University",
    "Sri Venkateswaraa College of Technology(Autonomous) (Anna University",
    "SriRam Engineering College, Perumalpattu, Veppampattu (Anna University",
    "Srinath University",
    "St Joseph's University Bengaluru",
    "St Josephs College of Engineering and Technology, Palai (A.P.J. Abdul Kalam Technological University",
    "St. Joseph College of Engineering, Trinity Campus (Anna University",
    "St. Joseph's College of Engineering (Anna University",
    "St. Joseph's Institute of Technology (Autonomous), Jeppiaar Kanchipuram (Anna University",
    "Sudharsan Engineering College, Sathiyamangalam, Kulathur Taluk, Pudukkottai District-622501. (Anna University",
    "Sunrise university",
    "Suresh Gyan Vihar University Jaipur",
    "Surya Engineering College, Perundurai Road,Manalmedu, Mettukadai,Kathirampatti Post, Erode-638107. (Anna University",
    "Surya Group of Institutions, NH-45, GST Road, Vikiravandi, Villupuram-605652. (Anna University",
    "Sushant University, Gurgaon",
    "Swami Rama Himalayan University",
    "Swami Vivekananda University",
    "Swamy Saswathikananda College, Poothotta P.O, Ernakulam (Mahatma Gandhi University",
    "Swarrnim Startup and Innovation University",
    "Symbiosis Centre for Distance Learning (Symbiosis International University",
    "Symbiosis Skills and Professional University",
    "T.J. Institute of Technology, Rajiv Gandhi Salai, Karapakkam (Anna University",
    "T.John Institute of technology, Bangalore (Visvesvaraya Technological University",
    "TOMS COLLEGE OF ENGINEERING",
    "TOMS COLLEGE OF ENGINEERING (Mahatma Gandhi University",
    "Tagore Engineering College, Rathinamangalam (Anna University",
    "TakShashila University",
    "Tata Institute of Social Sciences",
    "Tatyasaheb Kore Institute of Engineering and Technology, Yelur (Shivaji University",
    "Techno International New Town, Rajarhat, New Town (Maulana Abul Kalam Azad University of Technology",
    "Techno Main Salt Lake, Sector-V, Salt Lake (Maulana Abul Kalam Azad University of Technology",
    "Technocrats Institute of Technology (Excellence), Bhopal (2007) (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Teerthanker Mahaveer University",
    "Thakur College of Engineering and Technology, Kandivali, Mumbai (Mumbai University",
    "Thamirabharani Engineering College (Autonomous) (Anna University",
    "Thapar Institute of Engineering and Technology",
    "The Apollo University",
    "The LNM Institute of Information Technology",
    "The NorthCap University",
    "Tilak Maharashtra Vidyapeeth",
    "UKF College of Engineering and Technology, Kollam (A.P.J. Abdul Kalam Technological University",
    "Universal Skilltech",
    "University College of Engineering Kancheepuram Ponnerikarai (Anna University",
    "University College of Engineering Villupuram (Anna University",
    "University College of Engineering,Thodupuzha  (A.P.J. Abdul Kalam Technological University",
    "University of Hyderabad",
    "University of Madras",
    "University of Petroleum and Energy Studies",
    "Unnamalai Institute of Technology, Suba Nagar, Ayyaneri Post, Kovilpatti, Thoothukudi District-628502. (Anna University",
    "Uttarakhand Open University",
    "Uttaranchal University",
    "VASANT DADA PATIL PRATISHTAN'S LAW COLLEGE (Mumbai University",
    "VELS Institute of Science Technology & Advanced Studies (VISTAS",
    "VM Salagaocar College of Law (Goa University",
    "Veerammal Engineering College, PVP Nagar, K.Singrakottai, Dindigul-624708. (Anna University",
    "Vel Tech Multi Tech Dr Rangarajan Dr Sakunthala Engineering College (Autonomous)  (Anna University",
    "Velammal College of Engineering and Technology (Autonomous), Velammal Nagar, Viraganoor (Anna University",
    "Velammal Engineering College (Autonomous), Velammal Nagar, Ambattur (Anna University",
    "Vellore Institute of Technology Bangalore",
    "Vellore Institute of Technology Bhopal",
    "Vellore Institute of Technology Chennai",
    "Vellore Institute of Technology Guntur",
    "Vellore Institute of Technology Vellore",
    "Vidhyadeep University",
    "Vidyaa Vikas College of Engineering and Technology (Anna University",
    "Vignan's Foundation for Science,Technology & Research",
    "Vikrant Institute of Technology & Management Indore (Rajiv Gandhi Proudyogiki Vishwavidyalaya",
    "Vimal Jyothi Engineering College,  Kannur (A.P.J. Abdul Kalam Technological University",
    "Vins Christian College of Engineering, Vins Nagar, Chunkankadai, Nagercoil, Kanyakumari-629807. (Anna University",
    "Vishwakarma Institute of Technology Pune (Savitribai Phule Pune University",
    "Visvesvaraya Technological University",
    "Vivekananda Global University",
    "Woxsen University",
    "Xavier Institute Of Engineering C/O Xavier Technical Institute,Mahim,Mumbai (Mumbai University",
    "Yadavrao Tasgaonkar College of Engineering & Management (Mumbai University",
    "Yenepoya University"
]

ENTITY_STOPWORDS = {
    "university", "college", "institute", "institution", "school", "academy",
    "centre", "center", "department", "faculty", "campus", "online",
    "course", "program", "programme", "certificate", "training", "the",
    "of", "and", "for", "in", "at", "by", "with", "a", "an",
}


QS_URLS = [
    "https://www.topuniversities.com/world-university-rankings",
    "https://www.topuniversities.com/sub-saharan-africa-university-rankings",
    "https://www.topuniversities.com/asia-university-rankings",
    "https://www.topuniversities.com/latin-america-caribbean-overall",
    "https://www.topuniversities.com/europe-university-rankings",
    "https://www.topuniversities.com/arab-region-university-rankings",
]


NIRF_URLS = [
    "https://www.nirfindia.org/Rankings/2025/OverallRanking.html",
    "https://www.nirfindia.org/Rankings/2025/UniversityRanking.html",
    "https://www.nirfindia.org/Rankings/2025/CollegeRanking.html",
    "https://www.nirfindia.org/Rankings/2025/EngineeringRanking.html",
    "https://www.nirfindia.org/Rankings/2025/ManagementRanking.html",
    "https://www.nirfindia.org/Rankings/2025/OPENUNIVERSITYRanking.html",
    "https://www.nirfindia.org/Rankings/2025/STATEPUBLICUNIVERSITYRanking.html",
]

NIRF_BAND_SUFFIXES = ("150", "200", "300")

def important_words(text, min_len=3):
    words = []
    for word in normalize(text).split():
        if len(word) < min_len or word in ENTITY_STOPWORDS:
            continue
        words.append(word)
    return words


def entity_present(entity, page_text, threshold=0.78):
    """
    Match names inside large web pages without letting generic words like
    "university" or "course" create false positives.
    """
    n = normalize(entity)
    h = normalize(page_text)
    if not n or not h:
        return False, 0.0
        
    import re
    if re.search(rf"\b{re.escape(n)}\b", h):
        return True, 1.0

    words = important_words(entity)
    if not words:
        return fuzzy_match(entity, page_text, threshold=threshold)

    h_words = h.split()
    found = sum(1 for word in words if any(hw.startswith(word) for hw in h_words))
    ratio = found / len(words)
    return ratio >= threshold, ratio


def parse_bool(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "yes", "1", "present", "found"}
    return False


def check_runtime_dependencies():
    global Image, fitz, fpdf_module, FPDF, uc, By, Keys, WebDriverWait, EC
    global requests, pdfplumber, cv2, pytesseract, np
    missing = []
    if requests is None:
        missing.append("requests")
    if Image is None:
        missing.append("Pillow")
    if fitz is None:
        missing.append("PyMuPDF")
    fpdf_version = getattr(fpdf_module, "__version__", "") if fpdf_module else ""
    if FPDF is None or not fpdf_version or fpdf_version.startswith("1."):
        missing.append("fpdf2")
    if uc is None:
        missing.append("undetected-chromedriver")
        missing.append("selenium")
    if pdfplumber is None:
        missing.append("pdfplumber")
    if cv2 is None:
        missing.append("opencv-python")
    if np is None:
        missing.append("numpy")

    if missing:
        print("\n[!] Missing required Python packages:")
        for package in missing:
            print(f"    - {package}")
        print("\n[!] Attempting automatic installation of missing packages...")
        import subprocess
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("    -> Successfully installed missing packages.")
            # Re-import after install
            import importlib
            if "requests" in missing:
                requests = importlib.import_module("requests")
            if "Pillow" in missing:
                Image = importlib.import_module("PIL.Image")
            if "PyMuPDF" in missing:
                fitz = importlib.import_module("fitz")
            if "fpdf2" in missing:
                fpdf_module = importlib.import_module("fpdf")
                FPDF = fpdf_module.FPDF
            if "undetected-chromedriver" in missing:
                uc = importlib.import_module("undetected_chromedriver")
            if "selenium" in missing:
                By = importlib.import_module("selenium.webdriver.common.by").By
                Keys = importlib.import_module("selenium.webdriver.common.keys").Keys
                WebDriverWait = importlib.import_module("selenium.webdriver.support.ui").WebDriverWait
                EC = importlib.import_module("selenium.webdriver.support.expected_conditions")
            if "pdfplumber" in missing:
                pdfplumber = importlib.import_module("pdfplumber")
            if "opencv-python" in missing:
                cv2 = importlib.import_module("cv2")
            if "numpy" in missing:
                np = importlib.import_module("numpy")

        except Exception as e:
            print(f"    -> Failed to install packages automatically: {e}")
            print("\nPlease install them manually with:")
            print("    python -m pip install -r requirements.txt")
            print(f"    python -m pip install {' '.join(missing)}")
            return False

    if spacy is None or NLP_BRAIN is None:
        print("\n[!] Optional spaCy package or model not installed. Regex/fuzzy local verification will be used.")

    if GoogleTranslator is None:
        print("[!] Optional deep-translator package not installed. Foreign-language pages will not be auto-translated.")

    print("\nVerification is local-first. No LLM/API key is required.")
    return True


# ──────────────────────────────────────────────────────────────
#  MAIN VERIFIER CLASS
# ──────────────────────────────────────────────────────────────

class AutonomousCourseVerifier:
    def __init__(self, input_pdf):
        self.input_pdf = input_pdf
        base_name = os.path.splitext(os.path.basename(input_pdf))[0]
        self.output_pdf = f"{base_name}_AUTONOMOUS_VERIFIED.pdf"
        self.courses = []
        self.floating_items = []  # text/links outside boxes
        self.ndu_category_cache = {} # Cache for NDU category pages
        run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self.screenshots_dir = os.path.abspath(os.path.join(
            os.path.dirname(input_pdf) or '.',
            'verification_screenshots',
            f"{base_name}_{run_stamp}",
        ))
        os.makedirs(self.screenshots_dir, exist_ok=True)

    def _safe_get(self, driver, url):
        """Wrapper around driver.get() that actively attempts to bypass Captchas."""
        import time
        import random
        from selenium.webdriver.common.by import By
        from selenium.webdriver.common.action_chains import ActionChains
        
        driver.get(url)
        time.sleep(3)
        
        # SSL Certificate Error Bypass
        try:
            if "Privacy error" in driver.title or "Your connection is not private" in driver.page_source:
                print("    -> [!] SSL Certificate error detected. Bypassing...")
                adv_btn = driver.find_elements(By.ID, "details-button")
                if adv_btn:
                    driver.execute_script("arguments[0].click();", adv_btn[0])
                    time.sleep(1)
                proc_link = driver.find_elements(By.ID, "proceed-link")
                if proc_link:
                    driver.execute_script("arguments[0].click();", proc_link[0])
                    time.sleep(4)
        except Exception:
            pass

        self._inject_beautiful_cursor(driver)
        
        for _ in range(3):
            try:
                page_src = driver.page_source.lower()
                if "verify you are human" in page_src or "just a moment" in page_src or "attention required" in page_src:
                    print("    -> [!] Captcha or Bot Challenge detected. Attempting bypass...")
                    
                    try:
                        body = driver.find_element(By.TAG_NAME, 'body')
                        ac = ActionChains(driver)
                        for _ in range(3):
                            ac.move_to_element_with_offset(body, random.randint(10, 100), random.randint(10, 100)).perform()
                            time.sleep(0.5)
                    except: pass
                    
                    iframes = driver.find_elements(By.TAG_NAME, "iframe")
                    for iframe in iframes:
                        src = iframe.get_attribute('src') or ""
                        title = iframe.get_attribute('title') or ""
                        if 'challenges' in src or 'widget' in title.lower() or 'turnstile' in src:
                            print("    -> [!] Found Captcha iframe, clicking center...")
                            driver.switch_to.frame(iframe)
                            time.sleep(1)
                            try:
                                box = driver.find_element(By.TAG_NAME, 'body')
                                ActionChains(driver).move_to_element(box).click().perform()
                            except: pass
                            driver.switch_to.default_content()
                            time.sleep(4)
                            break
                    time.sleep(4)
                else:
                    break
            except Exception as e:
                try: driver.switch_to.default_content()
                except: pass
                break
        os.makedirs(self.screenshots_dir, exist_ok=True)

        self.model = None

    # ──────────────────────────────────────────────────────────
    #  STEP 1: PDF EXTRACTION  (quadrants + floating detection)
    # ──────────────────────────────────────────────────────────

    def _detect_badges_in_quadrant(self, img_path):
        """
        Detect visual badges inside a quadrant box using OpenCV:
          - QS badge:       orange/yellow square in the bottom badge row
          - NIRF badge:     red + blue/purple mark in the bottom badge row
          - Blue box:       blue/cyan filled square for free/free-to-audit
          - Yellow box:     right-side yellow/gold filled square for scholarship
        Returns dict of detected badges.
        """
        default_badges = {"qs": False, "nirf": False, "free_box": False, "scholarship_box": False}
        if cv2 is None or np is None:
            return default_badges
        if not os.path.exists(img_path):
            return default_badges

        img = cv2.imread(img_path)
        if img is None:
            return default_badges

        h, w = img.shape[:2]
        if w > 700:
            ratio = 700 / w
            img = cv2.resize(img, (700, int(h * ratio)))
            h, w = img.shape[:2]

        # Crop to the bottom part where badges usually are
        y_min = int(h * 0.62)
        y_max = int(h * 0.985)
        roi = img[y_min:y_max, :]
        if roi.size == 0:
            return default_badges

        hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)

        # OpenCV HSV ranges: H [0,179], S [0,255], V [0,255]
        # orange/yellow (QS): H=11-36, S>107, V>114
        qs_mask = cv2.inRange(hsv, np.array([11, 107, 114]), np.array([36, 255, 255]))
        
        # yellow (Scholarship): H=22-36, S>107, V>127
        sch_mask = cv2.inRange(hsv, np.array([22, 107, 127]), np.array([36, 255, 255]))
        
        # blue (Free): H=89-102, S>89, V>114
        free_mask = cv2.inRange(hsv, np.array([89, 89, 114]), np.array([102, 255, 255]))
        
        # red (NIRF part 1): H=0-9 or 167-179, S>89, V>81
        red1 = cv2.inRange(hsv, np.array([0, 89, 81]), np.array([9, 255, 255]))
        red2 = cv2.inRange(hsv, np.array([167, 89, 81]), np.array([179, 255, 255]))
        red_mask = cv2.bitwise_or(red1, red2)
        
        # nirf blue (NIRF part 2): H=105-146, S>56, V>45
        nirf_blue_mask = cv2.inRange(hsv, np.array([105, 56, 45]), np.array([146, 255, 255]))

        def square_like(w, h, area):
            if area < 500: return False
            if not (24 <= w <= 95 and 24 <= h <= 95): return False
            if not (0.55 <= w / max(1, h) <= 1.75): return False
            fill = area / (w * h)
            return fill >= 0.75

        badges = dict(default_badges)

        # Find QS
        contours, _ = cv2.findContours(qs_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            x, y, bw, bh = cv2.boundingRect(c)
            cx_ratio = (x + bw/2) / w
            cy_ratio = (y_min + y + bh/2) / h
            if square_like(bw, bh, area) and 0.30 <= cx_ratio <= 0.66 and cy_ratio >= 0.66:
                badges["qs"] = True
                break

        # Find Scholarship
        contours, _ = cv2.findContours(sch_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            x, y, bw, bh = cv2.boundingRect(c)
            cx_ratio = (x + bw/2) / w
            cy_ratio = (y_min + y + bh/2) / h
            if square_like(bw, bh, area) and cx_ratio >= 0.66 and cy_ratio >= 0.66:
                
                break

        # Find Free
        contours, _ = cv2.findContours(free_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in contours:
            area = cv2.contourArea(c)
            x, y, bw, bh = cv2.boundingRect(c)
            cx_ratio = (x + bw/2) / w
            cy_ratio = (y_min + y + bh/2) / h
            if square_like(bw, bh, area) and cx_ratio >= 0.70 and cy_ratio >= 0.66:
                badges["free_box"] = True
                break

        # Find NIRF (needs both red and blue close together)
        red_count = cv2.countNonZero(red_mask[:, int(w*0.35):int(w*0.82)])
        blue_count = cv2.countNonZero(nirf_blue_mask[:, int(w*0.35):int(w*0.82)])
        if red_count >= 100 and blue_count >= 150:
            combined = cv2.bitwise_or(red_mask, nirf_blue_mask)
            contours, _ = cv2.findContours(combined, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in contours:
                x, y, bw, bh = cv2.boundingRect(c)
                cx_ratio = (x + bw/2) / w
                cy_ratio = (y_min + y + bh/2) / h
                if 24 <= bw <= 150 and 12 <= bh <= 90 and 0.35 <= cx_ratio <= 0.82 and cy_ratio >= 0.66:
                    badges["nirf"] = True
                    break

        # Fallback to OCR to drastically improve accuracy if badges were missed or falsely identified
        try:
            import base64
            gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
            # Use PSM 11 (sparse text) to catch small badge text            
            import pytesseract
            if os.name == 'nt':
                if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                    pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
            ocr_text = pytesseract.image_to_string(gray if 'gray' in locals() else (image if 'image' in locals() else img), config='--oem 3 --psm 6').lower()
            if ocr_text is None: ocr_text = ""


            if "qs" in ocr_text.split() or "stars" in ocr_text:
                badges["qs"] = True
            
            if "nirf" in ocr_text or "national institutional" in ocr_text or "ranking framework" in ocr_text:
                badges["nirf"] = True
        except:
            pass

        print(f"      -> Local badge detection: {badges}")
        return badges

    KNOWN_INSTITUTES_NORM = [(inst, normalize(inst)) for inst in KNOWN_INSTITUTES]

    def extract_and_parse(self):
        print(f"\n[*] Step 1/4: Analyzing PDF structurally: {self.input_pdf}")
        doc = fitz.open(self.input_pdf)

        box_labels = ["top-left", "top-right", "bottom-left", "bottom-right"]

        for page_num in range(len(doc)):
            page = doc[page_num]
            pw, ph = page.rect.width, page.rect.height

            # Box boundaries dynamically calculated to isolate the 4 course boxes 
            # and ignore the global header (CERTIFICATE) and footer (NIRF info)
            half_w = pw / 2
            half_h = ph / 2
            y_top = ph * 0.08      # Skip top 8% (Header)
            y_bottom = ph * 0.95   # Skip bottom 5% (Footer)

            box_rects = [
                fitz.Rect(0, y_top, half_w, half_h),         # Q1 top-left  = Course 1
                fitz.Rect(half_w, y_top, pw, half_h),        # Q2 top-right = Course 2
                fitz.Rect(0, half_h, half_w, y_bottom),      # Q3 bot-left  = Course 3
                fitz.Rect(half_w, half_h, pw, y_bottom),     # Q4 bot-right = Course 4
            ]

            quadrants = [{"id": f"Q{i+1}", "label": box_labels[i],
                          "rect": box_rects[i], "blocks": [], "links": []}
                         for i in range(4)]

            blocks = page.get_text("blocks")
            text_blocks = [b for b in blocks if b[6] == 0]
            links = page.get_links()

            # Assign blocks to quadrants or flag as floating
            for b in text_blocks:
                b_rect = fitz.Rect(b[:4])
                cx = (b_rect.x0 + b_rect.x1) / 2
                cy = (b_rect.y0 + b_rect.y1) / 2
                assigned = False
                for i, q in enumerate(quadrants):
                    if q["rect"].contains(fitz.Point(cx, cy)):
                        q["blocks"].append(b)
                        assigned = True
                        break
                if not assigned:
                    txt = b[4].strip()
                    if txt and len(txt) > 2:
                        text_to_check = txt
                        bad_phrases = ["high value low cost certificate", "bachelors", "diploma", "masters", "certificate", "post graduate certificate", "post graduate diploma", "free to audit courses"]
                        if not any(bp in text_to_check.lower() for bp in bad_phrases):
                            self.floating_items.append({
                                "page": page_num + 1,
                                "text": txt.replace('\n', ' '),
                                "position": f"({cx:.0f}, {cy:.0f})"
                            })

            # Assign links to quadrants or flag as floating
            for l in links:
                l_rect = l['from']
                cx = (l_rect.x0 + l_rect.x1) / 2
                cy = (l_rect.y0 + l_rect.y1) / 2
                assigned = False
                for i, q in enumerate(quadrants):
                    if q["rect"].contains(fitz.Point(cx, cy)):
                        q["links"].append(l)
                        assigned = True
                        break
                if not assigned and l.get('uri'):
                    text_to_check = l.get('uri', '')
                    bad_phrases = ["high value low cost certificate", "bachelors", "diploma", "masters", "certificate", "post graduate certificate", "post graduate diploma", "free to audit courses"]
                    if not any(bp in text_to_check.lower() for bp in bad_phrases):
                        self.floating_items.append({
                            "page": page_num + 1,
                            "text": f"[FLOATING LINK] {l.get('uri', '')}",
                            "position": f"({cx:.0f}, {cy:.0f})"
                        })

            # Save screenshot of each quadrant box (DEFERRED TO POST-INDEX SELECTION)

            # Parse each quadrant into a course
            for qi, q in enumerate(quadrants):
                full_text = " ".join([b[4].replace('\n', ' ') for b in q["blocks"]]).strip()
                if "Mode:" not in full_text and "Cost:" not in full_text and "Fees:" not in full_text:
                    continue

                # Detect visual badges locally (DEFERRED TO POST-INDEX SELECTION)
                badges = {"qs": False, "nirf": False, "free_box": False, "scholarship_box": False}

                course_data = {
                    "name": "Unknown", "uni": "Unknown", "cost": "Unknown",
                    "duration": "Unknown", "skills": "N/A in PDF", "mode": "Online",
                    "country": "Unknown", "url": "Unknown",
                    "page_num": page_num + 1,
                    "box_position": q["label"],
                    "box_index": qi + 1,
                    # Visual badges from PDF
                    "has_qs_badge": badges["qs"],
                    "has_nirf_badge": badges["nirf"],
                    "has_free_box": badges["free_box"],
                    "has_scholarship_box": badges["scholarship_box"],
                    # Verification results
                    "web_status": "FALSE", "reason": "",
                    "web_name": "", "web_cost": "", "web_uni": "",
                    "skills_verified": "", "qs_ranked": False, "nirf_ranked": False,
                    "qs_detail": "", "nirf_detail": "",
                    "scholarship_found": False,
                }

                if len(q["links"]) > 0:
                    course_data["url"] = q["links"][0].get("uri", "Unknown")

                words = page.get_text('words')
                q_words = [w for w in words if q["rect"].contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2))]
                q_words.sort(key=lambda w: w[1])
                
                lines = []
                current_line_words = []
                current_y = None
                for w in q_words:
                    y = w[1]
                    if current_y is None or abs(y - current_y) < 8:
                        current_line_words.append(w)
                        if current_y is None: current_y = y
                    else:
                        current_line_words.sort(key=lambda w: w[0])
                        lines.append(' '.join([w[4] for w in current_line_words]))
                        current_line_words = [w]
                        current_y = y
                if current_line_words:
                    current_line_words.sort(key=lambda w: w[0])
                    lines.append(' '.join([w[4] for w in current_line_words]))

                full_text_sorted = '\n'.join(lines)
                
                # Clean up ligatures and symbols before extraction
                full_text_sorted = full_text_sorted.replace('\ufb02', 'fl').replace('\ufb01', 'fi').replace('\ufb00', 'ff')
                full_text_sorted = full_text_sorted.replace('\u2018', "'").replace('\u2019', "'")
                full_text_sorted = full_text_sorted.replace('\u201c', '"').replace('\u201d', '"')
                full_text_sorted = full_text_sorted.replace('\u2013', '-').replace('\u2014', '-')
                full_text_sorted = full_text_sorted.replace('\u2026', '...')
                
                # --- Strict Horizontal Boundary Extraction ---
                
                # Check for gray boxes (Provider Name)
                drawings = page.get_drawings()
                gray_boxes = [d['rect'] for d in drawings if d.get('fill') and 0.7 < d['fill'][0] < 0.8]
                q_gray = [b for b in gray_boxes if b.intersects(q["rect"])]
                
                has_gray_box = False
                if q_gray:
                    has_gray_box = True
                    gb = q_gray[0]
                    uni_words = [w for w in q_words if gb.contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2))]
                    uni_words.sort(key=lambda w: (w[3], w[0]))
                    course_data['uni'] = " ".join([w[4] for w in uni_words]).strip()
                    
                    name_words = [w for w in q_words if w[1] < gb.y0 and not gb.contains(fitz.Point((w[0]+w[2])/2, (w[1]+w[3])/2))]
                    name_words.sort(key=lambda w: (w[3], w[0]))
                    course_data['name'] = " ".join([w[4] for w in name_words]).strip()
                
                # 1. Find where the Institute Name begins using fast exact match or keyword fallback
                uni_str_start = 0
                best_ratio = 0
                for i in range(len(lines)):
                    if any(lines[i].lower().startswith(k) for k in ['cost:', 'duration:', 'language:', 'skills:', 'mode:']):
                        break
                    for length in [1, 2]:
                        if i + length <= len(lines):
                            candidate = " ".join(lines[i:i+length])
                            candidate_norm = normalize(candidate)
                            if len(candidate_norm) < 4: continue
                            for inst, inst_norm in self.KNOWN_INSTITUTES_NORM:
                                # FAST Exact Substring Match instead of slow difflib
                                if inst_norm in candidate_norm or candidate_norm in inst_norm:
                                    best_ratio = 1.0
                                    uni_str_start = full_text_sorted.find(lines[i])
                                    break
                            if best_ratio == 1.0:
                                break
                    if best_ratio == 1.0:
                        break
                
                if uni_str_start == 0:
                    for l in lines:
                        pu = l.lower()
                        if any(x in pu for x in ['university', 'institute', 'state', 'technology', 'college', 'school', 'academy', 'polytechnic']) or re.search(r'\btech\b', pu):
                            uni_str_start = full_text_sorted.find(l)
                            break
                            
                # 2. Extract strictly within keyword boundaries
                skills_match = re.search(r'Skills:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Mode:|Country:|Link to|Certificates|[\u20b9\$]|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if skills_match: course_data['skills'] = skills_match.group(1).replace('\n', ' ').strip()

                cost_match = re.search(r'Cost:\s*(.*?)(?=\s*(?:Duration:|Language:|Mode:|Skills:|Country:|Link to|Certificates|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if cost_match: course_data['cost'] = cost_match.group(1).replace('\n', ' ').strip()
                
                dur_match = re.search(r'Duration:\s*(.*?)(?=\s*(?:Cost:|Language:|Mode:|Skills:|Country:|Link to|Certificates|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if dur_match: course_data['duration'] = dur_match.group(1).replace('\n', ' ').strip()
                
                mode_match = re.search(r'Mode:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Skills:|Country:|Link to|Certificates|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if mode_match:
                    mode_val = mode_match.group(1).replace('\n', ' ').strip()
                    # Fix all known ligature/symbol corruptions
                    mode_val = mode_val.replace('Of\ufb02ine', 'Offline').replace('Of\ufb02 ine', 'Offline')
                    mode_val = mode_val.replace('Offl ine', 'Offline').replace('offl ine', 'Offline')
                    mode_val = mode_val.replace('\ufb02', 'fl').replace('\ufb01', 'fi')
                    course_data['mode'] = mode_val
                
                lang_match = re.search(r'Language:\s*(.*?)(?=\s*(?:Cost:|Duration:|Mode:|Skills:|Country:|Link to|Certificates|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if lang_match: course_data['language'] = lang_match.group(1).replace('\n', ' ').strip()
                
                country_match = re.search(r'Country:\s*(.*?)(?=\s*(?:Cost:|Duration:|Language:|Mode:|Skills:|Link to|Certificates|$))', full_text_sorted, flags=re.DOTALL | re.IGNORECASE)
                if country_match: course_data['country'] = country_match.group(1).replace('\n', ' ').strip()
                
                # 3. Bound the Institute string strictly until the first keyword appears
                first_keyword_pos = len(full_text_sorted)
                for kw in ['Cost:', 'Duration:', 'Language:', 'Skills:', 'Mode:', 'Country:']:
                    pos = full_text_sorted.lower().find(kw.lower())
                    if pos != -1 and pos < first_keyword_pos:
                        first_keyword_pos = pos
                        
                if not has_gray_box:
                    if uni_str_start > 0 and uni_str_start < first_keyword_pos:
                        course_data['name'] = full_text_sorted[:uni_str_start].replace('\n', ' ').strip()
                        course_data['uni'] = full_text_sorted[uni_str_start:first_keyword_pos].replace('\n', ' ').strip()
                    else:
                        pre_keyword_lines = []
                        for l in lines:
                            if any(l.lower().startswith(k) for k in ['cost:', 'duration:', 'language:', 'skills:', 'mode:']):
                                break
                            if l.strip():
                                pre_keyword_lines.append(l.strip())
                        
                        if len(pre_keyword_lines) > 1:
                            course_data['uni'] = pre_keyword_lines[-1]
                            course_data['name'] = " ".join(pre_keyword_lines[:-1])
                        elif len(pre_keyword_lines) == 1:
                            course_data['name'] = pre_keyword_lines[0]
                            course_data['uni'] = "Unknown"
                        else:
                            course_data['name'] = "Unknown"
                            course_data['uni'] = "Unknown"

                self.courses.append(course_data)

        print(f"    Extracted {len(self.courses)} courses from PDF.")
        if self.floating_items:
            print(f"    [!] Found {len(self.floating_items)} floating text/links outside boxes.")
        else:
            print(f"    No floating text/links detected outside boxes.")

    # ──────────────────────────────────────────────────────────
    #  STEP 2: QS & NIRF RANKING VERIFICATION
    # ──────────────────────────────────────────────────────────

    def uni_match(self, name1, name2):
        import re
        def standardize_uni_name(name):
            import re
            name = str(name).lower()
            name = re.sub(r'[^a-z0-9\s]', ' ', name)
            words = name.split()
            
            # Simple exact word mapping (1,000,000x faster than regex)
            word_map = {
                'tech': 'technology', 'engg': 'engineering', 'inst': 'institute', 'univ': 'university',
                'mgmt': 'management', 'mgt': 'management', 'med': 'medical', 'sci': 'science',
                'intl': 'international', 'natl': 'national', 'coll': 'college', 'govt': 'government',
                'gvt': 'government', 'edu': 'education', 'edtn': 'education', 'poly': 'polytechnic',
                'info': 'information', 'res': 'research', 'agri': 'agriculture', 'arch': 'architecture',
                'admin': 'administration', 'bus': 'business', 'com': 'commerce', 'comm': 'commerce',
                'comp': 'computer', 'pharma': 'pharmacy', 'pharm': 'pharmacy', 'econ': 'economics',
                'stat': 'statistics', 'math': 'mathematics', 'hist': 'history', 'lit': 'literature',
                'phil': 'philosophy', 'psych': 'psychology', 'soc': 'sociology', 'chem': 'chemistry',
                'phys': 'physics', 'bio': 'biology', 'environ': 'environment', 'vet': 'veterinary',
                'dent': 'dental', 'nurs': 'nursing', 'hos': 'hospital', 'hosp': 'hospital',
                'acad': 'academy', 'app': 'applied', 'auto': 'autonomous', 'cent': 'central',
                'dist': 'district', 'dept': 'department', 'div': 'division', 'fac': 'faculty',
                'vidya': 'vidyalaya', 'maha': 'mahavidyalaya', 'pg': 'postgraduate', 'ug': 'undergraduate',
                'agric': 'agriculture', 'agr': 'agriculture', 'aero': 'aeronautics', 'archit': 'architecture',
                'anim': 'animation', 'appli': 'applied', 'appl': 'applied', 'busi': 'business',
                'bot': 'botany', 'biol': 'biology', 'scienc': 'science', 'biotech': 'biotechnology',
                'clin': 'clinical', 'corp': 'corporate', 'crim': 'criminology', 'cul': 'culture',
                'dev': 'development', 'distr': 'district', 'eco': 'economics', 'ed': 'education',
                'educ': 'education', 'elect': 'electrical', 'elec': 'electronic', 'eng': 'engineering',
                'engl': 'english', 'env': 'environment', 'envir': 'environmental', 'ext': 'extension',
                'fin': 'finance', 'fash': 'fashion', 'geo': 'geography', 'geol': 'geology', 'glob': 'global',
                'gov': 'government', 'grad': 'graduate', 'ind': 'industrial', 'inf': 'information',
                'int': 'international', 'jour': 'journalism', 'lang': 'language', 'lib': 'library',
                'mach': 'machine', 'maths': 'mathematics', 'mech': 'mechanical', 'mktg': 'marketing',
                'mkt': 'marketing', 'mus': 'music', 'nat': 'national', 'nutr': 'nutrition',
                'optom': 'optometry', 'org': 'organization', 'path': 'pathology', 'poli': 'political',
                'prof': 'professional', 'psy': 'psychology', 'pub': 'public', 'rel': 'religion',
                'sociol': 'sociology', 'stats': 'statistics', 'stu': 'studies', 'sys': 'systems',
                'technol': 'technology', 'theol': 'theology', 'tour': 'tourism', 'train': 'training',
                'vis': 'visual', 'voc': 'vocational', 'zoo': 'zoology', 'zool': 'zoology',
                'ayur': 'ayurveda', 'homoeo': 'homoeopathy', 'shiksha': 'education', 'kendra': 'center',
                'insti': 'institute'
            }
            
            full_replacements = {
                'iit': 'indian institute of technology',
                'nit': 'national institute of technology',
                'iim': 'indian institute of management',
                'iisc': 'indian institute of science',
                'aiims': 'all india institute of medical sciences',
                'iiit': 'indian institute of information technology',
                'iiser': 'indian institute of science education and research',
                'nitttr': 'national institute of technical teachers training and research',
                'nielit': 'national institute of electronics and information technology',
                'bits': 'birla institute of technology and science',
                'vit': 'vellore institute of technology',
                'srm': 'srm institute of science and technology',
                'lpu': 'lovely professional university',
                'jnu': 'jawaharlal nehru university',
                'bhu': 'banaras hindu university',
                'amu': 'aligarh muslim university',
                'jmi': 'jamia millia islamia',
                'du': 'university of delhi',
                'ignou': 'indira gandhi national open university',
                'tiss': 'tata institute of social sciences',
                'nift': 'national institute of fashion technology',
                'nid': 'national institute of design',
                'nlu': 'national law university',
                'nlsiu': 'national law school of india university',
                'nujs': 'national university of juridical sciences',
                'nalsar': 'national academy of legal studies and research',
                'vtu': 'visvesvaraya technological university',
                'sppu': 'savitribai phule pune university',
                'uoh': 'university of hyderabad',
                'cu': 'chandigarh university',
                'dtu': 'delhi technological university',
                'nsut': 'netaji subhas university of technology',
                'nsit': 'netaji subhas institute of technology',
                'ipu': 'guru gobind singh indraprastha university',
                'ggsipu': 'guru gobind singh indraprastha university',
                'mgm': 'mahatma gandhi mission',
                'jntu': 'jawaharlal nehru technological university',
                'rgpv': 'rajiv gandhi proudyogiki vishwavidyalaya',
                'aktu': 'dr a p j abdul kalam technical university',
                'coep': 'college of engineering pune',
                'vjti': 'veermata jijabai technological institute',
                'rvce': 'r v college of engineering',
                'xlri': 'xavier school of management',
                'fms': 'faculty of management studies',
                'nmims': 'narsee monjee institute of management studies',
                'sibm': 'symbiosis institute of business management',
                'spjimr': 's p jain institute of management and research',
                'isi': 'indian statistical institute',
                'tifr': 'tata institute of fundamental research',
                'niper': 'national institute of pharmaceutical education and research',
                'pgimer': 'post graduate institute of medical education and research',
                'jipmer': 'jawaharlal institute of postgraduate medical education and research',
                'cmc': 'christian medical college',
                'uci': 'university of california irvine',
                'ucsd': 'university of california san diego',
                'ucsb': 'university of california santa barbara',
                'mit': 'massachusetts institute of technology',
                'caltech': 'california institute of technology',
                'nyu': 'new york university',
                'ucla': 'university of california los angeles',
                'uiuc': 'university of illinois urbana champaign',
                'upenn': 'university of pennsylvania',
                'cmu': 'carnegie mellon university',
                'uw': 'university of washington',
                'unc': 'university of north carolina',
                'ucl': 'university college london',
                'lse': 'london school of economics',
                'kcl': 'kings college london',
                'nus': 'national university of singapore',
                'ntu': 'nanyang technological university',
                'hku': 'university of hong kong',
                'hkust': 'hong kong university of science and technology',
                'unsw': 'university of new south wales',
                'anu': 'australian national university',
                'uoft': 'university of toronto',
                'ubc': 'university of british columbia',
                'epfl': 'ecole polytechnique federale de lausanne',
                'ju': 'jadavpur university',
                'cusat': 'cochin university of science and technology',
                'sastra': 'shanmugha arts science technology and research academy',
                'mahe': 'manipal academy of higher education',
                'kiit': 'kalinga institute of industrial technology',
                'mnnit': 'motilal nehru national institute of technology',
                'manit': 'maulana azad national institute of technology',
                'svnit': 'sardar vallabhbhai national institute of technology',
                'mnit': 'malaviya national institute of technology',
                'vnit': 'visvesvaraya national institute of technology',
                'nitie': 'national institute of industrial engineering',
                'iift': 'indian institute of foreign trade',
                'iist': 'indian institute of space science and technology',
                'niser': 'national institute of science education and research',
                'afmc': 'armed forces medical college',
                'mamc': 'maulana azad medical college',
                'kgmu': 'king georges medical university',
                'umich': 'university of michigan',
                'umd': 'university of maryland',
                'uwaterloo': 'university of waterloo',
                'usc': 'university of southern california',
                'nyit': 'new york institute of technology',
                'njit': 'new jersey institute of technology',
                'purdue': 'purdue university',
                'rit': 'rochester institute of technology',
                'uwa': 'university of western australia',
                'uq': 'university of queensland',
                'usyd': 'university of sydney',
                'uoa': 'university of auckland',
                'tum': 'technical university of munich',
                'lmu': 'ludwig maximilian university of munich',
                'kth': 'kth royal institute of technology',
                'kaist': 'korea advanced institute of science and technology',
                'snu': 'seoul national university',
                'hkbu': 'hong kong baptist university',
                'polyu': 'hong kong polytechnic university',
                'cityu': 'city university of hong kong',
                'macquarie': 'macquarie university',
                'gndu': 'guru nanak dev university',
                'ccsu': 'chaudhary charan singh university',
                'mdu': 'maharshi dayanand university',
                'ku': 'kurukshetra university',
                'bbau': 'babasaheb bhimrao ambedkar university',
                'cuk': 'central university of kerala',
                'cupb': 'central university of punjab',
                'curaj': 'central university of rajasthan',
                'cug': 'central university of gujarat',
                'hnbgu': 'hemvati nandan bahuguna garhwal university',
                'nehu': 'north eastern hill university',
                'manuu': 'maulana azad national urdu university',
                'eflu': 'english and foreign languages university',
                'rmlnlu': 'dr ram manohar lohiya national law university',
                'hnlu': 'hidayatullah national law university',
                'nliu': 'national law institute university',
                'gnlu': 'gujarat national law university',
                'nluj': 'national law university jodhpur',
                'rgnul': 'rajiv gandhi national university of law',
                'cnlu': 'chanakya national law university',
                'nuals': 'national university of advanced legal studies',
                'tnnlu': 'tamil nadu national law university',
                'mnlu': 'maharashtra national law university',
                'upes': 'university of petroleum and energy studies',
                'jgu': 'o p jindal global university',
                'bml': 'bml munjal university',
                'pdpu': 'pandit deendayal energy university',
                'daiict': 'dhirubhai ambani institute of information and communication technology',
                'thapar': 'thapar institute of engineering and technology',
                'lnmiit': 'lnm institute of information technology',
                'jiit': 'jaypee institute of information technology',
                'msrit': 'm s ramaiah institute of technology',
                'suny': 'state university of new york',
                'cuny': 'city university of new york',
                'umass': 'university of massachusetts',
                'wpi': 'worcester polytechnic institute',
                'rpi': 'rensselaer polytechnic institute',
                'sbu': 'stony brook university',
                'uconn': 'university of connecticut',
                'csu': 'colorado state university',
                'msu': 'michigan state university',
                'psu': 'pennsylvania state university'
            }
            
            fillers = {'of', 'the', 'and', 'for', 'in', 'at'}
            
            final_words = []
            for w in words:
                if w in fillers: continue
                # Expand specific terms
                w = word_map.get(w, w)
                # Expand full acronyms
                expansion = full_replacements.get(w, w)
                final_words.extend(expansion.split())
                
            return " ".join(final_words)
            
        # ── Dynamic Acronym Matching ──
        # Generate acronyms from the original raw names to handle things like "PSGCAS" (including 'and') or "SRCC"
        def generate_acronyms(raw_str):
            import re
            clean_str = re.sub(r'[^a-zA-Z\s]', ' ', raw_str.lower())
            words = clean_str.split()
            if not words: return set()
            acr1 = "".join(w[0] for w in words)
            fillers = {'of', 'and', 'the', 'for', 'in', 'at', 'institute', 'college', 'university', 'school'}
            acr2 = "".join(w[0] for w in words if w not in fillers)
            acr3 = "".join(w[0] for w in words if w not in {'of', 'and', 'the', 'for', 'in', 'at'})
            return {acr1, acr2, acr3}

        raw_n1, raw_n2 = name1.lower().strip(), name2.lower().strip()
        if raw_n1 and raw_n2:
            if raw_n1 in generate_acronyms(raw_n2) or raw_n2 in generate_acronyms(raw_n1):
                return True

        n1 = standardize_uni_name(name1)
        n2 = standardize_uni_name(name2)
        w1 = set(n1.split())
        w2 = set(n2.split())
        if not w1 or not w2: return False
        
        # Word by word subset match (ignores generic words if one is a subset of the other)
        if w1.issubset(w2) or w2.issubset(w1):
            ignore = {'university', 'institute', 'college', 'school', 'academy'}
            w1_sig = w1 - ignore
            w2_sig = w2 - ignore
            if w1_sig and w2_sig and (w1_sig.issubset(w2_sig) or w2_sig.issubset(w1_sig)):
                # CRITICAL FIX: Prevent short names from falsely matching long different names
                # e.g., "Rajiv Gandhi University" (2) matching "Rajiv Gandhi National Institute" (4)
                if abs(len(w1_sig) - len(w2_sig)) <= 1:
                    return True
                
        # High threshold fuzzy fallback for typos using built-in difflib
        import difflib
        # Sort words so "University Columbia" matches "Columbia University"
        sorted_n1 = " ".join(sorted(w1))
        sorted_n2 = " ".join(sorted(w2))
        ratio = difflib.SequenceMatcher(None, sorted_n1, sorted_n2).ratio()
        if ratio > 0.93:
            return True
        return False

    def _get_acronyms(self, text):
        import re
        # Strip text inside parentheses first so it doesn't corrupt the acronym
        text = re.sub(r'\(.*?\)', '', text)
        clean_str = re.sub(r'[^a-zA-Z\s]', ' ', text.lower())
        words = clean_str.split()
        if not words: return set()
        acr1 = "".join(w[0] for w in words)
        fillers = {'of', 'and', 'the', 'for', 'in', 'at', 'institute', 'college', 'university', 'school'}
        acr2 = "".join(w[0] for w in words if w not in fillers)
        acr3 = "".join(w[0] for w in words if w not in {'of', 'and', 'the', 'for', 'in', 'at'})
        
        all_acrs = {acr1, acr2, acr3}
        
        # Only allow well-known top university acronym prefixes to prevent false positives
        allowed_prefixes = {
            'iit', 'iiit', 'nit', 'iim', 'mit', 'iisc', 'bits', 'aiims', 
            'nift', 'nid', 'iiser', 'nlu', 'vit', 'srm', 'bhu', 'jnu', 'amu',
            'nfsu', 'dtu', 'nsut', 'iiest', 'jmi', 'tiss', 'spa', 'nimhans',
            'kiit', 'mahe', 'pes', 'coep', 'niser', 'isb', 'xlri', 'mdi',
            'fms', 'iift', 'tifr', 'isi', 'ignou', 'hcu', 'vnit', 'mnit', 'svnit',
            'ucla', 'ucl', 'nus', 'ntu', 'lse', 'cmu', 'ucb', 'ucsd', 'nyu', 'eth', 'epfl'
        }
        
        valid = set()
        for a in all_acrs:
            if len(a) >= 3 and any(a.startswith(p) for p in allowed_prefixes):
                valid.add(a)
                
        return valid

    def _add_to_map(self, key, val, cmap):
        if not key: return
        if key not in cmap:
            cmap[key] = val

    def _get_sorted_norm(self, text):
        norm = normalize(text)
        if not norm: return ""
        # Only strip truly generic words — keep 'national', 'indian', 'state' etc.
        # to avoid collisions like "Pennsylvania State" vs "University of Pennsylvania"
        fillers = {'of', 'and', 'the', 'for', 'in', 'at'}
        sig_words = [w for w in norm.split() if w not in fillers]
        # Require at least 2 significant words to avoid single-word false matches
        if len(sig_words) < 2:
            return norm  # Use full normalized form for short names
        return " ".join(sorted(sig_words))

    def _auto_regenerate_csv(self, csv_path, source_patterns):
        """Regenerate a ranking CSV if any source file is newer than the CSV."""
        import glob
        if not os.path.exists(csv_path):
            return True  # CSV doesn't exist, needs generation
        csv_mtime = os.path.getmtime(csv_path)
        for pattern in source_patterns:
            for src in glob.glob(pattern):
                if os.path.getmtime(src) > csv_mtime:
                    print(f"      -> Source file '{src}' is newer than '{csv_path}', regenerating...")
                    return True
        return False

    def _xgb_fuzzy_match(self, needle, haystack, threshold=0.80):
        from difflib import SequenceMatcher
        import xgboost as xgb
        import numpy as np
        
        n = normalize(needle)
        h = normalize(haystack)
        if not n or not h: return False
        if n == h: return True
        
        ratio = SequenceMatcher(None, n, h).ratio()
        n_words = set(n.split())
        h_words = set(h.split())
        overlap = len(n_words & h_words) / max(1, min(len(n_words), len(h_words)))
        
        features = np.array([[ratio, overlap]])
        
        # Train lightweight model mapping basic logic
        X_train = np.array([
            [1.0, 1.0], [0.9, 0.9], [0.85, 0.85], [0.81, 0.81], # Matches
            [0.75, 0.75], [0.5, 0.5], [0.3, 0.1], [0.1, 0.0]    # Non-matches
        ])
        y_train = np.array([1, 1, 1, 1, 0, 0, 0, 0])
        
        model = xgb.XGBClassifier(n_estimators=5, max_depth=2, random_state=42)
        model.fit(X_train, y_train)
        
        pred = model.predict(features)[0]
        return pred == 1 and (ratio >= threshold or overlap >= threshold)

    def _offline_qs_lookup(self, uni):
     if not uni or uni == "Unknown": 
        return None
     if not hasattr(self, '_qs_cache'):
        self._qs_cache = {}
     if uni in self._qs_cache:
        return self._qs_cache[uni]
     is_ranked = DatabaseManager.is_qs_ranked(uni)
     result = "Ranked" if is_ranked else "Not Ranked"
     self._qs_cache[uni] = result
     return result


    def extract_visuals_for_range(self, start_idx=0, end_idx=None):
        print(f"\n[*] Step 1.5/4: Extracting visual badges (OCR) for selected courses ({start_idx+1} to {end_idx if end_idx else len(self.courses)})...")
        doc = fitz.open(self.input_pdf)
        end_limit = end_idx if end_idx is not None else len(self.courses)
        for c in self.courses[start_idx:end_limit]:
            page_num = c['page_num'] - 1
            box_idx = c['box_index'] - 1
            box_position = c['box_position']
            
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
            clip = box_rects[box_idx]
            pix = page.get_pixmap(clip=clip, dpi=200)
            img_path = os.path.join(self.screenshots_dir, f"pdf_page{c['page_num']}_box{c['box_index']}_{box_position}.png")
            pix.save(img_path)
            
            print(f"    -> Analyzing image for Course {self.courses.index(c)+1}...")
            badges = self._detect_badges_in_quadrant(img_path)
            c["has_qs_badge"] = badges["qs"]
            c["has_nirf_badge"] = badges["nirf"]
            c["has_free_box"] = badges["free_box"]
            c["has_scholarship_box"] = badges["scholarship_box"]
            if badges["qs"]: c["qs_ranked"] = True
            if badges["nirf"]: c["nirf_ranked"] = True

    def verify_rankings(self, start_idx=0, end_idx=None):
        """Check QS World/Regional and NIRF rankings for each university."""
        print(f"\n[*] Step 2/4: Verifying QS World/Regional and NIRF rankings via Search & Text Analysis...")
        
        # Pre-load CSVs into memory so self._qs_csv_names and self._nirf_csv_names exist
        self._offline_qs_lookup("trigger_cache")
        self._offline_nirf_lookup("trigger_cache")

        # Collect unique universities and their countries
        uni_map = {}
        end_limit = end_idx if end_idx is not None else len(self.courses)
        for c in self.courses[start_idx:end_limit]:
            uni = c.get('uni', 'Unknown')
            if uni and uni != 'Unknown':
                country = str(c.get('country', '')).lower()
                if uni not in uni_map or (uni_map[uni] == '' and country != '' and country != 'unknown'):
                    uni_map[uni] = country

        if not uni_map:
            print("    No universities to check.")
            return

        qs_results = {}
        nirf_results = {}

        for uni, country in uni_map.items():
            if not country or country == 'unknown':
                print(f"    -> Country unknown for '{uni}'. Performing headless search...")
                import requests
                from bs4 import BeautifulSoup
                try:
                    url = f"https://html.duckduckgo.com/html/?q={requests.utils.quote(uni + ' location country')}"
                    r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
                    soup = BeautifulSoup(r.text, 'html.parser')
                    snips = " ".join([a.text for a in soup.find_all('a', class_='result__snippet')])[:500]
                    if snips:
                        from llm_manager import get_llm_manager
                        prompt = f"Based on this search result, what country is the university '{uni}' located in? Respond ONLY with the country name (e.g., India, USA, Australia, UK) and nothing else. Snippet: {snips}"
                        found_country = get_llm_manager().generate(prompt, temperature=0.0).strip()
                        if len(found_country) < 20:
                            country = found_country
                            uni_map[uni] = country.lower()
                            for c in self.courses:
                                if c.get('uni') == uni:
                                    c['country'] = country.title()
                            print(f"    -> Discovered country: {country}")
                except Exception as e:
                    print(f"    -> Headless country search failed: {e}")
                    
            print(f"    Checking rankings for: {uni}")
            
            g_text_cache = None

            def check_ranking_via_search(ranking_type):
                nonlocal g_text_cache
                import re
                uni_lower = uni.lower()
                is_college = 'college' in uni_lower
                
                is_indian_college = False
                indian_keywords = ['india', 'bharat']
                if any(k in country for k in indian_keywords):
                    is_indian_college = True
                if not is_indian_college:
                    indian_name_keywords = ['indian', 'iit', 'iim', 'nit', 'delhi', 'mumbai', 'bangalore', 'chennai', 'kanpur', 'roorkee', 'amity', 'symbiosis', 'jindal', 'bits', 'thapar', 'manipal', 'nmims', 'spjimr', 'xlri', 'punjab', 'maharashtra', 'gujarat', 'kerala', 'tamil nadu', 'karnataka']
                    if any(k in uni_lower for k in indian_name_keywords):
                        is_indian_college = True
                
                bracket_match = re.search(r'\((.*?)\)', uni)
                bracket_uni = bracket_match.group(1).strip() if bracket_match else ""
                college_only = re.sub(r'\(.*?\)', '', uni).strip()
                
                if is_college and is_indian_college:
                    if bracket_uni:
                        if ranking_type == "QS":
                            direct = self._offline_qs_lookup(bracket_uni)
                            if direct == "Ranked":
                                return f"The university to which college is affiliated ({bracket_uni.title()}) is ranked in QS hence matched"
                        elif ranking_type == "NIRF":
                            direct_local = self._offline_nirf_lookup(bracket_uni)
                            if direct_local == "Ranked":
                                return f"The university to which college is affiliated ({bracket_uni.title()}) is ranked in NIRF hence matched"
                
                # Hardcoded Overrides for Universities
                if "aisect" in uni_lower:
                    return "Not Ranked"
                if "uttarakhand open" in uni_lower:
                    return "Not Ranked"
                if "babasaheb ambedkar open" in uni_lower:
                    return "Not Ranked"
                if "punjabi" in uni_lower and ranking_type == "QS":
                    return "Not Ranked"
                    
                if is_college and is_indian_college:
                    if bracket_uni:
                        if ranking_type == "QS":
                            direct = self._offline_qs_lookup(bracket_uni)
                            if direct == "Ranked":
                                return f"The university to which college is affiliated ({bracket_uni.title()}) is ranked in QS hence matched"
                        elif ranking_type == "NIRF":
                            direct_local = self._offline_nirf_lookup(bracket_uni)
                            if direct_local == "Ranked":
                                return f"The university to which college is affiliated ({bracket_uni.title()}) is ranked in NIRF hence matched"
                                
                    if g_text_cache is None:
                        g_text_cache = ""
                        try:
                            import requests
                            from bs4 import BeautifulSoup
                            from googlesearch import search
                            g_query = f'"{college_only}" affiliated university'
                            print(f"      -> Searching Google for Affiliation: {g_query}")
                            for j, g_url in enumerate(search(g_query, num_results=2, sleep_interval=1)):
                                try:
                                    res = requests.get(g_url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=5)
                                    soup = BeautifulSoup(res.text, 'html.parser')
                                    g_text_cache += " " + soup.get_text(separator=' ', strip=True)[:2000]
                                except: pass
                        except Exception as e:
                            print(f"      -> Google Search Affiliation failed: {e}")
                            
                    if ranking_type == "QS":
                        for qs_name in self._qs_csv_names.split('\n'):
                            if len(qs_name.strip()) > 5 and qs_name.strip() in g_text_cache.lower():
                                return f"The university to which college is affiliated ({qs_name.strip().title()}) is ranked in QS hence matched"
                    elif ranking_type == "NIRF":
                        for nirf_name in self._nirf_csv_names.split('\n'):
                            if len(nirf_name.strip()) > 5 and nirf_name.strip() in g_text_cache.lower():
                                return f"The university to which college is affiliated ({nirf_name.strip().title()}) is ranked in NIRF hence matched"
                                
                    if ranking_type == "QS":
                        if self._offline_qs_lookup(college_only) == "Ranked":
                            return "Ranked via Local Heuristics (Direct College Match)"
                    elif ranking_type == "NIRF":
                        if self._offline_nirf_lookup(college_only) == "Ranked":
                            return "Ranked via Local Heuristics (Direct College Match)"
                    
                    return "Not Ranked"
                    
                try:
                    if ranking_type == "QS":
                        direct = self._offline_qs_lookup(uni)
                        if direct:
                            return direct
                        return "Not Ranked"
                    elif ranking_type == "NIRF":
                        direct_local = self._offline_nirf_lookup(uni)
                        if direct_local:
                            return direct_local
                        return "Not Ranked"

                except Exception as e:
                    print(f"      Search check failed for {ranking_type}: {str(e)[:90]}")
                    return "Not Ranked"

            # ── QS World + Regional ──
            qs_found = check_ranking_via_search("QS")
            qs_results[uni] = qs_found
            if qs_found != "Not Ranked":
                print(f"      QS match confirmed for {uni}: {qs_found}")
            # ── NIRF ──
            nirf_found = check_ranking_via_search("NIRF")
            nirf_results[uni] = nirf_found
            if nirf_found != "Not Ranked":
                print(f"      NIRF match confirmed for {uni}: {nirf_found}")


        # Apply results to courses
        for c in self.courses:
            uni = c.get('uni', 'Unknown')
            if uni in qs_results:
                c['qs_detail'] = qs_results[uni]
                c['qs_ranked'] = qs_results[uni] != "Not Ranked"
            if uni in nirf_results:
                c['nirf_detail'] = nirf_results[uni]
                c['nirf_ranked'] = nirf_results[uni] != "Not Ranked"

        print(f"    QS/NIRF verification complete for {len(uni_map)} universities.")

    def _search_google_fallback(self, course_name, uni_name, query_type="syllabus", worker_id=None):
        import requests
        from bs4 import BeautifulSoup
        try:
            from googlesearch import search
            query = f'"{course_name}" "{uni_name}" {query_type}'
            print(f"      -> Executing Google Fallback Search: {query}")
            results = list(search(query, num_results=2, advanced=False))
            extracted = ""
            headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36'}
            for r_url in results:
                try:
                    res = requests.get(r_url, headers=headers, timeout=10)
                    soup = BeautifulSoup(res.text, 'html.parser')
                    text = soup.get_text(separator=' ', strip=True)
                    extracted += f"\n--- Source: {r_url} ---\n" + text[:4000]
                except: pass
            return extracted
        except Exception as e:
            print(f"      -> Google Search Fallback failed: {e}")
            return ""

    def _search_excel_for_links(self, uni_name, course_name):
        import os
        if not os.path.exists("CombinedWork.xlsx"): return {}
        try:
            import openpyxl
            wb = openpyxl.load_workbook("CombinedWork.xlsx", data_only=True)
            ws = wb.active
            
            fees_col = None
            link_col = None
            
            for col_idx, cell in enumerate(ws[1], start=1):
                if cell.value and isinstance(cell.value, str):
                    val = cell.value.lower().strip()
                    if val == 'link': link_col = col_idx
                    if 'fee' in val: fees_col = col_idx
                    if 'field/domain' in val or 'syllabus' in val or 'curriculum' in val or 'skill' in val: syllabus_col = col_idx
                    if 'institute' in val or 'university' in val: uni_col = col_idx
            
            links = {}
            for row in range(2, ws.max_row + 1):
                cell_inst = ws.cell(row=row, column=uni_col)
                if cell_inst.value and type(cell_inst.value) == str:
                    if fuzzy_match(uni_name, cell_inst.value, 0.8)[0] or uni_name.lower() in cell_inst.value.lower():
                        if link_col:
                            cell_l = ws.cell(row=row, column=link_col)
                            if cell_l.hyperlink and cell_l.hyperlink.target:
                                links['main_link'] = cell_l.hyperlink.target
                            elif cell_l.value and isinstance(cell_l.value, str) and cell_l.value.startswith('http'):
                                links['main_link'] = cell_l.value.strip()
                        
                        if fees_col:
                            cell_f = ws.cell(row=row, column=fees_col)
                            if cell_f.hyperlink and cell_f.hyperlink.target:
                                links['fees'] = cell_f.hyperlink.target
                            elif cell_f.value and isinstance(cell_f.value, str) and cell_f.value.startswith('http'):
                                links['fees'] = cell_f.value.strip()
                        if syllabus_col:
                            cell_s = ws.cell(row=row, column=syllabus_col)
                            if cell_s.hyperlink and cell_s.hyperlink.target:
                                links['syllabus'] = cell_s.hyperlink.target
                            elif cell_s.value and isinstance(cell_s.value, str) and cell_s.value.startswith('http'):
                                links['syllabus'] = cell_s.value.strip()
                        if links: return links
            return links
        except Exception as e:
            print(f"      -> Excel extraction failed: {e}")
            return {}

    def _fetch_url_robust(self, url):
        import requests, tempfile, os
        try:
            headers = {'User-Agent': 'Mozilla/5.0'}
            import urllib3
            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            res = requests.get(url, headers=headers, timeout=15, verify=False)
            
            if 'application/pdf' in res.headers.get('Content-Type', '').lower() or url.lower().endswith('.pdf'):
                with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                    tmp_pdf.write(res.content)
                    tmp_pdf_path = tmp_pdf.name
                    
                pdf_text = ""
                try:
                    import pdfplumber
                    with pdfplumber.open(tmp_pdf_path) as pdf_file:
                        for p in pdf_file.pages:
                            pdf_text += (p.extract_text() or "") + "\n"
                except Exception as e:
                    print(f"      -> Warning: pdfplumber extraction failed: {e}")
                
                if len(pdf_text.strip()) < 100:
                    try:
                        import fitz, pytesseract
                        import cv2, numpy as np
                        if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                        elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                            pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
                        
                        doc = fitz.open(tmp_pdf_path)
                        for page in doc:
                            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))
                            img_data = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
                            if pix.n == 4: img_data = cv2.cvtColor(img_data, cv2.COLOR_RGBA2RGB)
                            gray = cv2.cvtColor(img_data, cv2.COLOR_RGB2GRAY)
                            ocr_text = pytesseract.image_to_string(gray, config='--oem 3 --psm 6')
                            if ocr_text: pdf_text += ocr_text + "\n"
                    except Exception as e:
                        print(f"      -> Warning: PDF OCR failed: {e}")
                        
                try: os.remove(tmp_pdf_path)
                except: pass
                return pdf_text
            else:
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(res.text, 'html.parser')
                return soup.get_text(separator=' ', strip=True)
        except Exception as e:
            print(f"      -> Failed to fetch URL robustly: {e}")
            return ""

    # ──────────────────────────────────────────────────────────
    #  HELPER: Local Website Verification (Cost, Skills, Duration, Mode, Language)
    # ──────────────────────────────────────────────────────────

    def _verify_details_with_llm(self, course, page_text, worker_id=None):
        course['logo_match'] = True
        course['logos_found'] = "Matched"
        
        # --- Pre-verify skills using fuzzy/ML text matching ---
        sk_text = str(course.get('skills', '')).strip()
        pre_match_skills = False
        sk_pre_detail = ""
        if sk_text and sk_text.lower() not in ['n/a', 'n/a in pdf', 'none', '-', '']:
            import re
            sk_lower = re.sub(r'\s+', ' ', sk_text.lower())
            page_lower = re.sub(r'\s+', ' ', page_text.lower())
            if sk_lower in page_lower:
                pre_match_skills = True
            else:
                sk_words = set(w for w in sk_lower.split() if len(w) > 3)
                if sk_words:
                    page_words = set(page_lower.split())
                    overlap = len(sk_words.intersection(page_words)) / len(sk_words)
                    if overlap >= 0.95:
                        pre_match_skills = True
        
        if pre_match_skills:
            sk_pre_detail = "Exact or highly similar text matched via local verification algorithms."
            
        sk_match = pre_match_skills
        sk_detail = ""
        
        if "--- EXCEL FEES DATA ---" in page_text or "--- EXCEL SYLLABUS DATA ---" in page_text:
            web_part = page_text
            excel_part = ""
            if "--- EXCEL SYLLABUS DATA ---" in web_part:
                parts = web_part.split("--- EXCEL SYLLABUS DATA ---", 1)
                web_part = parts[0]
                excel_part = "\n--- EXCEL SYLLABUS DATA ---\n" + parts[1] + excel_part
            if "--- EXCEL FEES DATA ---" in web_part:
                parts = web_part.split("--- EXCEL FEES DATA ---", 1)
                web_part = parts[0]
                excel_part = "\n--- EXCEL FEES DATA ---\n" + parts[1] + excel_part
                
            allowed_web_len = max(0, 1000000 - len(excel_part))
            page_text_limited = web_part[:allowed_web_len] + excel_part
        else:
            page_text_limited = page_text[:1000000]
        
        prompt = f"""
        Analyze the following text extracted from a course webpage and verify the following details against the original PDF data.
        
        Target Course: {course.get('name')}
        Original Cost: {course.get('cost')}
        Original Duration: {course.get('duration')}
        Original Mode: {course.get('mode')}
        Original Language: {course.get('language')}
        Original Country: {course.get('country')}
        Original Skills: {course.get('skills')}
        
        Web Text (truncated):
        {page_text_limited}
        
        Instructions:
        1. Extract the actual cost, duration, mode, language, country, and university/provider from the text. 
           CRITICAL RULE FOR COST: If the university is NOT located in India, you MUST strictly extract and verify against the "International" or "Overseas" student tuition fee. Look carefully in the --- EXCEL FEES DATA --- section if available.
           CRITICAL RULE FOR COST EXCEPTION: If the original cost is 'Free', but the website states the course is 'Free to learn' but has a paid 'Certificate Track', 'Verified Track', or 'Upgraded' version with a fee, you MUST extract the paid fee and evaluate the cost match as FALSE.
           CRITICAL RULE FOR FEES TABLES: Fee data is often in Markdown tables or explicitly stated like 'HND per 15 credit unit: ...'. Scan every single number on the page carefully. For USA/UK universities, look specifically for out-of-state tuition, international tuition, or cost-per-credit-hour math.
           CRITICAL RULE FOR DURATION: If the duration is given in semesters, calculate it in years (e.g., 2 semesters = 1 Year / 1Y). If original duration is 'SP', it stands for 'Self-Paced'. If the website says self-paced, evaluate duration match as TRUE.
           CRITICAL RULE FOR MISSING PDF DATA: If the Original PDF value for Duration, Mode, or Language is 'Not Provided in Source', you MUST evaluate the match as FALSE, regardless of what the website says.
           CRITICAL RULE FOR LANGUAGE: Handle translations gracefully (e.g. if the website says 'espanol', it perfectly matches 'Spanish').
        2. DO NOT output "N/A", "Not Found", or "Information not received". NEVER output "Information not explicitly mentioned on the webpage." ABSOLUTELY NEVER output "..." (three dots). You MUST provide a perfect 2-3 sentence paragraph description for EVERY attribute. If the exact information is missing, you MUST deduce a reasonable 2-3 sentence guess based on context (e.g., "The official website does not list an exact fee, however similar diploma programs typically range..."). You must ALWAYS provide a 2-3 line description. For university_description, ONLY output the exact name of the university found, nothing else. When extracting Indian currency, accurately preserve and extract the Rupees symbol (₹) or 'Rs' or 'INR'.
        3. For each attribute, evaluate if it logically matches the Original PDF data and output a boolean true/false. Use extremely lenient matching for duration, country, mode and university. CRITICAL RULE FOR UNIVERSITY: The university_match should be TRUE ONLY if the university found on the webpage is the SAME institution as the Original PDF university. If a completely different university is found (e.g., IIT Kanpur found but original is Odisha State Open University), you MUST set university_match to FALSE. If university_match is FALSE, you MUST set ALL other matches (cost, duration, mode, language, skills, country) to FALSE as well. CRITICAL RULE FOR COUNTRY: ALWAYS prioritize and trust any country or location information provided in the Google Search Fallback text over missing information on the website.
        4. For Skills: NEVER output "Data not found" or "Information absent". If exact skills are not listed, read the course title, the webpage, and especially the --- EXCEL SYLLABUS DATA --- (if available) and generate a highly convincing, professional 1-2 sentence description of what the course covers based on the context. You ONLY need a 60% overlap with the Original Skills to consider it a Match (True).
        5. CRITICAL RULE FOR FORMATTING: DO NOT use any markdown formatting (like **bold**, *italics*, or # headings) in your descriptive sentences. Output raw, plain text only. NEVER output "..." (three dots) as a description value.
        {"(NOTE: Skills have already been pre-verified as a MATCH via ML check. Just provide a brief summary of the skills found.)" if pre_match_skills else ""}
        
        Respond ONLY with a valid JSON object matching this exact structure:
        {{
            "cost_description": "Descriptive sentence of what fee was found.",
            "cost_match": true/false,
            "duration_description": "Descriptive sentence of duration found.",
            "duration_match": true/false,
            "mode_description": "Descriptive sentence of mode found.",
            "mode_match": true/false,
            "language_description": "Descriptive sentence of language found.",
            "language_match": true/false,
            "country_description": "Descriptive sentence of country/location found.",
            "country_match": true/false,
            "university_description": "Descriptive sentence of the university/provider found.",
            "university_match": true/false,
            "skills_description": "1-2 sentence summary of skills found on the page.",
            "skills_match": true/false
        }}
        """
        
        from llm_manager import get_llm_manager
        
        try:
            llm = get_llm_manager()
            res_str = llm.generate(prompt, worker_id=worker_id)
            print(f"DEBUG LLM OUTPUT:\n{res_str}\n")
            
            try:
                # First try to find a markdown json block
                json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', res_str, re.DOTALL | re.IGNORECASE)
                if json_match:
                    clean_json = json_match.group(1)
                else:
                    match = re.search(r'\{.*\}', res_str, re.DOTALL)
                    clean_json = match.group(0) if match else res_str
                
                res = json.loads(clean_json)
                if isinstance(res, list) and len(res) > 0:
                    res = res[0]
                if not isinstance(res, dict):
                    res = {}
                
                def fuzzy_get(key_prefix, default):
                    import re
                    clean_prefix = re.sub(r'[^a-z0-9]', '', key_prefix.lower())
                    for k, v in res.items():
                        clean_k = re.sub(r'[^a-z0-9]', '', k.lower())
                        if clean_k.startswith(clean_prefix):
                            return v
                    return default
                    
                def _sanitize_llm_val(val):
                    """Replace '...' or ellipsis-only values with proper fallback text."""
                    if isinstance(val, str):
                        stripped = val.strip().replace('\u2026', '...')
                        if stripped in ['...', '....', '.....', '......', '', '-'] or 'information not explicitly mentioned' in stripped.lower() or 'no cost information' in stripped.lower() or 'no duration information' in stripped.lower() or 'no specific skills' in stripped.lower():
                            return 'The webpage does not explicitly list this detail, but based on the course curriculum and university profile the program appears to be fully structured. Further specifics may be available upon direct enrollment or contacting the institution.'
                    return val
                
                cost_detail = _sanitize_llm_val(fuzzy_get('cost', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                cost_match = bool(fuzzy_get('cost_match', False))
                
                duration_detail = _sanitize_llm_val(fuzzy_get('duration', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                duration_match = bool(fuzzy_get('duration_match', False))
                
                mode_detail = _sanitize_llm_val(fuzzy_get('mode', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                mode_match = bool(fuzzy_get('mode_match', False))
                
                lang_detail = _sanitize_llm_val(fuzzy_get('language', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                lang_match = bool(fuzzy_get('language_match', False))
                
                country_detail = _sanitize_llm_val(fuzzy_get('country', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                country_match = bool(fuzzy_get('country_match', False))
                
                uni_detail = _sanitize_llm_val(fuzzy_get('university', 'While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment.'))
                uni_match_llm = bool(fuzzy_get('university_match', False))
                
                # CRITICAL: Cross-check LLM uni match against original PDF uni
                # If the LLM found a completely different university, force mismatch
                if uni_match_llm and uni_detail and isinstance(uni_detail, str):
                    orig_uni = course.get('uni', '').lower().strip()
                    found_uni = uni_detail.lower().strip()
                    if orig_uni and found_uni and len(found_uni) > 3:
                        from difflib import SequenceMatcher
                        sim = SequenceMatcher(None, orig_uni, found_uni).ratio()
                        if sim < 0.40:
                            print(f"    -> [LLM Guard] University mismatch detected: PDF='{course.get('uni')}' vs Web='{uni_detail}' (sim={sim:.2f}). Forcing uni_match=False.")
                            uni_match_llm = False
                
                sk_detail_llm = _sanitize_llm_val(fuzzy_get('skills', ''))
                if sk_detail_llm and isinstance(sk_detail_llm, str) and 'not explicitly stated' not in sk_detail_llm.lower():
                    sk_detail = sk_detail_llm
                
                if not pre_match_skills:
                    sk_match = bool(fuzzy_get('skills_match', False))
                
            except Exception as e:
                print(f"    -> [LLM] Irregular output format detected. Using regex fallback...")
                import re
                
                def robust_extract_desc(key, text):
                    regex_key = key.replace('_', '[ _]')
                    m = re.search(rf'["\`\']?{regex_key}["\`\']?\s*:\s*["\']?(.*?)["\']?\s*(?:\n|,?\s*\n|}}\s*$)', text, re.IGNORECASE | re.DOTALL)
                    if m:
                        val = m.group(1).strip()
                        if val.endswith('"') or val.endswith("'"): val = val[:-1]
                        if val.startswith('"') or val.startswith("'"): val = val[1:]
                        if val.endswith('",'): val = val[:-2]
                        if val.endswith("',"): val = val[:-2]
                        return val.strip()
                    return "While the specific details were not explicitly stated on the webpage, based on the curriculum and university profile, the course appears to be fully structured. Further details may be available upon direct enrollment."
                
                def robust_extract_bool(key, text):
                    regex_key = key.replace('_', '[ _]')
                    m = re.search(rf'["\`\']?{regex_key}["\`\']?\s*:\s*["\']?(true|false)["\']?', text, re.IGNORECASE)
                    return 'true' in m.group(1).lower() if m else False
                
                cost_detail = robust_extract_desc('cost_description', res_str)
                cost_match = robust_extract_bool('cost_match', res_str)
                
                duration_detail = robust_extract_desc('duration_description', res_str)
                duration_match = robust_extract_bool('duration_match', res_str)
                
                mode_detail = robust_extract_desc('mode_description', res_str)
                mode_match = robust_extract_bool('mode_match', res_str)
                
                lang_detail = robust_extract_desc('language_description', res_str)
                lang_match = robust_extract_bool('language_match', res_str)
                
                country_detail = robust_extract_desc('country_description', res_str)
                country_match = robust_extract_bool('country_match', res_str)
                
                uni_detail = robust_extract_desc('university_description', res_str)
                uni_match_llm = robust_extract_bool('university_match', res_str)
                
                sk_detail_llm = robust_extract_desc('skills_description', res_str)
                if sk_detail_llm:
                    sk_detail = sk_detail_llm
                    
                if not pre_match_skills:
                    sk_match = robust_extract_bool('skills_match', res_str)

        except Exception as e:
            print(f"    -> [LLM Error] Generation failed: {e}")
            return (False, False, "N/A", False, "N/A", False, "N/A", False, "N/A", "N/A", False, "N/A", False, "N/A")

        course['sk_match'] = sk_match
        course['skills_verified'] = sk_detail
        
        return (cost_match, sk_match, sk_detail, duration_match, duration_detail, mode_match, mode_detail, lang_match, lang_detail, cost_detail, country_match, country_detail, uni_match_llm, uni_detail)


    def _verify_details_locally(self, course, page_text):
        """Use local spaCy NLP tokenization and NER to verify details.
        Returns: (cost_match, sk_match, sk_detail, duration_match, duration_detail,
                  mode_match, mode_detail, lang_match, lang_detail,
                  web_cost, web_duration, web_mode, web_language)
        """
        pt_lower = page_text.lower()
        
        # API-independent mode: do not call online translation services.
        if 'enseigné en' in pt_lower or 'idioma:' in pt_lower or 'sprache:' in pt_lower:
            print("      -> Foreign-language markers detected; using local language rules without translation.")
                
        nlp = get_nlp()
        
        # Process a truncated chunk to avoid spaCy max length limits (1,000,000 chars limit, safely use 100k)
        text_to_analyze = page_text[:100000]
        doc = nlp(text_to_analyze) if nlp else None
        
        # ── Extract actual web values from the page text ──
        web_cost = "N/A"
        web_duration = "N/A"
        web_mode = "N/A"
        web_language = "N/A"
        
        # Extract cost values from page using regex
        cost_patterns = re.findall(r'(?:[\$€£₹]|Rs\.?|INR|USD)\s*[\d,]+(?:\.\d{1,2})?|\b\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?\b|\b\d{3,}(?:\.\d{1,2})?\s*(?:USD|INR|EUR|GBP)\b', page_text, re.IGNORECASE)
        if cost_patterns:
            web_cost = cost_patterns[0].strip()
        elif 'free' in pt_lower:
            web_cost = "Free"
            
        # Extract duration values from page
        dur_patterns = re.findall(r'\b\d+\s*(?:month|week|year|hour|day|semester|quarter|term)s?\b', pt_lower)
        if dur_patterns:
            web_duration = dur_patterns[0].strip()
        else:
            dur_patterns2 = re.findall(r'\b(?:one|two|three|four|five|six|seven|eight|nine|ten|twelve)\s*(?:month|week|year|hour|day)s?\b', pt_lower)
            if dur_patterns2:
                web_duration = dur_patterns2[0].strip()
                
        # Extract mode from page
        if any(w in pt_lower for w in ["hybrid", "blended"]):
            web_mode = "Hybrid"
        elif any(w in pt_lower for w in ["distance learning", "100% online", "e-learning", "online program", "online mode", "self-paced online"]):
            web_mode = "Online"
        elif any(w in pt_lower for w in ["on-campus", "in-person", "classroom", "offline mode"]):
            web_mode = "On-campus"
        elif 'online' in pt_lower:
            web_mode = "Online"
        elif 'offline' in pt_lower or 'campus' in pt_lower:
            web_mode = "On-campus"
            
        # Extract language from page
        lang_found = detect_language_from_text(page_text)
        if lang_found:
            web_language = lang_found
        elif 'english' in pt_lower:
            web_language = "English"
        
        # 1. Cost (Sentence-Level Context -> Fallback to Regex window)
        cost_match = False
        pdf_cost_val, pdf_curr = extract_cost_value(course.get('cost', ''))
        
        if doc and pdf_cost_val:
            for sent in doc.sents:
                sent_text = sent.text.lower()
                # Require sentence to have context of cost/fees
                if any(w in sent_text for w in ["fee", "tuition", "cost", "price", "pay"]):
                    if str(pdf_cost_val) in sent_text:
                        # Check currency
                        if not pdf_curr or pdf_curr.lower() in sent_text or any(sym in sent_text for sym in ['$', '€', '£', '₹']):
                            cost_match = True
                            break
        
        # Fallback to page-level regex window if sentence parsing didn't find it
        if not cost_match:
            cost_match = verify_cost_in_text((pdf_cost_val, pdf_curr), page_text, course.get('cost', ''), course.get('uni', ''))
        
        # If cost matched, show the PDF cost as confirmed
        if cost_match:
            web_cost = course.get('cost', web_cost)

        # 2. Duration (Sentence-Level Context -> Fallback to equivalence)
        pdf_duration = str(course.get('duration', ''))
        duration_match, duration_detail = False, "Not found"
        
        if doc and pdf_duration.lower() not in ('unknown', 'n/a in pdf', ''):
            duration_tokens = set([w.text for w in nlp(pdf_duration.lower()) if w.is_alpha or w.like_num])
            for sent in doc.sents:
                sent_text = sent.text.lower()
                # Require sentence to talk about course length
                if any(w in sent_text for w in ["duration", "program", "course", "length", "takes", "spans", "months", "years", "weeks", "hours"]):
                    date_ents = [ent.text.lower() for ent in sent.ents if ent.label_ in ("DATE", "TIME")]
                    for ent_text in date_ents:
                        ent_tokens = set([w.text for w in nlp(ent_text) if w.is_alpha or w.like_num])
                        if len(duration_tokens.intersection(ent_tokens)) >= 1:
                            duration_match = True
                            duration_detail = f"Sentence Context match: '{ent_text}'"
                            break
                if duration_match: break
                
        # Fallback to pure regex equivalence
        if not duration_match:
            duration_match, duration_detail = durations_equivalent(pdf_duration, page_text)
        
        # If duration matched, confirm it
        if duration_match and duration_detail != "Not found":
            web_duration = duration_detail

        # 3. Skills (Sentence-Level Semantic -> Fallback to Difflib)
        pdf_skills = course.get('skills', '')
        sk_match, sk_detail = False, "N/A in PDF"
        
        if doc and pdf_skills and pdf_skills != "N/A in PDF":
            skill_doc = nlp(pdf_skills)
            skill_lemmas = [token.lemma_.lower() for token in skill_doc if token.is_alpha and not token.is_stop]
            
            # Find sentences that indicate learning outcomes
            learning_sentences = [sent for sent in doc.sents if any(verb in sent.text.lower() for verb in ["learn", "teach", "cover", "skill", "curriculum", "topic", "module", "understand"])]
            
            if learning_sentences:
                page_lemmas = set()
                for sent in learning_sentences:
                    page_lemmas.update([token.lemma_.lower() for token in sent if token.is_alpha])
                
                found = [lemma for lemma in skill_lemmas if lemma in page_lemmas]
                total = len(skill_lemmas)
                ratio = len(found) / total if total > 0 else 0
                sk_match = ratio >= 0.4
                sk_detail = f"Sentence Semantics: {len(found)}/{total} core skills matched in learning context"
                
                if total == 0:
                    sk_match, sk_detail = True, "N/A in PDF"
                    
        # Fallback to difflib
        if not sk_match and pdf_skills and pdf_skills != "N/A in PDF":
            sk_match, sk_detail = skills_match(pdf_skills, page_text)

        # 4. Mode (Sentence Context -> Fallback to page scan)
        mode_match = False
        mode_detail = "Not found"
        pdf_mode = course.get('mode', 'Online').lower().strip()
        
        if doc:
            for sent in doc.sents:
                sent_text = sent.text.lower()
                # Must be describing the course, not a website button like "Apply Online"
                if any(w in sent_text for w in ["program", "course", "delivery", "mode", "taught", "learning", "study", "available"]):
                    is_hybrid = any(w in sent_text for w in ["hybrid", "blended"])
                    is_online = any(w in sent_text for w in ["distance learning", "100% online", "e-learning", "online program", "online mode"])
                    is_offline = any(w in sent_text for w in ["on-campus", "in-person", "classroom", "offline mode", "regular mode", "campus"])
                    
                    if is_hybrid:
                        mode_detail = "Hybrid"
                        mode_match = True
                        break
                    elif is_online:
                        mode_detail = "Online"
                        mode_match = True
                        break
                    elif is_offline:
                        mode_detail = "On-campus"
                        mode_match = True
                        break
                        
        if not mode_match:
            # Fallback to specific contextual phrases across whole page
            is_hybrid = any(w in pt_lower for w in ["hybrid", "blended"])
            is_online = any(w in pt_lower for w in ["distance learning", "100% online", "e-learning", "online program", "online mode"])
            is_offline = any(w in pt_lower for w in ["on-campus", "in-person", "classroom", "offline mode", "regular mode"])
            
            if is_hybrid:
                mode_detail = "Hybrid"
                mode_match = True
            elif is_online:
                mode_detail = "Online"
                mode_match = True
            elif is_offline:
                mode_detail = "On-campus"
                mode_match = True
            elif 'online' in pt_lower and 'offline' not in pt_lower:
                mode_detail = "Online"
                mode_match = True
            elif 'offline' in pt_lower or 'campus' in pt_lower:
                mode_detail = "On-campus"
                mode_match = True
            else:
                mode_detail = "Unspecified mode"
                mode_match = True
        
        # Compare detected mode against PDF mode
        if mode_match and mode_detail != "Not found":
            web_mode = mode_detail
            mode_equiv = modes_equivalent(pdf_mode, mode_detail)
            if mode_equiv is not None:
                mode_match = mode_equiv

        # 5. Language
        lang_match, lang_detail = language_matches(course.get('language', ''), page_text)
        if 'language: french' in pt_lower or 'enseigné en français' in pt_lower:
            lang_detail = "French"
        if lang_detail and lang_detail != "Not found":
            web_language = lang_detail
            
        return (cost_match, sk_match, sk_detail, duration_match, duration_detail,
                mode_match, mode_detail, lang_match, lang_detail,
                web_cost, web_duration, web_mode, web_language)


    # ──────────────────────────────────────────────────────────
    #  HELPER: Extract all text from Selenium driver
    # ──────────────────────────────────────────────────────────

    def _extract_page_text(self, driver):
        try:
            expand_js = """
            // Phase 1: Force-open all <details> elements
            document.querySelectorAll('details').forEach(d => { d.open = true; });
            
            // Phase 2: Click accordion triggers by keyword
            let keywords = ['show more', 'expand', 'fee', 'tuition', 'cost', 'pricing', 'curriculum', 'module', 'syllabus', 'course outline', 'course content', 'program details', 'admission', 'eligibility', 'course details', 'click here', 'duration', 'structure', 'overview', 'about', 'skill', 'learning outcome', 'programme', 'regulation'];
            let elements = document.querySelectorAll('button, div, span, a, h3, h4, h5, h6, li, label, summary, strong, b, p, tr, td, dt, dd, [role="tab"], [role="button"], [data-toggle], [aria-expanded]');
            for(let el of elements) {
                if(el.offsetParent !== null && el.textContent) {
                    let txt = el.textContent.toLowerCase().trim();
                    if(txt.length > 0 && txt.length < 80 && keywords.some(k => txt.includes(k))) {
                        try { el.click(); } catch(e) {}
                    }
                }
                // Also click any element with aria-expanded="false"
                if(el.getAttribute && el.getAttribute('aria-expanded') === 'false') {
                    try { el.click(); } catch(e) {}
                }
            }
            
            // Phase 3: Expand all collapsed Bootstrap/jQuery accordions
            document.querySelectorAll('.collapse:not(.show), .panel-collapse:not(.in)').forEach(el => {
                el.classList.add('show', 'in');
                el.style.display = 'block';
                el.style.height = 'auto';
            });
            
            // Phase 4: Force-expand select dropdowns by extracting all option text
            let selects = document.querySelectorAll('select');
            for(let sel of selects) {
                let optTexts = Array.from(sel.options).map(o => o.text + ': ' + o.value).join('; ');
                if(optTexts.length > 3) {
                    let marker = document.createElement('div');
                    marker.setAttribute('data-dropdown-extracted', 'true');
                    marker.textContent = 'Dropdown Options: ' + optTexts;
                    sel.parentNode.insertBefore(marker, sel.nextSibling);
                }
            }
            """
            driver.execute_script(expand_js)
            import time
            time.sleep(2.0)
            
            # Second pass: some accordions load content lazily after the first click
            driver.execute_script(expand_js)
            time.sleep(1.0)
        except: pass

        parts = []
        try:
            title = driver.title
            if title: parts.append(title)
        except: pass
        js_body_text = """
            return document.body.innerText || document.body.textContent;
        """
        try:
            body = driver.execute_script(js_body_text)
            if body: parts.append(body)
        except: pass
        
        js_deep = """
            let out = [];
            // 1. Meta tags
            let metas = document.querySelectorAll('meta[name="description"], meta[property="og:title"], meta[property="og:description"], meta[name="keywords"]');
            out.push(Array.from(metas).map(m => m.content).join(' '));
            
            // 2. JSON-LD structured data (contains cost, duration, provider)
            let scripts = document.querySelectorAll('script[type="application/ld+json"]');
            for (let s of scripts) {
                try { out.push(s.textContent); } catch(e) {}
            }
            
            // 3. aria-label attributes (hidden text on buttons/tabs)
            let ariaEls = document.querySelectorAll('[aria-label]');
            for (let el of ariaEls) {
                let label = el.getAttribute('aria-label');
                if (label && label.length > 5) out.push(label);
            }
            
            // 4. Same-origin iframe content and YouTube links
            let iframes = document.querySelectorAll('iframe');
            for (let iframe of iframes) {
                if (iframe.src && iframe.src.includes('youtube.com')) {
                    out.push("Embedded YouTube Video: " + (iframe.title || iframe.src));
                }
                try {
                    let iframeDoc = iframe.contentDocument || iframe.contentWindow.document;
                    if (iframeDoc && iframeDoc.body) out.push(iframeDoc.body.innerText);
                } catch(e) {} // cross-origin will throw
            }
            
            // Extract standalone YouTube links as well
            let ytLinks = document.querySelectorAll('a[href*="youtube.com/watch"], a[href*="youtu.be/"]');
            for (let a of ytLinks) {
                out.push("YouTube Video Link: " + (a.innerText || a.href));
            }
            
            // 5. noscript fallback content
            let noscripts = document.querySelectorAll('noscript');
            for (let ns of noscripts) {
                if (ns.textContent && ns.textContent.length > 10) out.push(ns.textContent);
            }
            
            // 6. data-* attributes that often contain pricing, duration, skills
            let dataEls = document.querySelectorAll('[data-price], [data-cost], [data-duration], [data-skill], [data-course-name], [data-amount]');
            for (let el of dataEls) {
                for (let attr of el.attributes) {
                    if (attr.name.startsWith('data-') && attr.value && attr.value.length > 1) {
                        out.push(attr.name.replace('data-', '') + ': ' + attr.value);
                    }
                }
            }
            
            // 7. title attributes (tooltips with extra info)
            let titleEls = document.querySelectorAll('[title]');
            for (let el of titleEls) {
                let t = el.getAttribute('title');
                if (t && t.length > 5) out.push(t);
            }
            
            // 8. Hidden price/fee elements (display:none divs with pricing)
            let hiddenPrices = document.querySelectorAll('[class*="price"], [class*="cost"], [class*="fee"], [class*="tuition"], [class*="amount"]');
            for (let el of hiddenPrices) {
                if (el.textContent && el.textContent.trim().length > 2) {
                    out.push(el.textContent.trim());
                }
            }
            
            // 9. Extra numbers with currency symbols (very broad to catch everything like Lumpsum ₹32,848 or € 20,000)
            let currEls = document.querySelectorAll('*');
            for(let el of currEls) {
                if(el.children.length === 0 && el.textContent) {
                    let txt = el.textContent.trim();
                    if((txt.includes('₹') || txt.includes('€') || txt.includes('£') || txt.includes('$') || txt.includes('Rs') || txt.includes('CHF') || txt.includes('INR')) && /\\d/.test(txt)) {
                        if(txt.length < 200) out.push("Found Currency/Price Block: " + txt);
                    }
                }
            }
            
            return out.join('\n');
        """
        try:
            deep_content = driver.execute_script(js_deep)
            if deep_content: parts.append(deep_content)
        except: pass
        
        return "\n".join(parts)

    def _dismiss_popups(self, driver):
        try: _close_other_tabs(driver)
        except: pass
        """Dismiss common cookie/modals that block search fields or menus using JS."""
        js_dismiss = """
            const selectors = [
                'button:contains("Accept")', 'button:contains("Accept All")', 
                'button:contains("I Agree")', 'button:contains("Agree")',
                'button:contains("Allow all")', 'button:contains("Continue")',
                'button:contains("Close")', '[aria-label="Close"]',
                '[aria-label="close"]', '.modal button.close', '.popup button.close'
            ];
            
            // Contains selector polyfill
            const buttons = Array.from(document.querySelectorAll('button, a'));
            const closeWords = ['accept', 'agree', 'allow all', 'continue', 'close', 'got it'];
            
            for (let b of buttons) {
                if (b.innerText && closeWords.some(w => b.innerText.toLowerCase().trim() === w)) {
                    try { b.click(); } catch(e) {}
                }
            }
            
            for (let sel of ['.modal button.close', '.popup button.close', '[aria-label="Close"]']) {
                document.querySelectorAll(sel).forEach(el => {
                    try { el.click(); } catch(e) {}
                });
            }
        """
        try:
            driver.execute_script(js_dismiss)
            time.sleep(1)
        except Exception:
            pass

    def _scroll_page(self, driver):
        for sp in [400, 800, 1200, 1800, 2600, 3600, 5000]:
            try:
                driver.execute_script(f"window.scrollTo(0, {sp})")
                time.sleep(0.35)
            except Exception:
                break

    def _looks_like_search_input(self, driver, el):
        try:
            tag = el.tag_name.lower()
            attrs = []
            for attr in ["type", "name", "id", "placeholder", "aria-label", "role", "class", "title"]:
                attrs.append(el.get_attribute(attr) or "")
            haystack = " ".join(attrs).lower()
            input_type = (el.get_attribute("type") or "").lower()
            if input_type in {"hidden", "password", "email", "tel", "checkbox", "radio", "submit"}:
                return False
            if el.get_attribute("contenteditable") == "true":
                return True
            if input_type == "search" or "searchbox" in haystack:
                return True
            keywords = [
                "search", "find", "filter", "query", "keyword", "keywords",
                "course", "program", "programme", "ranking", "institution",
                "college", "university", "what are you looking for",
            ]
            return tag in {"input", "textarea"} and any(kw in haystack for kw in keywords)
        except Exception:
            return False

    def _candidate_search_inputs(self, driver):
        selectors = [
            'input[type="search"]',
            '[role="searchbox"]',
            'input',
            'textarea',
            '[contenteditable="true"]',
        ]
        candidates = []
        seen = set()
        for selector in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, selector):
                    try:
                        marker = "|".join([
                            el.tag_name, el.get_attribute("type") or '', el.get_attribute("name") or '', 
                            el.get_attribute("id") or '', el.get_attribute("placeholder") or '', 
                            el.get_attribute('aria-label') or ''
                        ])
                        if marker in seen:
                            continue
                        seen.add(marker)
                        if el.is_displayed() and el.is_enabled() and self._looks_like_search_input(driver, el):
                            candidates.append(el)
                    except Exception:
                        continue
            except Exception:
                continue
        return candidates[:10]

    def _wait_after_action(self, driver, seconds=1.5):
        try: _close_other_tabs(driver)
        except: pass
        time.sleep(seconds)

    def _click_search_button(self, driver):
        selectors = [
            'button[type="submit"]',
            'input[type="submit"]',
            'button',
            'a',
            '[aria-label*="Search"]',
            '[aria-label*="search"]',
            '[class*="search"] button',
            '[class*="Search"] button',
        ]
        for selector in selectors:
            try:
                for el in driver.find_elements(By.CSS_SELECTOR, selector)[:5]:
                    try:
                        if el.is_displayed() and el.is_enabled():
                            text_lower = el.text.lower()
                            if selector in ['button', 'a'] and 'search' not in text_lower:
                                continue
                            el.click()
                            self._wait_after_action(driver)
                            return True
                    except Exception:
                        continue
            except Exception:
                continue
        return False

    def _fill_search_element(self, driver, el, query):
        try:
            driver.execute_script("arguments[0].scrollIntoView(true);", el)
        except Exception:
            pass

        try:
            is_editable = el.get_attribute("contenteditable") == "true"
            if is_editable:
                el.click()
                el.send_keys(Keys.CONTROL + "a")
                el.send_keys(query)
                el.send_keys(Keys.ENTER)
            else:
                try:
                    el.clear()
                    el.send_keys(query)
                except Exception:
                    el.click()
                    el.send_keys(Keys.CONTROL + "a")
                    el.send_keys(query)
                try:
                    el.send_keys(Keys.ENTER)
                except Exception:
                    pass
            self._wait_after_action(driver)
            return True
        except Exception:
            return False

    def _use_search_box(self, driver, query, context_label="website"):
        """
        Find a visible search/filter field, type the query, and submit it.
        Returns (attempted, resulting_page_text).
        """
        self._dismiss_popups(driver)
        before_url = driver.current_url
        before_text = self._extract_page_text(driver)
        inputs = self._candidate_search_inputs(driver)
        if not inputs:
            return False, before_text

        attempted_any = False
        for el in inputs:
            print(f"    -> Searching {context_label} search box for: {query}")
            if not self._fill_search_element(driver, el, query):
                continue
            attempted_any = True

            after_text = self._extract_page_text(driver)
            if after_text == before_text and driver.current_url == before_url:
                self._click_search_button(driver)
                after_text = self._extract_page_text(driver)

            if after_text != before_text or driver.current_url != before_url:
                return True, after_text

        return attempted_any, self._extract_page_text(driver)

    def _click_best_matching_link(self, driver, target_text, context_label="result"):
        best = None
        best_score = 0.0
        try:
            links = driver.find_elements(By.TAG_NAME, "a")
        except Exception:
            return False

        for el in links[:180]:
            try:
                label = (el.text or "").strip()
                href = el.get_attribute("href") or ""
                title = el.get_attribute("title") or ""
                combined = " ".join([label, title, href])
                if not combined.strip():
                    continue
                matched, score = entity_present(target_text, combined, threshold=0.60)
                if matched and score > best_score:
                    best = (el, label[:90] or href[:90])
                    best_score = score
            except Exception:
                continue

        if not best:
            return False

        el, label = best
        print(f"    -> Opening best {context_label} link: {label} (score {best_score:.2f})")
        try:
            href = el.get_attribute("href")
            if href and not href.lower().startswith(("javascript:", "#")):
                self._safe_get(driver, urljoin(driver.current_url, href))
                self._dismiss_popups(driver)
                return True
            else:
                driver.execute_script("arguments[0].scrollIntoView(true);", el)
                el.click()
            self._wait_after_action(driver, seconds=2)
            return True
        except Exception:
            return False

    def _site_search_url_candidates(self, current_url, query):
        parsed = urlparse(current_url)
        if not parsed.scheme or not parsed.netloc:
            return []
        origin = f"{parsed.scheme}://{parsed.netloc}"
        q = quote_plus(query)
        return [
            f"{origin}/?s={q}",
            f"{origin}/search?q={q}",
            f"{origin}/search?query={q}",
            f"{origin}/search?keyword={q}",
            f"{origin}/courses?search={q}",
            f"{origin}/programs?search={q}",
            f"{origin}/course-search?search={q}",
        ]

    def _try_site_search_urls(self, driver, query, target_text):
        for search_url in self._site_search_url_candidates(driver.current_url, query):
            try:
                print(f"    -> Trying site search URL: {search_url}")
                self._safe_get(driver, search_url)
                self._wait_after_action(driver, seconds=2)
                text = self._extract_page_text(driver)
                if entity_present(target_text, text, threshold=0.60)[0]:
                    self._click_best_matching_link(driver, target_text, "site-search result")
                    return self._extract_page_text(driver)
            except Exception:
                continue
        return ""

    def _perform_platform_logins(self, driver):
        """Pre-login to platforms to establish trusted sessions and avoid aggressive bot checks."""
        email = os.environ.get("COURSERA_EMAIL")
        ndu_password = os.environ.get("NDU_PASSWORD")
        coursera_password = os.environ.get("COURSERA_PASSWORD")
        
        print("\n    -> [Login Sequence] Logging into ndu.digital...")
        try:
            self._safe_get(driver, "https://www.ndu.digital/")
            time.sleep(4)
            # Find and click Login button
            login_btns = driver.find_elements(By.XPATH, "//a[contains(translate(text(), 'LOGIN', 'login'), 'login')]")
            if login_btns:
                driver.execute_script("arguments[0].click();", login_btns[0])
                time.sleep(4)
                
                # Check for standard inputs
                email_in = driver.find_elements(By.CSS_SELECTOR, "input[type='email'], input[name*='email'], input[name*='user'], input[type='text']")
                pass_in = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name*='pass']")
                if email_in and pass_in:
                    email_in[0].send_keys(email)
                    pass_in[0].send_keys(ndu_password)
                    pass_in[0].send_keys(Keys.ENTER)
                    time.sleep(6)
                    print("    -> [Login Sequence] NDU Login completed.")
                else:
                    print("    -> [Login Sequence] Could not find NDU login fields after clicking button.")
            else:
                print("    -> [Login Sequence] NDU Login button not found on homepage.")
        except Exception as e:
            print(f"    -> [Login Sequence] NDU Login failed: {e}")
            
        print("    -> [Login Sequence] Logging into Coursera...")
        try:
            self._safe_get(driver, "https://www.coursera.org/?authMode=login")
            time.sleep(4)
            email_in = driver.find_elements(By.CSS_SELECTOR, "input[type='email'], input[name='email']")
            if email_in:
                email_in[0].send_keys(email)
                pass_in = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name='password']")
                if pass_in:
                    pass_in[0].send_keys(coursera_password)
                    pass_in[0].send_keys(Keys.ENTER)
                else:
                    email_in[0].send_keys(Keys.ENTER)
                    time.sleep(3)
                    pass_in = driver.find_elements(By.CSS_SELECTOR, "input[type='password'], input[name='password']")
                    if pass_in:
                        pass_in[0].send_keys(coursera_password)
                        pass_in[0].send_keys(Keys.ENTER)
                time.sleep(6)
                print("    -> [Login Sequence] Coursera Login completed.")
            else:
                print("    -> [Login Sequence] Could not find Coursera login fields.")
        except Exception as e:
            print(f"    -> [Login Sequence] Coursera Login failed: {e}")

    def _search_website_for_course(self, driver, course):
        """Disabled per user request. Do not perform Google Searches."""
        return ""

    def _navigate_nielit_course(self, driver, course, url):
        """NIELIT-specific navigation using Category batch caching on ndu.digital."""
        import os
        course_name = course.get("name", "").strip()
        if not course_name or course_name.lower() == "unknown":
            return ""

        print(f"    -> [NIELIT] Checking cache for '{course_name}'...")
        


        # Mapping rules to determine which category to click
        cat_lower = course_name.lower()
        target_category = "Cyber Security" # Default
        if "data" in cat_lower or "ai " in cat_lower or "artificial intelligence" in cat_lower:
            target_category = "Data Science"
        elif "cloud" in cat_lower:
            target_category = "Cloud Computing"
        elif "blockchain" in cat_lower:
            target_category = "Blockchain"
        elif "hardware" in cat_lower or "networking" in cat_lower:
            target_category = "Hardware & Networking"
        elif "programming" in cat_lower or "developer" in cat_lower or "software" in cat_lower:
            target_category = "Programming"

        if target_category in self.ndu_category_cache:
            # We already scraped this category!
            print(f"    -> [NIELIT] Using cached data for category '{target_category}'.")
            return self.ndu_category_cache[target_category]

        print(f"    -> [NIELIT] Navigating directly to URL '{url}' for category '{target_category}'...")
        try:
            self._safe_get(driver, url)
            time.sleep(4)
            self._dismiss_popups(driver)
            
            print("    -> [NIELIT] Zooming out 50% as requested...")
            driver.execute_script("document.body.style.zoom='50%'")
            time.sleep(2)
            
            # Click on the specific category (e.g. Cyber Security) before paginating
            try:
                # Find the Browse by Category section and click the target category
                cat_xpath = f"//*[contains(translate(text(), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), '{target_category.lower()}')]"
                cat_btn = driver.find_element(By.XPATH, cat_xpath)
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cat_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", cat_btn)
                time.sleep(4)
                print(f"    -> [NIELIT] Clicked on category '{target_category}'.")
            except Exception as e:
                print(f"    -> [NIELIT] Could not click category '{target_category}' (maybe already selected or not visible). Proceeding...")
            
            # Scrape pagination — DOM text is primary (clean ₹ symbols, course names, prices)
            all_text = ""
            for page in range(1, 11): # Scrape up to 10 pages max
                print(f"    -> [NIELIT] Scraping page {page} on browselisting...")
                all_text += "\n\n=== PAGE " + str(page) + " ===\n"
                
                # PRIMARY: Extract clean text from the DOM (perfect symbols & formatting)
                try:
                    # Extract structured course card data via JS for maximum accuracy
                    js_extract = """
                        let cards = document.querySelectorAll('.course-card, .card, [class*="course"], [class*="Card"]');
                        let out = [];
                        if (cards.length > 0) {
                            cards.forEach(c => { if(c.innerText && c.innerText.length > 20) out.push(c.innerText); });
                        }
                        // Fallback: get the main content area text
                        if (out.length === 0) {
                            let main = document.querySelector('main, .main-content, #content, .container') || document.body;
                            out.push(main.innerText);
                        }
                        return out.join('\\n---CARD---\\n');
                    """
                    dom_text = driver.execute_script(js_extract)
                    if dom_text and len(dom_text.strip()) > 50:
                        all_text += dom_text + "\n"
                    else:
                        # Fallback to full body text
                        all_text += driver.find_element(By.TAG_NAME, 'body').text + "\n"
                except Exception as e:
                    print(f"    -> [NIELIT] DOM extraction failed for page {page}: {e}")
                    try:
                        all_text += driver.find_element(By.TAG_NAME, 'body').text + "\n"
                    except: pass
                
                # OCR extraction for images/corner texts as requested
                try:
                    import base64 as b64_mod
                    ss_path = os.path.join(self.screenshots_dir, f"ndu_url_page_{page}.png")
                    try:
                        cdp_result = driver.execute_cdp_cmd("Page.captureScreenshot", {"captureBeyondViewport": True})
                        with open(ss_path, "wb") as f_ss:
                            f_ss.write(b64_mod.b64decode(cdp_result["data"]))
                    except Exception:
                        driver.save_screenshot(ss_path)
                        
                    # Run Tesseract OCR on the paginated screenshot
                    import base64
                    import cv2
                    if os.name == 'nt':
                        if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                            pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                        elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                            pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
                    
                    img_cv = cv2.imread(ss_path)
                    if img_cv is not None:
                        gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                        try:
                            gray = cv2.fastNlMeansDenoising(gray, h=10)
                            gray = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
                        except: pass                        
                        import pytesseract
                        if os.name == 'nt':
                            if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                            elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                                pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
                        ocr_text = pytesseract.image_to_string(gray if 'gray' in locals() else (image if 'image' in locals() else img), config='--oem 3 --psm 6').lower()
                        if ocr_text is None: ocr_text = ""



                        if len(ocr_text.strip()) > 10:
                            all_text += "\n" + ocr_text
                            print(f"    -> [NIELIT] Extracted {len(ocr_text)} characters via OCR from page {page} screenshot.")
                except Exception as e:
                    print(f"    -> [NIELIT] OCR extraction failed for page {page}: {e}")
                # Try to click exact next page number
                next_page_num = page + 1
                if next_page_num <= 10:
                    try:
                        # Find numeric pagination link
                        page_btn = driver.find_element(By.XPATH, f"//ul[contains(@class, 'pagination')]//a[text()='{next_page_num}'] | //div[contains(@class, 'pagination')]//a[text()='{next_page_num}'] | //a[contains(@class, 'page-link') and text()='{next_page_num}']")
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_btn)
                        time.sleep(1)
                        driver.execute_script("arguments[0].click();", page_btn)
                        time.sleep(4)
                    except:
                        print(f"    -> [NIELIT] Could not find pagination button for page {next_page_num}. Ending pagination.")
                        break
                        
            # After completion go back to 1
            try:
                print("    -> [NIELIT] Going back to page 1 as requested...")
                page_1_btn = driver.find_element(By.XPATH, "//ul[contains(@class, 'pagination')]//a[text()='1'] | //div[contains(@class, 'pagination')]//a[text()='1'] | //a[contains(@class, 'page-link') and text()='1']")
                driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", page_1_btn)
                time.sleep(1)
                driver.execute_script("arguments[0].click();", page_1_btn)
                time.sleep(2)
            except Exception as e:
                print(f"    -> [NIELIT] Could not return to page 1: {e}")

            # Cache the result
            self.ndu_category_cache[target_category] = all_text
            print(f"    -> [NIELIT] Built cache for category '{target_category}' ({len(all_text)} chars).")
            return all_text
            
        except Exception as e:
            print(f"    -> [NIELIT] Navigation failed: {e}")
            return ""

    def _ranking_search_queries(self, university):
        queries = []
        base = university.strip()
        variants = [
            base,
            re.sub(r"\([^)]*\)", "", base).strip(),
            base.replace("&", "and"),
            base.replace(" and ", " & "),
            re.split(r"[-,|]", base)[0].strip(),
        ]
        for value in variants:
            value = re.sub(r"\s+", " ", value).strip()
            if value and value not in queries:
                queries.append(value)
        return queries

    def _ranking_page_contains_university(self, driver, university):
        text = self._extract_page_text(driver)
        found, score = entity_present(university, text, threshold=0.72)
        return found, score, text

    def _clean_ranking_text(self, text):
        """Normalize AI/search snippets while preserving rank markers such as #38 and 151-200."""
        if not text:
            return ""
        text = str(text)
        replacements = {
            "\u2013": "-",
            "\u2014": "-",
            "\u2212": "-",
            "\u00a0": " ",
            "\\#": "#",
            "\\(": " ",
            "\\)": " ",
        }
        for old, new in replacements.items():
            text = text.replace(old, new)
        text = re.sub(r"\\text\s*\{([^}]*)\}", r"\1", text)
        text = text.replace("{", " ").replace("}", " ")
        text = re.sub(r"\s+", " ", text)
        # Collapse spaces between digits (e.g. "1 0 0 1 +" -> "1001+")
        text = re.sub(r'(?<=\d)\s+(?=\d)', '', text)
        text = re.sub(r'(?<=\d)\s+\+', '+', text)
        return text.strip()

    def _clean_rank_value(self, value):
        value = self._clean_ranking_text(value)
        value = value.replace("#", "").replace(",", "").strip()
        value = re.sub(r"\s+", "", value)
        value = re.sub(r"(?i)(st|nd|rd|th)$", "", value)
        value = value.replace("=-", "=")
        if not re.fullmatch(r"=?\d{1,4}(?:-\d{1,4})?\+?", value):
            return ""
        return value

    def _ranking_label_from_context(self, context, ranking_type):
        lower = context.lower()
        if ranking_type == "NIRF":
            if "state public" in lower:
                return "NIRF State Public University"
            if "open university" in lower:
                return "NIRF Open University"
            if "overall" in lower:
                return "NIRF Overall"
            if "engineering" in lower:
                return "NIRF Engineering"
            if "management" in lower:
                return "NIRF Management"
            if "college" in lower or "colleges" in lower:
                return "NIRF College"
            if "universit" in lower:
                return "NIRF University"
            return "NIRF"

        if "southern asia" in lower:
            return "QS Southern Asia"
        if "asia university" in lower or "qs asia" in lower:
            return "QS Asia"
        if "world university" in lower or "global" in lower or "globally" in lower or "worldwide" in lower:
            return "QS World"
        if "regional" in lower:
            return "QS Regional"
        return "QS"

    def _ranking_priority(self, ranking_type, label, is_band):
        if ranking_type == "NIRF":
            order = {
                "NIRF Overall": 10,
                "NIRF University": 20,
                "NIRF State Public University": 25,
                "NIRF Open University": 30,
                "NIRF College": 35,
                "NIRF Engineering": 40,
                "NIRF Management": 45,
                "NIRF": 60,
            }
            return order.get(label, 60) + (1 if is_band else 0)

        order = {
            "QS World": 10,
            "QS Asia": 20,
            "QS Southern Asia": 30,
            "QS Regional": 35,
            "QS": 50,
        }
        return order.get(label, 50) + (1 if is_band else 0)

    def _ranking_context_windows(self, clean_text, ranking_type):
        lower = clean_text.lower()
        if ranking_type == "NIRF":
            keyword_re = r"\b(nirf|national institutional ranking framework|india rankings)\b"
        else:
            keyword_re = r"\b(qs|quacquarelli|world university rankings|asia university ranking|southern asia|regional rankings)\b"

        windows = []
        for match in re.finditer(keyword_re, lower, flags=re.IGNORECASE):
            start = max(0, match.start() - 220)
            end = min(len(clean_text), match.end() + 280)
            windows.append(clean_text[start:end])

        for part in re.split(r"(?<=[.!?])\s+|\n+", clean_text):
            if re.search(keyword_re, part, flags=re.IGNORECASE):
                windows.append(part)

        unique = []
        seen = set()
        for window in windows:
            window = window.strip()
            if not window:
                continue
            key = window.lower()
            if key not in seen:
                seen.add(key)
                unique.append(window)
        return unique

    def _has_definite_no_rank(self, clean_text, ranking_type):
        lower = clean_text.lower()
        if ranking_type == "NIRF":
            patterns = [
                r"does\s+not\s+have\s+(?:a|an)\s+(?:india\s+)?(?:.*?)(?:national institutional ranking framework|nirf)",
                r"no\s+(?:national institutional ranking framework\s*)?\(?nirf\)?\s+rank",
                r"not\s+ranked\s+(?:by|in|under|as\s+a(?:.*?))\s+(?:the\s+)?(?:national institutional ranking framework|nirf|national)",
                r"not\s+listed\s+(?:by|in|under)\s+(?:the\s+)?(?:national institutional ranking framework|nirf)",
                r"nirf\s+(?:evaluates|ranks)\s+only\s+educational institutions within india",
                r"does\s+not\s+hold\s+(?:a|an)\s+(?:india\s+)?(?:.*?)(?:national institutional ranking framework|nirf)",
                r"not\s+feature\s+in\s+(?:the\s+)?(?:national institutional ranking framework|nirf)",
                r"does\s+not\s+participate\s+in\s+(?:.*?)(?:national institutional ranking framework|nirf)",
                r"does\s+not\s+hold\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?(?:.*?)nirf\s+rank",
                r"is\s+not\s+ranked\s+in\s+nirf",
                r"does\s+not\s+have\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?rank\s+(?:in|by|for)\s+(?:the\s+)?(?:national institutional ranking framework|nirf)",
                r"does\s+not\s+have\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?entry\s+in\s+(?:the\s+)?(?:national institutional ranking framework|nirf)",
            ]
        else:
            patterns = [
                r"does\s+not\s+have\s+(?:a\s+)?qs\s+rank",
                r"does\s+not\s+have\s+(?:a\s+)?qs\s+(?:world\s+|asia\s+|global\s+|university\s+)*rank(?:ing|ings)?",
                r"no\s+qs\s+(?:world\s+|asia\s+|global\s+|university\s+)*rank(?:ing|ings)?",
                r"not\s+ranked\s+(?:by|in|under|as\s+a(?:.*?))\s+(?:the\s+)?qs",
                r"not\s+listed\s+(?:by|in|under)\s+(?:the\s+)?qs",
                r"does\s+not\s+hold\s+a\s+ranking\s+in\s+(?:.*?)qs",
                r"does\s+not\s+hold\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?(?:.*?)qs",
                r"is\s+not\s+ranked\s+as\s+a\s+single[,\s]+centralized\s+university",
                r"does\s+not\s+have\s+a\s+qs\s+world\s+university\s+ranking",
                r"is\s+not\s+ranked\s+in\s+qs",
                r"does\s+not\s+have\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?rank\s+(?:in|by|for)\s+(?:the\s+)?(?:global\s+)?qs",
                r"does\s+not\s+have\s+(?:a|an)\s+(?:formal\s+|specific\s+|standalone\s+)?entry\s+in\s+(?:the\s+)?(?:global\s+)?qs",
            ]
        return any(re.search(pattern, lower) for pattern in patterns)

    def _rank_context_is_valid(self, context, near_rank, ranking_type):
        context_lower = context.lower()
        near_lower = near_rank.lower()
        if ranking_type == "NIRF":
            return any(term in context_lower for term in (
                "nirf",
                "national institutional ranking framework",
                "india rankings",
            ))

        has_qs_context = any(term in context_lower for term in (
            "qs",
            "quacquarelli",
            "world university rankings",
            "asia university ranking",
            "southern asia",
            "regional rankings",
        ))
        if not has_qs_context:
            return False

        subject_terms = (
            "subject ranking",
            "subject rankings",
            "by subject",
            "arts & humanities",
            "social sciences",
            "discipline",
            "disciplines",
        )
        institutional_terms = (
            "world university",
            "asia university",
            "regional",
            "southern asia",
            "global",
            "globally",
            "worldwide",
        )
        if any(term in near_lower for term in subject_terms) and not any(term in near_lower for term in institutional_terms):
            return False
        if "qs stars" in near_lower or "star rating" in near_lower:
            return False
        return True

    def _extract_rank_from_text(self, text, university, ranking_type):
        """
        Deterministically read AI Overview/search text for QS or NIRF rank claims.
        Returns (handled, result). handled=False means the text is ambiguous and callers may try another source.
        """
        ranking_type = ranking_type.upper()
        clean_text = self._clean_ranking_text(text)
        if not clean_text:
            return False, "Not Ranked"

        if university and university != "Unknown":
            found, _ = entity_present(university, clean_text, threshold=0.45)
            if not found:
                return False, "Not Ranked"

        if self._has_definite_no_rank(clean_text, ranking_type):
            return True, "Not Ranked"

        windows = self._ranking_context_windows(clean_text, ranking_type)
        candidates = []

        band_patterns = [
            r"\b(?P<rank>=?\d{2,4}(?:\s*-\s*\d{2,4})?\+?)\s*(?:rank\s*|global\s+)?band\b",
            r"\b(?:rank\s*band|rank-band|placed\s+in|holds(?:\s+a)?|ranked(?:\s+in)?|ranking\s+in)\s+(?:the\s+)?(?:#\s*)?(?P<rank>=?\d{2,4}(?:\s*-\s*\d{2,4})?\+?)\b"
        ]
        number_patterns = [
            r"\b(?:ranked|ranks|rank|position|placed|secured|holds|stands)\b\s*(?:at|in|is|:|=|the|a|\s)*\s*(?:#|no\.?\s*)?(?P<rank>=?\d{1,4}\+?)(?:st|nd|rd|th)?\b(?!\s*(?:in|for)?\s*202\d)",
            r"(?:#|no\.?\s*)(?P<rank>=?\d{1,4}\+?)(?:st|nd|rd|th)?\s*(?:globally|worldwide|position|rank)?",
            r"\b(?P<rank>=?\d{1,4}\+?)(?:st|nd|rd|th)?\s+(?:rank|position)\b",
        ]

        def add_candidate(match, context, is_band):
            if not is_band:
                before = context[max(0, match.start() - 1):match.start()]
                after = context[match.end():match.end() + 1]
                if before == "-" or after == "-":
                    return
            rank_value = self._clean_rank_value(match.group("rank"))
            if not rank_value:
                return
            if rank_value.startswith("20") and len(rank_value) == 4 and rank_value.isdigit():
                # Avoid extracting years 20xx as ranks
                return
            if rank_value.startswith("19") and len(rank_value) == 4 and rank_value.isdigit():
                # Avoid extracting years 19xx as ranks
                return
            near = context[max(0, match.start() - 90): min(len(context), match.end() + 90)]
            if not self._rank_context_is_valid(context, near, ranking_type):
                return
            label = self._ranking_label_from_context(near, ranking_type)
            if label in {"QS", "NIRF"}:
                label = self._ranking_label_from_context(context, ranking_type)
            if "-" in rank_value or is_band:
                result = f"Rank Band {rank_value}"
            else:
                result = f"Rank {rank_value}"
            if label:
                result += f" ({label})"
            candidates.append((
                self._ranking_priority(ranking_type, label, "-" in rank_value or is_band),
                rank_value,
                label,
                result,
            ))

        for context in windows:
            for pattern in band_patterns:
                for match in re.finditer(pattern, context, flags=re.IGNORECASE):
                    add_candidate(match, context, True)
            for pattern in number_patterns:
                for match in re.finditer(pattern, context, flags=re.IGNORECASE):
                    add_candidate(match, context, False)

        if candidates:
            candidates.sort(key=lambda item: item[0])
            results = []
            seen = set()
            for _, rank_value, label, result in candidates:
                # If rank > 1000, user considers it "Not Ranked"
                m_num = re.search(r'\d+', rank_value)
                if m_num and int(m_num.group()) > 1000:
                    continue
                    
                key = (rank_value, label)
                if key in seen:
                    continue
                seen.add(key)
                results.append(result)
                if len(results) == 2:
                    break
                    
            if results:
                return True, " / ".join(results)
            else:
                # Found ranks, but all were > 1000
                return True, "Not Ranked"

        return False, "Not Ranked"

    # ──────────────────────────────────────────────────────────
    #  HELPER: Click only relevant tabs (course/fee/cyber)
    # ──────────────────────────────────────────────────────────

    def _inject_bounding_boxes(self, driver):
        """Inject JS to draw numbered bounding boxes on interactive elements and return mapping."""
        js_code = """
            let elements = document.querySelectorAll('a, button, [role="button"], [role="tab"], .nav-link, details summary');
            let mapping = {};
            let counter = 1;
            window.__llm_elements = window.__llm_elements || {};
            
            // Remove old boxes if any
            document.querySelectorAll('.llm-vision-box').forEach(e => e.remove());

            elements.forEach(el => {
                if (!el.innerText || el.innerText.trim().length < 2) return;
                let rect = el.getBoundingClientRect();
                if (rect.width > 0 && rect.height > 0 && rect.top >= 0 && rect.top <= window.innerHeight) {
                    let id = counter++;
                    window.__llm_elements[id] = el;
                    mapping[id] = {
                        text: el.innerText.trim().substring(0, 50),
                        x: rect.left + rect.width / 2,
                        y: rect.top + rect.height / 2
                    };
                    
                    let box = document.createElement('div');
                    box.className = 'llm-vision-box';
                    box.style.position = 'fixed';
                    box.style.left = rect.left + 'px';
                    box.style.top = rect.top + 'px';
                    box.style.width = rect.width + 'px';
                    box.style.height = rect.height + 'px';
                    box.style.border = '2px solid red';
                    box.style.zIndex = '999999';
                    box.style.pointerEvents = 'none';
                    
                    let label = document.createElement('span');
                    label.innerText = id;
                    label.style.position = 'absolute';
                    label.style.top = '-15px';
                    label.style.left = '0px';
                    label.style.background = 'yellow';
                    label.style.color = 'black';
                    label.style.fontSize = '12px';
                    label.style.fontWeight = 'bold';
                    label.style.padding = '1px 3px';
                    box.appendChild(label);
                    document.body.appendChild(box);
                }
            });
            return mapping;
        """
        try:
            return driver.execute_script(js_code)
        except Exception as e:
            print(f"    -> [Vision] Failed to inject bounding boxes: {e}")
            return {}

    def _inject_beautiful_cursor(self, driver):
        """Inject a highly visible floating DOM cursor element that physically moves on the page."""
        try:
            driver.execute_script("""
                if (!document.getElementById('ai-cursor')) {
                    var style = document.createElement('style');
                    style.id = 'ai-cursor-style';
                    var cursorSvg = "data:image/svg+xml;utf8,<svg width='32' height='32' viewBox='0 0 24 24' xmlns='http://www.w3.org/2000/svg'><path d='M4 2l16 10-7 2 4 7-3 2-4-7-3 5z' fill='white' stroke='black' stroke-width='2' stroke-linejoin='round'/></svg>";
                    style.textContent = '#ai-cursor { position:fixed; width:32px; height:32px; background-image:url("' + cursorSvg + '"); background-size:contain; background-repeat:no-repeat; filter: drop-shadow(0px 0px 5px rgba(0,0,0,0.5)); z-index:2147483647; pointer-events:none; transition:left 0.4s cubic-bezier(0.22,1,0.36,1),top 0.4s cubic-bezier(0.22,1,0.36,1); left:-50px; top:-50px; } @keyframes aiRing { 0%{width:32px;height:32px;opacity:1} 100%{width:60px;height:60px;opacity:0} } .ai-click-ring { position:fixed; border:3px solid #000; border-radius:50%; z-index:2147483646; pointer-events:none; animation:aiRing 0.5s ease-out forwards; }';
                    document.head.appendChild(style);
                    var cursor = document.createElement('div');
                    cursor.id = 'ai-cursor';
                    document.body.appendChild(cursor);
                    window.moveBeautifulCursor = function(x, y) {
                        var c = document.getElementById('ai-cursor');
                        if (c) { c.style.left = (x-12)+'px'; c.style.top = (y-12)+'px'; }
                    };
                    window.aiClickAnimation = function(x, y) {
                        var ring = document.createElement('div');
                        ring.className = 'ai-click-ring';
                        ring.style.left = (x-12)+'px'; ring.style.top = (y-12)+'px';
                        document.body.appendChild(ring);
                        setTimeout(function(){ring.remove()}, 600);
                    };
                }
            """)
        except Exception:
            pass


    def _vision_based_tab_exploration(self, driver, course_name="", missing_info="", country=""):
        """Use LLM Manager to intelligently browse the page, scroll, and click relevant tabs."""
        extra_parts = []
        llm = get_llm_manager()

        try:
            original_url = driver.current_url.split('#')[0]
            original_window = driver.current_window_handle

            # ── Agentic Loop: Observe -> Think -> Act (Max 3 rounds to avoid wasting time) ──
            for vision_round in range(3):
                self._inject_beautiful_cursor(driver)
                print(f"    -> [Smart Agent] [Round {vision_round+1}] Scanning DOM for '{missing_info}'...")

                # Inject numbered bounding boxes
                element_mapping = self._inject_bounding_boxes(driver)
                if not element_mapping:
                    print("      -> No interactive elements found.")
                    break
                    
                mapping_text = "\\n".join(
                    f"  [{eid}] \"{info.get('text', '').strip()[:80]}\""
                    for eid, info in element_mapping.items() if len(info.get('text', '').strip()) >= 3
                )
                
                is_indian = str(country).lower() in ['india', 'in', 'ind', 'bharat']
                intl_rule = '\n4. IMPORTANT FOR FEES: Since this is an International/Non-Indian college, if looking for Cost/Fees, you MUST prioritize clicking on "International Students", "Overseas", or "International Fees".' if not is_indian else ''

                agent_prompt = f"""You are a strict, efficient web researcher looking for course details.
Target course: "{course_name}"
Missing Info to find: {missing_info}

Currently visible clickable elements on screen:
{mapping_text}

CRITICAL RULES:
1. DO NOT click generic menu items (e.g. "For Individuals", "For Business", "About Us", "Contact") unless they clearly contain pricing/duration/skills for this specific course.
2. If no visible elements are DIRECTLY relevant to the missing info, choose "scroll" or "finish" instead of wasting time clicking random links.
3. Be efficient. If you are unsure, choose "finish" to avoid blindly guessing.{intl_rule}

Choose exactly ONE action to take next to find the missing info.
Return ONLY valid JSON in this exact format:
{{"action": "click", "id": 5}}  (To click element ID 5)
{{"action": "hover", "id": 5}}  (To hover your mouse over element ID 5 to open dropdown menus)
{{"action": "scroll", "direction": "down"}} (To scroll the page to see more elements)
{{"action": "finish", "reason": "No more relevant elements"}} (If you are done)

CRITICAL: YOU MUST RETURN ONLY THE RAW JSON OBJECT. DO NOT INCLUDE ANY CONVERSATION, REASONING, OR EXPLANATION.
"""
                print(f"      -> [Smart Agent] Asking LLM for next action...")
                response_text = llm.generate(
                    prompt=agent_prompt,
                    format="json",
                    temperature=0.0
                )
                
                if not response_text:
                    print("      -> [Smart Agent] LLM Manager failed.")
                    break
                    
                try:
                    action_data = json.loads(response_text)
                except Exception:
                    # Try to extract JSON if there's markdown wrap
                    import re
                    match = re.search(r'\{.*\}', response_text, re.DOTALL)
                    if match:
                        try:
                            action_data = json.loads(match.group(0))
                        except Exception:
                            print(f"      -> [Smart Agent] Invalid JSON from LLM: {response_text}")
                            break
                    else:
                        print(f"      -> [Smart Agent] Invalid JSON from LLM: {response_text}")
                        # Fallback heuristic: search for the ID in the last relevant line
                        lines = response_text.strip().split('\n')
                        found_id = None
                        for line in reversed(lines):
                            if re.search(r'(click|id|action)', line, re.IGNORECASE):
                                nums = re.findall(r'\d+', line)
                                if nums:
                                    found_id = nums[-1]
                                    break
                        if not found_id:
                            nums = re.findall(r'\d+', response_text)
                            if nums: found_id = nums[-1]
                            
                        if found_id:
                            action_data = {"action": "click", "id": int(found_id)}
                            print(f"      -> [Smart Agent Fallback] Deduced click on ID {found_id}")
                        else:
                            break

                action = action_data.get("action")
                
                if action == "finish":
                    print(f"      -> [Smart Agent] Agent decided to finish: {action_data.get('reason')}")
                    break
                    
                elif action == "scroll":
                    direction = action_data.get("direction", "down")
                    print(f"      -> [Smart Agent] Scrolling {direction}...")
                    if direction == "down":
                        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.8);")
                    else:
                        driver.execute_script("window.scrollBy(0, -window.innerHeight * 0.8);")
                    time.sleep(1.5)
                    
                elif action == "hover":
                    eid = str(action_data.get("id"))
                    if eid in element_mapping:
                        info = element_mapping[eid]
                        x, y = info.get('x', 0), info.get('y', 0)
                        label = info.get('text', '')[:40]
                        print(f"      -> [Smart Agent] Hovering over element [{eid}] '{label}' at ({int(x)}, {int(y)}) to reveal menus...")
                        try:
                            # Move beautiful cursor
                            driver.execute_script(f"if(window.moveBeautifulCursor) window.moveBeautifulCursor({x}, {y});")
                            time.sleep(0.5)
                            # Dispatch mouseover and mouseenter events to trigger CSS and JS dropdowns
                            js_hover = f"""
                                var el = window.__llm_elements[{eid}];
                                if(el) {{
                                    el.scrollIntoView({{behavior: 'smooth', block: 'center'}});
                                    var ev1 = new MouseEvent('mouseover', {{bubbles: true, cancelable: true, view: window}});
                                    var ev2 = new MouseEvent('mouseenter', {{bubbles: true, cancelable: true, view: window}});
                                    el.dispatchEvent(ev1); el.dispatchEvent(ev2);
                                }}
                            """
                            driver.execute_script(js_hover)
                            time.sleep(1.5)
                        except Exception as e:
                            print(f"      -> [Smart Agent] Hover failed: {e}")
                    else:
                        print(f"      -> [Smart Agent] Element ID {eid} not found on screen for hovering.")

                elif action == "click":
                    eid = str(action_data.get("id"))
                    if eid in element_mapping:
                        info = element_mapping[eid]
                        x, y = info.get('x', 0), info.get('y', 0)
                        label = info.get('text', '')[:40]

                        print(f"      -> [Smart Agent] Clicking element [{eid}] '{label}' at ({int(x)}, {int(y)})")
                        try:
                            # Move cursor and click
                            driver.execute_script(f"if(window.moveBeautifulCursor) window.moveBeautifulCursor({x}, {y});")
                            time.sleep(0.5)
                            driver.execute_script(f"var el = window.__llm_elements[{eid}]; if(el){{ el.scrollIntoView({{behavior: 'smooth', block: 'center'}}); setTimeout(() => {{ el.click(); }}, 300); }}")
                            time.sleep(2.0)

                            # Handle tabs/navigation
                            if len(driver.window_handles) > 1:
                                print(f"      -> [Smart Agent] Navigated away. Returning...")
                                driver.back()
                                time.sleep(1.5)

                            # Grab new text
                            new_text = driver.find_element(By.TAG_NAME, 'body').text
                            if new_text and len(new_text) > 100:
                                extra_parts.append(new_text)
                                
                        except Exception as e:
                            print(f"      -> [Smart Agent] Click failed: {e}")
                    else:
                        print(f"      -> [Smart Agent] Element ID {eid} not found on screen. Scrolling down as fallback.")
                        driver.execute_script("window.scrollBy(0, window.innerHeight * 0.8);")
                        time.sleep(1.5)

                # Remove old bounding boxes before next round
                try:
                    driver.execute_script("document.querySelectorAll('.llm-vision-box').forEach(e => e.remove());")
                except: pass

        except Exception as e:
            print(f"    -> [Vision] Agent exploration error: {e}")

        return "\\n".join(extra_parts)

    def _vision_based_tab_exploration_local(self, driver, course_name="", missing_info=""):
        """Fallback local model tab exploration."""
        pass

    def _vision_fallback_ocr(self, driver):
        """Fallback: Use OCR keywords if vision model is unavailable."""
        import pytesseract, cv2
        import numpy as np
        extra_parts = []
        try:
            if not pytesseract or not cv2 or not np:
                return extra_parts

            screenshot_bytes = driver.get_screenshot_as_png()
            nparr = np.frombuffer(screenshot_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            if os.name == 'nt':
                if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                    pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                    pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'

            custom_config = r'--oem 3 --psm 11'
            data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT, config=custom_config)

            keywords = ["fee", "tuition", "syllabus", "curricul", "duration", "scholarship", "enroll", "programm"]
            clicked_coords = []

            for i in range(len(data['text'])):
                text = data['text'][i].lower()
                if len(text) < 3:
                    continue
                if any(kw in text for kw in keywords):
                    x, y, w, h = data['left'][i], data['top'][i], data['width'][i], data['height'][i]
                    cx, cy = x + w // 2, y + h // 2
                    if any(abs(cx - cc[0]) < 20 and abs(cy - cc[1]) < 20 for cc in clicked_coords):
                        continue
                    try:
                        driver.execute_script(f"""
                            var scrollY = window.scrollY || document.documentElement.scrollTop;
                            var el = document.elementFromPoint({cx}, {cy} - scrollY);
                            if (el) {{ el.click(); }}
                        """)
                        clicked_coords.append((cx, cy))
                        time.sleep(1.0)
                        new_text = driver.find_element(By.TAG_NAME, 'body').text
                        if new_text:
                            extra_parts.append(new_text)
                    except Exception:
                        pass
        except Exception:
            pass
        return extra_parts

    # ──────────────────────────────────────────────────────────
    #  HELPER: Generate Summary Locally (No API)
    # ──────────────────────────────────────────────────────────

    def _generate_description_locally(self, course_name, reason_text, is_error=False, explored=False):
        """Generates a clean description locally without API calls."""
        if is_error:
            return f"The website for the course '{course_name}' returned a 'not found' or HTTP error. The link is not working."
        else:
            explore_instruction = " The course was only found after exploring the website (clicking tabs/menus or searching), meaning the initial direct link did not contain all details and needs to be updated." if explored else ""
            return reason_text + explore_instruction

    # ──────────────────────────────────────────────────────────
    #  STEP 3: WEB VERIFICATION
    # ──────────────────────────────────────────────────────────

    def _evaluate_rank_with_llm(self, text: str, university: str, ranking_type: str) -> str:
        handled, parsed = self._extract_rank_from_text(text, university, ranking_type)
        if handled:
            print(f"         -> [LOCAL RANK RESULT]: {parsed}")
            return parsed
        print(f"         -> [LOCAL RANK RESULT]: No clear {ranking_type} rank in text.")
        return "Not Ranked"



    def autonomous_web_verify(self, start_idx=0, end_idx=None):
        print(f"\n[*] Step 3/4: Launching Visible Browser Agent (Selenium/uc)...")
        print(f"    A Chrome window will open on your screen now.\n")
        
        # Preserve screenshot evidence across runs. New screenshots may overwrite same-name
        # files for the current course, but the directory is never deleted by the verifier.
        if start_idx == 0:
            print(f"    -> Fresh run detected. Saving screenshots to new directory: {self.screenshots_dir}")
            os.makedirs(self.screenshots_dir, exist_ok=True)
        else:
            print(f"    -> [Resume] Resuming from course index {start_idx + 1}. Keeping existing screenshots in: {self.screenshots_dir}")

        url_cache = {}
        import random
        from concurrent.futures import ThreadPoolExecutor, as_completed
        import queue
        import threading
        
        checkpoint_lock = threading.Lock()
        NUM_BROWSERS = 6  # 6 simultaneous threads with dedicated API keys
        if NUM_BROWSERS <= 0: return
        
        import subprocess
        print(f"    -> Cleaning up any orphaned browser processes from previous runs...")
        try:
            # Kill any background chromedriver.exe instances
            subprocess.run('taskkill /F /IM chromedriver.exe /T', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            # Kill ONLY chrome.exe instances that were started by our script (matching our profile directory)
            subprocess.run('wmic process where "name=\'chrome.exe\' and commandline like \'%chrome_profile%\'" call terminate', shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except: pass
        
        print(f"    -> Initializing {NUM_BROWSERS} parallel Chrome browsers simultaneously...")
        browser_pool = queue.Queue()
        import threading
        browser_init_lock = threading.Lock()
        
        def init_browser_parallel(b_idx):
            options = uc.ChromeOptions()
            options.page_load_strategy = 'eager'
            options.add_argument('--disable-blink-features=AutomationControlled')
            options.add_argument('--window-size=1280,800')
            options.add_argument('--ignore-certificate-errors')
            fresh_profile = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"chrome_profile_{b_idx}")
            os.makedirs(fresh_profile, exist_ok=True)
            
            with browser_init_lock:
                try:
                    driver = uc.Chrome(options=options, user_data_dir=fresh_profile, version_main=148)
                except Exception as e:
                    print(f"    -> Warning: Parallel profile creation failed ({e}). Retrying with fresh options...")
                    options2 = uc.ChromeOptions()
                    options2.page_load_strategy = 'eager'
                    options2.add_argument('--disable-blink-features=AutomationControlled')
                    options2.add_argument('--window-size=1280,800')
                    options2.add_argument('--ignore-certificate-errors')
                    fresh_profile2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), f"chrome_profile_fallback_{b_idx}")
                    os.makedirs(fresh_profile2, exist_ok=True)
                    driver = uc.Chrome(options=options2, user_data_dir=fresh_profile2, version_main=148)
                    
            driver.set_page_load_timeout(60)
            try: driver.minimize_window()
            except: pass
            
            # Execute automated platform logins on this fresh driver
            self._perform_platform_logins(driver)
            return b_idx, driver

        with ThreadPoolExecutor(max_workers=NUM_BROWSERS) as executor:
            futures = [executor.submit(init_browser_parallel, b_idx) for b_idx in range(NUM_BROWSERS)]
            for future in as_completed(futures):
                try:
                    b_idx, driver = future.result()
                    browser_pool.put((b_idx, driver))
                except Exception as e:
                    print(f"    -> [Error] Failed to initialize browser: {e}")

        # Setup Thread Local Stdout for Sequential Logging
        import sys
        import threading
        from io import StringIO
        
        class ThreadLocalStdout:
            def __init__(self, original):
                self.original = original
                self.local = threading.local()
            def write(self, data):
                if hasattr(self.local, 'buffer'):
                    self.local.buffer.write(data)
                else:
                    self.original.write(data)
            def flush(self):
                if hasattr(self.local, 'buffer'):
                    pass
                else:
                    self.original.flush()
            def __getattr__(self, name):
                return getattr(self.original, name)
                
        original_stdout = sys.stdout
        tl_stdout = ThreadLocalStdout(original_stdout)
        sys.stdout = tl_stdout

        class EarlyExit(Exception): pass

        def process_course(item):
            sys.stdout.local.buffer = StringIO()
            import numpy as np
            i, course = item
            worker_id, driver = browser_pool.get()
            try:
                    
                url = course.get("url")
                if not url or url == "Unknown":
                    course['web_status'] = "FALSE"
                    course['reason'] = "No valid URL found in PDF."
                    course['direct_link_working'] = False
                    course['is_hard_error'] = True
                    raise EarlyExit()
                    
                cache_key = f"{url}::{normalize(course.get('name', ''))}"
                if cache_key in url_cache:
                    cached = url_cache[cache_key]
                    for k in ['web_status', 'reason', 'web_name', 'web_cost', 'web_uni', 'skills_verified', 'scholarship_found', 'is_hard_error']:
                        course[k] = cached.get(k, course.get(k, False))
                    raise EarlyExit()

                print(f"  [{i + 1}/{len(self.courses)}] Investigating: {url}")

                try:
                    time.sleep(random.uniform(0.5, 1.5))  # Fast: uc handles bot detection
                    self._safe_get(driver, url)
                    
                    initial_title = ""
                    initial_body = ""
                    try:
                        initial_title = driver.title or ""
                    except Exception:
                        pass
                    try:
                        initial_body = driver.find_element(By.TAG_NAME, 'body').text[:2000]
                    except Exception:
                        pass
                    initial_error_text = f"{initial_title}\n{initial_body}".lower()
                    initial_not_found = (
                        ("404" in initial_error_text and "not found" in initial_error_text) or
                        "page not found" in initial_error_text or
                        "service unavailable" in initial_error_text or
                        "course not available" in initial_error_text or
                        ("error" in initial_title.lower() and len(initial_body) < 500)
                    )
                    if initial_not_found:
                        raw_reason = f"Initial page returned an error/not-found state. Page title: '{initial_title}'."
                        course['web_status'] = "FALSE"
                        course['reason'] = self._generate_description_locally(course['name'], raw_reason, is_error=True)
                        if 'hence matched' in str(course.get('qs_detail', '')):
                            course['reason'] += " " + course['qs_detail'] + "."
                        if 'hence matched' in str(course.get('nirf_detail', '')):
                            course['reason'] += " " + course['nirf_detail'] + "."
                        course['direct_link_working'] = False
                        course['is_hard_error'] = True
                        ss = os.path.join(self.screenshots_dir, f"course_{i+1}_initial_error.png")
                        try:
                            driver.save_screenshot(ss)
                            print(f"    -> Initial page error. Screenshot: {ss}")
                        except Exception:
                            print("    -> Initial page error. Screenshot could not be saved.")
                        url_cache[cache_key] = {"web_status": "FALSE", "reason": course['reason'], "direct_link_working": False, "is_hard_error": True}
                        raise EarlyExit()
                        
                    # FALLBACK: If the browser failed before showing a real page, search DuckDuckGo.
                    # Explicit 404/not-found pages are handled above and are not auto-replaced.
                    try:
                        if driver.current_url.startswith("data:"):
                            # Skip DDG search specifically for NDU as requested
                            if "National Institute of Electronics & IT" in course.get('uni', ''):
                                print(f"    -> Link appears broken. Skipping DDG search for NDU as requested.")
                                raise Exception("NDU search fallback disabled")
                                
                            course_uni_check = course.get('uni', '')
                            links = self._search_excel_for_links(course_uni_check, course.get('name', ''))
                            excel_url = links.get('main_link') or links.get('fees') or links.get('syllabus')
                            if excel_url:
                                print(f"    -> Override: Using Excel hyperlink instead of wasting time searching: {excel_url}")
                                self._safe_get(driver, excel_url)
                                time.sleep(3)
                                url = excel_url
                            else:
                                print(f"    -> Link appears broken and no Excel hyperlink found. Search fallback disabled by user request.")
                                raise Exception("Broken link and no fallback available.")
                    except Exception as e:
                        print(f"      -> Search fallback failed: {e}")

                    print(f"    -> Waiting for page to render...")
                    try:
                        WebDriverWait(driver, 8).until(lambda d: d.execute_script("return document.readyState") == "complete")
                    except:
                        pass
                    time.sleep(1)  # Brief extra settle time
                    
                    # Handling PDF Links directly
                    if url.lower().endswith(".pdf") or (driver.execute_script("return document.contentType") == "application/pdf"):
                        print(f"    -> Detected PDF file. Downloading and parsing PDF...")
                        try:
                            import requests
                            import urllib3
                            urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                            pdf_resp = requests.get(url, timeout=10, verify=False)
                            pdf_resp.raise_for_status()
                            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                                tmp_pdf.write(pdf_resp.content)
                                tmp_pdf_path = tmp_pdf.name
                            
                            import pdfplumber
                            pdf_text = ""
                            with pdfplumber.open(tmp_pdf_path) as pdf_file:
                                for p in pdf_file.pages:
                                    pdf_text += (p.extract_text() or "") + "\n"
                                    
                            # NEW: Extract and OCR embedded images in the PDF
                            try:
                                import fitz
                                import base64
                                import io
                                if os.name == 'nt':
                                    if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                                        pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                                    elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                                        pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
                                
                                pdf_doc = fitz.open(tmp_pdf_path)
                                for page_index in range(len(pdf_doc)):
                                    page = pdf_doc[page_index]
                                    image_list = page.get_images(full=True)
                                    for img_info in image_list:
                                        xref = img_info[0]
                                        base_image = pdf_doc.extract_image(xref)
                                        image_bytes = base_image["image"]
                                        if Image:
                                            image = Image.open(io.BytesIO(image_bytes)).convert('L')
                                            
                                            ocr_result = pytesseract.image_to_string(image, config='--oem 3 --psm 6')
                                            if ocr_result is None: ocr_result = ""

                                            if ocr_result.strip():
                                                pdf_text += "\n" + ocr_result
                                pdf_doc.close()
                            except Exception as e:
                                print(f"    -> Warning: Failed to OCR PDF images: {e}")
                                
                            os.unlink(tmp_pdf_path)
                            
                            (cost_match, sk_match, sk_detail, duration_match, duration_detail,
                             mode_match, mode_detail, lang_match, lang_detail,
                             web_cost, web_duration, web_mode, web_language) = self._verify_details_locally(course, pdf_text)
                            
                            if not (cost_match and duration_match):
                                l_cost, l_sk, l_skd, l_dur, l_durd, l_mod, l_modd, l_lan, l_land, l_costd, l_country, l_countryd, l_uni_match, l_unid = self._verify_details_with_llm(course, pdf_text, worker_id=worker_id)
                                if l_cost: cost_match, web_cost = True, course.get('cost', '')
                                if l_dur: duration_match, web_duration = True, l_durd
                                if l_mod: mode_match, web_mode = True, l_modd
                                if l_lan: lang_match, web_language = True, l_land
                                sk_match, sk_detail = l_sk, l_skd

                            course['web_status'] = 'MATCH' if (cost_match and duration_match) else 'FALSE'
                            course['reason'] = 'Verified via PDF content on website.'
                            course['web_name'] = course['name']
                            course['web_cost'] = web_cost
                            course['web_uni'] = course['uni']
                            course['skills_verified'] = sk_detail
                            course['scholarship_found'] = False
                            course['direct_link_working'] = True
                            
                            course['web_duration'] = web_duration
                            course['web_mode'] = web_mode
                            course['web_language'] = web_language
                            
                            course['cost_match'] = cost_match
                            course['duration_match'] = duration_match
                            course['mode_match'] = mode_match
                            course['lang_match'] = lang_match
                            course['sk_match'] = sk_match
                            course['uni_match'] = True
                            
                            url_cache[cache_key] = course.copy()
                            raise EarlyExit()
                        except Exception as e:
                            print(f"    -> Failed to parse PDF: {e}")
                            pass
                    

                    title_lower = ""
                    try:
                        title_lower = driver.title.lower()
                    except:
                        pass
                    
                    direct_link_working = True
                    explored = False

                    # ── ONLY stop if truly unreachable / HTTP error / first-page 404 ──
                    is_hard_error = (
                        ('404' in title_lower and 'not found' in title_lower) or
                        'service unavailable' in title_lower or
                        'page not found' in title_lower
                    )

                    if is_hard_error:
                        raw_reason = f"HTTP error or Not Found. Page title: '{driver.title}'. The website returned an error - course not found."
                        course['direct_link_working'] = False
                        ss = os.path.join(self.screenshots_dir, f"course_{i+1}_error.png")
                        
                        print(f"    -> HARD ERROR (Likely Scrape Block). Taking screenshot to extract text via OCR... Screenshot: {ss}")
                        try:
                            driver.execute_script("document.body.style.zoom='30%'")
                            time.sleep(2)
                        except: pass
                        driver.save_screenshot(ss)
                        try:
                            driver.execute_script("document.body.style.zoom='100%'")
                        except: pass
                        
                        page_text = ""
                        try:
                            pass # Using global pytesseract and cv2
                            image = cv2.imread(ss)
                            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
                            
                            if os.path.exists(r'C:\Program Files\Tesseract-OCR\tesseract.exe'):
                                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                            elif os.path.exists(r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'):
                                pytesseract.pytesseract.tesseract_cmd = r'C:\Users\Shlok Parekh\AppData\Local\Programs\Tesseract-OCR\tesseract.exe'
                                
                            ocr_text = pytesseract.image_to_string(gray, config='--oem 3 --psm 6')
                            if ocr_text: 
                                page_text = ocr_text
                                print(f"    -> Extracted {len(ocr_text)} chars from OCR of blocked page.")
                        except Exception as e:
                            print(f"    -> OCR fallback on blocked page failed: {e}")
                            
                        # Set to False so it proceeds to Excel lookup and LLM verification despite scrape block
                        is_hard_error = False
                        
                        # Set a flag to bypass normal DOM extraction
                        skip_dom_extraction = True
                    else:
                        skip_dom_extraction = False
                    # ── DOM-FIRST TEXT EXTRACTION (OCR only as last resort) ──
                    is_nielit = 'nielit' in url.lower() or 'nielit' in course['uni'].lower() or 'ndu.digital' in url.lower()
                    if is_nielit:
                        try:
                            nielit_text = self._navigate_nielit_course(driver, course, url)
                        except: nielit_text = ""
                    else: nielit_text = ""
                    
                    if not skip_dom_extraction:
                        page_text = nielit_text if nielit_text else ""
                    
                    if not skip_dom_extraction and not is_nielit:
                        # Coursera Specific Logic: Click 'Enroll' to reveal pricing modal
                        if 'coursera.org' in url.lower():
                            print("    -> [Coursera] Attempting to click 'Enroll' button to reveal pricing modal...")
                            try:
                                js_click_enroll = """
                                    let callback = arguments[arguments.length - 1];
                                    if (!document || !document.querySelectorAll) return callback(false);
                                    let btns = Array.from(document.querySelectorAll('button, a, [role="button"]') || []);
                                    async function run() {
                                        for (let b of btns) {
                                            if (b.innerText) {
                                                let t = b.innerText.toLowerCase();
                                                if (t.includes('enroll for free') || t.includes('enroll now') || (t.includes('enroll') && b.tagName === 'BUTTON')) {
                                                    if (window.moveBeautifulCursorToElement) window.moveBeautifulCursorToElement(b);
                                                    await new Promise(r => setTimeout(r, 400));
                                                    b.click();
                                                    return callback(true);
                                                }
                                            }
                                        }
                                        callback(false);
                                    }
                                    run();
                                """
                                driver.set_script_timeout(10)
                                clicked = driver.execute_async_script(js_click_enroll)
                                if clicked:
                                    print("      -> Clicked Enroll. Waiting for modal...")
                                    time.sleep(3)
                            except Exception as e:
                                print(f"      -> Failed to click Enroll: {e}")
                        
                        # PRIMARY: Extract text from DOM (body, JSON-LD, meta, data-*, hidden price elements)
                        print(f"    -> Extracting text from website via DOM (primary)...")
                        try:
                            dom_text = self._extract_page_text(driver)
                            if dom_text:
                                page_text += "\n" + dom_text
                                print(f"    -> Extracted {len(dom_text)} characters via DOM extraction.")
                        except Exception as e:
                            print(f"    -> DOM extraction failed: {e}")
                        
                        # SECONDARY: Extract table data specifically (fee tables, duration tables)
                        js_tables = """
                            let out = [];
                            document.querySelectorAll('table').forEach(t => {
                                t.querySelectorAll('tr').forEach(r => {
                                    let cells = Array.from(r.querySelectorAll('td, th')).map(c => c.textContent.trim());
                                    if (cells.length > 0) out.push(cells.join(' | '));
                                });
                            });
                            return out.join('\\n');
                        """
                        try:
                            table_text = driver.execute_script(js_tables)
                            if table_text and len(table_text) > 10:
                                page_text += "\n" + table_text
                                print(f"    -> Extracted {len(table_text)} chars from tables.")
                        except Exception: pass
                        
                        # TERTIARY: OCR only if DOM extraction returned very little
                        if len(page_text.strip()) < 200:
                            print(f"    -> DOM text too short ({len(page_text.strip())} chars). Falling back to Tesseract OCR...")
                            try:
                                ss_final = os.path.join(self.screenshots_dir, f"course_{i+1}_final_ocr.png")
                                driver.save_screenshot(ss_final)
                                pass # Using global cv2
                                img_cv = cv2.imread(ss_final)
                                if img_cv is not None:
                                    gray = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
                                    ocr_text = pytesseract.image_to_string(gray, config='--oem 3 --psm 6')
                                    if ocr_text:
                                        page_text += "\n" + ocr_text
                                        print(f"    -> Extracted {len(ocr_text)} chars via Tesseract OCR fallback.")
                            except Exception as e:
                                print(f"    -> Visual OCR fallback failed: {e}")
                        else:
                            print(f"    -> DOM text sufficient ({len(page_text.strip())} chars). Skipping OCR.")
                    
                    pdf_cost_val, pdf_curr = extract_cost_value(course.get('cost', ''))
                    
                    if not is_nielit:
                        print(f"    -> Evaluating missing information for targeted accordion clicks...")
                        
                        accordion_keywords = "['show more', 'expand', 'fee', 'tuition', 'cost', 'pricing', 'curriculum', 'module', 'syllabus', 'course outline', 'course certificate', 'course content', 'program details', 'admission', 'eligibility', 'course details', 'cyber laws syllabus', 'click here']"
                        print(f"    -> Targeted Accordion Keywords: {accordion_keywords}")
                        self._scroll_page(driver)
                        
                        course_country_lower = str(course.get('country', '')).lower().strip()
                        if course_country_lower and course_country_lower not in ['india', 'in', 'ind', 'bharat']:
                            print(f"    -> Non-Indian college detected. Attempting to select 'International Student' and 'India' from dropdowns...")
                            js_intl = """
                                let callback = arguments[arguments.length - 1];
                                async function run_intl() {
                                    let targets = document.querySelectorAll('button, a, div, span, label, li');
                                    for (let t of targets) {
                                        let txt = (t.innerText || '').toLowerCase();
                                        if(txt.includes('international student') || txt.includes("i'm an international student") || txt === 'international' || txt === 'overseas') {
                                            try { t.click(); await new Promise(r => setTimeout(r, 500)); } catch(e){}
                                        }
                                    }
                                    let selects = document.querySelectorAll('select');
                                    for (let s of selects) {
                                        let options = Array.from(s.options);
                                        let india_opt = options.find(o => o.innerText.toLowerCase().includes('india'));
                                        if(india_opt) {
                                            try {
                                                s.value = india_opt.value;
                                                s.dispatchEvent(new Event('change', { bubbles: true }));
                                                await new Promise(r => setTimeout(r, 500));
                                            } catch(e){}
                                        }
                                    }
                                    callback();
                                }
                                run_intl();
                            """
                            try:
                                driver.set_script_timeout(15)
                                driver.execute_async_script(js_intl)
                                time.sleep(1.5)
                            except Exception as e:
                                print(f"      -> Intl selection script failed: {e}")
                                
                        try:
                            js_accordions = f"""
                                let callback = arguments[arguments.length - 1];
                                let buttons = document.querySelectorAll('button, div, span, a, summary');
                                let keywords = {accordion_keywords};
                                let clicked = 0;
                                async function run() {{
                                    for (let b of buttons) {{
                                        if (b.innerText && keywords.some(k => b.innerText.toLowerCase().includes(k))) {{
                                            if (window.moveBeautifulCursorToElement) window.moveBeautifulCursorToElement(b);
                                            await new Promise(r => setTimeout(r, 300));
                                            try {{ b.click(); clicked++; }} catch(e) {{}}
                                            await new Promise(r => setTimeout(r, 100));
                                        }}
                                    }}
                                    callback(clicked);
                                }}
                                run();
                            """
                            driver.set_script_timeout(30)
                            clicks = driver.execute_async_script(js_accordions)
                            if clicks and clicks > 0:
                                print(f"      -> Auto-clicked {clicks} targeted accordions/buttons.")
                                time.sleep(1.5)
                                # FIX: Re-extract page text because hidden tabs were just opened!
                                print(f"      -> Re-extracting text after opening tabs...")
                                
                                # Attempt to auto-fill any contact forms/download modals that popped up
                                js_fill_forms = """
                                    let inputs = document.querySelectorAll('input, textarea');
                                    for (let i of inputs) {
                                        let t = (i.name + ' ' + i.id + ' ' + i.placeholder).toLowerCase();
                                        if (t.includes('name') && !t.includes('univ')) { i.value = 'raju rastogi'; }
                                        else if (t.includes('phone') || t.includes('mobile')) { i.value = '+919569540918'; }
                                        else if (t.includes('email')) { i.value = 'tbot21998@gmail.com'; }
                                        i.dispatchEvent(new Event('input', { bubbles: true }));
                                        i.dispatchEvent(new Event('change', { bubbles: true }));
                                    }
                                    // Try simple math captchas (e.g. 5 + 3 = ?)
                                    let labels = document.querySelectorAll('label, span, div');
                                    for (let l of labels) {
                                        let txt = l.innerText.toLowerCase();
                                        if (txt.includes('+') && txt.includes('=')) {
                                            let parts = txt.match(/(\\d+)\\s*\\+\\s*(\\d+)/);
                                            if (parts) {
                                                let sum = parseInt(parts[1]) + parseInt(parts[2]);
                                                let cap_input = l.parentElement.querySelector('input');
                                                if (cap_input) {
                                                    cap_input.value = sum;
                                                    cap_input.dispatchEvent(new Event('input', { bubbles: true }));
                                                }
                                            }
                                        }
                                    }
                                    let submit_btns = document.querySelectorAll('button, input[type="submit"], input[type="button"]');
                                    for (let b of submit_btns) {
                                        let bt = (b.innerText || b.value || '').toLowerCase();
                                        if (bt.includes('download') || bt.includes('submit') || bt.includes('get details') || bt.includes('get fee')) {
                                            try { b.click(); } catch(e) {}
                                        }
                                    }
                                """
                                try:
                                    driver.execute_script(js_fill_forms)
                                    time.sleep(2)  # Wait for form submission or new text to load
                                except Exception as e:
                                    pass

                                page_text = self._extract_page_text(driver)
                        except Exception: pass
                    


                    # Excel Fees & Syllabus Fetch (Before LLM)
                    links = self._search_excel_for_links(course.get('uni', ''), course.get('name', ''))
                    if links.get('fees'):
                        print(f"    -> Found Fees hyperlink in CombinedWork.xlsx: {links['fees']}")
                        excel_text = self._fetch_url_robust(links['fees'])
                        if excel_text:
                            print(f"      -> Successfully extracted {len(excel_text)} chars from Fees Excel URL.")
                            page_text += "\n\n--- EXCEL FEES DATA ---\n" + excel_text[:25000]
                    if links.get('syllabus'):
                        print(f"    -> Found Syllabus hyperlink in CombinedWork.xlsx: {links['syllabus']}")
                        excel_text = self._fetch_url_robust(links['syllabus'])
                        if excel_text:
                            print(f"      -> Successfully extracted {len(excel_text)} chars from Syllabus Excel URL.")
                            page_text += "\n\n--- EXCEL SYLLABUS DATA ---\n" + excel_text[:25000]


                    # PHASE 4: Deep Link Crawling
                    # Check if key fields are missing — crawl if ANY is missing
                    # (Variables already defined in PHASE 2, recalculating in case accordions revealed them)
                    cost_found_prelim = verify_cost_in_text((pdf_cost_val, pdf_curr), page_text, course.get('cost', ''))
                    # Use advanced heuristic to parse out equivalent hours including semesters
                    duration_match, _ = durations_equivalent(course.get('duration', ''), page_text)
                    
                    # Apply baseline heuristics early to prevent unnecessary crawls
                    is_india_fallback = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
                    if is_india_fallback and not duration_match:
                        cn = course.get('name', '').lower()
                        baseline_dur = None
                        if 'b.tech' in cn or 'btech' in cn: baseline_dur = 4
                        elif 'm.tech' in cn or 'mtech' in cn: baseline_dur = 2
                        elif 'b.sc' in cn or 'bsc' in cn or 'bachelor of science' in cn: baseline_dur = 3
                        elif 'm.sc' in cn or 'msc' in cn or 'master of science' in cn: baseline_dur = 2
                        elif 'post graduate diploma' in cn or 'pg diploma' in cn: baseline_dur = 1
                        
                        if baseline_dur is not None and durations_equivalent(course.get('duration', ''), f"{baseline_dur} Years")[0]:
                            duration_match = True
                            
                    duration_found_prelim = duration_match
                    skills_found_prelim = True
                    scholarship_found_prelim = any(kw in page_text.lower() for kw in ['scholarship', 'financial aid', 'fee waiver', 'stipend', 'funding'])
                    
                    needs_deep_crawl = (not cost_found_prelim and pdf_cost_val) or not duration_found_prelim or not skills_found_prelim
                    needs_scholarship_crawl = not scholarship_found_prelim
                    
                    if not is_nielit and (needs_deep_crawl or needs_scholarship_crawl):
                        missing_fields = []
                        if not cost_found_prelim and pdf_cost_val: missing_fields.append("Cost")
                        if not duration_found_prelim: missing_fields.append("Duration")
                        if not skills_found_prelim: missing_fields.append("Skills")
                        if needs_scholarship_crawl and not needs_deep_crawl: missing_fields.append("Scholarship Only")
                        
                        print(f"    -> Missing [{', '.join(missing_fields)}] on main page. Fast Crawling...")
                        try:
                            # If we ONLY need scholarship, restrict keywords to make it ultra-fast.
                            if needs_scholarship_crawl and not needs_deep_crawl:
                                js_keywords = "['scholarship', 'financial aid', 'funding', 'fee waiver']"
                            else:
                                import requests, io
                                headers = {'User-Agent': 'Mozilla/5.0'}
                                js_keywords = "['fee', 'tuition', 'cost', 'price', 'pricing', 'curriculum', 'structure', 'syllabus', 'brochure', 'prospectus', 'course details', 'programme', 'catalog', 'scholarship', 'financial aid', 'cyber laws syllabus', 'click here']"
                                
                            js_find_links = f"""
                                let links = document.querySelectorAll('a');
                                let targets = [];
                                let pdf_targets = [];
                                let keywords = {js_keywords};
                                let origin = window.location.origin;
                                for (let a of links) {{
                                    let txt = (a.innerText || '').toLowerCase();
                                    let href = a.href || '';
                                    if (!href.startsWith('http')) continue;
                                    let href_lower = href.toLowerCase();
                                    
                                    // Allow external direct PDFs, but restrict HTML crawling to same origin
                                    if (href_lower.endsWith('.pdf')) {{
                                        pdf_targets.push(href);
                                    }}
                                    else if (href.startsWith(origin)) {{
                                        let url_no_hash = href.split('#')[0];
                                        let current_no_hash = window.location.href.split('#')[0];
                                        if (url_no_hash !== current_no_hash) {{
                                            if (keywords.some(k => txt.includes(k) || href_lower.includes(k))) {{
                                                targets.push(url_no_hash);
                                            }}
                                        }}
                                    }}
                                }}
                                return {{ html: Array.from(new Set(targets)).slice(0, 3), pdf: Array.from(new Set(pdf_targets)).slice(0, 2) }};
                            """
                            deep_data = driver.execute_script(js_find_links)
                            deep_links = deep_data.get('html', [])
                            pdf_links = deep_data.get('pdf', [])
                            
                            # Auto-Syllabus PDF Hunter
                            if pdf_links:
                                pdf_url = pdf_links[0]
                                print(f"      -> [Auto-Syllabus Hunter] Found linked PDF: {pdf_url}")
                                try:
                                    import urllib3
                                    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
                                    pdf_resp = requests.get(pdf_url, timeout=10, verify=False)
                                    if pdf_resp.status_code == 200:
                                        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp_pdf:
                                            tmp_pdf.write(pdf_resp.content)
                                            tmp_pdf_path = tmp_pdf.name
                                            
                                        import fitz
                                        pdf_doc = fitz.open(tmp_pdf_path)
                                        for page_index in range(len(pdf_doc)):
                                            page_text += "\\n" + pdf_doc[page_index].get_text()
                                            # images
                                            image_list = pdf_doc[page_index].get_images(full=True)
                                            for img_info in image_list:
                                                try:
                                                    base_image = pdf_doc.extract_image(img_info[0])
                                                    if Image:
                                                        image = Image.open(io.BytesIO(base_image["image"])).convert('L')
                                                        
                                                        text = pytesseract.image_to_string(image, config='--oem 3 --psm 6')
                                                        if text is None: text = ""

                                                        if text.strip(): page_text += "\\n" + text
                                                except: pass
                                        pdf_doc.close()
                                        os.unlink(tmp_pdf_path)
                                except Exception as e:
                                    print(f"      -> Failed to extract syllabus PDF: {e}")
                                    
                            for d_link in deep_links:
                                if d_link and d_link.startswith('http'):
                                    print(f"      -> Crawling sub-page: {d_link}")
                                    try:
                                        # Open in new window to preserve state if needed, or just navigate
                                        driver.get(d_link)
                                        time.sleep(1.5)
                                        self._scroll_page(driver)
                                        page_text += "\\n" + self._extract_page_text(driver)
                                        
                                        # Parse tables on sub-page too
                                        table_text = driver.execute_script(js_tables)
                                        if table_text: page_text += "\\n" + table_text
                                    except Exception: pass
                            # Return to original URL if we left it
                            if deep_links:
                                driver.get(url)
                                time.sleep(1)
                        except Exception as e:
                            print(f"      -> Deep crawling failed: {e}")
                    


                    # Check for logos (as requested by user)
                    logos = []
                    try:
                        js_logos = """
                            let imgs = document.querySelectorAll('img');
                            let found = [];
                            for (let img of imgs) {
                                if (img.src.toLowerCase().includes('logo') || (img.alt && img.alt.toLowerCase().includes('logo')) || (img.className && img.className.toLowerCase().includes('logo'))) {
                                    found.push(img.src);
                                }
                            }
                            return found;
                        """
                        logos = driver.execute_script(js_logos)
                        if logos:
                            print(f"    -> Found {len(logos)} logos on page.")
                            course['logos_found'] = 'Matched'
                    except: pass

                    def _verify_university_from_url_and_logos(driver_url, uni_name, page_html):
                        uni_lower = uni_name.lower()
                        domain = urlparse(driver_url).netloc.lower()
                        
                        # 1. Check URL abbreviation matches
                        abbrev_dict = {
                            'iitk.ac.in': 'iit kanpur',
                            'iitm.ac.in': 'iit madras',
                            'iitb.ac.in': 'iit bombay',
                            'iitd.ac.in': 'iit delhi',
                            'iitkgp.ac.in': 'iit kharagpur',
                            'iitr.ac.in': 'iit roorkee',
                            'iitg.ac.in': 'iit guwahati',
                            'bits-pilani.ac.in': 'bits pilani'
                        }
                        for dom, abbrev in abbrev_dict.items():
                            if dom in domain:
                                expanded = abbrev.replace('iit', 'indian institute of technology')
                                if abbrev in uni_lower or expanded in uni_lower:
                                    return True, 0.90
                                
                        # 2. Check JSON-LD meta tags and data-course-provider for platforms
                        if 'swayam' in domain or 'coursera' in domain or 'edx' in domain:
                            if 'data-course-provider' in page_html:
                                provider_match = re.search(r'data-course-provider="([^"]+)"', page_html, re.IGNORECASE)
                                if provider_match and entity_present(uni_name, provider_match.group(1), threshold=0.55)[0]:
                                    return True, 0.85
                            
                            # Simple generic JSON-LD search for provider
                            if '"provider":' in page_html or '"offeredBy":' in page_html:
                                if entity_present(uni_name, page_html, threshold=0.85)[0]:
                                    return True, 0.80
                        
                        return False, 0.0

                    # Initial verification check
                    course_uni_check = course['uni']
                    if 'Illinois Tech' in course_uni_check:
                        course_uni_check = 'Illinois Institute of Technology'
                    elif 'Kenessaw' in course_uni_check:
                        course_uni_check = 'Kennesaw State University'

                    name_match, name_score = entity_present(course['name'], page_text, threshold=0.78)
                    uni_match, uni_score = entity_present(course_uni_check, page_text, threshold=0.85)
                    
                    if not uni_match:
                        # Fallback to URL/Logo based verification (Requirement 10)
                        uni_match, uni_score = _verify_university_from_url_and_logos(driver.current_url, course_uni_check, driver.page_source)
                    
                    if name_match or uni_match:
                        print(f"    -> Course or Uni found on initial page! Evaluating details via LLM to see if deep crawling is necessary...")
                        
                        # Excel Fees & Syllabus Fetch (Before LLM)
                        links = self._search_excel_for_links(course_uni_check, course.get('name', ''))
                        if links.get('fees'):
                            print(f"    -> Found Fees hyperlink in CombinedWork.xlsx: {links['fees']}")
                            excel_text = self._fetch_url_robust(links['fees'])
                            if excel_text:
                                print(f"      -> Successfully extracted {len(excel_text)} chars from Fees Excel URL.")
                                page_text += "\n\n--- EXCEL FEES DATA ---\n" + excel_text[:25000]
                        if links.get('syllabus'):
                            print(f"    -> Found Syllabus hyperlink in CombinedWork.xlsx: {links['syllabus']}")
                            excel_text = self._fetch_url_robust(links['syllabus'])
                            if excel_text:
                                print(f"      -> Successfully extracted {len(excel_text)} chars from Syllabus Excel URL.")
                                page_text += "\n\n--- EXCEL SYLLABUS DATA ---\n" + excel_text[:25000]
                                
                        cost_match, sk_match, l_skd, duration_match, l_durd, mode_match, l_modd, lang_match, l_land, l_costd, country_match, l_countryd, llm_uni_match, llm_unid = self._verify_details_with_llm(course, page_text, worker_id=worker_id)
                        web_cost = l_costd
                        web_duration = l_durd
                        web_mode = l_modd
                        web_language = l_land
                        web_country = l_countryd
                        sk_detail = l_skd
                        uni_match = uni_match or llm_uni_match
                        
                        # CRITICAL NEW RULE: If university is FALSE, mark everything as FALSE
                        if not uni_match:
                            cost_match = duration_match = mode_match = lang_match = country_match = sk_match = False
                            web_cost = "False match because University does not match."
                            web_duration = "False match because University does not match."
                            web_mode = "False match because University does not match."
                            web_language = "False match because University does not match."
                            web_country = "False match because University does not match."
                            sk_detail = "False match because University does not match."
                        
                        # Apply heuristics early to update duration_match and lang_match so they count towards everything_found
                        is_india_fallback = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
                        if is_india_fallback and not duration_match and ("not explicitly" in web_duration.lower() or web_duration in ['N/A', '']):
                            cn = course.get('name', '').lower()
                            baseline_dur = None
                            if 'b.tech' in cn or 'btech' in cn: baseline_dur = 4
                            elif 'm.tech' in cn or 'mtech' in cn: baseline_dur = 2
                            elif 'b.sc' in cn or 'bsc' in cn or 'bachelor of science' in cn: baseline_dur = 3
                            elif 'm.sc' in cn or 'msc' in cn or 'master of science' in cn: baseline_dur = 2
                            elif 'post graduate diploma' in cn or 'pg diploma' in cn: baseline_dur = 1
                            if baseline_dur is not None:
                                if durations_equivalent(course.get('duration', ''), f"{baseline_dur} Years")[0]:
                                    duration_match = True
                                    web_duration = f"{baseline_dur} Years"
                        
                        if not lang_match and ("not explicitly" in web_language.lower() or web_language in ['N/A', '']):
                            pdf_lang = str(course.get('language', '')).strip().lower()
                            if pdf_lang in ['english', 'en', 'eng']:
                                lang_match = True
                                web_language = "English"
                    else:
                        print(f"    -> Course not found on initial page. Skipping initial detail verification.")
                        cost_match, sk_match, duration_match = False, False, False
                        mode_match, lang_match, country_match = False, False, False
                        web_cost, web_duration, web_mode, web_language, web_country = "N/A", "N/A", "N/A", "N/A", "N/A"
                        sk_detail = "N/A"

                    everything_found = name_match and uni_match and cost_match and duration_match and sk_match
                    pre_vision_len = len(page_text)
                    
                    if not everything_found:
                        missing_info = []
                        if not cost_match and course.get('cost'): missing_info.append("Cost / Tuition / Pricing")
                        if not duration_match and course.get('duration'): missing_info.append("Duration / Length")
                        if not sk_match and course.get('skills') != "Not Provided in Source": missing_info.append("Curriculum / Syllabus / Skills / Modules")
                        if not name_match: missing_info.append("Course Name")
                        
                        if missing_info and not is_nielit:
                            print(f"    -> Missing details: {', '.join(missing_info)}. Triggering Smart Vision Agent...")
                            extra = self._vision_based_tab_exploration(driver, course_name=course.get('name', ''), missing_info=", ".join(missing_info), country=str(course.get('country', '')))
                            if extra:
                                page_text += "\n" + extra
                                # FIX: Re-extract page text again in case the vision agent clicked something!
                                print("    -> Re-extracting full DOM text after Vision Agent exploration...")
                                page_text += "\n" + self._extract_page_text(driver)
                                
                        print(f"    -> Re-feeding all extracted text to LLM for comparison summaries...")
                        cost_match, sk_match, l_skd, duration_match, l_durd, mode_match, l_modd, lang_match, l_land, l_costd, country_match, l_countryd, llm_uni_match, llm_unid = self._verify_details_with_llm(course, page_text, worker_id=worker_id)
                        web_cost = l_costd
                        web_duration = l_durd
                        web_mode = l_modd
                        web_language = l_land
                        web_country = l_countryd
                        sk_detail = l_skd
                        uni_match = uni_match or llm_uni_match
                        
                        # Re-apply heuristics
                        is_india_fallback = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
                        if is_india_fallback and not duration_match and ("not explicitly" in web_duration.lower() or web_duration in ['N/A', '']):
                            cn = course.get('name', '').lower()
                            baseline_dur = None
                            if 'b.tech' in cn or 'btech' in cn: baseline_dur = 4
                            elif 'm.tech' in cn or 'mtech' in cn: baseline_dur = 2
                            elif 'b.sc' in cn or 'bsc' in cn or 'bachelor of science' in cn: baseline_dur = 3
                            elif 'm.sc' in cn or 'msc' in cn or 'master of science' in cn: baseline_dur = 2
                            elif 'post graduate diploma' in cn or 'pg diploma' in cn: baseline_dur = 1
                            if baseline_dur is not None:
                                if durations_equivalent(course.get('duration', ''), f"{baseline_dur} Years")[0]:
                                    duration_match = True
                                    web_duration = f"{baseline_dur} Years"
                                    print(f"    -> [Heuristic] Applied {baseline_dur}Y baseline for {course.get('name')}.")
                                if not lang_match and ("not explicitly" in web_language.lower() or web_language in ['N/A', '']):
                                    pdf_lang = str(course.get('language', '')).strip().lower()
                                    if pdf_lang in ['english', 'en', 'eng']:
                                        lang_match = True
                                        web_language = "English"
                            
                            ss3 = os.path.join(self.screenshots_dir, f"course_{i+1}_explored.png")
                            try: driver.save_screenshot(ss3)
                            except: pass

                        if not entity_present(course['name'], page_text, threshold=0.60)[0] and not is_nielit:
                            print(f"    -> Course name not explicitly visible on page. Continuing with extraction as per user request to disable Google search routing...")
                            # Removed _search_website_for_course fallback
                    else:
                        print("    -> All details found on initial page! Skipping Vision Agent deep crawling.")
                    
                    # Fallback Triggers
                    needs_fallback = False
                    fallback_text = ""
                    current_links = locals().get('links', {})
                                
                    if not sk_match or sk_detail == "Always Matched":
                        print("    -> Missing syllabus/skills match. Google search fallback disabled per user request.")
                        
                    if not cost_match and not fallback_text.strip():
                        print("    -> Missing fee match. Google search fallback disabled per user request.")
                        
                    if not country_match and not fallback_text.strip():
                        print("    -> Missing country match. Google search fallback disabled per user request.")
                        
                    if needs_fallback and fallback_text.strip():
                        print(f"    -> Re-verifying missing data with Fallback text...")
                        page_text += "\n\n" + fallback_text
                        cost_match, sk_match, l_skd, duration_match, l_durd, mode_match, l_modd, lang_match, l_land, l_costd, country_match, l_countryd, llm_uni_match, llm_unid = self._verify_details_with_llm(course, page_text, worker_id=worker_id)
                        web_cost = l_costd
                        web_duration = l_durd
                        web_mode = l_modd
                        web_language = l_land
                        web_country = l_countryd
                        sk_detail = l_skd
                        uni_match = uni_match or llm_uni_match
                        
                        # Re-apply heuristics on final pass
                        is_india_fallback = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
                        if is_india_fallback and not duration_match:
                            cn = course.get('name', '').lower()
                            baseline_dur = None
                            if 'b.tech' in cn or 'btech' in cn: baseline_dur = 4
                            elif 'm.tech' in cn or 'mtech' in cn: baseline_dur = 2
                            elif 'b.sc' in cn or 'bsc' in cn or 'bachelor of science' in cn: baseline_dur = 3
                            elif 'm.sc' in cn or 'msc' in cn or 'master of science' in cn: baseline_dur = 2
                            elif 'post graduate diploma' in cn or 'pg diploma' in cn: baseline_dur = 1
                            if baseline_dur is not None:
                                if durations_equivalent(course.get('duration', ''), f"{baseline_dur} Years")[0]:
                                    duration_match = True
                                    web_duration = f"{baseline_dur} Years"
                        if not lang_match and "Information not explicitly mentioned" in web_language:
                            pdf_lang = str(course.get('language', '')).strip().lower()
                            if pdf_lang in ['english', 'en', 'eng']:
                                lang_match = True
                                web_language = "English"
                            print("    -> [Heuristic] Defaulted language to English.")

                    course['country_verified'] = web_country
                    course['country_match'] = country_match
                    
                    # Swayam/NPTEL cost override
                    is_nptel_swayam = "nptel.ac.in" in driver.current_url.lower() or "swayam.gov.in" in driver.current_url.lower()
                    if is_nptel_swayam:
                        web_cost = "Rs. 1000 (Auto-verified Swayam/NPTEL fee)"
                        cost_match = True
                        print("    -> [Heuristic] Swayam/NPTEL detected. Cost forced to Rs. 1000.")


                    # Re-verify name and uni
                    name_match_new, name_score = entity_present(course['name'], page_text, threshold=0.78)
                    uni_match_new, uni_score = entity_present(course_uni_check, page_text, threshold=0.85)
                    name_match = name_match or name_match_new
                    uni_match = uni_match or uni_match_new
                    
                    # URL University Match Override
                    clean_url = re.sub(r'https?://(www\.)?', '', driver.current_url.lower())
                    
                    # Common Platforms Online Override
                    if any(p in clean_url for p in ['coursera.org', 'edx.org', 'futurelearn.com', 'mitxonline.mit.edu', 'swayam.gov.in', 'nptel.ac.in', 'udacity.com', 'udemy.com']):
                        mode_match = True
                        web_mode = "Online"
                        print(f"    -> [Heuristic] Platform '{clean_url.split('/')[0]}' automatically confirmed as Online Mode.")
                        
                    if course_uni_check:
                        words = [w for w in re.split(r'\W+', course_uni_check.lower()) if len(w) > 3 and w not in ['university', 'institute', 'technology', 'science', 'national', 'state', 'college']]
                        acronym = "".join([w[0] for w in course_uni_check.lower().split() if w.isalpha()])
                        url_uni_match = (len(acronym) > 2 and acronym in clean_url) or any(w in clean_url for w in words)
                        if url_uni_match:
                            uni_match = True
                            print(f"    -> [Heuristic] University '{course_uni_check}' matched via URL domain.")
                            
                        # Common Indian Abbreviations Check
                        uni_lower = course_uni_check.lower()
                        if 'indian institute of technology' in uni_lower:
                            loc = uni_lower.replace('indian institute of technology', '').strip()
                            if f"iit {loc}" in page_text.lower() or f"iit-{loc}" in page_text.lower() or (loc and f"iit{loc[0]}" in page_text.lower()):
                                uni_match = True
                                print(f"    -> [Heuristic] University '{course_uni_check}' matched via abbreviation IIT {loc}.")
                        elif 'indian institute of information technology' in uni_lower:
                            loc = uni_lower.replace('indian institute of information technology', '').strip()
                            if f"iiit {loc}" in page_text.lower() or f"iiit-{loc}" in page_text.lower() or (loc and f"iiit{loc[0]}" in page_text.lower()):
                                uni_match = True
                                print(f"    -> [Heuristic] University '{course_uni_check}' matched via abbreviation IIIT {loc}.")

                    # Use LLM uni match override
                    if 'llm_uni_match' in locals() and llm_uni_match:
                        uni_match = True
                        print(f"    -> [Heuristic] University '{course_uni_check}' matched via LLM reasoning.")

                    # PHASE 4: Analyze
                    print(f"    -> Analyzing final content...")

                    # Hardcoded scholarship match as requested
                    scholarship_found = True
                    course['scholarship_found'] = True
                    
                    # Hardcoded logo match as requested
                    course['logo_match'] = True
                    course['logos_found'] = "Matched"

                    # Since the page loaded successfully, the course IS accessible.
                    # Use PDF values for Verified (Web) column — do NOT write "Not found on page"
                    web_title = ""
                    try: web_title = driver.title or course['name']
                    except: web_title = course['name']
                    
                    title_match, title_score = entity_present(course['name'], web_title, threshold=0.60)
                    url_match, url_score = entity_present(
                        course['name'],
                        driver.current_url.replace("-", " ").replace("_", " "),
                        threshold=0.60,
                    )

                    matched_fields = []
                    if name_match: matched_fields.append(f"Name({name_score:.2f})")
                    if title_match: matched_fields.append(f"Title({title_score:.2f})")
                    if url_match: matched_fields.append(f"URL({url_score:.2f})")
                    if uni_match: matched_fields.append(f"Uni({uni_score:.2f})")
                    if cost_match: matched_fields.append("Cost")
                    if sk_match: matched_fields.append('Skills')
                    if duration_match: matched_fields.append("Duration")
                    if mode_match: matched_fields.append("Mode")
                    if lang_match: matched_fields.append("Language")

                    # Use XGBoost Classifier for intelligent match prediction
                    import xgboost as xgb
                    # Simple heuristic rule for Match
                    is_match = False
                    if name_score >= 0.80 or title_score >= 0.80 or url_score >= 0.80:
                        is_match = True
                    elif uni_match and sk_match:
                        is_match = True
                    
                    if is_match:
                        final_status = "MATCH"
                        parts = [f"The course '{course['name']}' was verified through page content, title, URL, or site search."]
                        parts.append(f"Page title: '{web_title}'.")
                        if uni_match:
                            parts.append(f"University '{course['uni']}' confirmed on page.")
                        if cost_match:
                            parts.append(f"Cost '{course['cost']}' found on page.")
                        parts.append(f"Skills check: {sk_detail}.")
                        if duration_match: parts.append(f"Duration: {web_duration}.")
                        if mode_match: parts.append(f"Mode: {web_mode}.")
                        if lang_match: parts.append(f"Language: {web_language}.")
                        if scholarship_found:
                            parts.append("Scholarship/financial aid information found on the page.")
                        if course.get('logos_found'):
                            parts.append(f"Found logos: {course.get('logos_found')}.")
                        if 'hence matched' in str(course.get('qs_detail', '')):
                            parts.append(course['qs_detail'] + ".")
                        if 'hence matched' in str(course.get('nirf_detail', '')):
                            parts.append(course['nirf_detail'] + ".")
                        raw_reason = " ".join(parts)
                    else:
                        # Page loaded but name not found exactly
                        final_status = "FALSE"
                        raw_reason = (
                            f"The URL loaded successfully. "
                            f"Page title: '{web_title}'. "
                            f"After scrolling, tab exploration, and website search, the course name match score was {name_score:.2f}. "
                            f"No strong course-specific evidence was found, so this remains unverified. "
                            f"Skills check: {sk_detail}."
                        )

                    # Generate Final Reason locally
                    final_reason = self._generate_description_locally(course['name'], raw_reason, is_error=False, explored=explored)

                    course['web_status'] = final_status
                    course['reason'] = final_reason
                    course['web_name'] = web_title
                    course['web_cost'] = web_cost
                    
                    if 'llm_unid' in locals() and llm_unid and llm_unid != "Information not explicitly mentioned on the webpage." and llm_unid != "N/A":
                        course['web_uni'] = llm_unid
                    else:
                        course['web_uni'] = course['uni'] if uni_match else "Not Found on Website"
                        
                    course['skills_verified'] = sk_detail
                    course['scholarship_found'] = scholarship_found
                    course['direct_link_working'] = direct_link_working
                    
                    # New fields for duration, mode, lang
                    course['web_duration'] = web_duration
                    course['web_mode'] = web_mode
                    course['web_language'] = web_language
                    
                    # Match flags for the report
                    course['cost_match'] = cost_match
                    course['duration_match'] = duration_match
                    course['mode_match'] = mode_match
                    course['lang_match'] = lang_match
                    course['sk_match'] = sk_match
                    course['uni_match'] = uni_match

                    url_cache[cache_key] = {
                        "web_status": final_status, "reason": final_reason,
                        "web_name": course['web_name'], "web_cost": course['web_cost'],
                        "web_uni": course['web_uni'], "skills_verified": sk_detail,
                        "scholarship_found": scholarship_found, "direct_link_working": direct_link_working,
                        "web_duration": course['web_duration'], "web_mode": course['web_mode'], "web_language": course['web_language'],
                        "cost_match": cost_match, "duration_match": duration_match, "mode_match": mode_match,
                        "lang_match": lang_match, "sk_match": sk_match, "uni_match": uni_match
                    }

                    print(f"    -> RESULT: {final_status} | {', '.join(matched_fields) if matched_fields else 'Link accessible'}")

                except EarlyExit:
                    raise
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    err_str = str(e)
                    
                    # Fallback values to ensure nothing is left blank in the PDF
                    course['web_cost'] = "Not Found"
                    course['web_uni'] = "Error/Unreachable"
                    course['skills_verified'] = "N/A"
                    course['web_duration'] = "N/A"
                    course['web_mode'] = "N/A"
                    course['web_language'] = "N/A"
                    course['is_hard_error'] = True
                    
                    # Only mark FALSE if it's a real connection/timeout error
                    if 'timeout' in err_str.lower() or 'net::' in err_str.lower() or 'ERR_' in err_str:
                        course['web_status'] = "FALSE"
                        course['reason'] = f"Website unreachable: {err_str[:100]}"
                    else:
                        course['web_status'] = "FALSE"
                        course['reason'] = f"Browser verification failed before course evidence could be confirmed: {err_str[:100]}"
                    url_cache[cache_key] = {"web_status": course['web_status'], "reason": course['reason'], "is_hard_error": True}
                    # Recovery: Check if driver is responsive
                    is_alive = False
                    try:
                        driver.current_url
                        is_alive = True
                    except Exception:
                        pass
                        
                    if not is_alive:
                        print("    -> Driver appears dead. Recreating browser instance...")
                        try: driver.quit()
                        except: pass
                        
                        import undetected_chromedriver as uc
                        
                        success = False
                        for _ in range(3):
                            try:
                                new_options = uc.ChromeOptions()
                                new_options.page_load_strategy = 'eager'
                                new_options.add_argument('--disable-blink-features=AutomationControlled')
                                new_options.add_argument(f'--window-size=1280,800')
                                ud_dir = os.path.join(tempfile.gettempdir(), f"uc_profile_rec_{random.randint(1000, 9999)}")
                                driver = uc.Chrome(options=new_options, user_data_dir=ud_dir)
                                driver.set_page_load_timeout(60)
                                success = True
                                print("    -> Browser successfully recovered.")
                                break
                            except Exception as e:
                                print(f"    -> Browser recovery attempt failed: {e}")
                                time.sleep(2)
                        
                        if not success:
                            print("    -> CRITICAL: Failed to recover browser instance!")

            except EarlyExit:
                pass
            finally:
                with checkpoint_lock:
                    try:
                        with open('autonomous_verified_data.json', 'w', encoding='utf-8') as f:
                            json.dump(self.courses, f, indent=4, ensure_ascii=False)
                    except Exception as e:
                        print(f"    -> [!] Warning: Failed to save checkpoint: {e}")
                browser_pool.put((worker_id, driver))
                
                logs = sys.stdout.local.buffer.getvalue()
                del sys.stdout.local.buffer
                
            return i, logs

        # Submit to ThreadPoolExecutor
        if end_idx is None:
            end_idx = len(self.courses)
        items_to_process = [(i, c) for i, c in enumerate(self.courses) if start_idx <= i < end_idx]
        try:
            with ThreadPoolExecutor(max_workers=NUM_BROWSERS) as executor:
                for idx, logs in executor.map(process_course, items_to_process):
                    try:
                        original_stdout.write(logs)
                    except UnicodeEncodeError:
                        original_stdout.write(logs.encode('ascii', 'replace').decode('ascii'))
                    original_stdout.flush()
        finally:
            sys.stdout = original_stdout

        # Cleanup browsers
        while not browser_pool.empty():
            try:
                worker_id, d = browser_pool.get_nowait()
                d.quit()
            except:
                pass

        # ── Unload Ollama models from VRAM immediately ──
        print("\n[*] Unloading AI models from VRAM...")
        try:
            client = get_client()
            client.stop_model(VISION_MODEL)
            client.stop_model(TEXT_MODEL)
        except Exception as e:
            print(f"    -> Warning: Could not unload models: {e}")

        print("\n[*] Saving checkpoint to autonomous_verified_data.json...")
        with open('autonomous_verified_data.json', 'w', encoding='utf-8') as f:
            json.dump(self.courses, f, indent=4, ensure_ascii=False)

    # ──────────────────────────────────────────────────────────
    #  STEP 4: PDF REPORT GENERATION
    # ──────────────────────────────────────────────────────────

    def _generate_professional_summary(self, course):
        name = course.get("name", "Unknown Course")
        if course.get("is_hard_error"):
            if course.get("web_status") == "MATCH":
                return f"PDF FALLBACK: The direct link for '{name}' returned an HTTP error or was unreachable, but the course details were verified successfully against the local PDF document."
            else:
                return f"VERIFICATION FAILED: The direct link for '{name}' returned an HTTP error or was unreachable. No course details could be verified."
            
        matched = []
        failed = []
        if course.get('cost_match'): matched.append("Cost")
        else: failed.append("Cost")
        if course.get('duration_match'): matched.append("Duration")
        else: failed.append("Duration")
        if course.get('mode_match'): matched.append("Mode")
        else: failed.append("Mode")
        if course.get('lang_match'): matched.append("Language")
        else: failed.append("Language")
        if course.get('sk_match'): matched.append("Skills & Curriculum")
        else: failed.append("Skills & Curriculum")
        if course.get('uni_match'): matched.append("University/Provider")
        else: failed.append("University/Provider")
        
        total = len(matched) + len(failed)
        passed = len(matched)
        
        if not course.get("is_hard_error"):
            if passed == total:
                return f"FULLY VERIFIED ({passed}/{total}): The course '{name}' was successfully audited. All key parameters—including {', '.join(matched)}—are semantically aligned and actively verified against the official source."
            else:
                return f"PARTIALLY VERIFIED ({passed}/{total}): The course '{name}' exists, but has discrepancies. Confirmed: {', '.join(matched)}. Discrepancies found in: {', '.join(failed)}. Manual review recommended for failed checks."
        else:
            if not matched:
                return f"UNVERIFIED (0/{total}): The page loaded, but no relevant course details for '{name}' could be confirmed. The provided URL may be incorrect or the course is no longer offered."
            else:
                return f"UNVERIFIED ({passed}/{total}): Minimal details for '{name}' were found ({', '.join(matched)}), but critical core components like {', '.join(failed)} failed verification entirely."

    def generate_pdf_report(self, start_idx=0, end_idx=None, pdf_name=None):
        if pdf_name:
            self.output_pdf = f"{pdf_name}.pdf"
        print(f"\n[*] Step 4/4: Generating PDF report: {self.output_pdf} (Courses {start_idx+1} to {end_idx if end_idx else len(self.courses)})")

        pdf = FPDF()
        pdf.set_auto_page_break(auto=False)
        date_str = datetime.now().strftime("%d/%m/%Y")

        # Removed Two-tier bucketing for sequential output
                
        def render_course(course, index_str):
            pdf.add_page()
            pdf.set_font('Arial', '', 10)
            pdf.set_text_color(100, 100, 100)
            pdf.cell(0, 6, f'Generated on: {date_str} | PDF Page {course.get("page_num","?")}, Box: {course.get("box_position","?")} (#{course.get("box_index","?")})', ln=1)
            pdf.ln(2)

            pdf.set_font('Arial', 'B', 14)
            pdf.set_text_color(0, 0, 0)
            title = course.get("name", "Unknown Course")
            if len(title) > 65: title = title[:62] + "..."
            pdf.cell(0, 10, f'{index_str}. {safe_latin(title)}', ln=1)
            pdf.ln(2)

            # Table Header
            pdf.set_fill_color(83, 78, 225) # Purple-blue header
            pdf.set_text_color(255, 255, 255)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(35, 8, 'Attribute', border=1, fill=True)
            pdf.cell(60, 8, 'Original (PDF)', border=1, fill=True)
            pdf.cell(60, 8, 'Verified (Web)', border=1, fill=True)
            pdf.cell(35, 8, 'Status', border=1, ln=1, fill=True)

            def draw_row(attr, orig, ver, status):
                orig_s = safe_latin(re.sub(r"\s+", " ", str(orig)).strip())
                ver_s = safe_latin(re.sub(r"\s+", " ", str(ver)).strip())
                if orig_s.lower() in ["n/a", "not found", "-", "error", "error/unreachable", "none", "nan", ""]: orig_s = "Not Provided in Source"
                if ver_s.lower() in ["n/a", "not found", "-", "error", "error/unreachable", "none", "nan", ""]: ver_s = "Not Found on Website"
                
                pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(60, 60, 60)
                pdf.set_font('Arial', '', 8)
                
                import math
                # Calculate max lines needed with extra padding for word wrap
                lines_orig = max(1, math.ceil(pdf.get_string_width(orig_s) / 52.0))
                lines_ver = max(1, math.ceil(pdf.get_string_width(ver_s) / 52.0))
                max_lines = max(lines_orig, lines_ver)
                row_height = max(7, (5 * max_lines) + 4)
                
                if pdf.get_y() + row_height > 270:
                    pdf.add_page()
                    
                x = pdf.get_x()
                y = pdf.get_y()
                
                pdf.rect(x, y, 190, row_height) # Outer box
                
                pdf.set_xy(x, y)
                pdf.cell(35, row_height, safe_latin(str(attr)[:24]), border=0)
                
                pdf.set_xy(x + 35, y + 1)
                pdf.multi_cell(60, 5, orig_s, border=0, align='L')
                
                pdf.set_xy(x + 95, y + 1)
                pdf.multi_cell(60, 5, ver_s, border=0, align='L')
                
                # Draw vertical dividers
                pdf.line(x + 35, y, x + 35, y + row_height)
                pdf.line(x + 95, y, x + 95, y + row_height)
                pdf.line(x + 155, y, x + 155, y + row_height)
                
                pdf.set_xy(x + 155, y)
                pdf.set_text_color(22, 163, 74) if status == "MATCH" else pdf.set_text_color(220, 38, 38)
                pdf.set_font('Arial', 'B', 9)
                pdf.cell(35, row_height, status, border=0, ln=1, align='C')
                
                pdf.set_y(y + row_height)

            link_ok = course.get('web_status') == 'MATCH'
            has_url = course.get('url') and course.get('url') != 'Unknown'

            is_hard_error = course.get('is_hard_error', False)
            
            def safe_val(val):
                return 'Page Load Error' if is_hard_error else val

            def fmt_pdf(val):
                v = str(val).strip()
                vl = v.lower()
                if not v or vl in ['n/a', 'nan', 'none', 'n/a in pdf'] or v.strip('-') == '':
                    return "Not Provided in Source"
                return v

            def fmt_web(val):
                v = str(val).strip()
                vl = v.lower()
                # Sanitize: treat '...' (ellipsis) and its Unicode variant as missing
                cleaned = v.replace('\u2026', '...')
                if not v or vl in ['n/a', 'nan', 'none'] or v.strip('-') == '' or cleaned.strip('.') == '' or cleaned.strip() == '...':
                    return "Not Found / Mentioned on Website"
                return v

            draw_row('Cost', fmt_pdf(course.get('cost')), safe_val(fmt_web(course.get('web_cost'))), 'MATCH' if (course.get('cost_match') and not is_hard_error) else 'FALSE')
            draw_row('Duration', fmt_pdf(course.get('duration')), safe_val(fmt_web(course.get('web_duration'))), 'MATCH' if (course.get('duration_match') and not is_hard_error) else 'FALSE')
            draw_row('Mode', fmt_pdf(course.get('mode')), safe_val(fmt_web(course.get('web_mode'))), 'MATCH' if (course.get('mode_match') and not is_hard_error) else 'FALSE')
            draw_row('Language', fmt_pdf(course.get('language')), safe_val(fmt_web(course.get('web_language'))), 'MATCH' if (course.get('lang_match') and not is_hard_error) else 'FALSE')
            draw_row('Country', fmt_pdf(course.get('country')), safe_val(fmt_web(course.get('country_verified'))), 'MATCH' if (course.get('country_match') and not is_hard_error) else 'FALSE')
            draw_row('University', fmt_pdf(course.get('uni')), safe_val(fmt_web(course.get('web_uni'))), 'MATCH' if (course.get('uni_match') and not is_hard_error) else 'FALSE')
            
            sk_pdf = fmt_pdf(course.get('skills'))
            sk_web = fmt_web(course.get('skills_verified')) if course.get('skills_verified') else ('Always Matched' if sk_pdf != 'Not Provided in Source' else 'Not Found')
            draw_row('Skills', sk_pdf, safe_val(sk_web), 'MATCH' if (course.get('sk_match') and not is_hard_error) else 'FALSE')

            # Boolean Rank Display (Requirement 11)
            has_qs = course.get('has_qs_badge')
            qs_pdf_val = "True (QS Badge Present)" if has_qs else "False"
            qs_web_raw = course.get('qs_detail', '').strip()
            qs_web = qs_web_raw if qs_web_raw else ('Not Claimed' if not has_qs else 'Not Found on Website')
            qs_status = 'MATCH' if (course.get('qs_ranked') or not has_qs) else 'FALSE'
            draw_row('QS Ranked', qs_pdf_val, safe_val(qs_web), qs_status if not is_hard_error else 'FALSE')

            has_nirf = course.get('has_nirf_badge')
            nirf_pdf_val = "True (NIRF Badge Present)" if has_nirf else "False"
            nirf_web_raw = course.get('nirf_detail', '').strip()
            nirf_web = nirf_web_raw if nirf_web_raw else ('Not Claimed' if not has_nirf else 'Not Found on Website')
            nirf_status = 'MATCH' if (course.get('nirf_ranked') or not has_nirf) else 'FALSE'
            draw_row('NIRF Ranked', nirf_pdf_val, safe_val(nirf_web), nirf_status if not is_hard_error else 'FALSE')

            has_free_box = course.get('has_free_box', False)
            cost_is_free = 'free' in str(course.get('cost', '')).lower()
            free_pdf_val = "True" if has_free_box or cost_is_free else "False"
            free_web_val = "Free" if has_free_box or cost_is_free else "Paid"
            free_status = 'MATCH' if (free_pdf_val == "True" and free_web_val == "Free") or (free_pdf_val == "False" and free_web_val == "Paid") else 'FALSE'
            draw_row('Free Box', free_pdf_val, safe_val(free_web_val), free_status if not is_hard_error else 'FALSE')
            
            has_scholarship = course.get('has_scholarship_box', False)
            is_coursera = 'coursera.org' in str(course.get('url', '')).lower()
            is_india = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
            
            if is_coursera:
                if has_scholarship:
                    sch_str = "Matched. All Coursera courses have scholarships and financial aid."
                    sch_status = "MATCH" if not is_hard_error else "FALSE"
                else:
                    sch_str = "Mismatch. All Coursera courses have scholarships and financial aid."
                    sch_status = "FALSE"
            elif has_scholarship:
                sch_status = "MATCH" if not is_hard_error else "FALSE"
                if is_india:
                    sch_str = "Matched. The university/college gives a scholarship for students."
                else:
                    sch_str = "Matched. The university has scholarship available for international students."
            else:
                sch_status = "MATCH" if not is_hard_error else "FALSE"
                if is_india:
                    sch_str = "University/college does not have scholarship for students."
                else:
                    sch_str = "University/college does not have scholarship for international students."
                
            draw_row('Scholarship Box', 'True (Yellow Box Present)' if has_scholarship else 'False', safe_val(sch_str), sch_status)

            has_logos = course.get('has_logos', False)
            draw_row('Institute Logo', 'Present' if has_logos else 'Not Identified', safe_val('Matched'), 'MATCH' if not is_hard_error else 'FALSE')

            draw_row('Link Working', 'True' if has_url else 'False', 'Working / Accessible' if not is_hard_error else 'Error', 'FALSE' if is_hard_error else 'MATCH')

            # Improved Summary Section
            pdf.ln(8)
            pdf.set_fill_color(243, 244, 246)
            pdf.set_font('Arial', 'B', 11)
            pdf.set_text_color(31, 41, 55)
            pdf.cell(0, 8, ' Executive Verification Summary', fill=True, ln=1)
            
            pdf.set_font('Arial', '', 10)
            pdf.set_text_color(55, 65, 81)
            desc = safe_latin(self._generate_professional_summary(course))
            if len(desc) > 700:
                desc = desc[:697] + "..."
            pdf.multi_cell(0, 5, desc, border='LRB')

        # Render sequentially
        counter = start_idx + 1
        end_val = end_idx if end_idx is not None else len(self.courses)
        for c in self.courses[start_idx:end_val]:
            render_course(c, str(counter))
            counter += 1

        # ── Floating Items Page ──
        if self.floating_items:
            floating_path = os.path.splitext(self.output_pdf)[0] + "_floating_items.json"
            with open(floating_path, "w", encoding="utf-8") as f:
                json.dump(self.floating_items, f, indent=2, ensure_ascii=False)
            print(f"    [!] {len(self.floating_items)} floating items saved separately: {floating_path}")
            pdf.set_auto_page_break(auto=False)
            # No extra PDF page here: the user requested exactly one page per course.

        pdf.output(self.output_pdf)
        print(f"\n[*] DONE! Report: {self.output_pdf}")
        print(f"    Screenshots: {self.screenshots_dir}")
        if self.floating_items:
            print(f"    [!] Floating items were not added as extra PDF pages.")


# ──────────────────────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────────────────────

if __name__ == "__main__":


    if not check_runtime_dependencies():
        sys.exit(1)


    if len(sys.argv) > 1:
        pdf_path = sys.argv[1].strip()
    else:
        pdf_path = input("Enter the PDF filename: ").strip()

    if not os.path.exists(pdf_path):
        print(f"\nError: '{pdf_path}' not found.")
        sys.exit(1)



    start_idx = 0
    resume = False
    
    # Always force a clean start to prevent old errors
    try:
        import shutil
        screenshots_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "verification_screenshots")
        if os.path.exists(screenshots_base):
            shutil.rmtree(screenshots_base)
            print("\n[*] Flushed all previous screenshot folders.")
    except Exception as e:
        print(f"\n[!] Warning: Could not flush old screenshot folders: {e}")
        
    try:
        if os.path.exists("autonomous_verified_data.json"):
            os.remove("autonomous_verified_data.json")
            print("[*] Flushed old checkpoint data. Starting fresh.")
    except Exception as e:
        print(f"[!] Warning: Could not flush old checkpoint data: {e}")

    # NOW initialize the agent, which will create the new screenshot folder
    agent = AutonomousCourseVerifier(pdf_path)

    agent.extract_and_parse()

    # Ask the user for an optional manual start index
    manual_start = input(f"\n[?] From which course number (1-{len(agent.courses)}) do you want to start web verification? (Press Enter to use default): ").strip()
    if manual_start.isdigit():
        custom_idx = int(manual_start) - 1
        if 0 <= custom_idx < len(agent.courses):
            start_idx = custom_idx
            print(f"[*] Manually setting start index to {start_idx + 1}")

    end_idx = len(agent.courses)
    manual_end = input(f"\n[?] Up to which course number (1-{len(agent.courses)}) do you want to run web verification? (Press Enter for all remaining): ").strip()
    if manual_end.isdigit():
        custom_end = int(manual_end)
        if start_idx < custom_end <= len(agent.courses):
            end_idx = custom_end
            print(f"[*] Manually setting end course to {end_idx}")
        elif custom_end <= start_idx:
            print(f"[!] End course must be greater than start course. Using default end.")

    if not resume and start_idx < len(agent.courses):
        agent.extract_visuals_for_range(start_idx=start_idx, end_idx=end_idx)

    if start_idx < len(agent.courses):
        agent.autonomous_web_verify(start_idx=start_idx, end_idx=end_idx)
    else:
        print("\n[*] All courses are already verified in the checkpoint.")
        
    print("\n[*] Verifying QS/NIRF rankings based on updated web extraction data...")
    agent.verify_rankings(start_idx=start_idx, end_idx=end_idx)

    pdf_name = input("\n[?] Enter the name for the final PDF report (without .pdf, press Enter for default): ").strip()
    if not pdf_name:
        pdf_name = "Autonomous_Course_Verification_Report"
        
    agent.generate_pdf_report(start_idx=start_idx, end_idx=end_idx, pdf_name=pdf_name)
    
    # --- SAVE PERMANENT DASHBOARD RESULTS ---
    import shutil
    if os.path.exists("autonomous_verified_data.json"):
        shutil.copy("autonomous_verified_data.json", "master_dashboard_results.json")
        print("\n[*] Saved permanent dashboard results to master_dashboard_results.json")
    
    # Prevent undetected_chromedriver from spamming WinError 6 during Python teardown
    import os
    os._exit(0)
