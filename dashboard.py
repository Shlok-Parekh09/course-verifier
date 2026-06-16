import os
import json
import re
import fitz
import pdfplumber
import tempfile
import firebase_admin
from firebase_admin import credentials, firestore
from flask import Flask, render_template, jsonify, request
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024 # 50 MB

# Initialize Firebase
db = None
try:
    if os.path.exists('serviceAccountKey.json'):
        cred = credentials.Certificate('serviceAccountKey.json')
        # Check if already initialized to avoid errors in hot-reloads
        if not firebase_admin._apps:
            firebase_admin.initialize_app(cred)
        db = firestore.client()
        print("Connected to Firestore (Local)")
    else:
        if not firebase_admin._apps:
            firebase_admin.initialize_app()
        db = firestore.client()
        print("Connected to Firestore (Cloud Run)")
except Exception as e:
    print("Firestore initialization failed:", e)

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

def save_courses(updated_courses=None):
    try:
        # Also backup to local 1.json just in case
        with open(PERSISTENT_FILE, "w", encoding="utf-8") as f:
            json.dump(global_courses, f, indent=2)
            
        # Update Firestore
        if db and updated_courses:
            batch = db.batch()
            for c in updated_courses:
                doc_ref = db.collection('courses').document(str(c['id']))
                batch.set(doc_ref, c)
            batch.commit()
            
        # --- EXPORT STATIC JSON FOR PUBLIC HOSTING ---
        os.makedirs(os.path.join("public", "api"), exist_ok=True)
        
        # 1. Export courses.json
        with open(os.path.join("public", "api", "courses.json"), "w", encoding="utf-8") as f:
            json.dump({"status": "success", "courses": global_courses}, f, indent=2)
            
        # 2. Export data.json (aggregated stats)
        total_courses = len(global_courses)
        verified = sum(1 for c in global_courses if c.get('status') == 'Verified')
        discrepancies = sum(1 for c in global_courses if c.get('status') == 'Discrepancy')
        errors = sum(1 for c in global_courses if c.get('status') == 'Error')
        unverified = sum(1 for c in global_courses if c.get('status') == 'Unverified')
        
        domain_counts = {}
        country_counts = {}
        discrepancy_list = []
        
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
        
        data_json = {
            "status": "success",
            "stats": {
                "total": total_courses,
                "verified": verified,
                "discrepancies": discrepancies,
                "errors": errors,
                "unverified": unverified
            },
            "domain_counts": domain_counts,
            "country_counts": country_counts,
            "discrepancy_list": discrepancy_list,
            "recent": [c for c in global_courses if c.get('status') in ['Discrepancy', 'Error'] and 'pdf_page' in c]
        }
        with open(os.path.join("public", "api", "data.json"), "w", encoding="utf-8") as f:
            json.dump(data_json, f, indent=2)

        # 3. Trigger Firebase deploy in background to update the live site
        if updated_courses:
            import threading
            def deploy_site():
                print("Deploying updated static files to live website...")
                os.system("firebase deploy --only hosting")
            threading.Thread(target=deploy_site).start()

    except Exception as e:
        print("Error saving courses:", e)

def load_courses():
    global global_courses
    global_courses.clear()
    
    if db:
        try:
            print("Loading courses from Firestore...")
            docs = db.collection('courses').stream()
            for doc in docs:
                global_courses.append(doc.to_dict())
            
            # Sort by ID to ensure sequence is maintained
            global_courses.sort(key=lambda x: int(x.get('id', 0)))
            print(f"Loaded {len(global_courses)} courses from Firestore.")
            return
        except Exception as e:
            print("Error loading from Firestore, falling back to local files:", e)
    
    loaded_raw = False
    
    if os.path.exists(PERSISTENT_FILE):
        try:
            with open(PERSISTENT_FILE, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
            loaded_raw = True
            print(f"Loaded {len(raw_data)} courses from {PERSISTENT_FILE}")
        except Exception as e:
            print("Error loading 1.json, falling back to base JSON:", e)
            
    if not loaded_raw:
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
                "cost_match": d.get('cost_match', False),
                "duration_match": d.get('duration_match', False),
                "disc_reason": str(d.get('disc_reason', d.get('reason', '')))
            }
            global_courses.append(course)
            
        save_courses()

# Load immediately
load_courses()

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/courses")
@app.route("/api/courses.json")
def api_courses():
    return jsonify({"status": "success", "courses": global_courses})

@app.route("/api/data")
@app.route("/api/data.json")
def api_data():
    total_courses = len(global_courses)
    verified = sum(1 for c in global_courses if c['status'] == 'Verified')
    discrepancies = sum(1 for c in global_courses if c['status'] == 'Discrepancy')
    errors = sum(1 for c in global_courses if c['status'] == 'Error')
    unverified = sum(1 for c in global_courses if c['status'] == 'Unverified')
    
    domain_counts = {}
    country_counts = {}
    discrepancy_list = []
    
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
            
    return jsonify({
        "status": "success",
        "stats": {
            "total": total_courses,
            "verified": verified,
            "discrepancies": discrepancies,
            "errors": errors,
            "unverified": unverified
        },
        "domain_counts": domain_counts,
        "country_counts": country_counts,
        "discrepancy_list": discrepancy_list,
        "recent": [c for c in global_courses if c['status'] in ['Discrepancy', 'Error'] and 'pdf_page' in c] # Show all issues for uploaded PDFs
    })

@app.route("/api/course/<int:course_id>", methods=["DELETE"])
def api_delete_course(course_id):
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
        if db:
            try:
                db.collection('courses').document(str(len(global_courses) + 1)).delete()
            except Exception as e:
                print("Error deleting document from Firestore:", e)
            
        return jsonify({"status": "success", "message": "Course deleted and IDs updated"})
    else:
        return jsonify({"status": "error", "message": "Course not found"}), 404

import pandas as pd
import os

@app.route("/api/analytics", methods=["GET"])
@app.route("/api/analytics.json", methods=["GET"])
def api_analytics():
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

@app.route("/api/upload", methods=["POST"])
def api_upload():
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
                            else:
                                c['status'] = 'Discrepancy'
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
        save_courses(verified_in_this_batch)
        
    return jsonify({
        "status": "success", 
        "updates": updates, 
        "message": f"Processed {len(files)} files. Updated {updates} courses.",
        "verified_courses": verified_in_this_batch
    })

if __name__ == "__main__":
    print("[*] Starting Live Verification Dashboard on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
