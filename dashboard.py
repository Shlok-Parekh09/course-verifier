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

# CORS — allow the Firebase-hosted static site (and any other client) to call
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

# Initialize Firebase
import os

db_client = None
db = None
try:
    mongo_uri = os.environ.get('MONGO_URI')
    if not mongo_uri and os.path.exists('mongo_uri.txt'):
        with open('mongo_uri.txt', 'r') as f:
            mongo_uri = f.read().strip()
            
    if mongo_uri:
        db_client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        db_client.admin.command('ping')
        db = db_client['course_verifier']
        print("Connected to MongoDB Atlas")
    else:
        print("No MONGO_URI found. Create 'mongo_uri.txt' with your connection string.")
except Exception as e:
    print("MongoDB initialization failed:", e)
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
    """
    Save courses to all persistence layers
    Args:
        updated_courses: Optional list of courses that were updated. 
                        If None, all courses will be saved to Firestore.
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
            
        # 3. EXPORT STATIC JSON FOR PUBLIC HOSTING
        try:
            os.makedirs(os.path.join("public", "api"), exist_ok=True)
            
            # Export courses.json
            with open(os.path.join("public", "api", "courses.json"), "w", encoding="utf-8") as f:
                json.dump({"status": "success", "courses": global_courses}, f, indent=2)
                
            # Export data.json (aggregated stats)
            total_courses = len(global_courses)
            verified = sum(1 for c in global_courses if c.get('status') == 'Verified')
            discrepancies = sum(1 for c in global_courses if c.get('status') == 'Discrepancy')
            errors = sum(1 for c in global_courses if c.get('status') == 'Error')
            unverified = sum(1 for c in global_courses if c.get('status') == 'Unverified')
            website_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE)
            course_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE)

            website_sub_counts = {}
            course_sub_counts = {}
            domain_issue_counts = {}
            for c in global_courses:
                sub = c.get('issue_sub_type', '')
                if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE and sub:
                    website_sub_counts[sub] = website_sub_counts.get(sub, 0) + 1
                elif c.get('issue_category') == ISSUE_CATEGORY_COURSE and sub:
                    course_sub_counts[sub] = course_sub_counts.get(sub, 0) + 1
                if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
                    dom = normalize_domain(c.get('domain', 'Unknown'))
                    domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1

            domain_warnings = [{"domain": d, "issue_count": cnt} for d, cnt in domain_issue_counts.items() if cnt >= 3]

            domain_counts = {}
            country_counts = {}
            country_status = {}
            discrepancy_list = []
            website_issue_list = []
            course_issue_list = []

            for c in global_courses:
                d = normalize_domain(c.get('domain')) if c.get('domain') else None
                if d:
                    domain_counts[d] = domain_counts.get(d, 0) + 1
                cty = c.get('country')
                if cty and cty != 'Unknown':
                    cty = clean_country(cty)
                    country_counts[cty] = country_counts.get(cty, 0) + 1
                    st = country_status.setdefault(cty, {"total": 0, "verified": 0, "discrepancies": 0, "errors": 0})
                    st["total"] += 1
                    s = c.get('status')
                    if s == 'Verified':
                        st["verified"] += 1
                    elif s == 'Discrepancy':
                        st["discrepancies"] += 1
                    elif s == 'Error':
                        st["errors"] += 1

                if c.get('status') == 'Discrepancy':
                    discrepancy_list.append({
                        "name": c.get('name', ''),
                        "university": c.get('university', ''),
                        "reason": c.get('disc_reason', ''),
                        "domain": d
                    })
                if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
                    website_issue_list.append({
                        "name": c.get('name', ''),
                        "university": c.get('university', ''),
                        "sub_type": c.get('issue_sub_type', ''),
                        "reason": c.get('disc_reason', ''),
                        "domain": d
                    })
                elif c.get('issue_category') == ISSUE_CATEGORY_COURSE:
                    course_issue_list.append({
                        "name": c.get('name', ''),
                        "university": c.get('university', ''),
                        "sub_type": c.get('issue_sub_type', ''),
                        "reason": c.get('disc_reason', ''),
                        "domain": d
                    })

            data_json = {
                "status": "success",
                "stats": {
                    "total": total_courses,
                    "verified": verified,
                    "discrepancies": discrepancies,
                    "errors": errors,
                    "unverified": unverified,
                    "website_issues": website_issues,
                    "course_issues": course_issues,
                    "open_issues": sum(course_open_issues(c) for c in global_courses)
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
                "recent": [c for c in global_courses if c.get('status') in ['Discrepancy', 'Error'] and 'pdf_page' in c]
            }
            with open(os.path.join("public", "api", "data.json"), "w", encoding="utf-8") as f:
                json.dump(data_json, f, indent=2)

            # Export analytics.json so the hosted Analytics tab (which reads the
            # static file) stays in sync with the normalized credential mix +
            # tiered pricing. Without this, analytics.json drifts stale because
            # it is only ever written here, never on demand by the live route.
            try:
                analytics_payload = {"status": "success", "data": build_analytics_data()}
                with open(os.path.join("public", "api", "analytics.json"), "w", encoding="utf-8") as f:
                    json.dump(analytics_payload, f, indent=2)
            except Exception as ae:
                print(f"[SAVE] ⚠ Could not export analytics.json: {ae}")

            print("[SAVE] ✓ Exported static JSON files for hosting")
        except Exception as e:
            print(f"[SAVE] ✗ Error exporting static JSON: {e}")

        # 4. OPTIONAL: Trigger Firebase deploy (non-blocking)
        # Only deploy if AUTO_DEPLOY environment variable is set to 'true'
        if updated_courses and os.environ.get('AUTO_DEPLOY', 'false').lower() == 'true':
            import threading
            def deploy_site():
                try:
                    print("[DEPLOY] Starting Firebase deployment...")
                    result = os.system("firebase deploy --only hosting")
                    if result == 0:
                        print("[DEPLOY] ✓ Successfully deployed to live website")
                    else:
                        print(f"[DEPLOY] ✗ Deployment failed with exit code {result}")
                except Exception as e:
                    print(f"[DEPLOY] ✗ Deployment error: {e}")
            threading.Thread(target=deploy_site, daemon=True).start()
        else:
            print("[DEPLOY] ⚠ Auto-deploy disabled. Run 'firebase deploy --only hosting' manually to update live site.")

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
        # Check both disc_reason and reason since they might be labeled differently depending on the source
        desc_text = str(c.get('cost_description', '')) + " " + str(c.get('duration_description', '')) + " " + str(c.get('cost_verified', '')) + " " + str(c.get('duration_verified', '')) + " " + str(c.get('disc_reason', '')) + " " + str(c.get('reason', '')) + " " + _pdf_table_text(c)
        
        has_page_error = 'page load error' in desc_text.lower() or 'website unreachable' in desc_text.lower() or 'llm fallback' in desc_text.lower()
        has_uni_match = c.get('uni_match') is not False
        matched_fields_str = str(c.get('matched_fields', '[]'))
        has_name_match = True
        if 'matched_fields' in c and 'Name' not in matched_fields_str:
            has_name_match = False
            
        web_status = str(c.get('web_status', '')).upper()
        
        # If it was natively flagged as Unverified in older runs, and has an error message, it's a website issue
        is_unverified = c.get('status') == 'Unverified'
        
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

        # Backfill issue_sub_type from real signals when missing. Never
        # overwrites a value already persisted in Mongo / 1.json.
        if not c.get('issue_sub_type'):
            c['issue_sub_type'] = derive_issue_sub_type(c)

    # Atomic swap: global_courses is never observed empty by a concurrent
    # reader (solve's compute_stats, /api/data.json) mid-reload.
    global_courses[:] = loaded

# Load immediately
load_courses()

# On Vercel, the serverless function instance is reused across requests, so
# global_courses (loaded once above) goes stale and the hosted dashboard never
# sees new uploads. Refresh from MongoDB on a short TTL so the live site stays
# current. Local dev benefits too: it picks up writes from other clients.
_LAST_LOAD_TS = time.time()
# On the local machine (1.json present) we never poll MongoDB — the local file
# IS the source of truth and MongoDB re-polling would overwrite in-memory edits.
# On production (Vercel / Cloud Run) we reload every 120 s so multi-client
# changes propagate without hammering Atlas.
_IS_LOCAL = os.path.exists(PERSISTENT_FILE)
_LOAD_TTL_SEC = 999999 if _IS_LOCAL else 120
_load_lock = threading.Lock()

def _refresh_courses_if_stale():
    """Reload global_courses from MongoDB if the in-memory cache is older than
    _LOAD_TTL_SEC seconds. No-op when MongoDB is not connected."""
    global _LAST_LOAD_TS
    if db is None:
        return
    if (time.time() - _LAST_LOAD_TS) < _LOAD_TTL_SEC:
        return
    with _load_lock:
        # Re-check inside the lock to avoid duplicate concurrent reloads.
        if (time.time() - _LAST_LOAD_TS) < _LOAD_TTL_SEC:
            return
        try:
            load_courses()
            _LAST_LOAD_TS = time.time()
            print("[REFRESH] reloaded global_courses from MongoDB")
        except Exception as e:
            print("[REFRESH] error reloading from MongoDB:", e)

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
    verified = discrepancies = errors = unverified = 0
    website_issues = course_issues = 0
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

        # Issue lists (only name/uni/reason/domain — NOT full course objects)
        if s == 'Discrepancy':
            discrepancy_list.append({
                "name": c.get('name', ''), "university": c.get('university', ''),
                "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
            })
        if cat == ISSUE_CATEGORY_WEBSITE:
            website_issue_list.append({
                "name": c.get('name', ''), "university": c.get('university', ''),
                "sub_type": sub, "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
            })
        elif cat == ISSUE_CATEGORY_COURSE:
            course_issue_list.append({
                "name": c.get('name', ''), "university": c.get('university', ''),
                "sub_type": sub, "reason": c.get('disc_reason', ''), "domain": c.get('domain', '')
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
            
        # Resync everything to Firestore (since IDs changed)
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

    Persists to Firestore + 1.json + public/api/data.json so every dashboard
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

def build_analytics_data():
    """Build the analytics payload dict (course_category, pricing_category,
    variant_category, domain_pivot, country_pivot). Uses global_courses (live
    MongoDB data) as the single source of truth — NOT static Excel/JSON files
    that drift stale after uploads/solves."""
    data = {
        "course_category": {},
        "variant_category": {},
        "pricing_category": {},
        "domain_pivot": {},
        "country_pivot": {}
    }

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

    return data


@app.route("/api/analytics", methods=["GET"])
@app.route("/api/analytics.json", methods=["GET"])
def api_analytics():
    _refresh_courses_if_stale()
    try:
        return jsonify({"status": "success", "data": build_analytics_data()})
    except Exception as e:
        import traceback
        return jsonify({"status": "error", "message": str(e), "trace": traceback.format_exc()})

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