import os
import json
import re
import sys
import hashlib
import fitz
import pdfplumber
import tempfile
import time
import threading
import pymongo
from pymongo import MongoClient, UpdateOne
from flask import Flask, render_template, jsonify, request
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

load_dotenv()

# Windows consoles default to the cp1252 codepage, which CANNOT encode the
# status glyphs used throughout the print() statements below (✓ ✗ ⚠ ▸ …). A
# print() of one of those chars raises UnicodeEncodeError, which aborts
# save_courses() BEFORE it reaches the MongoDB bulk_write / static-JSON export
# — so uploads mutate global_courses in memory (counts briefly rise) but never
# persist; the next stale-cache reload from MongoDB reverts them (counts fall
# back). Forcing UTF-8 on stdout/stderr fixes the crash for every status print.
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50 MB

# CORS — allow the Vercel-hosted dashboard (and any other client) to call
# this dashboard API cross-origin. Set CORS_ALLOW_ORIGIN to a specific origin
# in production if you want to lock it down; defaults to '*'.
@app.after_request
def _add_cors_headers(resp):
    resp.headers['Access-Control-Allow-Origin'] = os.environ.get('CORS_ALLOW_ORIGIN', '*')
    resp.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
    resp.headers['Access-Control-Allow-Methods'] = 'GET, POST, DELETE, OPTIONS'
    resp.headers['Access-Control-Allow-Private-Network'] = 'true'
    # Never cache the HTML shell or the JSON API — the browser must always
    # revalidate so a new deploy (or a new ?v= on app.js/style.css) is picked
    # up immediately. Static assets (app.js, style.css) are cache-busted via
    # the ?v= query string in index.html instead.
    ctype = resp.headers.get('Content-Type', '')
    if 'text/html' in ctype or 'application/json' in ctype:
        resp.headers['Cache-Control'] = 'no-store, must-revalidate'
    return resp

# Issue category constants (mirrored from verifier)
ISSUE_CATEGORY_WEBSITE = "website_issue"
ISSUE_CATEGORY_COURSE = "course_issue"
ISSUE_CATEGORY_VERIFIED = "verified"

# Initialize MongoDB
import os

# Load .env file if present (works locally and in CI; production servers
# inject env vars directly so this is a no-op when dotenv isn't installed).
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv not installed — rely on env vars being set externally

db_client = None
db = None
try:
    mongo_uri = os.environ.get('MONGO_URI')
    # Fallback: read from mongo_uri.txt for local dev convenience
    if not mongo_uri and os.path.exists('mongo_uri.txt'):
        with open('mongo_uri.txt', 'r') as f:
            mongo_uri = f.read().strip()

    if mongo_uri:
        db_client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=10000,
            connectTimeoutMS=10000,
            # Raised from 10s → 90s: loading 3,727 large documents over an
            # Atlas free-tier connection routinely takes 20-40s; the old 10s
            # limit caused every cold startup to fall back to the stale 1.json.
            socketTimeoutMS=90000,
            retryWrites=True,
            w='majority',
        )
        db_client.admin.command('ping')
        db = db_client['course_verifier']
        print("Connected to MongoDB Atlas")
    else:
        print("WARNING: No MONGO_URI found. Set MONGO_URI env var or create 'mongo_uri.txt'.")
except Exception as e:
    print(f"MongoDB initialization failed: {e}")
    db = None
JSON_FILES = ["autonomous_verified_link_compile.pdf.json", "autonomous_verified_link_compile.pdf..json"]
PERSISTENT_FILE = "1.json"
global_courses = []

def clean_country(country):
    cl = country.lower().replace('country:', '').replace('(online)', '').strip()
    if not cl: return 'Unknown'
    if cl == 'hk' or 'hong kong' in cl: return 'Hong Kong'
    if cl == 'lux' or 'luxembourg' in cl or 'luxemborg' in cl: return 'Luxembourg'
    if cl in ['sa', 'sau', 'ksa'] or 'saudi arabia' in cl: return 'Saudi Arabia'
    if cl == 'za' or 'south africa' in cl: return 'South Africa'
    if cl == 'ch' or 'switzerland' in cl: return 'Switzerland'
    
    if 'usa' in cl or 'united states' in cl or 'america' in cl: return 'United States of America'
    if 'uk' in cl or 'united kingdom' in cl or 'england' in cl: return 'United Kingdom'
    if 'india' in cl: return 'India'
    if 'nz' in cl or 'new zealand' in cl: return 'New Zealand'
    if 'australia' in cl: return 'Australia'
    if 'canada' in cl: return 'Canada'
    if 'ireland' in cl: return 'Ireland'
    if 'france' in cl: return 'France'
    if 'spain' in cl: return 'Spain'
    if 'germany' in cl: return 'Germany'
    if 'uae' in cl or 'united arab emirates' in cl: return 'United Arab Emirates'
    if 'singapore' in cl: return 'Singapore'
    if 'romania' in cl: return 'Romania'
    if 'thailand' in cl: return 'Thailand'
    if 'nl' in cl or 'netherlands' in cl: return 'Netherlands'
    if 'qatar' in cl: return 'Qatar'
    if 'denmark' in cl: return 'Denmark'
    if 'sweden' in cl: return 'Sweden'
    if 'italy' in cl: return 'Italy'
    if 'china' in cl: return 'China'
    if 'japan' in cl: return 'Japan'
    
    country = country.replace('Country:', '').replace('(Online)', '').strip()
    return country if country else 'Unknown'

# Canonical academic-domain labels. The raw `domain` field arrives from a mix
# of upload-filename matching (Title Case, e.g. "Bachelors") and CombinedWork
# migration (UPPERCASE, e.g. "BACHELORS DEGREE"). These are the same degrees
# spelled differently — collapse them to one canonical label so the Dashboard
# "Course Breakdown" and Analytics "Credential Mix" don't split a degree into
# multiple bars/segments.
_CANON_DOMAIN_MAP = [
    ("bachelor",          "Bachelor's Degree"),
    ("master",            "Master's Degree"),
    ("post graduate diploma", "Post Graduate Diploma"),
    ("post graduate certificate", "Post Graduate Certificate"),
    ("post grad diploma", "Post Graduate Diploma"),
    ("post grad cert",    "Post Graduate Certificate"),
    ("graduate diploma",  "Diploma"),
    ("diploma",            "Diploma"),
    ("certificate",        "Certificate"),
    ("free to audit",     "Free to Audit"),
    ("high value low cost", "High Value Low Cost"),
    ("free",              "Free"),
]

def normalize_domain(raw):
    """Collapse case/spelling variants of a course domain/type to one label."""
    if not raw:
        return "Other"
    key = str(raw).strip().lower()
    if not key or key in ('unknown', 'unknown domain', 'none', 'null'):
        return "Other"
    for frag, label in _CANON_DOMAIN_MAP:
        if frag in key:
            return label
    return "Other"

# ── Per-attribute issue model (mirrors the modal table in app.js) ──────────────
# An "issue" is any attribute row whose verified value does NOT match the PDF.
# Users can tick individual attributes as Solved, or solve every open issue in a
# course at once. A course with zero open issues becomes Verified.
ATTRIBUTE_ROWS = [
    ('Cost',        'cost_match'),
    ('Duration',    'duration_match'),
    ('Mode',        'mode_match'),
    ('Language',    'lang_match'),
    ('Country',     'country_match'),
    ('University',  'uni_match'),
    ('Skills',      'sk_match'),
    ('QS Ranked',   'qs_match_expr'),
    ('NIRF Ranked', 'nirf_match_expr'),
    ('Free Box',    'free_match_expr'),
    ('Scholarship Box', 'scholarship_match_expr'),
]

def _attr_is_match(c, key):
    """Resolve a modal-table MATCH/FALSE flag for a course dict."""
    if key == 'qs_match_expr':
        # Check pdf_table first (authoritative — set by upload or verifier)
        for row in (c.get('pdf_table') or []):
            if isinstance(row, dict) and row.get('attribute', '').lower().startswith('qs'):
                return str(row.get('status', '')).upper() != 'FALSE'
        # Fall back to field-based logic
        return bool(c.get('qs_ranked', False)) or (not c.get('has_qs_badge', False))
    if key == 'nirf_match_expr':
        for row in (c.get('pdf_table') or []):
            if isinstance(row, dict) and row.get('attribute', '').lower().startswith('nirf'):
                return str(row.get('status', '')).upper() != 'FALSE'
        return bool(c.get('nirf_ranked', False)) or (not c.get('has_nirf_badge', False))
    if key == 'free_match_expr':
        has_free = bool(c.get('has_free_box', False))
        web_cost = str(c.get('web_cost', '') or '').lower()
        web_free = 'free' in web_cost
        return has_free == web_free
    if key == 'scholarship_match_expr':
        for row in (c.get('pdf_table') or []):
            if isinstance(row, dict) and 'scholarship' in str(row.get('attribute', '')).lower():
                return str(row.get('status', '')).upper() != 'FALSE'
        return True  # No scholarship row = not an issue
    return bool(c.get(key, False))

# The user-solvable subset: includes the 7 basic attributes plus QS/NIRF/Free
# so that solving ALL visible issues (including ranking mismatches) flips the
# course to Verified. The old code excluded QS/NIRF/Free, so a course with a
# ranking mismatch stayed Discrepancy forever even after solving everything else.
SOLVABLE_ATTRIBUTE_ROWS = ATTRIBUTE_ROWS[:7]
QS_NIRF_ROWS = ATTRIBUTE_ROWS[7:10]  # QS Ranked, NIRF Ranked, Free Box

def _qs_nirf_false_attrs(c):
    """List QS/NIRF/Free/Scholarship attribute names that are currently FALSE."""
    false = []
    for row in (c.get('pdf_table') or []):
        if not isinstance(row, dict):
            continue
        attr_name = str(row.get('attribute', '')).strip()
        status = str(row.get('status', '')).strip().upper()
        if status == 'FALSE':
            if attr_name.lower().startswith('qs'):
                false.append('QS Ranked')
            elif attr_name.lower().startswith('nirf'):
                false.append('NIRF Ranked')
            elif attr_name.lower().startswith('free'):
                false.append('Free Box')
            elif attr_name.lower().startswith('scholarship'):
                false.append('Scholarship Box')
    return false

def course_false_attrs(c):
    """List of attribute names currently FALSE (i.e. open) for a course.

    Includes the 7 basic attrs PLUS QS/NIRF/Free if their pdf_table row is
    FALSE — so that ranking mismatches count as open issues and block
    Verified status until solved."""
    false = [name for name, key in SOLVABLE_ATTRIBUTE_ROWS if not _attr_is_match(c, key)]
    # Also check QS/NIRF/Free from pdf_table (more reliable than derived fields)
    qs_nirf_false = _qs_nirf_false_attrs(c)
    for attr in qs_nirf_false:
        if attr not in false:
            false.append(attr)
    return false

def course_open_issues(c):
    """Number of unsolved issue-units a course contributes to the Open Issues KPI."""
    cat = c.get('issue_category', '')
    if c.get('status') == 'Verified' or cat == ISSUE_CATEGORY_VERIFIED:
        return 0
    if cat == ISSUE_CATEGORY_WEBSITE:
        # A broken/inaccessible site is one unit, solved via the single Solved button.
        return 1
    if cat == ISSUE_CATEGORY_COURSE:
        solved = set(c.get('solved_attrs', []) or [])
        return sum(1 for a in course_false_attrs(c) if a not in solved)
    return 0

def recompute_course_status(c):
    """Re-derive status/issue_category from solved_attrs after a per-attr change.
    website_issue courses are left untouched here (handled by the _website action)."""
    if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
        return
    solved = set(c.get('solved_attrs', []) or [])
    unsolved = [a for a in course_false_attrs(c) if a not in solved]
    if not unsolved:
        c['issue_category'] = ISSUE_CATEGORY_VERIFIED
        c['status'] = 'Verified'
        c['disc_reason'] = ''
    else:
        c['issue_category'] = ISSUE_CATEGORY_COURSE
        c['status'] = 'Discrepancy'
    c['issue_sub_type'] = derive_issue_sub_type(c)

def _derived_classification(c):
    """Return (issue_category, status) a course SHOULD have under the CORRECTED
    rules — a website issue only when the site is genuinely broken (page-load
    error / hard web FALSE); otherwise Verified (all basic matches solved) or
    course_issue/Discrepancy. Pure: does not mutate c. Used for dry-run tallies
    and by reclassify_course."""
    desc = (str(c.get('cost_description', '')) + ' ' + str(c.get('duration_description', ''))
            + ' ' + str(c.get('cost_verified', '')) + ' ' + str(c.get('duration_verified', ''))
            + ' ' + str(c.get('reason', '')) + ' ' + str(c.get('disc_reason', ''))
            + ' ' + _pdf_table_text(c)).lower()
    has_page_error = ('page load error' in desc) or ('website unreachable' in desc) \
        or ('llm fallback' in desc) or ('site down' in desc)
    web_status = str(c.get('web_status', '')).upper()
    if has_page_error or (web_status == 'FALSE' and c.get('is_hard_error')):
        return (ISSUE_CATEGORY_WEBSITE, 'Error')
    # "Not uploaded" / no live web page to match against: all 7 basic fields
    # are False and there is no page error. Per the user's direction these stay
    # as website-Error (they are not course discrepancies — there is no page to
    # compare fields against), so do NOT reclassify them.
    _basic_keys = ['cost_match', 'duration_match', 'mode_match', 'lang_match',
                   'country_match', 'uni_match', 'sk_match']
    if not any(bool(c.get(k, False)) for k in _basic_keys):
        return (ISSUE_CATEGORY_WEBSITE, 'Error')
    # Check ALL attributes including QS/NIRF from pdf_table
    solved = set(c.get('solved_attrs', []) or [])
    unsolved = [a for a in course_false_attrs(c) if a not in solved]
    if not unsolved:
        return (ISSUE_CATEGORY_VERIFIED, 'Verified')
    return (ISSUE_CATEGORY_COURSE, 'Discrepancy')

def reclassify_course(c):
    """Apply the corrected classification to c in place (mutates). Used only by
    the /api/reclassify endpoint when confirm=true is sent."""
    cat, status = _derived_classification(c)
    c['issue_category'] = cat
    c['status'] = status
    if status == 'Verified':
        c['disc_reason'] = ''
    elif cat == ISSUE_CATEGORY_COURSE:
        unsolved = [a for a in course_false_attrs(c) if a not in set(c.get('solved_attrs', []) or [])]
        c['disc_reason'] = 'Mismatch: ' + ', '.join(unsolved)
    # website_issue: leave disc_reason as-is
    c['issue_sub_type'] = derive_issue_sub_type(c)

def compute_stats():
    """Shared stats block used by /api/data, save_courses data.json, and /solve."""
    total = len(global_courses)
    verified = sum(1 for c in global_courses if c.get('status') == 'Verified')
    discrepancies = sum(1 for c in global_courses if c.get('status') == 'Discrepancy')
    errors = sum(1 for c in global_courses if c.get('status') == 'Error')
    unverified = sum(1 for c in global_courses if c.get('status') == 'Unverified')
    website_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE)
    course_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE)
    open_issues = sum(course_open_issues(c) for c in global_courses)
    return {
        "total": total,
        "verified": verified,
        "discrepancies": discrepancies,
        "errors": errors,
        "unverified": unverified,
        "website_issues": website_issues,
        "course_issues": course_issues,
        "open_issues": open_issues,
    }

def save_courses(updated_courses=None):
    global _LAST_SAVE_TS, _LAST_LOAD_TS
    """
    Save courses to all persistence layers
    Args:
        updated_courses: Optional list of courses that were updated.
                        If None, all courses will be saved to MongoDB.
    """
    try:
        print(f"[SAVE] Saving {len(global_courses)} total courses...")
        
        # 1. ALWAYS backup to local 1.json (primary backup)
        try:
            with open(PERSISTENT_FILE, "w", encoding="utf-8") as f:
                json.dump(global_courses, f, indent=2)
            print(f"[SAVE] ✓ Saved to local file: {PERSISTENT_FILE}")
        except Exception as e:
            print(f"[SAVE] ✗ Error saving to local file: {e}")
            # Do not raise in Cloud Run environment to avoid breaking the API response
            pass
        # 2. Update MongoDB - SAVE SPECIFIC COURSES
        if db is not None:
            try:
                courses_to_save = updated_courses if updated_courses is not None else global_courses
                if courses_to_save:
                    operations = []
                    for c in courses_to_save:
                        operations.append(UpdateOne({'id': int(c.get('id')) if str(c.get('id')).isdigit() else c.get('id')}, {'$set': c}, upsert=True))
                    
                    if operations:
                        db.courses.bulk_write(operations)
                        print(f"[SAVE] ✓ Saved {len(operations)} courses to MongoDB")
            except Exception as e:
                print(f"[SAVE] ✗ Error saving to MongoDB: {e}")
        else:
            print("[SAVE] ⚠ MongoDB not available, skipping cloud sync")

        # Data changed → analytics summary is stale. Mark dirty so the next
        # /api/analytics request rebuilds it (instead of serving the old cache).
        try:
            _invalidate_analytics()
        except Exception:
            pass

        with _load_lock:
            _LAST_SAVE_TS = time.time()
            _LAST_LOAD_TS = time.time()  # Prevent immediate redundant reload

    except Exception as e:
        print(f"[SAVE] ✗ Critical error in save_courses: {e}")
        import traceback
        traceback.print_exc()

def _pdf_table_text(c):
    """Flatten a course's pdf_table row values into one string so the web-issue
    heuristic can spot signals like 'Page Load Error' that live inside the
    nested table rows rather than in top-level fields."""
    parts = []
    for row in (c.get('pdf_table') or []):
        if isinstance(row, dict):
            parts.extend(str(v) for v in row.values())
    return ' '.join(parts)

def derive_issue_sub_type(c):
    """Derive issue_sub_type from REAL signals only (disc_reason + pdf_table text).

    Mirrors the vocabulary in autonomous_course_verifier.classify_issue but never
    fabricates a value: returns '' when no signal matches. Used to backfill the
    sub_type that older records never stored, so the dashboard's sub-type filters
    are populated from real data instead of being empty.
    """
    cat = c.get('issue_category', '')
    reason = str(c.get('disc_reason', '') or '').lower()
    text = reason + " " + _pdf_table_text(c).lower()

    if cat == ISSUE_CATEGORY_WEBSITE:
        if '404' in text or 'not found' in text:
            return '404_not_found'
        if 'ssl' in text or 'certificate' in text:
            return 'ssl_error'
        if 'timeout' in text or 'timed out' in text:
            return 'timeout'
        if 'waf' in text or 'blocked' in text:
            return 'blocked_by_waf'
        if 'dns' in text:
            return 'dns_fail'
        if 'login' in text or 'authentication required' in text:
            return 'login_required'
        if 'redirect' in text:
            return 'redirect_loop'
        # Numeric HTTP codes: check the reason only (word-bounded) so a cost
        # value like "500" inside pdf_table can't trigger a false server_error.
        if 'server error' in text or any((' ' + code + ' ') in (' ' + reason + ' ') for code in ('500', '502', '503')):
            return 'server_error'
        if 'page load error' in text or 'website unreachable' in text or 'llm fallback' in text or 'site down' in text:
            return 'site_down'
        return ''

    if cat == ISSUE_CATEGORY_COURSE:
        if 'replaced' in text:
            return 'course_replaced'
        if 'wrong url' in text:
            return 'wrong_url'
        # Uploads format this as "Mismatch: Cost, Duration, ..."
        attrs = []
        if reason.startswith('mismatch:'):
            attrs = [a.strip() for a in reason[len('mismatch:'):].split(',') if a.strip()]
        attr_map = {
            'cost': 'cost_mismatch', 'duration': 'duration_mismatch',
            'university': 'university_mismatch', 'country': 'country_mismatch',
            'mode': 'mode_mismatch', 'language': 'language_mismatch',
            'skills': 'skills_mismatch', 'name': 'name_mismatch',
            'qs ranked': 'qs_mismatch', 'nirf ranked': 'nirf_mismatch',
            'free box': 'free_box_mismatch', 'scholarship box': 'scholarship_box_mismatch',
        }
        # Ranking-only mismatch: QS/NIRF FALSE but no other attr mismatch
        if len(attrs) == 1 and attrs[0].lower() in ('qs ranked', 'nirf ranked'):
            return attr_map[attrs[0].lower()]
        if len(attrs) >= 2:
            return 'multiple_mismatches'
        if len(attrs) == 1:
            return attr_map.get(attrs[0].lower(), '')
        return ''

    if cat == ISSUE_CATEGORY_VERIFIED:
        return 'perfect_match'

    return ''

def load_courses():
    global global_courses
    fetch_start_time = time.time()
    # Build into a local list and swap ONCE at the end. The old code did
    # clear() then extend(), leaving a window where global_courses was empty —
    # a concurrent /api/data.json poll (via _refresh_courses_if_stale) could
    # then make a solve's compute_stats() return 0, so the frontend briefly
    # showed "0" after solving instead of the incremented count.
    loaded = []

    loaded_raw = False
    
    # ── LOCAL OVERRIDE ──
    # If 1.json exists, we are running locally and should prioritize it over MongoDB
    # to avoid overwriting local changes with old remote data on startup.
    if os.path.exists(PERSISTENT_FILE):
        try:
            with open(PERSISTENT_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            loaded_raw = True
            print(f"Loaded {len(raw_data)} courses from {PERSISTENT_FILE}")
        except Exception as e:
            print("Error loading 1.json:", e)

    loaded_from_mongo = False
    if not loaded_raw and db is not None:
        try:
            print("Loading courses from MongoDB...")
            docs = list(db.courses.find({}, {'_id': 0}))
            if docs:
                loaded.extend(docs)
                loaded.sort(key=lambda x: int(x.get('id', 0)))
                print(f"Loaded {len(loaded)} courses from MongoDB.")
                loaded_from_mongo = True
        except Exception as e:
            print(f"Error loading from MongoDB: {e}")
            
    if not loaded_from_mongo and not loaded_raw:
        # Fallback to original JSON files if 1.json doesn't exist
        for jf in JSON_FILES:
            if os.path.exists(jf):
                try:
                    with open(jf, "r", encoding="utf-8") as f:
                        raw_data = json.load(f)
                    loaded_raw = True
                    print(f"Loaded {len(raw_data)} courses from {jf}")
                    break
                except Exception as e:
                    print(f"Error loading {jf}:", e)
                    
    if loaded_raw:
        for idx, d in enumerate(raw_data):
            country = clean_country(d.get('country', d.get('Country', 'Unknown')))
            domain = str(d.get('domain', d.get('Domain', 'Unknown Domain'))).strip()
            if not domain: domain = 'Unknown Domain'
            
            status = d.get('status')
            if not status or status == 'Unverified':
                web_status = d.get('web_status', '')
                if web_status == 'MATCH':
                    status = 'Verified'
                elif web_status == 'FALSE':
                    status = 'Error' if d.get('is_hard_error') else 'Discrepancy'
                else:
                    status = 'Unverified'
            
            issue_cat = d.get('issue_category', '')
            issue_sub = d.get('issue_sub_type', '')
            
            # --- DYNAMIC WEBSITE ISSUE HEURISTIC ---
            desc_text = str(d.get('cost_description', '')) + " " + str(d.get('duration_description', '')) + " " + str(d.get('cost_verified', '')) + " " + str(d.get('duration_verified', '')) + " " + str(d.get('reason', '')) + " " + _pdf_table_text(d)
            
            # Explicit network/page load errors
            has_page_error = 'page load error' in desc_text.lower() or 'website unreachable' in desc_text.lower() or 'llm fallback' in desc_text.lower()
            
            # If the course lacks a university match or a name match, it is immediately a website issue.
            has_uni_match = d.get('uni_match', False)
            
            # Some old records might not have 'name_match', so we check 'matched_fields' if available
            matched_fields_str = str(d.get('matched_fields', '[]'))
            has_name_match = True
            if 'matched_fields' in d and 'Name' not in matched_fields_str:
                has_name_match = False
                
            web_status = str(d.get('web_status', '')).upper()

            # A website issue = a genuinely broken/inaccessible site: an explicit
            # page-load / unreachable / LLM-fallback error, or a hard web FALSE.
            # A university or name field MISMATCH is a COURSE issue (the page
            # loaded fine, the field just doesn't match) — it must NOT trigger
            # website_issue classification here. Treating uni_match=False as a
            # broken site previously misclassified ~3700 courses as website
            # errors and was persisted to MongoDB.
            if has_page_error or (web_status == 'FALSE' and d.get('is_hard_error')):
                issue_cat = ISSUE_CATEGORY_WEBSITE
                # Make sure the status is mapped to Error
                status = 'Error'

            # Derive status from issue_category if present, else fall back to old logic
            if issue_cat == ISSUE_CATEGORY_VERIFIED:
                status = 'Verified'
            elif issue_cat == ISSUE_CATEGORY_WEBSITE:
                status = 'Error'
            elif issue_cat == ISSUE_CATEGORY_COURSE:
                status = 'Discrepancy'
            elif not status or status == 'Unverified':
                web_status = d.get('web_status', '')
                if web_status == 'MATCH':
                    status = 'Verified'
                elif web_status == 'FALSE':
                    status = 'Error' if d.get('is_hard_error') else 'Discrepancy'
                else:
                    status = 'Unverified'

            course = {
                "id": d.get("id", idx + 1),
                "name": str(d.get('name', d.get('Course Name', 'Unknown'))).strip(),
                "university": str(d.get('uni', d.get('university', d.get('University (PDF)', 'Unknown')))).strip(),
                "domain": domain,
                "country": country,
                "cost": str(d.get('cost', '')),
                "duration": str(d.get('duration', '')),
                "mode": str(d.get('mode', '')),
                "skills": str(d.get('skills', '')),
                "qs": str(d.get('qs_detail', d.get('qs', ''))),
                "nirf": str(d.get('nirf_detail', d.get('nirf', ''))),
                "has_qs_badge": d.get('has_qs_badge', False),
                "has_nirf_badge": d.get('has_nirf_badge', False),

                "status": status,
                "issue_category": issue_cat,
                "issue_sub_type": issue_sub,
                "solved_attrs": d.get('solved_attrs', []) or [],
                "retry_count": d.get('retry_count', 0),
                "error_screenshot_path": d.get('error_screenshot_path', ''),
                "cost_match": d.get('cost_match', False),
                "duration_match": d.get('duration_match', False),
                "mode_match": d.get('mode_match', False),
                "lang_match": d.get('lang_match', False),
                "country_match": d.get('country_match', False),
                "uni_match": d.get('uni_match', False),
                "sk_match": d.get('sk_match', False),
                "disc_reason": str(d.get('disc_reason', d.get('reason', ''))),

                # Preserve PDF verification data
                "pdf_page": d.get('pdf_page'),
                "pdf_table": d.get('pdf_table', [])
            }
            loaded.append(course)
            
        print(f"Loaded {len(global_courses)} courses locally.")

<<<<<<< HEAD
    # APPLY HEURISTIC TO ALL LOADED COURSES (From Mongo or Local)
    # BUG FIX: iterate over `loaded` (the freshly-fetched list) — NOT
    # `global_courses` (the OLD in-memory list).  The atomic swap below
    # overwrites global_courses with `loaded`, so any mutations applied to
    # global_courses here were thrown away immediately after, meaning MongoDB
    # courses never had their status corrected before being served.
    _basic_match_keys = ['cost_match', 'duration_match', 'mode_match',
                         'lang_match', 'country_match', 'uni_match', 'sk_match']
    for c in loaded:
=======
    # APPLY HEURISTIC TO ALL LOADED COURSES (iterate over `loaded`, not the
    # old global_courses — the old code iterated global_courses but swapped
    # `loaded` in at the end, so the heuristic never touched the freshly-loaded
    # data and stale classifications persisted.)
    for c in loaded:
        # Ensure qs_match/nirf_match/free_match fields exist on Mongo-loaded
        # courses (they were only set by the upload handler; older Mongo docs
        # lack them). Derive from pdf_table if present.
        if 'qs_match' not in c:
            c['qs_match'] = True
            c['nirf_match'] = True
            c['free_match'] = True
            for row in (c.get('pdf_table') or []):
                if not isinstance(row, dict): continue
                row_attr = str(row.get('attribute', '')).lower().strip()
                row_status = str(row.get('status', '')).strip().upper()
                if 'qs' in row_attr and 'ranked' in row_attr:
                    c['qs_match'] = (row_status != 'FALSE')
                elif 'nirf' in row_attr and 'ranked' in row_attr:
                    c['nirf_match'] = (row_status != 'FALSE')
                elif 'free' in row_attr and 'box' in row_attr:
                    c['free_match'] = (row_status != 'FALSE')
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
        # Check both disc_reason and reason since they might be labeled differently depending on the source
        desc_text = str(c.get('cost_description', '')) + " " + str(c.get('duration_description', '')) + " " + str(c.get('cost_verified', '')) + " " + str(c.get('duration_verified', '')) + " " + str(c.get('disc_reason', '')) + " " + str(c.get('reason', '')) + " " + _pdf_table_text(c)
        
        has_page_error = 'page load error' in desc_text.lower() or 'website unreachable' in desc_text.lower() or 'llm fallback' in desc_text.lower()
            
        web_status = str(c.get('web_status', '')).upper()
        
        # If it was natively flagged as Unverified in older runs, and has an error message, it's a website issue
        is_unverified = c.get('status') == 'Unverified'
        
<<<<<<< HEAD
        issue_cat = c.get('issue_category', '')
        
        # If the course has been explicitly categorised (e.g. by PDF upload), respect it!
        # Do not let legacy text in c['reason'] override a recent PDF verification.
        if issue_cat == ISSUE_CATEGORY_VERIFIED:
            c['status'] = 'Verified'
        elif issue_cat == ISSUE_CATEGORY_COURSE:
            c['status'] = 'Discrepancy'
        elif issue_cat == ISSUE_CATEGORY_WEBSITE:
            c['status'] = 'Error'
        elif has_page_error:
            # Apply heuristics only if not explicitly categorised yet
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
        elif is_unverified and not issue_cat and not any(bool(c.get(k, False)) for k in _basic_match_keys):
            # Only reclassify as website_issue when ALL 7 basic match flags are
            # False (i.e. the page never loaded at all).
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
=======
        # Web issues are detected from actual website error signals only — a
        # page-load / unreachable / LLM-fallback error in the description, or an
        # existing website_issue classification (preserved by the else-branch
        # below). We intentionally do NOT use uni_match / name_match here: PDF
        # uploads set uni_match=True when the University cell reads MATCH, which
        # would mask genuine website issues and make the count drift down.
        # IMPORTANT: Do not override courses that have a pdf_table (uploaded /
        # verified) — their status was set authoritatively by the upload handler.
        has_pdf_table = bool(c.get('pdf_table'))
        if has_page_error:
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
        elif is_unverified and not c.get('issue_category'):
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
        elif has_pdf_table and c.get('issue_category') in (ISSUE_CATEGORY_VERIFIED, ISSUE_CATEGORY_COURSE):
            # Uploaded course with real pdf_table data — trust the stored
            # status/issue_category, don't re-derive from heuristics.
            pass
        else:
            # Sync status with issue_category for existing records
            issue_cat = c.get('issue_category', '')
            if issue_cat == ISSUE_CATEGORY_VERIFIED:
                c['status'] = 'Verified'
            elif issue_cat == ISSUE_CATEGORY_WEBSITE:
                c['status'] = 'Error'
            elif issue_cat == ISSUE_CATEGORY_COURSE:
                c['status'] = 'Discrepancy'
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35

        # Backfill issue_sub_type from real signals when missing. Never
        # overwrites a value already persisted in Mongo / 1.json.
        if not c.get('issue_sub_type'):
            c['issue_sub_type'] = derive_issue_sub_type(c)

    with _load_lock:
        if globals().get('_LAST_SAVE_TS', 0) > fetch_start_time:
            print("[REFRESH] Save occurred during load; discarding stale fetch.")
            return
        # Atomic swap: global_courses is never observed empty by a concurrent
        # reader (solve's compute_stats, /api/data.json) mid-reload.
        global_courses[:] = loaded

# On Vercel, the serverless function instance is reused across requests, so
# global_courses (loaded once above) goes stale and the hosted dashboard never
# sees new uploads. Refresh from MongoDB on a short TTL so the live site stays
# current. Local dev benefits too: it picks up writes from other clients.
_LAST_LOAD_TS = time.time()
<<<<<<< HEAD
_LAST_SAVE_TS = time.time()
_LOAD_TTL_SEC = 15
=======
# On the local machine (1.json present) we never poll MongoDB — the local file
# IS the source of truth and MongoDB re-polling would overwrite in-memory edits.
# On production (Vercel / Cloud Run) we reload every 120 s so multi-client
# changes propagate without hammering Atlas.
_IS_LOCAL = os.path.exists(PERSISTENT_FILE)
_LOAD_TTL_SEC = 999999 if _IS_LOCAL else 120
_load_lock = threading.Lock()
_refresh_in_progress = False
analytics_thread = None

# Load immediately
load_courses()

def _build_analytics_in_background():
    """Module-level builder thread loop: rebuild analytics cache in the background.
    Must be at module level (not nested) so it can be referenced by
    _refresh_courses_if_stale before that function has been called."""
    while True:
        try:
            print("[ANABUILD] rebuilding analytics data (background)...")
            data = build_analytics_data()
            with _load_lock:
                _ANALYTICS_CACHE["data"] = data
                _ANALYTICS_CACHE["ts"] = time.time()
                _ANALYTICS_CACHE["dirty"] = False
                _ANALYTICS_CACHE["mtimes"] = _analytics_mtimes()
            print("[ANABUILD] \u2713 rebuild complete.")
        except Exception as e:
            print(f"[ANABUILD] \u2717 error: {e}")
            import traceback
            traceback.print_exc()
        time.sleep(_ANALYTICS_TTL_SEC)

def _refresh_courses_if_stale():
    """Stale-while-revalidate: serve the current in-memory global_courses and
    trigger a background MongoDB reload when the cache is older than
    _LOAD_TTL_SEC seconds. The route returns immediately using the cached list
    so no request blocks on a full 13 MB Mongo pull (which previously stalled
    /api/data.json and /api/courses.json for ~80s every TTL expiry). Solves
    mutate global_courses synchronously via save_courses(), so the acting user
    still sees their change instantly; other clients pick it up after the
    next background refresh — same eventual-consistency as before, just
    non-blocking. No-op when MongoDB is not connected."""
    global _LAST_LOAD_TS, _refresh_in_progress, analytics_thread
    if db is None:
        return

    # Analytics builder thread (starts once)
    with _load_lock:
        if not analytics_thread:
            analytics_thread = threading.Thread(target=_build_analytics_in_background, daemon=True)
            analytics_thread.start()
            print("[ANABUILD] analytics builder thread started.")

    if (time.time() - _LAST_LOAD_TS) < _LOAD_TTL_SEC:
        return
    # Mark the cache fresh-scheduled so concurrent requests don't each spawn a
    # reload thread; the background reload bumps _LAST_LOAD_TS when done.
    with _load_lock:
        if _refresh_in_progress or (time.time() - _LAST_LOAD_TS) < _LOAD_TTL_SEC:
            return
        _refresh_in_progress = True

    def _bg_reload():
        global _LAST_LOAD_TS, _refresh_in_progress
        try:
            load_courses()
            print("[REFRESH] reloaded global_courses from MongoDB (background)")
        except Exception as e:
            print("[REFRESH] error reloading from MongoDB:", e)
        finally:
            with _load_lock:
                _LAST_LOAD_TS = time.time()
                _refresh_in_progress = False

    threading.Thread(target=_bg_reload, daemon=True).start()

@app.route("/")
def index():
    # Embed the current stats payload directly into the HTML so the browser
    # renders real KPI numbers the instant the page is parsed — no extra HTTP
    # round-trip to /api/data.json before the first paint.
    try:
        initial_payload = _get_cached_data_payload()
        initial_data_json = json.dumps({
            "status": initial_payload.get("status"),
            "stats": initial_payload.get("stats"),
            "country_counts": initial_payload.get("country_counts"),
            "domain_counts": initial_payload.get("domain_counts"),
            "recent": initial_payload.get("recent", []),
        })
    except Exception:
        initial_data_json = 'null'
    return render_template("index.html", initial_data=initial_data_json)

@app.route("/api/courses")
@app.route("/api/courses.json")
def api_courses():
    _refresh_courses_if_stale()
    return jsonify({"status": "success", "courses": global_courses})

@app.route("/api/debug")
def api_debug():
    uri = os.environ.get('MONGO_URI')
    masked_uri = "NOT_SET"
    if uri:
        masked_uri = uri[:15] + "..." + uri[-15:]
    
    return jsonify({
        "has_mongo_uri": bool(uri),
        "masked_uri": masked_uri,
        "is_db_connected": db is not None,
        "global_courses_length": len(global_courses),
        "dnspython_installed": True
    })

# ── Caching: avoid recomputing the massive /api/data payload on every 5s poll ──
# The old code iterated 3727 courses 7+ times and built 3 full issue lists on
# every request. Now we cache the result and only recompute when global_courses
# actually changes (after a solve, upload, or stale refresh).
_data_cache = None
_data_cache_key = None  # (len(global_courses), sum of statuses hash)

def _get_data_cache_key():
    """Cheap signature of global_courses — changes when any status/length changes."""
    # Use a lightweight hash: length + counts of each status. This is O(n) but
    # a single pass, and the result is cached so the 5s poll just compares ints.
    counts = {}
    for c in global_courses:
        s = c.get('status', '')
        counts[s] = counts.get(s, 0) + 1
    # Include solved_attrs count so solve actions invalidate the cache
    solved_total = sum(len(c.get('solved_attrs', []) or []) for c in global_courses)
    return (len(global_courses), tuple(sorted(counts.items())), solved_total)

def _get_cached_data_payload():
    """Return the /api/data.json payload, recomputing only when data changes."""
    global _data_cache, _data_cache_key
    key = _get_data_cache_key()
    if _data_cache is not None and _data_cache_key == key:
        return _data_cache

    # ── Single-pass computation over global_courses ──
    total_courses = len(global_courses)
<<<<<<< HEAD
    verified = sum(1 for c in global_courses if c.get('status') == 'Verified')
    discrepancies = sum(1 for c in global_courses if c.get('status') == 'Discrepancy')
    errors = sum(1 for c in global_courses if c.get('status') == 'Error')
    unverified = sum(1 for c in global_courses if c.get('status') == 'Unverified')

    # Issue category breakdown
    website_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE)
    course_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE)

    # Sub-type tallies
=======
    verified = discrepancies = errors = unverified = 0
    website_issues = course_issues = 0
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
    website_sub_counts = {}
    course_sub_counts = {}
    domain_issue_counts = {}
    domain_counts = {}
    country_counts = {}
    country_status = {}
    discrepancy_list = []
    website_issue_list = []
    course_issue_list = []
    recent = []
    open_issues = 0

    for c in global_courses:
        s = c.get('status', '')
        cat = c.get('issue_category', '')

        # Stats (single pass instead of 7 separate sum() calls)
        if s == 'Verified': verified += 1
        elif s == 'Discrepancy': discrepancies += 1
        elif s == 'Error': errors += 1
        elif s == 'Unverified': unverified += 1

        if cat == ISSUE_CATEGORY_WEBSITE: website_issues += 1
        elif cat == ISSUE_CATEGORY_COURSE: course_issues += 1

        # Sub-type tallies
        sub = c.get('issue_sub_type', '')
        if cat == ISSUE_CATEGORY_WEBSITE and sub:
            website_sub_counts[sub] = website_sub_counts.get(sub, 0) + 1
        elif cat == ISSUE_CATEGORY_COURSE and sub:
            course_sub_counts[sub] = course_sub_counts.get(sub, 0) + 1

        # Domain counts + issue counts
        if c.get('domain'):
            dom = normalize_domain(c.get('domain'))
            domain_counts[dom] = domain_counts.get(dom, 0) + 1
            if cat == ISSUE_CATEGORY_WEBSITE:
                domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1

        # Country counts + status
        cty = c.get('country')
        if cty and cty != 'Unknown':
            cty = clean_country(cty)
            country_counts[cty] = country_counts.get(cty, 0) + 1
            st = country_status.setdefault(cty, {"total": 0, "verified": 0, "discrepancies": 0, "errors": 0})
            st["total"] += 1
            if s == 'Verified': st["verified"] += 1
            elif s == 'Discrepancy': st["discrepancies"] += 1
            elif s == 'Error': st["errors"] += 1

<<<<<<< HEAD
        if c.get('status') == 'Discrepancy':
            discrepancy_list.append({
                "name": c.get('name', ''),
                "university": c.get('university', ''),
                "reason": c.get('disc_reason', ''),
                "domain": c.get('domain', '')
=======
        # Issue lists (only name/uni/reason/domain — NOT full course objects)
        if s == 'Discrepancy':
            discrepancy_list.append({
                "name": c.get('name', ''), "university": c.get('university', ''),
                "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
            })
        if cat == ISSUE_CATEGORY_WEBSITE:
            website_issue_list.append({
<<<<<<< HEAD
                "name": c.get('name', ''),
                "university": c.get('university', ''),
                "sub_type": c.get('issue_sub_type', ''),
                "reason": c.get('disc_reason', ''),
                "domain": c.get('domain', '')
=======
                "name": c.get('name', ''), "university": c.get('university', ''),
                "sub_type": sub, "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
            })
        elif cat == ISSUE_CATEGORY_COURSE:
            course_issue_list.append({
<<<<<<< HEAD
                "name": c.get('name', ''),
                "university": c.get('university', ''),
                "sub_type": c.get('issue_sub_type', ''),
                "reason": c.get('disc_reason', ''),
                "domain": c.get('domain', '')
=======
                "name": c.get('name', ''), "university": c.get('university', ''),
                "sub_type": sub, "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
            })

        # Recent list: only discrepancy/error courses with a pdf_page
        if s in ('Discrepancy', 'Error') and 'pdf_page' in c:
            recent.append(c)

        # Open issues (only for non-verified/non-website courses)
        if s != 'Verified' and cat == ISSUE_CATEGORY_COURSE:
            solved = set(c.get('solved_attrs', []) or [])
            open_issues += sum(1 for a in course_false_attrs(c) if a not in solved)

    domain_warnings = [
        {"domain": d, "issue_count": cnt}
        for d, cnt in domain_issue_counts.items() if cnt >= 3
    ]

    payload = {
        "status": "success",
        "stats": {
            "total": total_courses, "verified": verified,
            "discrepancies": discrepancies, "errors": errors,
            "unverified": unverified, "website_issues": website_issues,
            "course_issues": course_issues, "open_issues": open_issues,
        },
        "website_sub_counts": website_sub_counts,
        "course_sub_counts": course_sub_counts,
        "domain_warnings": domain_warnings,
        "domain_counts": domain_counts,
        "country_counts": country_counts,
        "country_status": country_status,
        "discrepancy_list": discrepancy_list,
        "website_issue_list": website_issue_list,
        "course_issue_list": course_issue_list,
<<<<<<< HEAD
        "recent": [c for c in global_courses if c.get('status') in ['Discrepancy', 'Error'] and 'pdf_page' in c]
    })
=======
        "recent": recent,
    }

    _data_cache = payload
    _data_cache_key = key
    return payload

def _invalidate_data_cache():
    """Call after any mutation to global_courses (solve, upload, delete) so
    the next /api/data.json request recomputes instead of returning stale cache."""
    global _data_cache, _data_cache_key
    _data_cache = None
    _data_cache_key = None

def _push_cached_payloads_to_mongo():
    """Push pre-computed /api/data.json and /api/courses.json payloads to MongoDB
    so the public website can load data in milliseconds by reading a single cached
    document rather than re-computing stats from 3700+ individual course documents.
    Also pushes to Cloudflare KV if configured."""
    if db is None:
        return
    try:
        data_payload = _get_cached_data_payload()
        courses_payload = {"status": "success", "courses": global_courses}

        # Store in a 'api_cache' collection — one doc per endpoint
        db.api_cache.update_one(
            {"_endpoint": "data.json"},
            {"$set": {"_endpoint": "data.json", "payload": data_payload, "_ts": time.time()}},
            upsert=True
        )
        db.api_cache.update_one(
            {"_endpoint": "courses.json"},
            {"$set": {"_endpoint": "courses.json", "payload": courses_payload, "_ts": time.time()}},
            upsert=True
        )
        print("[CACHE] ✓ Pushed pre-computed API payloads to MongoDB")
    except Exception as e:
        print(f"[CACHE] ✗ Error pushing payloads: {e}")

    # Cloudflare KV sync is now handled manually via push_kv_manual.py
    # _push_to_cloudflare_kv(data_payload, courses_payload)

def _push_to_cloudflare_kv(data_payload, courses_payload):
    """Push pre-computed payloads to the Cloudflare Worker's KV store so the
    public website at courseverifiy.kesug.com loads data in milliseconds."""
    import requests as req_lib

    worker_url = os.environ.get('CF_WORKER_URL', '').rstrip('/')
    kv_push_key = os.environ.get('CF_KV_PUSH_KEY', '')
    if not worker_url or not kv_push_key:
        print("[CF-KV] ⚠ CF_WORKER_URL or CF_KV_PUSH_KEY not set — skipping Cloudflare KV push")
        return
    push_url = f'{worker_url}/api/kv-push'
    for endpoint, payload in [('data.json', data_payload), ('courses.json', courses_payload)]:
        try:
            # Dump to JSON bytes string
            import json
            raw_data = json.dumps(payload, separators=(',', ':'))
            headers = {
                'Authorization': f'Bearer {kv_push_key}',
                'Content-Type': 'application/json',
                'X-Endpoint': endpoint
            }
            resp = req_lib.post(push_url, data=raw_data, headers=headers, timeout=60)
            if resp.status_code == 200:
                print(f"[CF-KV] ✓ Pushed {endpoint} to Cloudflare KV")
            else:
                print(f"[CF-KV] ✗ Failed to push {endpoint}: HTTP {resp.status_code} — {resp.text[:200]}")
        except Exception as e:
            print(f"[CF-KV] ✗ Error pushing {endpoint}: {e}")

@app.route("/api/data")
@app.route("/api/data.json")
def api_data():
    _refresh_courses_if_stale()
    payload = _get_cached_data_payload()
    return jsonify(payload)
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35

@app.route("/api/course/<int:course_id>", methods=["DELETE", "OPTIONS"])
def delete_course(course_id):
    if request.method == "OPTIONS": return "", 204
    global global_courses
    
    idx_to_delete = None
    for i, c in enumerate(global_courses):
        if c.get('id') == course_id:
            idx_to_delete = i
            break
            
    if idx_to_delete is not None:
        del global_courses[idx_to_delete]
        
        # Re-index all courses so numbers change sequentially
        for i, c in enumerate(global_courses):
            c['id'] = i + 1
            
        # Resync everything to MongoDB (since IDs changed)
        save_courses(global_courses)
        _invalidate_data_cache()
        
        # Delete the extra document at the end since size decreased by 1
        if db is not None:
            try:
                db.courses.delete_one({'id': str(len(global_courses) + 1)})
            except Exception as e:
                print("Error deleting document from MongoDB:", e)
            
        return jsonify({"status": "success", "message": "Course deleted and IDs updated"})
    else:
        return jsonify({"status": "error", "message": "Course not found"}), 404

@app.route("/api/course/<int:course_id>/solve", methods=["POST", "OPTIONS"])
def solve_course_issue(course_id):
    if request.method == "OPTIONS": return "", 204
    """Mark one issue (or all issues) in a course as Solved.
    Body: {"attr": "Cost" | "_all" | "_website", "unsolve": false}
      - "Cost"/"Duration"/...  -> toggle that single attribute
      - "_all"                  -> solve (or un-solve) every open FALSE attribute
      - "_website"              -> solve (or un-solve) a broken-site (website_issue) course

    Persists to MongoDB + 1.json so every dashboard
    client (multiple users) sees the change on its next 5s poll.
    """
    data = request.get_json(silent=True) or {}
    attr = str(data.get('attr') or '').strip()
    unsolve = bool(data.get('unsolve', False))

    course = next((c for c in global_courses if str(c.get('id')) == str(course_id)), None)
    if not course:
        return jsonify({"status": "error", "message": "Course not found"}), 404

    cat = course.get('issue_category', '')

    # Broken-site courses are a single unit; no per-attribute rows exist.
    if attr == '_website' or cat == ISSUE_CATEGORY_WEBSITE:
        if unsolve:
            course['issue_category'] = ISSUE_CATEGORY_WEBSITE
            course['status'] = 'Error'
        else:
            course['issue_category'] = ISSUE_CATEGORY_VERIFIED
            course['status'] = 'Verified'
            course['disc_reason'] = ''
            course['issue_sub_type'] = derive_issue_sub_type(course)
    elif attr == '_all':
        false_attrs = course_false_attrs(course)
        solved = set(course.get('solved_attrs', []) or [])
        if unsolve:
            solved -= set(false_attrs)
        else:
            solved |= set(false_attrs)
        course['solved_attrs'] = sorted(solved)
        recompute_course_status(course)
    elif attr:
        solved = set(course.get('solved_attrs', []) or [])
        if unsolve:
            solved.discard(attr)
        else:
            solved.add(attr)
        course['solved_attrs'] = sorted(solved)
        recompute_course_status(course)
    else:
        return jsonify({"status": "error", "message": "Missing 'attr'"}), 400

    try:
        save_courses([course])
        _invalidate_data_cache()
    except Exception as e:
        print("[SOLVE] save error:", e)

    return jsonify({
        "status": "success",
        "course": {
            "id": course.get('id'),
            "issue_category": course.get('issue_category', ''),
            "issue_sub_type": course.get('issue_sub_type', ''),
            "status": course.get('status', ''),
            "disc_reason": course.get('disc_reason', ''),
            "solved_attrs": course.get('solved_attrs', []),
        },
        "stats": compute_stats()
    })

@app.route("/api/reclassify", methods=["GET", "POST", "OPTIONS"])
def api_reclassify():
    if request.method == "OPTIONS":
        return "", 204
    # DRY RUN by default (GET, or POST without confirm): tally the
    # corrected classification WITHOUT mutating global_courses or saving.
    before_status, before_cat = {}, {}
    for c in global_courses:
        s = c.get('status', ''); k = c.get('issue_category', '')
        before_status[s] = before_status.get(s, 0) + 1
        before_cat[k] = before_cat.get(k, 0) + 1
    after_status, after_cat = {}, {}
    for c in global_courses:
        cat, status = _derived_classification(c)
        after_status[status] = after_status.get(status, 0) + 1
        after_cat[cat] = after_cat.get(cat, 0) + 1
    saved = False
    if request.method == "POST" and bool((request.get_json(silent=True) or {}).get('confirm')):
        for c in global_courses:
            reclassify_course(c)
        try:
            save_courses(None)
            _invalidate_data_cache()
            saved = True
        except Exception as e:
            print("[RECLASSIFY] save error:", e)
        # recompute the after tally from the now-mutated global_courses
        after_status, after_cat = {}, {}
        for c in global_courses:
            after_status[c.get('status', '')] = after_status.get(c.get('status', ''), 0) + 1
            after_cat[c.get('issue_category', '')] = after_cat.get(c.get('issue_category', ''), 0) + 1
    return jsonify({
        "status": "success",
        "saved": saved,
        "note": "DRY RUN — nothing was written. POST with {\"confirm\":true} to apply."
                if not saved else "Applied and saved to MongoDB.",
        "before_status": before_status,
        "after_status": after_status,
        "before_category": before_cat,
        "after_category": after_cat,
        "stats": compute_stats(),
    })

import pandas as pd
import os

# ── Analytics helpers (module-level so save_courses + routes can reuse) ──────
import sqlite3
import statistics as _statistics

_RANKINGS_CACHE = None

def _load_rankings():
    """Return (qs_set, nirf_set) of lowercased university names from rankings.db.
    Membership-only (no rank numbers). Returns (set(), set()) if the DB is
    unreadable/missing so ranking fields gracefully default to zero/false."""
    global _RANKINGS_CACHE
    if _RANKINGS_CACHE is not None:
        return _RANKINGS_CACHE
    qs, nirf = set(), set()
    if os.path.exists('rankings.db'):
        try:
            conn = sqlite3.connect('rankings.db')
            cur = conn.cursor()
            for row in cur.execute('SELECT university FROM qs_ranking'):
                if row and row[0]:
                    qs.add(str(row[0]).strip().lower())
            for row in cur.execute('SELECT university FROM nirf_ranking'):
                if row and row[0]:
                    nirf.add(str(row[0]).strip().lower())
            conn.close()
        except Exception as e:
            print('[ANALYTICS] rankings.db read failed:', e)
    _RANKINGS_CACHE = (qs, nirf)
    return _RANKINGS_CACHE

# ── Analytics result cache ──────────────────────────────────────────────────
# build_analytics_data() is expensive (~30-40 full passes over global_courses
# plus xlsx/json parses) and used to take ~9s of pure compute (the hosted
# /api/analytics.json took ~89s only because _refresh_courses_if_stale blocked
# on a 13 MB Mongo pull — now fixed by SWR). Cache the built payload so repeated
# requests are instant, and only rebuild when:
#   - save_courses() set the dirty flag (a local solve/upload mutated data), or
#   - the TTL expires (catches external Mongo writes from other clients), or
#   - a source file (CombinedWork.xlsx / variants JSON / rankings.db) changed.
# load_courses() intentionally does NOT set dirty: a background reload that
# fetches unchanged data should not force a 9s rebuild every 15s; external
# changes are picked up via the TTL instead.
_ANALYTICS_CACHE = {"data": None, "ts": 0, "dirty": False, "mtimes": None}
_ANALYTICS_TTL_SEC = 60

def _file_mtime(path):
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0

def _analytics_mtimes():
    # NOTE: rankings.db is intentionally excluded — sqlite3 read access can bump
    # its mtime via journal/WAL checkpoint, which would nondeterministically
    # invalidate the cache. rankings.db is a static asset; the 60s TTL catches
    # any external change, and save_courses() sets the dirty flag on uploads.
    return (
        _file_mtime('CombinedWork.xlsx'),
        _file_mtime('autonomous_verified_link_compile.pdf.json'),
    )

def _invalidate_analytics():
    """Mark the analytics cache dirty so the next request rebuilds it."""
    _ANALYTICS_CACHE["dirty"] = True

def get_analytics_data(force_rebuild=False):
    """Return the cached analytics payload. Never builds, never blocks."""
    if force_rebuild:
        print("[ANACACHE] force-rebuild requested, marking dirty.")
        _ANALYTICS_CACHE["dirty"] = True

    # The cache is populated by a background thread. If it's empty, the first
    # few polls will get this "building" status until the first build completes.
    if _ANALYTICS_CACHE["data"] is None:
        return {"status": "building"}

    # Also check the dirty flag for near-instant rebuilds on solve/upload.
    if _ANALYTICS_CACHE["dirty"]:
        return {"status": "building"}

    return _ANALYTICS_CACHE["data"]


@app.route("/api/analytics", methods=["GET", "POST", "OPTIONS"])
@app.route("/api/analytics.json", methods=["GET", "POST", "OPTIONS"])
def api_analytics():
    if request.method == "OPTIONS":
        return "", 204
    # POST to /api/analytics to force-trigger a rebuild on the next cycle.
    if request.method == "POST":
        return jsonify(get_analytics_data(force_rebuild=True))
    return jsonify(get_analytics_data())

# Parsed-source-rows caches: parsing CombinedWork.xlsx (pandas) and the variants
# JSON is the expensive part of a rebuild; keep the parsed df + cw_rows and the
# parsed variants list keyed by file mtime so a rebuild reuses them when the
# files haven't changed (only global_courses did).
_CW_CACHE = {"mtime": None, "df": None, "cw_rows": None}
_VARIANTS_CACHE = {"mtime": None, "variants": None}

# Standard world-region bucketing for the Geography sub-tab regional panel.
_REGION_MAP = {
    'india': 'INDIA',
    'pakistan': 'SOUTH ASIA', 'bangladesh': 'SOUTH ASIA', 'sri lanka': 'SOUTH ASIA',
    'nepal': 'SOUTH ASIA', 'bhutan': 'SOUTH ASIA', 'maldives': 'SOUTH ASIA',
    'china': 'EAST ASIA & PACIFIC', 'japan': 'EAST ASIA & PACIFIC',
    'south korea': 'EAST ASIA & PACIFIC', 'korea': 'EAST ASIA & PACIFIC',
    'hong kong': 'EAST ASIA & PACIFIC', 'taiwan': 'EAST ASIA & PACIFIC',
    'singapore': 'EAST ASIA & PACIFIC', 'malaysia': 'EAST ASIA & PACIFIC',
    'thailand': 'EAST ASIA & PACIFIC', 'indonesia': 'EAST ASIA & PACIFIC',
    'philippines': 'EAST ASIA & PACIFIC', 'phillipines': 'EAST ASIA & PACIFIC',
    'vietnam': 'EAST ASIA & PACIFIC', 'australia': 'EAST ASIA & PACIFIC',
    'new zealand': 'EAST ASIA & PACIFIC', 'fiji': 'EAST ASIA & PACIFIC',
    'usa': 'NORTH AMERICA', 'united states': 'NORTH AMERICA',
    'united states of america': 'NORTH AMERICA', 'canada': 'NORTH AMERICA',
    'mexico': 'NORTH AMERICA',
    'uk': 'EUROPE', 'united kingdom': 'EUROPE', 'england': 'EUROPE',
    'ireland': 'EUROPE', 'france': 'EUROPE', 'germany': 'EUROPE', 'spain': 'EUROPE',
    'italy': 'EUROPE', 'netherlands': 'EUROPE', 'belgium': 'EUROPE',
    'switzerland': 'EUROPE', 'austria': 'EUROPE', 'sweden': 'EUROPE',
    'denmark': 'EUROPE', 'norway': 'EUROPE', 'finland': 'EUROPE',
    'poland': 'EUROPE', 'portugal': 'EUROPE', 'romania': 'EUROPE',
    'hungary': 'EUROPE', 'lithuania': 'EUROPE', 'luxembourg': 'EUROPE',
    'russia': 'EUROPE', 'ukraine': 'EUROPE', 'turkey': 'EUROPE', 'greece': 'EUROPE',
    'czech': 'EUROPE', 'slovakia': 'EUROPE', 'croatia': 'EUROPE',
    'saudi arabia': 'MIDDLE EAST & AFRICA', 'uae': 'MIDDLE EAST & AFRICA',
    'united arab emirates': 'MIDDLE EAST & AFRICA', 'qatar': 'MIDDLE EAST & AFRICA',
    'oman': 'MIDDLE EAST & AFRICA', 'israel': 'MIDDLE EAST & AFRICA',
    'iran': 'MIDDLE EAST & AFRICA', 'jordan': 'MIDDLE EAST & AFRICA',
    'kuwait': 'MIDDLE EAST & AFRICA', 'bahrain': 'MIDDLE EAST & AFRICA',
    'south africa': 'MIDDLE EAST & AFRICA', 'egypt': 'MIDDLE EAST & AFRICA',
    'nigeria': 'MIDDLE EAST & AFRICA', 'kenya': 'MIDDLE EAST & AFRICA',
    'morocco': 'MIDDLE EAST & AFRICA', 'ghana': 'MIDDLE EAST & AFRICA',
    'brazil': 'LATIN AMERICA', 'argentina': 'LATIN AMERICA',
    'chile': 'LATIN AMERICA', 'colombia': 'LATIN AMERICA', 'peru': 'LATIN AMERICA',
}

def _region_for_country(name):
    if not name:
        return 'OTHER'
    k = str(name).strip().lower()
    if k in _REGION_MAP:
        return _REGION_MAP[k]
    for frag, reg in _REGION_MAP.items():
        if frag in k:
            return reg
    return 'OTHER'

def _get_level(ctype):
    """Canonical credential label from a Course Type / domain string."""
    c = str(ctype).lower().replace('gradiuate', 'graduate').strip()
    if 'post graduate diploma' in c or 'post grad diploma' in c or 'graduate diploma' in c:
        return "Post Graduate Diploma"
    if 'post graduate certificate' in c or 'post grad certificate' in c or 'post grad cert' in c:
        return "Post Graduate Certificate"
    if 'bachelor' in c or c == 'ug' or 'undergrad' in c:
        return "Bachelor's Degree"
    if 'master' in c or c == 'pg':
        return "Master's Degree"
    if 'diploma' in c:
        return "Diploma"
    if 'cert' in c:
        return "Certificate"
    return "Other"

def _parse_inr(fee):
    """Parse a fee string to a numeric INR value. 'Free'/0 -> 0, unparseable -> None."""
    s = str(fee).lower()
    if 'free' in s:
        return 0
    m = re.search(r'[\d][\d,]*(?:\.\d+)?', str(fee))
    if not m:
        return None
    try:
        return float(m.group(0).replace(',', ''))
    except ValueError:
        return None

def _parse_fee_tier(fee):
    """Bucket a fee string into Free/Affordable/Mid/Premium (INR). None if unparseable."""
    val = _parse_inr(fee)
    if val is None:
        return None
    if val <= 0:
        return 'Free'
    if val <= 50000:
        return 'Affordable'
    if val <= 200000:
        return 'Mid'
    return 'Premium'

_TIER_WEIGHT = {'Free': 100, 'Affordable': 70, 'Mid': 45, 'Premium': 15}
_DEGREE_LEVELS = ["Bachelor's Degree", "Master's Degree", "Diploma",
                  "Post Graduate Certificate", "Post Graduate Diploma", "Certificate"]

def _median(vals):
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    mid = n // 2
    if n % 2:
        return vals[mid]
    return (vals[mid - 1] + vals[mid]) / 2.0

def _hhi(counts_dict):
    """Herfindahl-Hirschman Index (0-10000) over a {key: count} dict."""
    total = sum(counts_dict.values()) if counts_dict else 0
    if total <= 0:
        return 0
    return int(round(sum((c / total) * 10000 for c in counts_dict.values() if c)))

def _hhi_label(hhi):
    if hhi >= 2500:
        return "Highly Concentrated"
    if hhi >= 1500:
        return "Moderately Concentrated"
    return "Diversified"

def _geo_hhi_label(hhi):
    if hhi >= 2500:
        return "CONCENTRATED"
    if hhi >= 1500:
        return "MODERATELY CONCENTRATED"
    return "DIVERSIFIED"

def _norm_name(s):
    return re.sub(r'\s+', ' ', str(s or '').strip().lower())

def _saturation_label(share_pct):
    if share_pct >= 20:
        return "SATURATED"
    if share_pct >= 10:
        return "COMPETITIVE"
    if share_pct >= 5:
        return "NICHE"
    return "EMERGING"

def _parse_mismatch_attrs(reason):
    """Extract canonical attribute names from a 'Mismatch: Cost, Duration' string."""
    r = str(reason or '').strip().lower()
    if r.startswith('mismatch:'):
        parts = [p.strip() for p in r[len('mismatch:'):].split(',') if p.strip()]
        cap = []
        for p in parts:
            cap.append(p[:1].upper() + p[1:])
        return cap
    return []

_ATTR_KEYS = {
    'Cost': 'cost_match', 'Duration': 'duration_match', 'Mode': 'mode_match',
    'Language': 'lang_match', 'Country': 'country_match',
    'University': 'uni_match', 'Skills': 'sk_match',
}

def build_analytics_data():
<<<<<<< HEAD
    """Build the analytics payload dict per the Analytics Tab data contract.

    Pure data build — used by the /api/analytics route. Every
    new field gracefully no-ops (empty/zero/null) when its source file is
    missing so the route never 500s."""
    qs_set, nirf_set = _load_rankings()

=======
    """Build the analytics payload dict (course_category, pricing_category,
    variant_category, domain_pivot, country_pivot). Uses global_courses (live
    MongoDB data) as the single source of truth — NOT static Excel/JSON files
    that drift stale after uploads/solves."""
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
    data = {
        # EXISTING (preserved)
        "course_category": {},
        "variant_category": {},
        "pricing_category": {},
        "domain_pivot": {},
        "country_pivot": {},
        # NEW blocks
        "cost_access": {},
        "concentration": {},
        "geo_concentration": {},
        "regional_groups": {},
        "country_quality": {},
        "geo_problem_ranking": [],
        "geo_anomalies": {"low_verification": [], "high_issue_rate": [],
                          "fee_outlier": [], "global_median_fee": None},
        "geo_comparison_seed": {"country_a": None, "country_b": None},
        "ranked_share": {"qs_pct": 0, "nirf_pct": 0},
        "ranking_mix": {"qs_ranked": 0, "nirf_ranked": 0, "both": 0,
                        "unranked": 0, "total": 0, "qs_ranked_pct": 0,
                        "nirf_ranked_pct": 0, "unranked_pct": 0},
        "ranked_vs_unranked_metrics": [],
        "credential_ladder": {},
        "credential_verification_matrix": {},
        "ranked_credential_mix": {},
        "credential_level_pricing": {},
        "domain_saturation": [],
        "specialization_hhi": {"value": 0, "label": "Diversified"},
        "university_leaderboard": [],
        "verification_quality": {
            "status_counts": {"verified": 0, "discrepancies": 0, "errors": 0,
                               "unverified": 0, "total": 0},
            "issue_category_counts": {"website_issue": 0, "course_issue": 0,
                                       "verified": 0},
            "issue_sub_counts": {},
            "reason_clusters": {},
            "disc_reason_pareto": [],
            "reason_attribute_matrix": {},
            "attribute_match_rates": [],
            "country_quality": [],
            "country_quality_anomalies": {},
            "domain_quality": [],
            "data_quality_health": {"score": 0, "verified_rate": 0,
                                    "error_rate": 0, "attribute_completeness": 0,
                                    "open_issues": 0},
            "anomalies": [],
        },
        "benchmark_india_intl": {},
        "analytics_courses": [],
        "filter_facets": {"levels": [], "countries": [], "cost_tiers": [],
                          "ranking": ["QS Ranked", "NIRF Ranked", "Unranked"]},
        "anomalies": {"outlier_fees": [], "low_verification_countries": [],
                      "high_error_domains": []},
        "cost_distribution": {"histogram": [], "median_fee_inr": None,
                              "iqr_low": None, "iqr_high": None, "free_share": 0,
                              "affordable_share": 0, "cost_access_index": 0},
        "key_findings": [],
        "stats": {"total": 0, "verified": 0, "discrepancies": 0, "errors": 0,
                  "unverified": 0, "website_issues": 0, "course_issues": 0,
                  "open_issues": 0},
    }

<<<<<<< HEAD
    # ────────────────────────────────────────────────────────────────────────
    # 1. CombinedWork.xlsx → course_category, pricing_category, country_pivot,
    #    cost_access, credential_ladder, ranked_credential_mix,
    #    credential_level_pricing, cost_distribution.
    # ────────────────────────────────────────────────────────────────────────
    cw_rows = []  # list of dicts: {name, country, level, fee_inr, tier, university}
    df = None
    if os.path.exists('CombinedWork.xlsx'):
        cw_mtime = _file_mtime('CombinedWork.xlsx')
        if _CW_CACHE["mtime"] == cw_mtime and _CW_CACHE["df"] is not None:
            # Cache hit: reuse the parsed DataFrame + enriched rows.
            df = _CW_CACHE["df"]
            cw_rows = _CW_CACHE["cw_rows"]
        else:
            try:
                xl = pd.ExcelFile('CombinedWork.xlsx')
                dfs = [xl.parse(s).assign(Country=s) for s in xl.sheet_names]
                df = pd.concat(dfs)
                df = df.dropna(subset=['Course name'])

                # Single-pass enrichment for cost_access / credential ladder.
                uni_col = 'Name of Institute' if 'Name of Institute' in df.columns else None
                for _, row in df.iterrows():
                    name = str(row.get('Course name', '')).strip()
                    if not name:
                        continue
                    level = _get_level(row.get('Course Type', ''))
                    fee_inr = _parse_inr(row.get('Fees', ''))
                    tier = _parse_fee_tier(row.get('Fees', ''))
                    country = str(row.get('Country', '')).strip()
                    university = str(row.get(uni_col, '')).strip() if uni_col else ''
                    cw_rows.append({'name': name, 'country': country, 'level': level,
                                    'fee_inr': fee_inr, 'tier': tier,
                                    'university': university})
                _CW_CACHE["mtime"] = cw_mtime
                _CW_CACHE["df"] = df
                _CW_CACHE["cw_rows"] = cw_rows
            except Exception as e:
                print('[ANALYTICS] CombinedWork.xlsx parse failed:', e)

        # Cheap derivations from the (possibly cached) DataFrame.
        if df is not None:
            # Country Count (preserved)
            data['country_pivot'] = {str(k): int(v) for k, v in
                                     df['Country'].value_counts().to_dict().items()}

            # Academic credential mix (degree levels only)
            levels = df['Course Type'].apply(_get_level).value_counts().to_dict()
            for k, v in levels.items():
                if k != 'Other':
                    data['course_category'][k] = int(v)

            # Pricing tiers (preserved)
            pricing = {'Free': 0, 'Affordable': 0, 'Mid': 0, 'Premium': 0}
            for fee in df['Fees'].tolist():
                tier = _parse_fee_tier(fee)
                if tier:
                    pricing[tier] = pricing.get(tier, 0) + 1
            data['pricing_category'] = pricing

    if cw_rows:
        data['cost_access'] = _build_cost_access(cw_rows)
        data['cost_distribution'] = _build_cost_distribution(cw_rows)
        data['credential_ladder'] = _build_credential_ladder(cw_rows, qs_set, nirf_set)
        data['ranked_credential_mix'] = _build_ranked_credential_mix(cw_rows, qs_set, nirf_set)
        data['credential_level_pricing'] = _build_credential_level_pricing(cw_rows)

    # ────────────────────────────────────────────────────────────────────────
    # 2. Variants JSON → variant_category, domain_pivot.
    # ────────────────────────────────────────────────────────────────────────
    json_file = 'autonomous_verified_link_compile.pdf.json'
    variants = []
    if os.path.exists(json_file):
        v_mtime = _file_mtime(json_file)
        if _VARIANTS_CACHE["mtime"] == v_mtime and _VARIANTS_CACHE["variants"] is not None:
            variants = _VARIANTS_CACHE["variants"]
        else:
            try:
                with open(json_file, 'r', encoding='utf-8') as f:
                    variants = json.load(f)
                _VARIANTS_CACHE["mtime"] = v_mtime
                _VARIANTS_CACHE["variants"] = variants
            except Exception as e:
                print('[ANALYTICS] variants JSON parse failed:', e)

    if variants:
        ind_var = sum(1 for v in variants if v.get('country') == 'India')
        int_var = len(variants) - ind_var
        data['variant_category'] = {"Indian": ind_var, "International": int_var,
                                     "Total Variants": len(variants)}
        domains = {}
        for v in variants:
            d = v.get('domain', 'Unknown')
            entry = domains.setdefault(d, {'Total': 0, 'Indian': 0, 'International': 0})
            entry['Total'] += 1
            if v.get('country') == 'India':
                entry['Indian'] += 1
            else:
                entry['International'] += 1
        data['domain_pivot'] = domains
=======
    # ── All numbers come from global_courses (live data) ──
    course_category = {}
    pricing_category = {'Free': 0, 'Affordable': 0, 'Mid': 0, 'Premium': 0}
    country_pivot = {}
    domain_pivot = {}

    import re as _re

    for c in global_courses:
        # Course type / credential mix (from normalized domain)
        level = normalize_domain(c.get('domain', ''))
        if level and level != 'Other':
            course_category[level] = course_category.get(level, 0) + 1

        # Country pivot
        cty = clean_country(str(c.get('country', '')))
        if cty and cty != 'Unknown':
            country_pivot[cty] = country_pivot.get(cty, 0) + 1

        # Pricing tier from cost field
        cost_str = str(c.get('cost', '')).lower()
        if 'free' in cost_str:
            pricing_category['Free'] += 1
        else:
            m = _re.search(r'[\d][\d,]*(?:\.\d+)?', cost_str)
            if m:
                try:
                    val = float(m.group(0).replace(',', ''))
                    if val <= 0:
                        pricing_category['Free'] += 1
                    elif val <= 50000:
                        pricing_category['Affordable'] += 1
                    elif val <= 200000:
                        pricing_category['Mid'] += 1
                    else:
                        pricing_category['Premium'] += 1
                except ValueError:
                    pass

        # Domain pivot (Indian vs International per domain)
        dom = normalize_domain(c.get('domain', ''))
        if dom and dom != 'Other':
            if dom not in domain_pivot:
                domain_pivot[dom] = {'Total': 0, 'Indian': 0, 'International': 0}
            domain_pivot[dom]['Total'] += 1
            if cty == 'India':
                domain_pivot[dom]['Indian'] += 1
            else:
                domain_pivot[dom]['International'] += 1

    data['course_category'] = course_category
    data['country_pivot'] = country_pivot
    data['pricing_category'] = pricing_category
    data['domain_pivot'] = domain_pivot

    # Variant counts: Indian vs International from live data
    ind_var = sum(1 for c in global_courses if clean_country(str(c.get('country', ''))) == 'India')
    int_var = len(global_courses) - ind_var
    data['variant_category']['Indian Variants'] = ind_var
    data['variant_category']['International Variants'] = int_var
    data['variant_category']['Total Variants'] = len(global_courses)
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35

    # ────────────────────────────────────────────────────────────────────────
    # 3. global_courses → analytics_courses, verification_quality, country
    #    intelligence, university leaderboard, benchmarks.
    # ────────────────────────────────────────────────────────────────────────
    gc = list(global_courses)
    data['stats'] = compute_stats()
    data['analytics_courses'] = _build_analytics_courses(gc, qs_set, nirf_set)
    data['filter_facets'] = _build_filter_facets(data['analytics_courses'])
    data['verification_quality'] = _build_verification_quality(gc)
    data['credential_verification_matrix'] = _build_credential_verification_matrix(gc)

    # Country intelligence (global_courses + rankings.db)
    cq_dict = _build_country_quality(gc, qs_set, nirf_set)
    data['country_quality'] = cq_dict
    data['regional_groups'] = _build_regional_groups(gc)
    data['geo_concentration'] = _build_geo_concentration(gc)
    data['geo_problem_ranking'] = _build_geo_problem_ranking(cq_dict)
    data['geo_anomalies'] = _build_geo_anomalies(cq_dict)
    data['geo_comparison_seed'] = _build_geo_comparison_seed(cq_dict)
    data['verification_quality']['country_quality'] = _build_vq_country_quality(gc)
    data['verification_quality']['country_quality_anomalies'] = _build_vq_country_anomalies(gc)
    data['verification_quality']['domain_quality'] = _build_domain_quality(gc)
    data['anomalies'] = _build_cross_anomalies(gc, data['verification_quality'])
    data['university_leaderboard'] = _build_university_leaderboard(gc, qs_set, nirf_set)
    data['benchmark_india_intl'] = _build_benchmark(gc, qs_set, nirf_set,
                                                    data['geo_concentration'])

    # Rankings (analytics_courses joined to rankings.db)
    data['ranking_mix'] = _build_ranking_mix(data['analytics_courses'])
    data['ranked_share'] = _build_ranked_share(data['analytics_courses'])
    data['ranked_vs_unranked_metrics'] = _build_ranked_vs_unranked(data['analytics_courses'])

    # ────────────────────────────────────────────────────────────────────────
    # 4. Derived from pivots (concentration, saturation, HHI).
    # ────────────────────────────────────────────────────────────────────────
    data['concentration'] = _build_concentration(data['country_pivot'], data['domain_pivot'])
    data['specialization_hhi'] = _build_specialization_hhi(data['domain_pivot'])
    data['domain_saturation'] = _build_domain_saturation(data['domain_pivot'])

    # ────────────────────────────────────────────────────────────────────────
    # 5. Auto-generated executive narrative.
    # ────────────────────────────────────────────────────────────────────────
    data['key_findings'] = _build_key_findings(data)

    return data


# ── Populator helpers (each guards its inputs; never raises) ─────────────────

def _build_cost_access(cw_rows):
    """cost_access block from CombinedWork rows."""
    out = {
        "affordability_index": 0, "median_fee_inr": None, "mean_fee_inr": None,
        "free_vs_paid": {"free": 0, "paid": 0, "free_pct": 0, "paid_pct": 0, "ratio": None},
        "fee_histogram": [],
        "cost_tier_by_level": {},
        "region_affordability": {
            "india": {"affordability_index": 0, "free_pct": 0, "median_fee_inr": None},
            "intl": {"affordability_index": 0, "free_pct": 0, "median_fee_inr": None},
        },
    }
    try:
        tiered = [r for r in cw_rows if r['tier']]
        priced = [r['fee_inr'] for r in cw_rows if r['fee_inr'] and r['fee_inr'] > 0]
        free = [r for r in cw_rows if r['fee_inr'] == 0 or r['tier'] == 'Free']

        if tiered:
            out['affordability_index'] = int(round(
                sum(_TIER_WEIGHT[r['tier']] for r in tiered) / len(tiered)))
        if priced:
            med = _median(priced)
            mean = sum(priced) / len(priced)
            out['median_fee_inr'] = int(round(med)) if med is not None else None
            out['mean_fee_inr'] = int(round(mean))

        total = len(cw_rows)
        nf = len(free)
        npaid = len(priced)
        if total > 0:
            out['free_vs_paid'] = {
                "free": nf, "paid": npaid,
                "free_pct": round(nf / total * 100, 1),
                "paid_pct": round(npaid / total * 100, 1),
                "ratio": round(nf / npaid, 2) if npaid else None,
            }

        # Fee histogram buckets
        buckets = [
            {"label": "Free", "min": None, "max": 0, "count": 0},
            {"label": "1-25k", "min": 1, "max": 25000, "count": 0},
            {"label": "25k-50k", "min": 25001, "max": 50000, "count": 0},
            {"label": "50k-100k", "min": 50001, "max": 100000, "count": 0},
            {"label": "100k-200k", "min": 100001, "max": 200000, "count": 0},
            {"label": "200k-500k", "min": 200001, "max": 500000, "count": 0},
            {"label": "500k+", "min": 500001, "max": None, "count": 0},
        ]
        for r in cw_rows:
            v = r['fee_inr']
            if v is None:
                continue
            if v == 0:
                buckets[0]['count'] += 1
            elif v <= 25000:
                buckets[1]['count'] += 1
            elif v <= 50000:
                buckets[2]['count'] += 1
            elif v <= 100000:
                buckets[3]['count'] += 1
            elif v <= 200000:
                buckets[4]['count'] += 1
            elif v <= 500000:
                buckets[5]['count'] += 1
            else:
                buckets[6]['count'] += 1
        out['fee_histogram'] = buckets

        # Cost tier by credential level
        ctl = {}
        for r in cw_rows:
            lvl = r['level']
            if lvl == 'Other' or not r['tier']:
                continue
            d = ctl.setdefault(lvl, {'Free': 0, 'Affordable': 0, 'Mid': 0, 'Premium': 0})
            d[r['tier']] += 1
        out['cost_tier_by_level'] = ctl

        # Region affordability (India vs International)
        def region_block(rows):
            rt = [r for r in rows if r['tier']]
            rp = [r['fee_inr'] for r in rows if r['fee_inr'] and r['fee_inr'] > 0]
            rf = [r for r in rows if r['fee_inr'] == 0 or r['tier'] == 'Free']
            ai = int(round(sum(_TIER_WEIGHT[r['tier']] for r in rt) / len(rt))) if rt else 0
            fp = round(len(rf) / len(rows) * 100, 1) if rows else 0
            med = _median(rp) if rp else None
            return {"affordability_index": ai, "free_pct": fp,
                    "median_fee_inr": int(round(med)) if med is not None else None}

        india_rows = [r for r in cw_rows if str(r['country']).lower() == 'india']
        intl_rows = [r for r in cw_rows if str(r['country']).lower() != 'india']
        out['region_affordability']['india'] = region_block(india_rows)
        out['region_affordability']['intl'] = region_block(intl_rows)
    except Exception as e:
        print('[ANALYTICS] cost_access build failed:', e)
    return out


def _build_cost_distribution(cw_rows):
    """Richer fee distribution complementing cost_access."""
    out = {"histogram": [], "median_fee_inr": None, "iqr_low": None,
           "iqr_high": None, "free_share": 0, "affordable_share": 0,
           "cost_access_index": 0}
    try:
        priced = sorted(r['fee_inr'] for r in cw_rows if r['fee_inr'] and r['fee_inr'] > 0)
        total = len(cw_rows)
        nfree = sum(1 for r in cw_rows if r['fee_inr'] == 0)
        naff = sum(1 for r in cw_rows if r['fee_inr'] and 0 < r['fee_inr'] <= 50000)
        bands = [
            ("Free", 0, 0), ("0-50000", 1, 50000),
            ("50001-100000", 50001, 100000), ("100001-200000", 100001, 200000),
            ("200001-500000", 200001, 500000), ("500001-1000000", 500001, 1000000),
            ("above_1000000", 1000001, float('inf')),
        ]
        hist = []
        for label, lo, hi in bands:
            cnt = sum(1 for r in cw_rows
                      if r['fee_inr'] is not None
                      and (lo <= r['fee_inr'] <= hi if hi != float('inf')
                           else r['fee_inr'] >= lo))
            hist.append({"band": label, "count": cnt})
        out['histogram'] = hist
        if priced:
            med = _median(priced)
            out['median_fee_inr'] = int(round(med)) if med is not None else None
            n = len(priced)
            q1 = priced[int(n * 0.25)] if n >= 4 else (priced[0] if priced else None)
            q3 = priced[int(n * 0.75)] if n >= 4 else (priced[-1] if priced else None)
            out['iqr_low'] = round(q1, 1) if q1 is not None else None
            out['iqr_high'] = round(q3, 1) if q3 is not None else None
        if total > 0:
            fs = nfree / total
            as_ = naff / total
            out['free_share'] = round(fs, 3)
            out['affordable_share'] = round(as_, 3)
            med = out['median_fee_inr'] or 0
            out['cost_access_index'] = int(round(
                40 * fs + 35 * as_ + 25 * (1 - min(med, 1000000) / 1000000)))
    except Exception as e:
        print('[ANALYTICS] cost_distribution build failed:', e)
    return out


def _build_credential_ladder(cw_rows, qs_set, nirf_set):
    """Per-level cost, geography, verification (joined by name) and rank presence."""
    out = {}
    try:
        # name -> status lookup from global_courses (case-insensitive, trimmed)
        name_status = {}
        for c in global_courses:
            name_status[_norm_name(c.get('name'))] = c.get('status')

        agg = {}
        for r in cw_rows:
            lvl = r['level']
            if lvl == 'Other':
                continue
            a = agg.setdefault(lvl, {'count': 0, 'fees': [], 'free': 0,
                                    'indian': 0, 'intl': 0,
                                    'verified': 0, 'matched': 0,
                                    'ranked': 0, 'unranked': 0})
            a['count'] += 1
            if r['fee_inr'] and r['fee_inr'] > 0:
                a['fees'].append(r['fee_inr'])
            if r['fee_inr'] == 0:
                a['free'] += 1
            if str(r['country']).lower() == 'india':
                a['indian'] += 1
            else:
                a['intl'] += 1
            st = name_status.get(_norm_name(r['name']))
            if st:
                a['matched'] += 1
                if st == 'Verified':
                    a['verified'] += 1
            uni_l = _norm_name(r['university'])
            if uni_l and (uni_l in qs_set or uni_l in nirf_set):
                a['ranked'] += 1
            else:
                a['unranked'] += 1

        for lvl, a in agg.items():
            cnt = a['count'] or 0
            priced = [f for f in a['fees'] if f]
            med = _median(priced)
            out[lvl] = {
                "count": cnt,
                "avg_cost_inr": round(sum(priced) / len(priced), 1) if priced else None,
                "median_cost_inr": round(med, 1) if med is not None else None,
                "free_count": a['free'],
                "free_pct": round(a['free'] / cnt * 100, 1) if cnt else 0,
                "indian": a['indian'],
                "international": a['intl'],
                "indian_pct": round(a['indian'] / cnt * 100, 1) if cnt else 0,
                "verification_rate": round(a['verified'] / a['matched'], 3)
                                     if a['matched'] else None,
                "ranked_count": a['ranked'],
                "unranked_count": a['unranked'],
            }
    except Exception as e:
        print('[ANALYTICS] credential_ladder build failed:', e)
    return out


def _build_ranked_credential_mix(cw_rows, qs_set, nirf_set):
    out = {}
    try:
        agg = {}
        for r in cw_rows:
            lvl = r['level']
            if lvl == 'Other':
                continue
            a = agg.setdefault(lvl, {'ranked': 0, 'unranked': 0})
            uni_l = _norm_name(r['university'])
            if uni_l and (uni_l in qs_set or uni_l in nirf_set):
                a['ranked'] += 1
            else:
                a['unranked'] += 1
        out = {lvl: {"ranked": a['ranked'], "unranked": a['unranked']}
               for lvl, a in agg.items()}
    except Exception as e:
        print('[ANALYTICS] ranked_credential_mix build failed:', e)
    return out


def _build_credential_level_pricing(cw_rows):
    out = {}
    try:
        agg = {}
        for r in cw_rows:
            lvl = r['level']
            if lvl == 'Other' or not r['tier']:
                continue
            d = agg.setdefault(lvl, {'Free': 0, 'Affordable': 0, 'Mid': 0, 'Premium': 0})
            d[r['tier']] += 1
        out = agg
    except Exception as e:
        print('[ANALYTICS] credential_level_pricing build failed:', e)
    return out


def _build_credential_verification_matrix(gc):
    """Per-credential-level verification quality (percentages share within level)."""
    out = {}
    try:
        agg = {}
        for c in gc:
            lvl = _get_level(c.get('domain', ''))
            a = agg.setdefault(lvl, {'verified': 0, 'discrepancy': 0,
                                     'error': 0, 'unverified': 0, 'total': 0})
            a['total'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancy'] += 1
            elif s == 'Error': a['error'] += 1
            elif s == 'Unverified': a['unverified'] += 1
        for lvl, a in agg.items():
            tot = a['total']
            if not tot:
                continue
            out[lvl] = {
                "verified_pct": round(a['verified'] / tot * 100, 1),
                "discrepancy_pct": round(a['discrepancy'] / tot * 100, 1),
                "error_pct": round(a['error'] / tot * 100, 1),
                "unverified_pct": round(a['unverified'] / tot * 100, 1),
                "total": tot, "blank_when_zero": tot == 0,
            }
    except Exception as e:
        print('[ANALYTICS] credential_verification_matrix build failed:', e)
    return out


def _build_analytics_courses(gc, qs_set, nirf_set):
    """Normalized per-course rows for client-side filtering."""
    out = []
    try:
        for c in gc:
            uni = c.get('university') or ''
            uni_l = _norm_name(uni)
            qs = uni_l in qs_set if uni_l else False
            nirf = uni_l in nirf_set if uni_l else False
            fee = _parse_inr(c.get('cost', ''))
            out.append({
                "name": c.get('name', ''),
                "university": uni or None,
                "country": c.get('country'),
                "level": _get_level(c.get('domain', '')),
                "domain": normalize_domain(c.get('domain', '')),
                "cost_tier": _parse_fee_tier(c.get('cost', '')) or "Free",
                "fee_inr": round(fee, 1) if fee is not None else None,
                "status": c.get('status', ''),
                "qs_ranked": bool(qs),
                "nirf_ranked": bool(nirf),
                "issue_category": c.get('issue_category') or None,
                "disc_reason": c.get('disc_reason') or None,
            })
    except Exception as e:
        print('[ANALYTICS] analytics_courses build failed:', e)
    return out


def _build_filter_facets(analytics_courses):
    try:
        levels = sorted({r['level'] for r in analytics_courses
                         if r.get('level') and r['level'] != 'Other'})
        countries = sorted({r['country'] for r in analytics_courses
                            if r.get('country') and r['country'] != 'Unknown'})
        tiers = sorted({r['cost_tier'] for r in analytics_courses if r.get('cost_tier')})
        return {"levels": levels, "countries": countries, "cost_tiers": tiers,
                "ranking": ["QS Ranked", "NIRF Ranked", "Unranked"]}
    except Exception:
        return {"levels": [], "countries": [], "cost_tiers": [],
                "ranking": ["QS Ranked", "NIRF Ranked", "Unranked"]}


def _build_verification_quality(gc):
    vq = {
        "status_counts": {"verified": 0, "discrepancies": 0, "errors": 0,
                          "unverified": 0, "total": 0},
        "issue_category_counts": {"website_issue": 0, "course_issue": 0, "verified": 0},
        "issue_sub_counts": {},
        "reason_clusters": {},
        "disc_reason_pareto": [],
        "reason_attribute_matrix": {},
        "attribute_match_rates": [],
        "country_quality": [],
        "country_quality_anomalies": {},
        "domain_quality": [],
        "data_quality_health": {"score": 0, "verified_rate": 0, "error_rate": 0,
                                "attribute_completeness": 0, "open_issues": 0},
        "anomalies": [],
    }
    try:
        total = len(gc)
        verified = sum(1 for c in gc if c.get('status') == 'Verified')
        discrepancies = sum(1 for c in gc if c.get('status') == 'Discrepancy')
        errors = sum(1 for c in gc if c.get('status') == 'Error')
        unverified = sum(1 for c in gc if c.get('status') == 'Unverified')
        vq["status_counts"] = {"verified": verified, "discrepancies": discrepancies,
                                "errors": errors, "unverified": unverified, "total": total}
        vq["issue_category_counts"] = {
            "website_issue": sum(1 for c in gc if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE),
            "course_issue": sum(1 for c in gc if c.get('issue_category') == ISSUE_CATEGORY_COURSE),
            "verified": sum(1 for c in gc if c.get('issue_category') == ISSUE_CATEGORY_VERIFIED),
        }
        sub = {}
        for c in gc:
            s = c.get('issue_sub_type', '')
            if s:
                sub[s] = sub.get(s, 0) + 1
        vq["issue_sub_counts"] = dict(sorted(sub.items(), key=lambda x: -x[1]))

        # Reason clusters + reason-attribute matrix
        clusters = {}
        matrix = {}
        for c in gc:
            if c.get('status') != 'Discrepancy':
                continue
            attrs = _parse_mismatch_attrs(c.get('disc_reason', ''))
            if attrs:
                key = ", ".join(attrs)
            elif c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
                key = "Website Unreachable"
            else:
                key = c.get('disc_reason', '') or "Other"
            clusters[key] = clusters.get(key, 0) + 1
            row = matrix.setdefault(key, {a: 0 for a in _ATTR_KEYS})
            for a in attrs:
                if a in row:
                    row[a] += 1
        vq["reason_clusters"] = dict(sorted(clusters.items(), key=lambda x: -x[1]))
        vq["reason_attribute_matrix"] = matrix

        # Pareto (top 8 clusters)
        pareto = []
        cum = 0
        tot_clusters = sum(clusters.values()) if clusters else 0
        for k, v in sorted(clusters.items(), key=lambda x: -x[1])[:8]:
            cum += v
            pareto.append({"reason": k, "count": v,
                           "cumulative_pct": round(cum / tot_clusters * 100, 1)
                           if tot_clusters else 0})
        vq["disc_reason_pareto"] = pareto

        # Attribute match rates
        rates = []
        for attr, key in _ATTR_KEYS.items():
            matched = sum(1 for c in gc if bool(c.get(key, False)))
            rates.append({"attribute": attr, "total": total,
                          "matched": matched,
                          "mismatched": total - matched,
                          "match_rate": round(matched / total, 3) if total else 0})
        rates.sort(key=lambda x: x['match_rate'])
        vq["attribute_match_rates"] = rates

        # Data-quality health
        vr = verified / total if total else 0
        er = errors / total if total else 0
        completeness = (sum(r['match_rate'] for r in rates) / len(rates)) if rates else 0
        score = int(round(100 * (0.4 * vr + 0.3 * (1 - er) + 0.3 * completeness)))
        vq["data_quality_health"] = {
            "score": score, "verified_rate": round(vr, 3),
            "error_rate": round(er, 3),
            "attribute_completeness": round(completeness, 3),
            "open_issues": sum(course_open_issues(c) for c in gc),
        }

        # Anomaly panel
        vq["anomalies"] = _build_vq_anomalies(gc)
    except Exception as e:
        print('[ANALYTICS] verification_quality build failed:', e)
    return vq


def _build_vq_anomalies(gc):
    out = []
    try:
        fees = [(_parse_inr(c.get('cost', '')) or 0) for c in gc]
        fees_pos = [f for f in fees if f > 0]
        med = _median(fees_pos) or 0
        outlier = [c for c in gc if (_parse_inr(c.get('cost', '')) or 0) > 3 * med and med > 0]
        rank_claim = [c for c in gc
                      if (c.get('has_qs_badge') or c.get('has_nirf_badge'))
                      and not _norm_name(c.get('university', ''))]
        all_mis = [c for c in gc
                   if c.get('issue_category') == ISSUE_CATEGORY_COURSE
                   and all(not bool(c.get(k, False)) for k in _ATTR_KEYS.values())]
        web_un = [c for c in gc if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE]

        def samples(rows, n=5):
            res = []
            for c in rows[:n]:
                fee = _parse_inr(c.get('cost', ''))
                res.append({"id": str(c.get('id', '')), "name": c.get('name', ''),
                            "country": c.get('country'),
                            "domain": normalize_domain(c.get('domain', '')),
                            "cost": round(fee, 1) if fee is not None else None})
            return res

        out = [
            {"type": "outlier_fees", "count": len(outlier), "severity": "High",
             "sample_ids": samples(outlier)},
            {"type": "unverified_rank_claim", "count": len(rank_claim), "severity": "Med",
             "sample_ids": samples(rank_claim)},
            {"type": "all_attribute_mismatch", "count": len(all_mis), "severity": "High",
             "sample_ids": samples(all_mis)},
            {"type": "website_unreachable", "count": len(web_un), "severity": "Med",
             "sample_ids": samples(web_un)},
        ]
    except Exception as e:
        print('[ANALYTICS] vq anomalies build failed:', e)
    return out


def _build_country_quality(gc, qs_set, nirf_set):
    out = {}
    try:
        agg = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            if not country or country == 'Unknown':
                continue
            a = agg.setdefault(country, {
                'total': 0, 'verified': 0, 'discrepancies': 0, 'errors': 0,
                'fees': [], 'free': 0, 'unis': set(), 'qs_unis': set(),
                'nirf_unis': set(), 'domains': {}, 'universities': {},
                'complete': 0})
            a['total'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancies'] += 1
            elif s == 'Error': a['errors'] += 1
            fee = _parse_inr(c.get('cost', ''))
            if fee is not None and fee > 0:
                a['fees'].append(fee)
            if fee == 0:
                a['free'] += 1
            uni = c.get('university', '')
            if uni:
                a['unis'].add(uni)
                uni_l = _norm_name(uni)
                if uni_l in qs_set: a['qs_unis'].add(uni)
                if uni_l in nirf_set: a['nirf_unis'].add(uni)
            dom = normalize_domain(c.get('domain', ''))
            a['domains'][dom] = a['domains'].get(dom, 0) + 1
            if uni:
                a['universities'][uni] = a['universities'].get(uni, 0) + 1
            # Single-pass completeness tally (replaces the old O(countries×N)
            # nested loop): count courses whose 7 solvable attrs are all True.
            if all(bool(c.get(k, False)) for k in
                   ('cost_match', 'duration_match', 'mode_match', 'lang_match',
                    'country_match', 'uni_match', 'sk_match')):
                a['complete'] += 1

        for country, a in agg.items():
            tot = a['total']
            vr = a['verified'] / tot if tot else 0
            ir = (a['discrepancies'] + a['errors']) / tot if tot else 0
            med = _median(a['fees'])
            top_dom = max(a['domains'], key=a['domains'].get) if a['domains'] else None
            top_uni = max(a['universities'], key=a['universities'].get) if a['universities'] else None
            qs_unis = len(a['qs_unis'])
            nirf_unis = len(a['nirf_unis'])
            completeness = (a['complete'] / tot) if tot else 0
            qs_score = round(100 * (0.5 * vr + 0.3 * (1 - ir) + 0.2 * completeness))
            flags = []
            if tot >= 5 and vr < 0.5: flags.append("LOW-VERIF")
            if tot >= 5 and ir > 0.5: flags.append("HIGH-ISSUE")
            if med and med > 500000: flags.append("FEE-OUTLIER")
            out[country] = {
                "total": tot, "verified": a['verified'],
                "discrepancies": a['discrepancies'], "errors": a['errors'],
                "verified_rate": round(vr, 3), "issue_rate": round(ir, 3),
                "median_fee": int(round(med)) if med is not None else None,
                "free_count": a['free'], "qs_universities": qs_unis,
                "nirf_universities": nirf_unis,
                "top_domain": top_dom, "top_university": top_uni,
                "quality_score": max(0, min(100, qs_score)),
                "anomaly_flags": flags,
            }
    except Exception as e:
        print('[ANALYTICS] country_quality build failed:', e)
    return out


def _build_regional_groups(gc):
    out = {}
    try:
        agg = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            region = _region_for_country(country)
            a = agg.setdefault(region, {'countries': set(), 'total': 0,
                                        'verified': 0, 'discrepancies': 0,
                                        'errors': 0})
            a['countries'].add(country)
            a['total'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancies'] += 1
            elif s == 'Error': a['errors'] += 1
        for region, a in agg.items():
            out[region] = {
                "countries": len(a['countries']), "total": a['total'],
                "verified": a['verified'], "discrepancies": a['discrepancies'],
                "errors": a['errors'],
                "verified_rate": round(a['verified'] / a['total'], 3) if a['total'] else 0,
            }
    except Exception as e:
        print('[ANALYTICS] regional_groups build failed:', e)
    return out


def _build_geo_concentration(gc):
    out = {"hhi": 0, "n_countries": 0, "top1_share": 0, "top3_share": 0,
           "effective_countries": 0, "label": "DIVERSIFIED", "top1_country": None}
    try:
        counts = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            if country and country != 'Unknown':
                counts[country] = counts.get(country, 0) + 1
        total = sum(counts.values())
        if total <= 0:
            return out
        hhi = _hhi(counts)
        ranked = sorted(counts.items(), key=lambda x: -x[1])
        top1 = ranked[0][1] / total if ranked else 0
        top3 = sum(v for _, v in ranked[:3]) / total if ranked else 0
        eff = 1 / sum((v / total) ** 2 for v in counts.values()) if total else 0
        out = {"hhi": hhi, "n_countries": len(counts),
               "top1_share": round(top1 * 100, 1),
               "top3_share": round(top3 * 100, 1),
               "effective_countries": round(eff, 1),
               "label": _geo_hhi_label(hhi),
               "top1_country": ranked[0][0] if ranked else None}
    except Exception as e:
        print('[ANALYTICS] geo_concentration build failed:', e)
    return out


def _build_geo_problem_ranking(cq_dict):
    out = []
    try:
        for country, d in cq_dict.items():
            if d.get('total', 0) >= 5:
                out.append({"country": country, "total": d['total'],
                            "issues": d['discrepancies'] + d['errors'],
                            "issue_rate": d.get('issue_rate', 0),
                            "quality_score": d.get('quality_score', 0)})
        out.sort(key=lambda x: -x['issue_rate'])
        out = out[:12]
    except Exception as e:
        print('[ANALYTICS] geo_problem_ranking build failed:', e)
    return out


def _build_geo_anomalies(cq_dict):
    out = {"low_verification": [], "high_issue_rate": [], "fee_outlier": [],
           "global_median_fee": None}
    try:
        meds = [d['median_fee'] for d in cq_dict.values() if d.get('median_fee')]
        gmed = _median(meds) if meds else None
        out["global_median_fee"] = int(round(gmed)) if gmed is not None else None
        for country, d in cq_dict.items():
            if d.get('total', 0) < 5:
                continue
            if d.get('verified_rate', 1) < 0.6:
                out["low_verification"].append(country)
            if d.get('issue_rate', 0) > 0.4:
                out["high_issue_rate"].append(country)
            if d.get('median_fee') and gmed and d['median_fee'] > 2 * gmed:
                out["fee_outlier"].append(country)
    except Exception as e:
        print('[ANALYTICS] geo_anomalies build failed:', e)
    return out


def _build_geo_comparison_seed(cq_dict):
    try:
        ranked = sorted(cq_dict.items(), key=lambda x: -x[1].get('total', 0))
        a = ranked[0][0] if len(ranked) > 0 else None
        b = ranked[1][0] if len(ranked) > 1 else None
        return {"country_a": a, "country_b": b}
    except Exception:
        return {"country_a": None, "country_b": None}


def _build_vq_country_quality(gc):
    out = []
    try:
        agg = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            if not country or country == 'Unknown':
                continue
            a = agg.setdefault(country, {'total': 0, 'verified': 0,
                                         'discrepancies': 0, 'errors': 0,
                                         'matched': 0})
            a['total'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancies'] += 1
            elif s == 'Error': a['errors'] += 1
            for k in _ATTR_KEYS.values():
                if bool(c.get(k, False)):
                    a['matched'] += 1
        for country, a in agg.items():
            tot = a['total']
            vr = a['verified'] / tot if tot else 0
            er = a['errors'] / tot if tot else 0
            comp = a['matched'] / (tot * len(_ATTR_KEYS)) if tot else 0
            score = int(round(100 * (0.5 * vr + 0.3 * (1 - er) + 0.2 * comp)))
            out.append({"country": country, "total": tot, "verified": a['verified'],
                        "discrepancies": a['discrepancies'], "errors": a['errors'],
                        "verification_rate": round(vr, 3), "error_rate": round(er, 3),
                        "quality_score": max(0, min(100, score)),
                        "completeness": round(comp, 3)})
        out.sort(key=lambda x: -x['total'])
    except Exception as e:
        print('[ANALYTICS] vq country_quality build failed:', e)
    return out


def _build_vq_country_anomalies(gc):
    out = {}
    try:
        agg = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            if not country or country == 'Unknown':
                continue
            a = agg.setdefault(country, {'total': 0, 'verified': 0,
                                         'issues': 0})
            a['total'] += 1
            if c.get('status') == 'Verified': a['verified'] += 1
            if c.get('status') in ('Discrepancy', 'Error'): a['issues'] += 1
        for country, a in agg.items():
            tot = a['total']
            if tot < 5:
                out[country] = "SAMPLE-TOO-SMALL"
            elif a['verified'] / tot < 0.5:
                out[country] = "LOW"
            elif a['issues'] / tot > 0.5:
                out[country] = "HIGH"
            else:
                out[country] = None
    except Exception as e:
        print('[ANALYTICS] vq country anomalies build failed:', e)
    return out


def _build_domain_quality(gc):
    out = []
    try:
        agg = {}
        for c in gc:
            dom = normalize_domain(c.get('domain', ''))
            a = agg.setdefault(dom, {'total': 0, 'verified': 0,
                                     'discrepancies': 0, 'errors': 0})
            a['total'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancies'] += 1
            elif s == 'Error': a['errors'] += 1
        for dom, a in agg.items():
            tot = a['total']
            vr = a['verified'] / tot if tot else 0
            ir = (a['discrepancies'] + a['errors']) / tot if tot else 0
            score = int(round(100 * (0.6 * vr + 0.4 * (1 - ir))))
            out.append({"domain": dom, "total": tot, "verified": a['verified'],
                        "discrepancies": a['discrepancies'], "errors": a['errors'],
                        "verification_rate": round(vr, 3),
                        "quality_score": max(0, min(100, score))})
        out.sort(key=lambda x: -x['total'])
    except Exception as e:
        print('[ANALYTICS] domain_quality build failed:', e)
    return out


def _build_cross_anomalies(gc, vq):
    out = {"outlier_fees": [], "low_verification_countries": [],
           "high_error_domains": []}
    try:
        fees = [(_parse_inr(c.get('cost', '')) or 0) for c in gc]
        med = _median([f for f in fees if f > 0]) or 0
        for c in gc:
            f = _parse_inr(c.get('cost', '')) or 0
            if med > 0 and f > 3 * med:
                out["outlier_fees"].append({"course": c.get('name', ''),
                                             "university": c.get('university'),
                                             "country": c.get('country'),
                                             "fee_inr": round(f, 1)})
        # low verification countries
        ctry = {}
        for c in gc:
            country = c.get('country', 'Unknown')
            a = ctry.setdefault(country, {'total': 0, 'verified': 0})
            a['total'] += 1
            if c.get('status') == 'Verified': a['verified'] += 1
        for country, a in ctry.items():
            if a['total'] >= 5:
                vr = a['verified'] / a['total']
                if vr < 0.5:
                    out["low_verification_countries"].append(
                        {"country": country, "verification_rate": round(vr, 3),
                         "course_count": a['total']})
        # high error domains
        dom_agg = {}
        for c in gc:
            dom = normalize_domain(c.get('domain', ''))
            a = dom_agg.setdefault(dom, {'total': 0, 'errors': 0})
            a['total'] += 1
            if c.get('status') == 'Error': a['errors'] += 1
        for dom, a in dom_agg.items():
            if a['total'] >= 5:
                er = a['errors'] / a['total']
                if er > 0.3:
                    out["high_error_domains"].append(
                        {"domain": dom, "error_rate": round(er, 3),
                         "course_count": a['total']})
    except Exception as e:
        print('[ANALYTICS] cross anomalies build failed:', e)
    return out


def _build_university_leaderboard(gc, qs_set, nirf_set):
    out = []
    try:
        agg = {}
        for c in gc:
            uni = c.get('university', '')
            if not uni:
                continue
            a = agg.setdefault(uni, {'country': c.get('country'), 'count': 0,
                                     'verified': 0, 'discrepancies': 0, 'errors': 0})
            a['count'] += 1
            s = c.get('status')
            if s == 'Verified': a['verified'] += 1
            elif s == 'Discrepancy': a['discrepancies'] += 1
            elif s == 'Error': a['errors'] += 1
        rows = []
        for uni, a in agg.items():
            uni_l = _norm_name(uni)
            qs = uni_l in qs_set
            nirf = uni_l in nirf_set
            rows.append({"university": uni, "country": a['country'],
                          "course_count": a['count'], "verified": a['verified'],
                          "discrepancies": a['discrepancies'], "errors": a['errors'],
                          "verification_rate": round(a['verified'] / a['count'], 3)
                                               if a['count'] else 0,
                          "qs_ranked": bool(qs), "nirf_ranked": bool(nirf),
                          "ranked": bool(qs or nirf)})
        rows.sort(key=lambda x: -x['course_count'])
        out = rows[:15]
    except Exception as e:
        print('[ANALYTICS] university_leaderboard build failed:', e)
    return out


def _build_benchmark(gc, qs_set, nirf_set, geo_conc):
    out = {}
    try:
        india = [c for c in gc if str(c.get('country', '')).lower() == 'india']
        intl = [c for c in gc if str(c.get('country', '')).lower() != 'india']
        n_i, n_x = len(india), len(intl)
        tot = n_i + n_x

        def rate(rows, status):
            return round(sum(1 for c in rows if c.get('status') == status) / len(rows), 3) \
                if rows else 0

        def median_fee(rows):
            fees = [_parse_inr(c.get('cost', '')) for c in rows]
            fees = [f for f in fees if f and f > 0]
            m = _median(fees)
            return int(round(m)) if m is not None else None

        def cai(rows):
            fees = [_parse_inr(c.get('cost', '')) for c in rows]
            free = sum(1 for f in fees if f == 0)
            aff = sum(1 for f in fees if f and 0 < f <= 50000)
            t = len(rows)
            return int(round(40 * free / t + 35 * aff / t)) if t else 0

        def ranked_share(rows, s):
            return round(sum(1 for c in rows
                             if _norm_name(c.get('university', '')) in s) / len(rows), 3) \
                if rows else 0

        def top_spec(rows):
            doms = {}
            for c in rows:
                d = normalize_domain(c.get('domain', ''))
                doms[d] = doms.get(d, 0) + 1
            return max(doms, key=doms.get) if doms else None

        india_hhi = _hhi({c.get('country', 'Unknown'): 1 for c in india}) if india else 0
        # geographic contribution: share of total catalog
        def metric(label, india_v, intl_v, fmt=None):
            delta = round(india_v - intl_v, 3) if isinstance(india_v, (int, float)) \
                and isinstance(intl_v, (int, float)) else None
            return {"india": india_v, "international": intl_v, "delta": delta,
                    "label": label}

        out = {
            "courses": metric("Total Courses", n_i, n_x),
            "variant_share": metric("Catalog Share",
                                     round(n_i / tot, 3) if tot else 0,
                                     round(n_x / tot, 3) if tot else 0),
            "verification_rate": metric("Verification Rate",
                                        rate(india, 'Verified'), rate(intl, 'Verified')),
            "discrepancy_rate": metric("Discrepancy Rate",
                                       rate(india, 'Discrepancy'), rate(intl, 'Discrepancy')),
            "error_rate": metric("Error Rate",
                                  rate(india, 'Error'), rate(intl, 'Error')),
            "median_fee_inr": metric("Median Fee INR",
                                     median_fee(india), median_fee(intl)),
            "cost_access_index": metric("Cost Access Index",
                                         cai(india), cai(intl)),
            "qs_ranked_share": metric("QS-Ranked Share",
                                       ranked_share(india, qs_set),
                                       ranked_share(intl, qs_set)),
            "nirf_ranked_share": metric("NIRF-Ranked Share",
                                        ranked_share(india, nirf_set),
                                        ranked_share(intl, nirf_set)),
            "top_specialization": metric("Top Specialization",
                                          top_spec(india), top_spec(intl)),
            "geographic_contribution_hhi": metric("Geographic Contribution HHI",
                                                  india_hhi, geo_conc.get('hhi', 0)),
        }
    except Exception as e:
        print('[ANALYTICS] benchmark build failed:', e)
    return out


def _build_ranking_mix(analytics_courses):
    out = {"qs_ranked": 0, "nirf_ranked": 0, "both": 0, "unranked": 0, "total": 0,
           "qs_ranked_pct": 0, "nirf_ranked_pct": 0, "unranked_pct": 0}
    try:
        qs = sum(1 for r in analytics_courses if r.get('qs_ranked') and not r.get('nirf_ranked'))
        nirf = sum(1 for r in analytics_courses if r.get('nirf_ranked') and not r.get('qs_ranked'))
        both = sum(1 for r in analytics_courses if r.get('qs_ranked') and r.get('nirf_ranked'))
        unranked = sum(1 for r in analytics_courses
                       if not r.get('qs_ranked') and not r.get('nirf_ranked'))
        total = len(analytics_courses)
        out = {"qs_ranked": qs, "nirf_ranked": nirf, "both": both,
               "unranked": unranked, "total": total,
               "qs_ranked_pct": round(qs / total * 100, 1) if total else 0,
               "nirf_ranked_pct": round(nirf / total * 100, 1) if total else 0,
               "unranked_pct": round(unranked / total * 100, 1) if total else 0}
    except Exception as e:
        print('[ANALYTICS] ranking_mix build failed:', e)
    return out


def _build_ranked_share(analytics_courses):
    try:
        total = len(analytics_courses)
        if not total:
            return {"qs_pct": 0, "nirf_pct": 0}
        qs = sum(1 for r in analytics_courses if r.get('qs_ranked'))
        nirf = sum(1 for r in analytics_courses if r.get('nirf_ranked'))
        return {"qs_pct": round(qs / total * 100, 1),
                "nirf_pct": round(nirf / total * 100, 1)}
    except Exception:
        return {"qs_pct": 0, "nirf_pct": 0}


def _build_ranked_vs_unranked(analytics_courses):
    out = []
    try:
        def cohort(pred):
            rows = [r for r in analytics_courses if pred(r)]
            tot = len(rows)
            vr = round(sum(1 for r in rows if r.get('status') == 'Verified') / tot, 3) \
                if tot else 0
            dr = round(sum(1 for r in rows if r.get('status') == 'Discrepancy') / tot, 3) \
                if tot else 0
            fees = [r['fee_inr'] for r in rows if r.get('fee_inr') and r['fee_inr'] > 0]
            med = _median(fees)
            return {"courses": tot, "verification_rate": vr,
                    "discrepancy_rate": dr,
                    "median_fee_inr": int(round(med)) if med is not None else None}

        out = [
            {"cohort": "QS Ranked", **cohort(lambda r: r.get('qs_ranked'))},
            {"cohort": "NIRF Ranked", **cohort(lambda r: r.get('nirf_ranked'))},
            {"cohort": "Both", **cohort(lambda r: r.get('qs_ranked') and r.get('nirf_ranked'))},
            {"cohort": "Unranked",
             **cohort(lambda r: not r.get('qs_ranked') and not r.get('nirf_ranked'))},
        ]
    except Exception as e:
        print('[ANALYTICS] ranked_vs_unranked build failed:', e)
    return out


def _build_concentration(country_pivot, domain_pivot):
    out = {"geographic_hhi": 0, "specialization_hhi": {"value": 0, "label": "Diversified"},
           "top_country_share_pct": 0, "top_domain_share_pct": 0,
           "top_country": None, "top_domain": None}
    try:
        geo_h = _hhi(country_pivot)
        spec_h = _hhi({d: v['Total'] for d, v in domain_pivot.items()
                       if isinstance(v, dict) and 'Total' in v}) if domain_pivot else 0
        c_tot = sum(country_pivot.values()) if country_pivot else 0
        d_tot = sum(v['Total'] for v in domain_pivot.values()
                   if isinstance(v, dict) and 'Total' in v) if domain_pivot else 0
        top_c = max(country_pivot.items(), key=lambda x: x[1]) if country_pivot else None
        top_d = max(((d, v['Total']) for d, v in domain_pivot.items()
                     if isinstance(v, dict) and 'Total' in v), key=lambda x: x[1]) \
            if domain_pivot else None
        out = {
            "geographic_hhi": geo_h,
            "specialization_hhi": {"value": spec_h, "label": _hhi_label(spec_h)},
            "top_country_share_pct": round(top_c[1] / c_tot * 100, 1)
            if top_c and c_tot else 0,
            "top_domain_share_pct": round(top_d[1] / d_tot * 100, 1)
            if top_d and d_tot else 0,
            "top_country": top_c[0] if top_c else None,
            "top_domain": top_d[0] if top_d else None,
        }
    except Exception as e:
        print('[ANALYTICS] concentration build failed:', e)
    return out


def _build_specialization_hhi(domain_pivot):
    try:
        counts = {d: v['Total'] for d, v in domain_pivot.items()
                  if isinstance(v, dict) and 'Total' in v}
        h = _hhi(counts)
        return {"value": h, "label": _hhi_label(h)}
    except Exception:
        return {"value": 0, "label": "Diversified"}


def _build_domain_saturation(domain_pivot):
    out = []
    try:
        counts = {d: v['Total'] for d, v in domain_pivot.items()
                  if isinstance(v, dict) and 'Total' in v
                  and d not in ('Unknown Domain', 'Unknown', 'Total')}
        total = sum(counts.values())
        for d, c in sorted(counts.items(), key=lambda x: -x[1]):
            share = c / total * 100 if total else 0
            out.append({"domain": d, "total": c, "share_pct": round(share, 1),
                        "hhi_contribution": round((c / total) ** 2 * 10000, 1) if total else 0,
                        "saturation_label": _saturation_label(share)})
    except Exception as e:
        print('[ANALYTICS] domain_saturation build failed:', e)
    return out


def _build_key_findings(d):
    """Auto-generated professional plain-text findings (no emoji)."""
    findings = []
    try:
        stats = d.get('stats', {})
        total = stats.get('total', 0)
        verified = stats.get('verified', 0)
        discrepancies = stats.get('discrepancies', 0)
        errors = stats.get('errors', 0)
        vr = round(verified / total * 100, 1) if total else 0
        findings.append(
            f"The catalog spans {total} programs with a verification match rate "
            f"of {vr} percent, {verified} perfectly matched, {discrepancies} "
            f"flagged for review, and {errors} unreachable pages.")

        cc = d.get('country_pivot') or {}
        top_c = max(cc.items(), key=lambda x: x[1]) if cc else None
        if top_c:
            findings.append(
                f"Geographic footprint covers {len(cc)} countries; the leading "
                f"origin is {top_c[0]} with {top_c[1]} programs.")

        dp = d.get('domain_pivot') or {}
        top_d = max(((k, v['Total']) for k, v in dp.items()
                     if isinstance(v, dict) and 'Total' in v), key=lambda x: x[1],
                    default=None)
        if top_d:
            findings.append(
                f"Specialization concentration is highest in {top_d[0]} "
                f"({top_d[1]} programs).")

        ca = d.get('cost_access') or {}
        ai = ca.get('affordability_index', 0)
        med = ca.get('median_fee_inr')
        fvp = ca.get('free_vs_paid') or {}
        free = fvp.get('free', 0)
        findings.append(
            f"Cost-access intelligence shows an affordability index of {ai} "
            f"with {free} free programs and a median paid fee of "
            f"{med if med is not None else 'n/a'} INR.")

        rm = d.get('ranking_mix') or {}
        qs = rm.get('qs_ranked_pct', 0)
        nirf = rm.get('nirf_ranked_pct', 0)
        findings.append(
            f"University ranking coverage stands at {qs} percent QS-ranked "
            f"and {nirf} percent NIRF-ranked across the catalog.")

        dqh = (d.get('verification_quality') or {}).get('data_quality_health') or {}
        score = dqh.get('score', 0)
        findings.append(
            f"The composite data-quality health score is {score} out of 100, "
            f"reflecting verification rate, error load, and attribute completeness.")
    except Exception as e:
        print('[ANALYTICS] key_findings build failed:', e)
    return findings




@app.route("/api/upload", methods=["POST", "OPTIONS"])
def upload_data():
    if request.method == "OPTIONS": return "", 204
    if 'files[]' not in request.files:
        return jsonify({"status": "error", "message": "No files uploaded"})
        
    files = request.files.getlist('files[]')
    
    attributes = ['Cost', 'Duration', 'Mode', 'Language', 'Country', 'University', 'Skills']
    ranking_attributes = ['QS', 'NIRF', 'Free Box', 'Scholarship Box']
    
    updates = 0
    wiped_count = 0
    verified_in_this_batch = []
    # Collect ALL extracted courses across all files first, then do a range-wipe.
    # Pass 1: parse every page of every PDF, collect {id -> data} map.
    all_extracted = {}   # pdf_course_id -> {extracted fields, pdf_table, page, filename}
    
    for file in files:
        if file.filename == '': continue
        
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        file.save(temp_path)
        
        try:
            import fitz
            doc = fitz.open(temp_path)
            for page_num in range(len(doc)):
                # 1. Ultra-fast text extraction with PyMuPDF
                fitz_page = doc[page_num]
                text = fitz_page.get_text()
                if not text: continue
                
                match = re.search(r'^\s*(\d+)\.\s+(.+?)\s*$', text, re.MULTILINE)
                if not match: continue
                
                title = match.group(2).strip()
                
                # 2. Ultra-fast native table extraction with PyMuPDF
                tabs = fitz_page.find_tables()
                extracted = {}
                if tabs:
                    table = tabs[0].extract()
                    for row in table:
                        if len(row) >= 4:
                            attr_name = str(row[0]).strip().replace('\n', ' ')
                            if attr_name.lower() == 'attribute': continue
                            
                            original = str(row[1]).strip().replace('\n', ' ') if len(row) > 1 else ''
                            verified = str(row[2]).strip().replace('\n', ' ') if len(row) > 2 else ''
                            row_status = str(row[3]).strip().replace('\n', ' ') if len(row) > 3 else ''
                            
                            if 'pdf_table' not in extracted:
                                extracted['pdf_table'] = []
                            extracted['pdf_table'].append({
                                "attribute": attr_name,
                                "original": original,
                                "verified": verified,
                                "status": row_status
                            })
                            
                            for a in attributes:
                                if a.lower() in attr_name.lower():
                                    if a.lower() == 'university':
                                        extracted['Original_University'] = original
                                    if row_status == 'MATCH':
                                        extracted[a] = 'MATCH'
                                    break
                            
                            for ra in ranking_attributes:
                                if ra.lower().replace(' box', '') in attr_name.lower().replace(' box', ''):
                                    if row_status == 'MATCH':
                                        extracted[ra] = 'MATCH'
                                    break
                
                actual_page = page_num + 1
                page_match = re.search(r'PDF Page (\d+)', text)
                if page_match:
                    actual_page = int(page_match.group(1))
                
                if 'free' in file.filename.lower() and actual_page <= 7:
                    actual_page += 16
                    
                pdf_course_id = int(match.group(1))
                
                # Detect domain from filename
                raw_name = file.filename.replace('_', ' ').replace('-', ' ').lower()
                detected_domain = None
                valid_domains = [
                    "High Value Low Cost", "Post Graduate Certificate", "Certificate",
                    "Bachelors", "Masters", "Post Graduate Diploma", "Diploma",
                    "Free to Audit", "Free"
                ]
                for d in valid_domains:
                    if d.lower() in raw_name:
                        detected_domain = normalize_domain(d)
                        break
                
                all_extracted[pdf_course_id] = {
                    'extracted': extracted,
                    'title': title,
                    'page': actual_page,
                    'domain': detected_domain,
                }
            if 'doc' in locals():
                doc.close()
        except Exception as e:
            print(f"Error processing {file.filename}: {e}")
        finally:
            if os.path.exists(temp_path):
<<<<<<< HEAD
                os.remove(temp_path)
    if updates > 0:
        # Re-apply updates to the CURRENT global_courses in case a background 
        # reload swapped the objects out from under us during the long PDF processing.
        for updated_c in verified_in_this_batch:
            for i, c in enumerate(global_courses):
                if c.get('id') == updated_c.get('id'):
                    global_courses[i] = updated_c
                    break

        # Save specific courses to ensure complete data persistence
        # This prevents data loss when MongoDB is the primary data source
        try:
            save_courses(verified_in_this_batch)
=======
                try:
                    os.remove(temp_path)
                except Exception:
                    pass
    
    # Pass 2: Range-wipe + replace.
    # Determine the [min_id, max_id] range from the uploaded PDF.
    # ALL courses in that range get a FULL reset, even if the PDF only
    # covers some of them — the old data is wiped so nothing stale persists.
    if all_extracted:
        min_id = min(all_extracted.keys())
        max_id = max(all_extracted.keys())
        
        for c in global_courses:
            cid = c.get('id')
            if cid is None: continue
            try:
                cid = int(cid)
            except (ValueError, TypeError):
                continue
            
            # Only touch courses within the PDF's ID range
            if cid < min_id or cid > max_id:
                continue
            
            # ── FULL RESET: wipe all old verification state ──
            c['pdf_page'] = None
            c['solved_attrs'] = []
            c['cost_match'] = False
            c['duration_match'] = False
            c['mode_match'] = False
            c['lang_match'] = False
            c['country_match'] = False
            c['uni_match'] = False
            c['sk_match'] = False
            c['qs_match'] = False
            c['nirf_match'] = False
            c['free_match'] = False
            c['scholarship_match'] = False
            c['pdf_table'] = []
            c['disc_reason'] = ''
            c['status'] = 'Unverified'
            c['issue_category'] = ''
            c['issue_sub_type'] = ''
            
            # ── Replace with new PDF data if this course is in the PDF ──
            if cid in all_extracted:
                ext_data = all_extracted[cid]
                extracted = ext_data['extracted']
                
                c['pdf_page'] = ext_data['page']
                c['cost_match'] = (extracted.get('Cost') == 'MATCH')
                c['duration_match'] = (extracted.get('Duration') == 'MATCH')
                c['mode_match'] = (extracted.get('Mode') == 'MATCH')
                c['lang_match'] = (extracted.get('Language') == 'MATCH')
                c['country_match'] = (extracted.get('Country') == 'MATCH')
                c['uni_match'] = (extracted.get('University') == 'MATCH')
                c['sk_match'] = (extracted.get('Skills') == 'MATCH')
                
                if 'pdf_table' in extracted:
                    c['pdf_table'] = extracted['pdf_table']
                    
                    # Parse QS/NIRF badge status from pdf_table
                    for row in extracted['pdf_table']:
                        row_attr = str(row.get('attribute', '')).lower()
                        row_orig = str(row.get('original', '')).lower()
                        if 'qs' in row_attr and 'badge' in row_orig:
                            c['has_qs_badge'] = 'true' in row_orig or 'present' in row_orig
                        if 'nirf' in row_attr and 'badge' in row_orig:
                            c['has_nirf_badge'] = 'true' in row_orig or 'present' in row_orig
                
                if ext_data['domain']:
                    c['domain'] = ext_data['domain']
                
                # Check QS/NIRF/Free/Scholarship from pdf_table rows
                qs_match = True
                nirf_match = True
                free_match = True
                scholarship_match = True
                if 'pdf_table' in extracted:
                    for row in extracted['pdf_table']:
                        row_attr_name = str(row.get('attribute', '')).lower().strip()
                        row_status = str(row.get('status', '')).strip().upper()
                        if 'qs' in row_attr_name and 'ranked' in row_attr_name:
                            qs_match = (row_status != 'FALSE')
                        elif 'nirf' in row_attr_name and 'ranked' in row_attr_name:
                            nirf_match = (row_status != 'FALSE')
                        elif 'free' in row_attr_name and 'box' in row_attr_name:
                            free_match = (row_status != 'FALSE')
                        elif 'scholarship' in row_attr_name and 'box' in row_attr_name:
                            scholarship_match = (row_status != 'FALSE')
                
                c['qs_match'] = qs_match
                c['nirf_match'] = nirf_match
                c['free_match'] = free_match
                c['scholarship_match'] = scholarship_match
                
                has_mismatch = False
                fails = []
                if 'pdf_table' in extracted:
                    for row in extracted['pdf_table']:
                        row_status = str(row.get('status', '')).strip().upper()
                        if row_status != 'MATCH':
                            has_mismatch = True
                            attr = str(row.get('attribute', '')).strip()
                            if attr: fails.append(attr)
                else:
                    has_mismatch = True
                    fails.append("No Verification Data")
                
                if not has_mismatch:
                    c['status'] = 'Verified'
                    c['disc_reason'] = ''
                    c['issue_category'] = ISSUE_CATEGORY_VERIFIED
                    c['issue_sub_type'] = ''
                else:
                    c['status'] = 'Discrepancy'
                    c['issue_category'] = ISSUE_CATEGORY_COURSE
                    c['disc_reason'] = "Mismatch: " + ", ".join(fails)
                
                c['issue_sub_type'] = derive_issue_sub_type(c)
                updates += 1
                verified_in_this_batch.append(dict(c))
            else:
                # Course is in the ID range but NOT in the PDF — it stays
                # reset to Unverified (already done above). Count it as
                # processed so the frontend knows it was wiped.
                wiped_count += 1
    
    if (updates > 0 or wiped_count > 0) and all_extracted:
        try:
            # Collect ONLY courses in the uploaded PDF's ID range.
            # Do NOT rewrite all 3700+ courses — just the affected slice.
            modified_range = []
            for c in global_courses:
                try:
                    cid = int(c.get('id', -1))
                except (ValueError, TypeError):
                    continue
                if min_id <= cid <= max_id:
                    modified_range.append(c)

            # Delete stale MongoDB documents for this range first so no
            # leftover docs survive if the new PDF has fewer courses.
            if db is not None and modified_range:
                try:
                    ids_in_range = [int(c['id']) for c in modified_range]
                    result_del = db.courses.delete_many({'id': {'$in': ids_in_range}})
                    print(f"[UPLOAD] Deleted {result_del.deleted_count} stale MongoDB docs for range {min_id}-{max_id}")
                except Exception as del_err:
                    print(f"[UPLOAD] MongoDB delete error: {del_err}")

            # Now upsert only the fresh range (not all global_courses).
            save_courses(modified_range)
            _invalidate_data_cache()
            # Push the TTL far enough ahead so the background stale-check
            # doesn't immediately reload from MongoDB before the writes are
            # durable (120 s is plenty for Atlas to acknowledge the bulk write).
            global _LAST_LOAD_TS
            _LAST_LOAD_TS = time.time() + 90  # delay next mongo reload by 120s total

            # ── Push pre-computed API payloads to MongoDB for instant website loading ──
            try:
                _push_cached_payloads_to_mongo()
            except Exception as cache_err:
                print(f"[UPLOAD] Cache push error: {cache_err}")
>>>>>>> c8f96f6d812a0ceb07e05419211df53a7dce0d35
        except Exception as e:
            print(f"[UPLOAD] save_courses error: {e}")

    # Compute fresh stats to include in the response so the frontend
    # can update KPIs instantly without a second fetch round-trip.
    fresh_data_payload = _get_cached_data_payload()

    return jsonify({
        "status": "success",
        "updates": updates,
        "wiped": wiped_count,
        "message": f"Processed {len(files)} files. Updated {updates} courses" + (f" (range {min_id}-{max_id}), wiped {wiped_count} stale." if all_extracted else "."),
        "verified_courses": verified_in_this_batch,
        "data_payload": fresh_data_payload
    })

if __name__ == "__main__":
    print("[*] Starting Live Verification Dashboard on http://localhost:5000")
    # Single, stable process — no debug reloader. The watchdog reloader spawns
    # a second process and restarts the child on file changes, which briefly
    # empties global_courses mid-request (so /api/data.json and solve responses
    # can return 0) and makes localhost appear to "sleep" during the restart.
    app.run(debug=False, use_reloader=False, host="0.0.0.0", port=5000)