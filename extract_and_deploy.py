import os
import json
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

def get_mappings():
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
    
    mapping = {}
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
    return mapping

def process_courses(json_path, mapping):
    print(f"[*] Loading original course data from {json_path}...")
    with open(json_path, 'r', encoding='utf-8') as f:
        courses = json.load(f)
        
    print(f"    Loaded {len(courses)} courses. Applying index mappings...")
    for c in courses:
        idx = c.get('id')
        if idx in mapping:
            c['domain'] = mapping[idx]['domain']
            c['course_category'] = mapping[idx]['course_category']
            
    # Final pass: categorize page load errors as Web Issues
    for c in courses:
        has_page_load_error = False
        for row in c.get('pdf_table', []):
            if 'page load error' in str(row.get('verified', '')).lower() or 'page load error' in str(row.get('original', '')).lower():
                has_page_load_error = True
                break
        if has_page_load_error:
            c['status'] = 'Error'
            c['issue_category'] = 'error'
            c['issue_sub_type'] = 'page_load_error'
            c['disc_reason'] = 'Page Load Error'
            
    return courses


def update_mongo(courses):
    print("[*] Updating MongoDB Atlas...")
    load_dotenv('.env')
    MONGO_URI = os.getenv("MONGO_URI")
    if not MONGO_URI:
        print("    [!] MONGO_URI not found in .env")
        return
        
    client = MongoClient(MONGO_URI)
    db = client['course_verifier']
    collection = db['courses']
    
    count = collection.count_documents({})
    print(f"    Current collection has {count} documents.")
    
    print("    WIPING COLLECTION...")
    collection.delete_many({})
    
    print(f"    Inserting {len(courses)} new documents...")
    
    # ensure no _id conflicts
    for c in courses:
        if '_id' in c:
            del c['_id']
            
    collection.insert_many(courses)
    print("    [OK] MongoDB updated successfully.")

def update_cloudflare(courses):
    print("[*] Updating Cloudflare KV...")
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
    
    try:
        raw = json.dumps(wrapper)
        resp = requests.post(f"{cf_url}/api/kv-push", data=raw.encode("utf-8"), headers=headers, timeout=120)
        
        if resp.status_code == 200:
            print("    [OK] Cloudflare KV updated successfully.")
        else:
            print(f"    [!] Cloudflare KV push failed: {resp.status_code} - {resp.text}")
    except Exception as e:
        print(f"    [!] Failed to push to Cloudflare: {e}")

if __name__ == "__main__":
    mapping = get_mappings()
    courses = process_courses("frontend/1.json", mapping)
    update_mongo(courses)
    update_cloudflare(courses)
    print("\n[*] ALL OPERATIONS COMPLETE.")
