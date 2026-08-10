import json
import re
import requests
import concurrent.futures

def fix_acronyms(name):
    # Standardize casing. Capitalize words properly, keeping acronyms uppercase.
    words = name.split()
    acronyms = {"iit", "iiit", "nit", "iim", "bits", "nielit", "mit", "vit", "jnu", "du", "ucl", "nyu", "nus", "lse", "ucla"}
    fixed = []
    for i, w in enumerate(words):
        clean_w = re.sub(r'[^a-zA-Z]', '', w).lower()
        if clean_w in acronyms:
            # Preserve non-alphabetic chars but uppercase the acronym part
            fixed.append(w.upper())
        elif w.lower() in ["of", "and", "the", "in", "at", "for", "on"]:
            # Only lowercase if it's not the first word
            if i == 0:
                fixed.append(w.capitalize())
            else:
                fixed.append(w.lower())
        else:
            fixed.append(w.capitalize())
    # Special cases handling
    res = " ".join(fixed)
    res = res.replace(" Of ", " of ").replace(" And ", " and ").replace(" The ", " the ")
    return res

def normalize_uni_name(n):
    return re.sub(r'[^a-z0-9]', '_', n.lower())

def process_logo(uni_name):
    norm = normalize_uni_name(uni_name)
    url = f"https://pub-188fdc39f1ee412d9ed0028c80cc4778.r2.dev/logos/{norm}.png"
    try:
        resp = requests.head(url, timeout=5)
        if resp.status_code == 200:
            return uni_name, url
    except:
        pass
    return uni_name, ""

print("Loading data...")
# 1. Load data
with open('frontend/infinityfree/data/courses.json', 'r', encoding='utf-8') as f:
    courses_data = json.load(f).get('courses', [])

# Map by exact name & badly extracted university from PDF
with open('extracted_catalog.json', 'r', encoding='utf-8') as f:
    catalog = json.load(f)

updated_catalog = []
unique_unis_to_check = set()

for item in catalog:
    # 1. Add banner_url
    item['banner_url'] = ""
    
    # Try to find corresponding course in verified courses.json
    c = None
    for c_old in courses_data:
        if c_old.get('url', '').strip() == item.get('url', '').strip():
            c = c_old
            break
            
    if c:
        # Overwrite badly extracted names with the verified names!
        item['name'] = c['name']
        
        # Apply Acronym fix just in case the verified name isn't perfect
        fixed_uni = fix_acronyms(c['university'])
        item['university'] = fixed_uni
        
        # Extract correct badges from pdf_table!
        free_box = False; schol_box = False
        for r in c.get('pdf_table', []):
            if r['attribute'] == 'Free Box' and 'True' in str(r.get('original', '')): free_box = True
            if r['attribute'] == 'Scholarship Box' and 'True' in str(r.get('original', '')): schol_box = True
        
        item['has_qs_badge'] = c.get('has_qs_badge', False)
        item['has_nirf_badge'] = c.get('has_nirf_badge', False)
        item['has_scholarship'] = schol_box
        item['has_free'] = free_box
        
        # Extract AI verified skills description
        verified_skills = ""
        for r in c.get('pdf_table', []):
            if r['attribute'] == 'Skills':
                verified_skills = r.get('verified', '')
        
        if verified_skills:
            item['skills_description'] = verified_skills
        else:
            item['skills_description'] = c.get('skills_description', c.get('skills', ''))

    else:
        # If no match, just fix the acronym of whatever it currently is
        item['university'] = fix_acronyms(item.get('university', ''))
        
    unique_unis_to_check.add(item['university'])
    updated_catalog.append(item)

# Pre-fetch logos
uni_to_logo = {}
print(f"Checking logos for {len(unique_unis_to_check)} universities...")
with concurrent.futures.ThreadPoolExecutor(max_workers=50) as executor:
    results = executor.map(process_logo, unique_unis_to_check)
    for uni, url in results:
        uni_to_logo[uni] = url
print("Finished checking logos.")

missing_logos = set()
for item in updated_catalog:
    logo_url = uni_to_logo.get(item['university'], "")
    item['logo_url'] = logo_url
    if not logo_url:
        missing_logos.add(item['university'])

with open('frontend/course_catalog.json', 'w', encoding='utf-8') as f:
    json.dump(updated_catalog, f, indent=4)

print("Updated course_catalog.json successfully.")
print(f"Number of universities with missing logos: {len(missing_logos)}")
with open('missing_logos.txt', 'w', encoding='utf-8') as f:
    f.write("\n".join(sorted(missing_logos)))
print("Saved missing logos to missing_logos.txt")
