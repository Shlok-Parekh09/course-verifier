import os
import re
import json
import fitz
from pymongo import MongoClient
from dotenv import load_dotenv
import requests

def parse_indexing(pdf_path):
    print(f"[*] Parsing {pdf_path} for domain and category mapping...")
    doc = fitz.open(pdf_path)
    text = ""
    for page in doc:
        text += page.get_text() + "\n"
        
    mapping = {}
    
    # Fix the ligature issues from PDF
    text = text.replace('ﬁ', 'fi')
    
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        
        match = re.search(r'(\d+)\s+to\s+(\d+)\s+(.+)', line)
        if match:
            start = int(match.group(1))
            end = int(match.group(2))
            desc = match.group(3).lower()
            
            # Extract domain and category
            category = ""
            domain = ""
            
            if 'certificate' in desc or 'certifi' in desc: category = 'Certificate'
            elif 'diploma' in desc: category = 'Diploma'
            elif 'bachelors' in desc: category = 'Bachelors'
            elif 'masters' in desc: category = 'Masters'
            elif 'post graduate' in desc: category = 'Post Graduate'
            else: category = 'Certificate'
            
            if 'free to audit' in desc: domain = 'Free to Audit'
            elif 'free' in desc: domain = 'Free'
            elif 'high value low cost' in desc: domain = 'High Value Low Cost'
            elif 'foundational' in desc: domain = 'Foundational'
            elif 'network infra' in desc: domain = 'Network Infrastructure'
            elif 'system and endpoint' in desc: domain = 'System & Endpoint'
            elif 'cyber forensics' in desc: domain = 'Cyber Forensics'
            elif 'data and application' in desc: domain = 'Data & Application'
            elif 'legal and ethical' in desc: domain = 'Legal & Ethical'
            
            for i in range(start, end + 1):
                mapping[i] = {
                    'domain': domain,
                    'course_category': category
                }
    
    print(f"    Loaded {len(mapping)} mappings from indexing.")
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
        
        def extract_val(field1, field2=None):
            # Find everything between field1 and field2 (or the end of chunk)
            f1_pos = chunk.find(field1 + "\n")
            if f1_pos == -1: return ""
            f1_pos += len(field1) + 1
            
            f2_pos = len(chunk)
            if field2:
                idx = chunk.find(field2 + "\n", f1_pos)
                if idx != -1:
                    f2_pos = idx
            
            subchunk = chunk[f1_pos:f2_pos].strip()
            # The first line of subchunk is usually the Original PDF data
            # Let's just grab the first line. If it spans multiple, we might truncate, but it's usually short.
            lines = subchunk.split('\n')
            if not lines: return ""
            
            # The status is the last line if it matches MATCH/MISMATCH/NOT FOUND
            # The original value is the first line
            orig_val = lines[0].strip()
            return orig_val

        cost = extract_val("Cost", "Duration")
        duration = extract_val("Duration", "Mode")
        mode = extract_val("Mode", "Language")
        language = extract_val("Language", "Country")
        country = extract_val("Country", "University")
        uni = extract_val("University", "Skills")
        skills = extract_val("Skills", "QS Ranked")
        qs = extract_val("QS Ranked", "NIRF Ranked")
        nirf = extract_val("NIRF Ranked", "Free Box")
        
        c = {
            "id": idx,
            "name": name,
            "cost": cost,
            "duration": duration,
            "mode": mode,
            "language": language,
            "country": country,
            "uni": uni,
            "skills": skills,
            "qs": qs,
            "nirf": nirf,
            "domain": mapping.get(idx, {}).get('domain', 'Uncategorised'),
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
