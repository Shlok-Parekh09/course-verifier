#!/usr/bin/env python3
"""Restore original 1.json statuses from committed backup while adding issue_category."""
import json, os

ISSUE_WEBSITE = 'website_issue'
ISSUE_COURSE = 'course_issue'
ISSUE_VERIFIED = 'verified'

# Load the committed backup (original statuses before my destructive script)
with open('committed_courses_backup.json', encoding='utf-8') as f:
    backup = json.load(f)['courses']

# Load current 1.json
with open('1.json', encoding='utf-8') as f:
    current = json.load(f)

restored = 0
for idx, c in enumerate(current):
    if idx >= len(backup):
        break
    b = backup[idx]
    old_status = b.get('status', 'Unverified')

    # If the backup says this course was previously Verified or Discrepancy,
    # restore that status UNLESS the current file has fresh verifier evidence (web_status)
    has_fresh_evidence = bool(c.get('web_status')) or bool(c.get('reason')) or bool(c.get('issue_category'))

    if old_status in ('Verified', 'Discrepancy', 'Error') and not has_fresh_evidence:
        c['status'] = old_status
        c['disc_reason'] = b.get('disc_reason', '')

        # Derive issue_category from restored status
        if old_status == 'Verified':
            c['issue_category'] = ISSUE_VERIFIED
            c['issue_sub_type'] = 'perfect_match'
        elif old_status == 'Error':
            c['issue_category'] = ISSUE_WEBSITE
            c['issue_sub_type'] = 'site_down'
        elif old_status == 'Discrepancy':
            c['issue_category'] = ISSUE_COURSE
            reason_txt = c.get('disc_reason', '')
            fails = []
            if 'Cost' in reason_txt: fails.append('Cost')
            if 'Duration' in reason_txt: fails.append('Duration')
            if 'Mode' in reason_txt: fails.append('Mode')
            if 'Language' in reason_txt: fails.append('Language')
            if 'Country' in reason_txt: fails.append('Country')
            if 'University' in reason_txt: fails.append('University')
            if 'Skills' in reason_txt: fails.append('Skills')
            if len(fails) >= 3:
                c['issue_sub_type'] = 'multiple_mismatches'
            elif fails:
                field_map = {
                    'Cost': 'cost_mismatch', 'Duration': 'duration_mismatch', 'Mode': 'mode_mismatch',
                    'Language': 'language_mismatch', 'Country': 'country_mismatch',
                    'University': 'university_mismatch', 'Skills': 'skills_mismatch'
                }
                c['issue_sub_type'] = field_map.get(fails[0], 'course_issue')
            else:
                c['issue_sub_type'] = 'course_issue'
        restored += 1

with open('1.json', 'w', encoding='utf-8') as f:
    json.dump(current, f, indent=2, ensure_ascii=False)

# Recompute stats
total = len(current)
verified = sum(1 for c in current if c.get('status') == 'Verified')
disc = sum(1 for c in current if c.get('status') == 'Discrepancy')
errors = sum(1 for c in current if c.get('status') == 'Error')
unver = sum(1 for c in current if c.get('status') == 'Unverified')
wi = sum(1 for c in current if c.get('issue_category') == ISSUE_WEBSITE)
ci = sum(1 for c in current if c.get('issue_category') == ISSUE_COURSE)

print(f'Restored {restored} courses to their original status')
print(f'Statuses: Verified={verified}, Discrepancy={disc}, Error={errors}, Unverified={unver}')
print(f'Issues: website={wi}, course={ci}')

# Regenerate public JSONs
website_sub_counts = {}
course_sub_counts = {}
for c in current:
    sub = c.get('issue_sub_type', '')
    if c.get('issue_category') == ISSUE_WEBSITE and sub:
        website_sub_counts[sub] = website_sub_counts.get(sub, 0) + 1
    elif c.get('issue_category') == ISSUE_COURSE and sub:
        course_sub_counts[sub] = course_sub_counts.get(sub, 0) + 1

domain_issue_counts = {}
for c in current:
    if c.get('issue_category') == ISSUE_WEBSITE:
        dom = c.get('domain', 'Unknown')
        domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1
domain_warnings = [{'domain': d, 'issue_count': cnt} for d, cnt in domain_issue_counts.items() if cnt >= 3]

domain_counts = {}
country_counts = {}
for c in current:
    d = c.get('domain')
    if d:
        domain_counts[d] = domain_counts.get(d, 0) + 1
    cty = c.get('country')
    if cty and cty != 'Unknown':
        country_counts[cty] = country_counts.get(cty, 0) + 1

data_json = {
    'status': 'success',
    'stats': {
        'total': total, 'verified': verified, 'discrepancies': disc,
        'errors': errors, 'unverified': unver,
        'website_issues': wi, 'course_issues': ci,
    },
    'website_sub_counts': website_sub_counts,
    'course_sub_counts': course_sub_counts,
    'domain_warnings': domain_warnings,
    'domain_counts': domain_counts,
    'country_counts': country_counts,
    'discrepancy_list': [
        {'name': c['name'], 'university': c['university'], 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in current if c.get('status') == 'Discrepancy'
    ],
    'website_issue_list': [
        {'name': c['name'], 'university': c['university'], 'sub_type': c.get('issue_sub_type', ''), 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in current if c.get('issue_category') == ISSUE_WEBSITE
    ],
    'course_issue_list': [
        {'name': c['name'], 'university': c['university'], 'sub_type': c.get('issue_sub_type', ''), 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in current if c.get('issue_category') == ISSUE_COURSE
    ],
    'recent': [c for c in current if c.get('status') in ['Discrepancy', 'Error'] and c.get('pdf_page')]
}

os.makedirs('public/api', exist_ok=True)
with open('public/api/data.json', 'w', encoding='utf-8') as f:
    json.dump(data_json, f, indent=2, ensure_ascii=False)
with open('public/api/courses.json', 'w', encoding='utf-8') as f:
    json.dump({'status': 'success', 'courses': current}, f, indent=2, ensure_ascii=False)

print('Regenerated public/api/data.json and courses.json')
