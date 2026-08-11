import json
import re
import requests
import concurrent.futures

def fix_acronyms(name):
    """Standardize casing. Capitalize words properly, keeping acronyms uppercase."""
    # Common acronyms that must remain completely uppercase
    acronyms = {
        "iit", "iiit", "nit", "iim", "bits", "nielit", "mit", "vit", "jnu", 
        "du", "ucl", "nyu", "nus", "lse", "ucla", "upes", "mca", "bca", 
        "btech", "mtech", "bba", "mba", "ignou", "cdac", "ugc", "csme", "amity",
        "ibm", "tcs", "infosys", "cisco", "aws", "google", "meta"
    }
    
    words = name.split()
    fixed = []
    
    for i, w in enumerate(words):
        clean_w = re.sub(r'[^a-zA-Z]', '', w).lower()
        if clean_w in acronyms:
            # Preserve original non-alpha chars (like hyphens) but uppercase the alpha parts
            # e.g., iit-b -> IIT-B
            fixed_w = ""
            for char in w:
                if char.isalpha():
                    fixed_w += char.upper()
                else:
                    fixed_w += char
            fixed.append(fixed_w)
        else:
            # Normal title casing, but handle small words properly
            if clean_w in ["of", "and", "the", "in", "at", "for", "on"] and i != 0 and i != len(words) - 1:
                fixed.append(w.lower())
            else:
                fixed.append(w.capitalize())
                
    res = " ".join(fixed)
    return res

def normalize_uni_name(n):
    return re.sub(r'[^a-z0-9]', '_', n.lower())

GITHUB_USERNAME = "tbot21998-alt"
GITHUB_REPO = "logos"

def process_logo(uni_name):
    norm = normalize_uni_name(uni_name)
    # Using jsDelivr + GitHub format
    url = f"https://cdn.jsdelivr.net/gh/{GITHUB_USERNAME}/{GITHUB_REPO}@main/logos/{norm}.png"
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
        item['name'] = fix_acronyms(c['name'])
        
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
        item['name'] = fix_acronyms(item.get('name', ''))
        
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
