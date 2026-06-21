#!/usr/bin/env python3
import json, os

ISSUE_CATEGORY_WEBSITE = 'website_issue'
ISSUE_CATEGORY_COURSE = 'course_issue'
ISSUE_CATEGORY_VERIFIED = 'verified'

with open('1.json', encoding='utf-8') as f:
    global_courses = json.load(f)

def derive_status_and_issue(c):
    matches = [
        c.get('cost_match', False),
        c.get('duration_match', False),
        c.get('mode_match', False),
        c.get('lang_match', False),
        c.get('country_match', False),
        c.get('uni_match', False),
        c.get('sk_match', False),
    ]
    has_pdf = c.get('pdf_page') is not None

    if has_pdf and all(matches):
        return 'Verified', ISSUE_CATEGORY_VERIFIED, 'perfect_match', ''
    elif has_pdf:
        fails = []
        if not c.get('cost_match'): fails.append('Cost')
        if not c.get('duration_match'): fails.append('Duration')
        if not c.get('mode_match'): fails.append('Mode')
        if not c.get('lang_match'): fails.append('Language')
        if not c.get('country_match'): fails.append('Country')
        if not c.get('uni_match'): fails.append('University')
        if not c.get('sk_match'): fails.append('Skills')
        reason = 'Mismatch: ' + ', '.join(fails)
        if len(fails) >= 3:
            sub = 'multiple_mismatches'
        else:
            field_map = {'Cost':'cost_mismatch','Duration':'duration_mismatch','Mode':'mode_mismatch',
                         'Language':'language_mismatch','Country':'country_mismatch',
                         'University':'university_mismatch','Skills':'skills_mismatch'}
            sub = field_map.get(fails[0], 'course_issue')
        return 'Discrepancy', ISSUE_CATEGORY_COURSE, sub, reason
    else:
        web_status = c.get('web_status', '')
        if web_status == 'MATCH':
            return 'Verified', ISSUE_CATEGORY_VERIFIED, 'perfect_match', ''
        elif web_status == 'FALSE':
            is_hard = c.get('is_hard_error', False)
            reason = c.get('reason', '')
            if is_hard:
                return 'Error', ISSUE_CATEGORY_WEBSITE, 'site_down', reason
            else:
                reason_l = reason.lower()
                fails = []
                if 'cost' in reason_l: fails.append('Cost')
                if 'duration' in reason_l: fails.append('Duration')
                if 'mode' in reason_l: fails.append('Mode')
                if 'language' in reason_l: fails.append('Language')
                if 'country' in reason_l: fails.append('Country')
                if 'university' in reason_l: fails.append('University')
                if 'skills' in reason_l: fails.append('Skills')
                if len(fails) >= 3:
                    sub = 'multiple_mismatches'
                elif fails:
                    field_map = {'Cost':'cost_mismatch','Duration':'duration_mismatch','Mode':'mode_mismatch',
                                 'Language':'language_mismatch','Country':'country_mismatch',
                                 'University':'university_mismatch','Skills':'skills_mismatch'}
                    sub = field_map.get(fails[0], 'course_issue')
                else:
                    sub = 'course_issue'
                return 'Discrepancy', ISSUE_CATEGORY_COURSE, sub, reason
        else:
            return 'Unverified', '', '', ''

fixed = 0
for c in global_courses:
    old_status = c.get('status')
    status, cat, sub, reason = derive_status_and_issue(c)
    if c.get('status') != status or c.get('issue_category') != cat:
        fixed += 1
    c['status'] = status
    c['issue_category'] = cat
    c['issue_sub_type'] = sub
    if status == 'Discrepancy':
        c['disc_reason'] = reason
    elif status == 'Verified':
        c['disc_reason'] = ''

total = len(global_courses)
verified = sum(1 for c in global_courses if c['status'] == 'Verified')
disc = sum(1 for c in global_courses if c['status'] == 'Discrepancy')
errors = sum(1 for c in global_courses if c['status'] == 'Error')
unverified = sum(1 for c in global_courses if c['status'] == 'Unverified')
wi = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE)
ci = sum(1 for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE)

print(f'Fixed {fixed} courses')
print(f'Statuses: Verified={verified}, Discrepancy={disc}, Error={errors}, Unverified={unverified}')
print(f'Issues: website={wi}, course={ci}')

website_sub_counts = {}
course_sub_counts = {}
for c in global_courses:
    sub = c.get('issue_sub_type', '')
    if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE and sub:
        website_sub_counts[sub] = website_sub_counts.get(sub, 0) + 1
    elif c.get('issue_category') == ISSUE_CATEGORY_COURSE and sub:
        course_sub_counts[sub] = course_sub_counts.get(sub, 0) + 1

domain_issue_counts = {}
for c in global_courses:
    if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE:
        dom = c.get('domain', 'Unknown')
        domain_issue_counts[dom] = domain_issue_counts.get(dom, 0) + 1
domain_warnings = [{'domain': d, 'issue_count': cnt} for d, cnt in domain_issue_counts.items() if cnt >= 3]

domain_counts = {}
country_counts = {}
for c in global_courses:
    d = c.get('domain')
    if d:
        domain_counts[d] = domain_counts.get(d, 0) + 1
    cty = c.get('country')
    if cty and cty != 'Unknown':
        country_counts[cty] = country_counts.get(cty, 0) + 1

data_json = {
    'status': 'success',
    'stats': {
        'total': total,
        'verified': verified,
        'discrepancies': disc,
        'errors': errors,
        'unverified': unverified,
        'website_issues': wi,
        'course_issues': ci,
    },
    'website_sub_counts': website_sub_counts,
    'course_sub_counts': course_sub_counts,
    'domain_warnings': domain_warnings,
    'domain_counts': domain_counts,
    'country_counts': country_counts,
    'discrepancy_list': [
        {'name': c['name'], 'university': c['university'], 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in global_courses if c['status'] == 'Discrepancy'
    ],
    'website_issue_list': [
        {'name': c['name'], 'university': c['university'], 'sub_type': c.get('issue_sub_type', ''), 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_WEBSITE
    ],
    'course_issue_list': [
        {'name': c['name'], 'university': c['university'], 'sub_type': c.get('issue_sub_type', ''), 'reason': c.get('disc_reason', ''), 'domain': c['domain']}
        for c in global_courses if c.get('issue_category') == ISSUE_CATEGORY_COURSE
    ],
    'recent': [c for c in global_courses if c['status'] in ['Discrepancy', 'Error'] and c.get('pdf_page')]
}

os.makedirs('public/api', exist_ok=True)
with open('public/api/data.json', 'w', encoding='utf-8') as f:
    json.dump(data_json, f, indent=2, ensure_ascii=False)
with open('public/api/courses.json', 'w', encoding='utf-8') as f:
    json.dump({'status': 'success', 'courses': global_courses}, f, indent=2, ensure_ascii=False)
with open('1.json', 'w', encoding='utf-8') as f:
    json.dump(global_courses, f, indent=2, ensure_ascii=False)

print('Saved public/api/data.json, courses.json, and 1.json')
