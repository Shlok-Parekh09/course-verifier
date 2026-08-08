import os
import re
import json
import fitz
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

def parse_indexing(pdf_path):
    print(f"[*] Using hardcoded domain and category mapping...")
    mapping = {}
    
    DOMAIN_RANGES = [
        ('Free', 1, 22),
        ('Free to Audit', 23, 49),
        ('High Value Low Cost', 50, 104),
        ('Foundational', 105, 659),
        ('Network Infrastructure', 660, 1623),
        ('System & Endpoint', 1624, 1919),
        ('Cyber Forensics', 1920, 2653),
        ('Data & Application', 2654, 2979),
        ('Legal & Ethical', 2980, 3720),
    ]
    
    CATEGORY_RANGES = [
        ('Certificate', 1, 104),
        ('Diploma', 105, 116),
        ('Bachelors', 117, 331),
        ('Masters', 332, 506),
        ('Post Graduate Diploma', 507, 518),
        ('Certificate', 519, 637),
        ('Post Graduate Certificate', 638, 659),
        ('Diploma', 660, 681),
        ('Bachelors', 682, 1165),
        ('Masters', 1166, 1504),
        ('Post Graduate Diploma', 1505, 1526),
        ('Certificate', 1527, 1594),
        ('Post Graduate Certificate', 1595, 1623),
        ('Diploma', 1624, 1626),
        ('Bachelors', 1627, 1745),
        ('Masters', 1746, 1876),
        ('Post Graduate Diploma', 1877, 1885),
        ('Certificate', 1886, 1909),
        ('Post Graduate Certificate', 1910, 1919),
        ('Diploma', 1920, 1930),
        ('Bachelors', 1931, 2317),
        ('Masters', 2318, 2591),
        ('Post Graduate Diploma', 2592, 2613),
        ('Certificate', 2614, 2637),
        ('Post Graduate Certificate', 2638, 2653),
        ('Diploma', 2654, 2661),
        ('Bachelors', 2662, 2796),
        ('Masters', 2797, 2937),
        ('Post Graduate Diploma', 2938, 2941),
        ('Certificate', 2942, 2968),
        ('Post Graduate Certificate', 2969, 2979),
        ('Diploma', 2980, 3000),
        ('Bachelors', 3001, 3420),
        ('Masters', 3421, 3631),
        ('Post Graduate Diploma', 3632, 3661),
        ('Certificate', 3662, 3702),
        ('Post Graduate Certificate', 3703, 3720)
    ]
    
    for i in range(1, 3721):
        domain = 'Uncategorised'
        category = 'Certificate'
        for lbl, mn, mx in DOMAIN_RANGES:
            if mn <= i <= mx:
                domain = lbl
                break
        for lbl, mn, mx in CATEGORY_RANGES:
            if mn <= i <= mx:
                category = lbl
                break
        mapping[i] = {
            'domain': domain,
            'course_category': category
        }
    
    print(f"    Loaded {len(mapping)} mappings from hardcoded ranges.")
    return mapping

def parse_finalreport(pdf_path, mapping):
    print(f"[*] Parsing {pdf_path} for courses...")
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
        
    pattern = re.compile(r'\n(\d+)\.\s+(.+?)\nAttribute', re.DOTALL)
    matches = list(pattern.finditer(text))
    
    print(f"    Found {len(matches)} courses. Extracting details...")
    
    courses = []
    
    for i in range(len(matches)):
        start = matches[i].end()
        end = matches[i+1].start() if i+1 < len(matches) else len(text)
        chunk = text[start:end]
        
        idx = int(matches[i].group(1))
        name = matches[i].group(2).strip()
        
        def extract_val_and_status(field1, field2=None):
            f1_pos = chunk.find(field1 + "\n")
            if f1_pos == -1: return "", "NOT FOUND"
            f1_pos += len(field1) + 1
            
            f2_pos = len(chunk)
            if field2:
                idx_pos = chunk.find(field2 + "\n", f1_pos)
                if idx_pos != -1:
                    f2_pos = idx_pos
            
            subchunk = chunk[f1_pos:f2_pos].strip()
            lines = subchunk.split('\n')
            if not lines: return "", "NOT FOUND"
            
            orig_val = lines[0].strip()
            status = lines[-1].strip() if len(lines) > 1 else "MATCH"
            return orig_val, status

        cost, cost_st = extract_val_and_status("Cost", "Duration")
        duration, dur_st = extract_val_and_status("Duration", "Mode")
        mode, mode_st = extract_val_and_status("Mode", "Language")
        language, lang_st = extract_val_and_status("Language", "Country")
        country, country_st = extract_val_and_status("Country", "University")
        if country.strip().lower() == 'english':
            country = "Not Identified"
        uni, uni_st = extract_val_and_status("University", "Skills")
        skills, sk_st = extract_val_and_status("Skills", "QS Ranked")
        qs, _ = extract_val_and_status("QS Ranked", "NIRF Ranked")
        nirf, _ = extract_val_and_status("NIRF Ranked", "Free Box")
        
        c = {
            "id": idx,
            "name": name,
            "university": uni,
            "domain": mapping.get(idx, {}).get('domain', 'Uncategorised'),
            "country": country,
            "cost": cost,
            "duration": duration,
            "mode": mode,
            "skills": skills,
            "qs": "",
            "nirf": "",
            "has_qs_badge": qs != "False",
            "has_nirf_badge": nirf != "False",
            "status": "Verified",
            "issue_category": "verified",
            "issue_sub_type": "perfect_match",
            "solved_attrs": [],
            "retry_count": 0,
            "error_screenshot_path": "",
            "cost_match": cost_st == "MATCH",
            "duration_match": dur_st == "MATCH",
            "mode_match": mode_st == "MATCH",
            "lang_match": lang_st == "MATCH",
            "country_match": country_st == "MATCH",
            "uni_match": uni_st == "MATCH",
            "sk_match": sk_st == "MATCH",
            "disc_reason": "",
            "pdf_page": 1,
            "pdf_table": [],
            "course_category": mapping.get(idx, {}).get('course_category', 'Certificate')
        }
        
        courses.append(c)
    
    return courses

def update_mongodb(courses):
    print("[*] Updating MongoDB Atlas...")
    load_dotenv('.env')
    uri = os.environ.get('MONGO_URI')
    if not uri:
        print("    [!] Missing MONGO_URI")
        return
        
    client = MongoClient(uri)
    db = client['course_verifier']
    coll = db['courses']
    
    count = coll.count_documents({})
    print(f"    Current collection has {count} documents.")
    
    # DANGER: Wipe collection
    print("    WIPING COLLECTION...")
    coll.delete_many({})
    
    print(f"    Inserting {len(courses)} new documents...")
    coll.insert_many(courses)
    print("    [OK] MongoDB updated successfully.")

def update_cloudflare(courses):
    print("[*] Updating Cloudflare KV...")
    # Remove _id injected by pymongo
    for c in courses:
        if '_id' in c:
            del c['_id']
            
    out_file = "frontend/infinityfree/data/courses.json"
    wrapper = {
        "status": "success",
        "courses": courses
    }
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(wrapper, f, indent=4)
    print(f"    Saved to {out_file}")
    
    load_dotenv('.env')
    cf_url = os.environ.get("CF_WORKER_URL", "https://course-verifier-api.shlokparekh08.workers.dev")
    cf_key = os.environ.get("CF_KV_PUSH_KEY", "courseverify_secure_push_key_2026")
    
    headers = {
        "Authorization": f"Bearer {cf_key}",
        "Content-Type": "application/json",
        "X-Endpoint": "courses.json",
    }
    
    raw = json.dumps(courses)
    resp = requests.post(f"{cf_url}/api/kv-push", data=raw.encode("utf-8"), headers=headers, timeout=120)
    
    if resp.status_code == 200:
        print("    [OK] Cloudflare KV updated successfully.")
    else:
        print(f"    [!] Cloudflare KV push failed: {resp.status_code} - {resp.text}")

if __name__ == "__main__":
    mapping = parse_indexing('indexing.pdf')
    courses = parse_finalreport('finalreport.pdf', mapping)
    
    # Verification
    if len(courses) > 0:
        print(f"\nSample Course 1: {courses[0]}")
        print(f"Sample Course Last: {courses[-1]}")
    
    update_mongodb(courses)
    update_cloudflare(courses)
    print("\n[*] ALL OPERATIONS COMPLETE.")
