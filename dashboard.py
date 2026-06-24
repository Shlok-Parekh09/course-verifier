import os
import json
import re
import fitz
import pdfplumber
import tempfile
import time
import threading
import pymongo
from pymongo import MongoClient, UpdateOne
from flask import Flask, render_template, jsonify, request
from werkzeug.utils import secure_filename

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
]

def _attr_is_match(c, key):
    """Resolve a modal-table MATCH/FALSE flag for a course dict."""
    if key == 'qs_match_expr':
        return bool(c.get('qs_ranked', False)) or (not c.get('has_qs_badge', False))
    if key == 'nirf_match_expr':
        return bool(c.get('nirf_ranked', False)) or (not c.get('has_nirf_badge', False))
    if key == 'free_match_expr':
        has_free = bool(c.get('has_free_box', False))
        web_cost = str(c.get('web_cost', '') or '').lower()
        web_free = 'free' in web_cost
        return has_free == web_free
    return bool(c.get(key, False))

def course_false_attrs(c):
    """List of attribute names currently FALSE (i.e. open) for a course."""
    return [name for name, key in ATTRIBUTE_ROWS if not _attr_is_match(c, key)]

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
        c['issue_sub_type'] = ''
        c['status'] = 'Verified'
        c['disc_reason'] = ''
    else:
        c['issue_category'] = ISSUE_CATEGORY_COURSE
        c['status'] = 'Discrepancy'

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
                    dom = c.get('domain', 'Unknown')
                    domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1

            domain_warnings = [{"domain": d, "issue_count": cnt} for d, cnt in domain_issue_counts.items() if cnt >= 3]

            domain_counts = {}
            country_counts = {}
            discrepancy_list = []
            website_issue_list = []
            course_issue_list = []

            for c in global_courses:
                d = c.get('domain')
                if d:
                    domain_counts[d] = domain_counts.get(d, 0) + 1
                cty = c.get('country')
                if cty and cty != 'Unknown':
                    country_counts[cty] = country_counts.get(cty, 0) + 1

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
                "discrepancy_list": discrepancy_list,
                "website_issue_list": website_issue_list,
                "course_issue_list": course_issue_list,
                "recent": [c for c in global_courses if c.get('status') in ['Discrepancy', 'Error'] and 'pdf_page' in c]
            }
            with open(os.path.join("public", "api", "data.json"), "w", encoding="utf-8") as f:
                json.dump(data_json, f, indent=2)
            
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

def load_courses():
    global global_courses
    global_courses.clear()
    
    loaded_from_mongo = False
    if db is not None:
        try:
            print("Loading courses from MongoDB...")
            docs = list(db.courses.find({}, {'_id': 0}))
            if docs:
                global_courses.extend(docs)
                global_courses.sort(key=lambda x: int(x.get('id', 0)))
                print(f"Loaded {len(global_courses)} courses from MongoDB.")
                loaded_from_mongo = True
        except Exception as e:
            print(f"Error loading from MongoDB, falling back to local files: {e}")
    
    loaded_raw = False
    
    if not loaded_from_mongo and os.path.exists(PERSISTENT_FILE):
        try:
            with open(PERSISTENT_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            loaded_raw = True
            print(f"Loaded {len(raw_data)} courses from {PERSISTENT_FILE}")
        except Exception as e:
            print("Error loading 1.json, falling back to base JSON:", e)
            
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
            desc_text = str(d.get('cost_description', '')) + " " + str(d.get('duration_description', '')) + " " + str(d.get('cost_verified', '')) + " " + str(d.get('duration_verified', '')) + " " + str(d.get('reason', ''))
            
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
            
            if not has_uni_match or not has_name_match or has_page_error or (web_status == 'FALSE' and has_page_error):
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
            global_courses.append(course)
            
        print(f"Loaded {len(global_courses)} courses locally.")

    # APPLY HEURISTIC TO ALL LOADED COURSES (From Mongo or Local)
    for c in global_courses:
        # Check both disc_reason and reason since they might be labeled differently depending on the source
        desc_text = str(c.get('cost_description', '')) + " " + str(c.get('duration_description', '')) + " " + str(c.get('cost_verified', '')) + " " + str(c.get('duration_verified', '')) + " " + str(c.get('disc_reason', '')) + " " + str(c.get('reason', ''))
        
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
        if has_page_error:
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
        elif is_unverified and not c.get('issue_category'):
            # Any remaining unverified that didn't explicitly match a page error but failed to load
            c['issue_category'] = ISSUE_CATEGORY_WEBSITE
            c['status'] = 'Error'
        else:
            # Sync status with issue_category for existing records
            issue_cat = c.get('issue_category', '')
            if issue_cat == ISSUE_CATEGORY_VERIFIED:
                c['status'] = 'Verified'
            elif issue_cat == ISSUE_CATEGORY_WEBSITE:
                c['status'] = 'Error'
            elif issue_cat == ISSUE_CATEGORY_COURSE:
                c['status'] = 'Discrepancy'

# Load immediately
load_courses()

# On Vercel, the serverless function instance is reused across requests, so
# global_courses (loaded once above) goes stale and the hosted dashboard never
# sees new uploads. Refresh from MongoDB on a short TTL so the live site stays
# current. Local dev benefits too: it picks up writes from other clients.
_LAST_LOAD_TS = time.time()
_LOAD_TTL_SEC = 15
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
    return render_template("index.html")

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

@app.route("/api/data")
@app.route("/api/data.json")
def api_data():
    _refresh_courses_if_stale()
    total_courses = len(global_courses)
    verified = sum(1 for c in global_courses if c['status'] == 'Verified')
    discrepancies = sum(1 for c in global_courses if c['status'] == 'Discrepancy')
    errors = sum(1 for c in global_courses if c['status'] == 'Error')
    unverified = sum(1 for c in global_courses if c['status'] == 'Unverified')

    # Issue category breakdown
    website_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE)
    course_issues = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE)

    # Sub-type tallies
    website_sub_counts = {}
    course_sub_counts = {}
    for c in global_courses:
        sub = c.get('issue_sub_type', '')
        if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE and sub:
            website_sub_counts[sub] = website_sub_counts.get(sub, 0) + 1
        elif c.get('issue_category') == ISSUE_CATEGORY_COURSE and sub:
            course_sub_counts[sub] = course_sub_counts.get(sub, 0) + 1

    # Domain health warnings
    domain_issue_counts = {}
    for c in global_courses:
        if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
            dom = c.get('domain', 'Unknown')
            domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1
    domain_warnings = [
        {"domain": d, "issue_count": cnt}
        for d, cnt in domain_issue_counts.items() if cnt >= 3
    ]

    domain_counts = {}
    country_counts = {}
    discrepancy_list = []
    website_issue_list = []
    course_issue_list = []

    for c in global_courses:
        if c['domain']:
            domain_counts[c['domain']] = domain_counts.get(c['domain'], 0) + 1
        if c['country'] and c['country'] != 'Unknown':
            country_counts[c['country']] = country_counts.get(c['country'], 0) + 1

        if c['status'] == 'Discrepancy':
            discrepancy_list.append({
                "name": c['name'],
                "university": c['university'],
                "reason": c['disc_reason'],
                "domain": c['domain']
            })
        if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
            website_issue_list.append({
                "name": c['name'],
                "university": c['university'],
                "sub_type": c.get('issue_sub_type', ''),
                "reason": c['disc_reason'],
                "domain": c['domain']
            })
        elif c.get('issue_category') == ISSUE_CATEGORY_COURSE:
            course_issue_list.append({
                "name": c['name'],
                "university": c['university'],
                "sub_type": c.get('issue_sub_type', ''),
                "reason": c['disc_reason'],
                "domain": c['domain']
            })

    return jsonify({
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
        "discrepancy_list": discrepancy_list,
        "website_issue_list": website_issue_list,
        "course_issue_list": course_issue_list,
        "recent": [c for c in global_courses if c['status'] in ['Discrepancy', 'Error'] and 'pdf_page' in c]
    })

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
            course['issue_sub_type'] = ''
            course['status'] = 'Verified'
            course['disc_reason'] = ''
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

import pandas as pd
import os

@app.route("/api/analytics", methods=["GET"])
@app.route("/api/analytics.json", methods=["GET"])
def api_analytics():
    _refresh_courses_if_stale()
    # Attempt to load and parse analytics data
    try:
        data = {
            "course_category": {},
            "variant_category": {},
            "pricing_category": {},
            "domain_pivot": {},
            "country_pivot": {}
        }
        
        # 1. Parse CombinedWork.xlsx
        if os.path.exists('CombinedWork.xlsx'):
            xl = pd.ExcelFile('CombinedWork.xlsx')
            dfs = [xl.parse(s).assign(Country=s) for s in xl.sheet_names]
            df = pd.concat(dfs)
            df = df.dropna(subset=['Course name'])
            
            # Country Count
            country_counts = df['Country'].value_counts().to_dict()
            data['country_pivot'] = country_counts
            
            # Course Categories (Indian vs Int)
            indian = df[df['Country'] == 'India'].shape[0]
            intl = df[df['Country'] != 'India'].shape[0]
            data['course_category']['Indian Programs'] = indian
            data['course_category']['International Programs'] = intl
            data['course_category']['Total Programs'] = indian + intl
            
            # Extract Levels
            def get_level(ctype):
                ctype = str(ctype).lower()
                if 'bach' in ctype or 'ug' in ctype: return "Bachelor's Degrees"
                if 'mast' in ctype or 'pg' in ctype: return "Master's Degrees"
                if 'dip' in ctype: return "Diplomas"
                if 'cert' in ctype: return "Certificates"
                return "Other"
                
            levels = df['Course Type'].apply(get_level).value_counts().to_dict()
            for k, v in levels.items():
                if k != 'Other': data['course_category'][k] = v
                
            # Pricing
            free = df[df['Fees'].astype(str).str.contains('free|0', case=False, na=False)].shape[0]
            data['pricing_category']['Free Courses'] = free
            data['pricing_category']['Affordable'] = df.shape[0] - free
            data['pricing_category']['Total Pricing'] = df.shape[0]

        # 2. Parse Variants (link_compile.pdf.json)
        json_file = 'autonomous_verified_link_compile.pdf.json'
        if os.path.exists(json_file):
            with open(json_file, 'r', encoding='utf-8') as f:
                variants = json.load(f)
            
            ind_var = len([v for v in variants if v.get('country') == 'India'])
            int_var = len(variants) - ind_var
            
            data['variant_category']['Indian Variants'] = ind_var
            data['variant_category']['International Variants'] = int_var
            data['variant_category']['Total Variants'] = len(variants)
            
            # Pivot by domain
            domains = {}
            for v in variants:
                d = v.get('domain', 'Unknown')
                if d not in domains:
                    domains[d] = {'Total': 0, 'Indian': 0, 'International': 0}
                domains[d]['Total'] += 1
                if v.get('country') == 'India':
                    domains[d]['Indian'] += 1
                else:
                    domains[d]['International'] += 1
            data['domain_pivot'] = domains

        return jsonify({"status": "success", "data": data})
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
    
    updates = 0
    verified_in_this_batch = []
    
    for file in files:
        if file.filename == '': continue
        
        fd, temp_path = tempfile.mkstemp(suffix=".pdf")
        os.close(fd)
        file.save(temp_path)
        
        try:
            with pdfplumber.open(temp_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()
                    if not text: continue
                    
                    match = re.search(r'^\s*(\d+)\.\s+(.+?)\s*$', text, re.MULTILINE)
                    if not match: continue
                    
                    title = match.group(2).strip()
                    
                    tables = page.extract_tables()
                    extracted = {}
                    if tables:
                        table = tables[0]
                        for row in table:
                            if len(row) >= 4:
                                attr = str(row[0]).strip().replace('\n', ' ')
                                if attr.lower() == 'attribute': continue # Skip header row
                                
                                original = str(row[1]).strip().replace('\n', ' ') if len(row) > 1 else ''
                                verified = str(row[2]).strip().replace('\n', ' ') if len(row) > 2 else ''
                                status = str(row[3]).strip().replace('\n', ' ') if len(row) > 3 else ''
                                
                                if 'pdf_table' not in extracted:
                                    extracted['pdf_table'] = []
                                extracted['pdf_table'].append({
                                    "attribute": attr,
                                    "original": original,
                                    "verified": verified,
                                    "status": status
                                })
                                
                                for a in attributes:
                                    if a.lower() in attr.lower():
                                        if a.lower() == 'university':
                                            extracted['Original_University'] = original
                                        if status == 'MATCH':
                                            extracted[a] = 'MATCH'
                                        break
                                        
                    actual_page = page_num
                    page_match = re.search(r'PDF Page (\d+)', text)
                    if page_match:
                        actual_page = int(page_match.group(1))
                    
                    if 'free' in file.filename.lower() and actual_page <= 7:
                        actual_page += 16
                        
                    pdf_course_id = int(match.group(1))
                    
                    # Find and update the course in memory using its ID
                    for c in global_courses:
                        if c.get('id') == pdf_course_id:
                            c['pdf_page'] = actual_page
                            c['cost_match'] = (extracted.get('Cost') == 'MATCH')
                            c['duration_match'] = (extracted.get('Duration') == 'MATCH')
                            c['mode_match'] = (extracted.get('Mode') == 'MATCH')
                            c['lang_match'] = (extracted.get('Language') == 'MATCH')
                            c['country_match'] = (extracted.get('Country') == 'MATCH')
                            c['uni_match'] = (extracted.get('University') == 'MATCH')
                            c['sk_match'] = (extracted.get('Skills') == 'MATCH')
                            
                            if 'pdf_table' in extracted:
                                c['pdf_table'] = extracted['pdf_table']
                                
                            # Detect and assign exact domain from filename
                            raw_name = file.filename.replace('_', ' ').replace('-', ' ').lower()
                            valid_domains = [
                                "High Value Low Cost", "Post Graduate Certificate", "Certificate", 
                                "Bachelors", "Masters", "Post Graduate Diploma", "Diploma", 
                                "Free to Audit", "Free"
                            ]
                            for d in valid_domains:
                                if d.lower() in raw_name:
                                    c['domain'] = d
                                    break
                            
                            matches = [c['cost_match'], c['duration_match'], c['mode_match'], c['lang_match'], c['country_match'], c['uni_match'], c['sk_match']]
                            
                            if all(matches):
                                c['status'] = 'Verified'
                                c['disc_reason'] = ''
                                c['issue_category'] = ISSUE_CATEGORY_VERIFIED
                                c['issue_sub_type'] = ''
                            else:
                                c['status'] = 'Discrepancy'
                                c['issue_category'] = ISSUE_CATEGORY_COURSE
                                fails = []
                                if not c['cost_match']: fails.append('Cost')
                                if not c['duration_match']: fails.append('Duration')
                                if not c['mode_match']: fails.append('Mode')
                                if not c['lang_match']: fails.append('Language')
                                if not c['country_match']: fails.append('Country')
                                if not c['uni_match']: fails.append('University')
                                if not c['sk_match']: fails.append('Skills')
                                c['disc_reason'] = "Mismatch: " + ", ".join(fails)
                            
                            updates += 1
                            verified_in_this_batch.append(c)
                            break
        except Exception as e:
            print(f"Error processing {file.filename}: {e}")
        finally:
            if os.path.exists(temp_path):
                os.remove(temp_path)
    if updates > 0:
        # Save ALL courses to ensure complete data persistence
        # This prevents data loss when Firestore is the primary data source
        save_courses(global_courses)
        
    return jsonify({
        "status": "success", 
        "updates": updates, 
        "message": f"Processed {len(files)} files. Updated {updates} courses.",
        "verified_courses": verified_in_this_batch
    })

if __name__ == "__main__":
    print("[*] Starting Live Verification Dashboard on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
