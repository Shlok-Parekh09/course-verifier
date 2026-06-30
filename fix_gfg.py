import json
import re
from autonomous_course_verifier import AutonomousCourseVerifier

def fix_gfg():
    print("Loading gfg.json...")
    with open('gfg.json', 'r', encoding='utf-8') as f:
        courses = json.load(f)

    verifier = AutonomousCourseVerifier('dummy.pdf')

    fixed_count = 0
    for c in courses:
        uni = c.get('uni', 'Unknown')
        aff_uni = c.get('affiliated_uni', 'NOT FOUND')
        uni_lower = uni.lower()
        
        c['qs_detail'] = "Not Ranked"
        c['qs_ranked'] = False
        c['nirf_detail'] = "Not Ranked"
        c['nirf_ranked'] = False
        
        bracket_unis = [b.strip() for b in re.findall(r'\((.*?)\)', uni)]
        affiliated_match = re.search(r'affiliated to (.*)', uni, flags=re.IGNORECASE)
        if affiliated_match:
            bracket_unis.append(affiliated_match.group(1).strip())
            
        is_college = any(kw in uni_lower for kw in ['college', 'institute of technology', 'school of', 'academy', 'institute'])
        
        # Check affiliated universities if found
        matched_db = False
        if is_college and bracket_unis:
            for b_uni in bracket_unis:
                b_lower = b_uni.lower()
                if b_lower in ['autonomous', 'open', 'deemed', 'deemed to be university', 'private', 'state', 'central', 'government', 'govt']: continue
                qs_res = verifier._offline_qs_lookup(b_uni)
                nirf_res = verifier._offline_nirf_lookup(b_uni)
                if qs_res == "Ranked":
                    c['qs_detail'] = f"The university to which college is affiliated ({b_uni.title()}) is ranked in QS hence matched"
                    c['qs_ranked'] = True
                    matched_db = True
                if nirf_res == "Ranked":
                    c['nirf_detail'] = f"The university to which college is affiliated ({b_uni.title()}) is ranked in NIRF hence matched"
                    c['nirf_ranked'] = True
                    matched_db = True

        # Anna University specific logic
        anna_kw = ['anna university', 'anna univ']
        is_anna_affiliated = any(kw in uni_lower for kw in anna_kw)
        tn_hints = ['thiruv', 'chennai', 'coimbatore', 'madurai', 'trichy',
                    'tirunelveli', 'salem', 'vellore', 'tirupur', 'erode',
                    'kanchipuram', 'chengalpattu', 'villupuram', 'cuddalore',
                    'tiruvannamalai', 'krishnagiri', 'dharmapuri', 'namakkal',
                    's.a.', 'svcet', 'saet', 'tiruv']
        is_likely_tn = any(h in uni_lower for h in tn_hints)
        
        if not matched_db and is_college and 'india' in c.get('country', '').lower() and not bracket_unis:
            if is_anna_affiliated or is_likely_tn:
                if verifier._offline_nirf_lookup("Anna University") == "Ranked":
                    c['nirf_detail'] = "The university to which college is affiliated (Anna University) is ranked in NIRF hence matched"
                    c['nirf_ranked'] = True
                    matched_db = True
                if verifier._offline_qs_lookup("Anna University") == "Ranked":
                    c['qs_detail'] = "The university to which college is affiliated (Anna University) is ranked in QS hence matched"
                    c['qs_ranked'] = True
                    matched_db = True
        
        if not matched_db:
            qs_res = verifier._offline_qs_lookup(uni)
            nirf_res = verifier._offline_nirf_lookup(uni)
            
            if qs_res == "Ranked":
                c['qs_detail'] = "Ranked"
                c['qs_ranked'] = True
            if nirf_res == "Ranked":
                c['nirf_detail'] = "Ranked"
                c['nirf_ranked'] = True
                
        fixed_count += 1

    print(f"Saving {fixed_count} courses to gfg.json...")
    with open('gfg.json', 'w', encoding='utf-8') as f:
        json.dump(courses, f, indent=4)
    print("Done!")

if __name__ == "__main__":
    fix_gfg()
