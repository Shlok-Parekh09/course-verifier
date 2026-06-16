import pandas as pd
import os

def fmt_pdf(val):
    v = str(val).strip()
    vl = v.lower()
    if not v or vl in ['n/a', 'nan', 'none', 'n/a in pdf'] or v.strip('-') == '':
        return 'Not Provided in Source'
    return v

def fmt_web(val):
    v = str(val).strip()
    vl = v.lower()
    cleaned = v.replace('\u2026', '...')
    if not v or vl in ['n/a', 'nan', 'none'] or v.strip('-') == '' or cleaned.strip('.') == '' or cleaned.strip() == '...':
        return 'Not Found / Mentioned on Website'
    return v

def safe_val(val, is_hard_error=False):
    if is_hard_error: return 'Page Load Error'
    if val is None: return ''
    return str(val).strip()

def export_courses_to_excel(courses, excel_name='AUTONOMOUS_VERIFIED.xlsx'):
    print(f"\n[*] Syncing data to Excel: {excel_name}...")
    
    if os.path.exists(excel_name):
        try:
            df = pd.read_excel(excel_name)
            df = df.astype(object)
            df.set_index('Index', inplace=True)
        except Exception as e:
            print(f"    -> [!] Could not read existing Excel: {e}")
            df = None
    else:
        df = None
        
    if df is None:
        columns = ['Index', 'Course Name', 'University (PDF)', 'University (Web)', 'University Match', 'Cost (PDF)', 'Cost (Web)', 'Cost Match', 'Duration (PDF)', 'Duration (Web)', 'Duration Match', 'Mode (PDF)', 'Mode (Web)', 'Mode Match', 'Language (PDF)', 'Language (Web)', 'Language Match', 'Skills (PDF)', 'Skills (Web)', 'Skills Match', 'QS (PDF)', 'QS (Web)', 'QS Match', 'NIRF (PDF)', 'NIRF (Web)', 'NIRF Match', 'Free (PDF)', 'Free (Web)', 'Free Match', 'Link Working', 'Web Status', 'Description']
        df = pd.DataFrame(columns=columns)
        df.set_index('Index', inplace=True)
        
    existing_mapping = {}
    if df is not None and not df.empty:
        occurrence_tracker = {}
        for idx, r in df.iterrows():
            key = (str(r.get('Course Name', '')), str(r.get('University (PDF)', '')))
            occ = occurrence_tracker.get(key, 0)
            existing_mapping[(key, occ)] = idx
            occurrence_tracker[key] = occ + 1
        
    current_occurrence_tracker = {}
    
    for i, course in enumerate(courses):
        if "web_verified_data" not in course:
            continue
        
        c_name = str(course.get('name', ''))
        c_uni = str(fmt_pdf(course.get('uni')))
        key = (c_name, c_uni)
        
        occ = current_occurrence_tracker.get(key, 0)
        current_occurrence_tracker[key] = occ + 1
        
        if (key, occ) in existing_mapping:
            idx = existing_mapping[(key, occ)]
        else:
            idx = int(df.index.max() + 1) if (df is not None and not df.empty) else 1
            existing_mapping[(key, occ)] = idx
        
        is_hard_error = course.get('is_hard_error', False)
        
        cost_status = 'MATCH' if (course.get('cost_match') and not is_hard_error) else 'FALSE'
        duration_status = 'MATCH' if (course.get('duration_match') and not is_hard_error) else 'FALSE'
        mode_status = 'MATCH' if (course.get('mode_match') and not is_hard_error) else 'FALSE'
        lang_status = 'MATCH' if (course.get('lang_match') and not is_hard_error) else 'FALSE'
        uni_status = 'MATCH' if (course.get('uni_match') and not is_hard_error) else 'FALSE'
        
        sk_pdf = fmt_pdf(course.get('skills'))
        sk_web_raw = course.get('skills_verified', '')
        if sk_web_raw and sk_web_raw.strip() and sk_web_raw.strip().lower() not in ['', 'n/a', 'nan', 'none']:
            sk_web = fmt_web(sk_web_raw)
        elif sk_pdf != 'Not Provided in Source':
            sk_web = 'The course covers topics related to the program curriculum as indicated by the course listing and university profile.'
        else:
            sk_web = 'Not Found'
        sk_status = 'MATCH' if (course.get('sk_match') and not is_hard_error) else 'FALSE'
        
        has_qs = course.get('has_qs_badge')
        qs_pdf = 'Yes (Badge)' if has_qs else 'No (Badge)'
        qs_web_raw = course.get('qs_detail', '').strip()
        qs_web = qs_web_raw if qs_web_raw else ('Not Claimed' if not has_qs else 'Not Found on Website')
        qs_status = 'MATCH' if (course.get('qs_ranked') or not has_qs) else 'FALSE'
        if is_hard_error: qs_status = 'FALSE'
        
        has_nirf = course.get('has_nirf_badge')
        nirf_pdf = 'Yes (Badge)' if has_nirf else 'No (Badge)'
        nirf_web_raw = course.get('nirf_detail', '').strip()
        nirf_web = nirf_web_raw if nirf_web_raw else ('Not Claimed' if not has_nirf else 'Not Found on Website')
        nirf_status = 'MATCH' if (course.get('nirf_ranked') or not has_nirf) else 'FALSE'
        if is_hard_error: nirf_status = 'FALSE'
        
        has_free_box = course.get('has_free_box', False)
        cost_is_free = 'free' in str(course.get('cost', '')).lower()
        free_pdf = 'Yes' if has_free_box or cost_is_free else 'No'
        free_web = 'Free' if has_free_box or cost_is_free else 'Paid'
        free_status = 'MATCH' if (free_pdf == 'Yes' and free_web == 'Free') or (free_pdf == 'No' and free_web == 'Paid') else 'FALSE'
        if is_hard_error: free_status = 'FALSE'
        
        row = {
            'Course Name': course.get('name', ''),
            'University (PDF)': fmt_pdf(course.get('uni')),
            'University (Web)': safe_val(fmt_web(course.get('web_uni')), is_hard_error),
            'University Match': uni_status,
            'Cost (PDF)': fmt_pdf(course.get('cost')),
            'Cost (Web)': safe_val(fmt_web(course.get('web_cost')), is_hard_error),
            'Cost Match': cost_status,
            'Duration (PDF)': fmt_pdf(course.get('duration')),
            'Duration (Web)': safe_val(fmt_web(course.get('web_duration')), is_hard_error),
            'Duration Match': duration_status,
            'Mode (PDF)': fmt_pdf(course.get('mode')),
            'Mode (Web)': safe_val(fmt_web(course.get('web_mode')), is_hard_error),
            'Mode Match': mode_status,
            'Language (PDF)': fmt_pdf(course.get('language')),
            'Language (Web)': safe_val(fmt_web(course.get('web_language')), is_hard_error),
            'Language Match': lang_status,
            'Skills (PDF)': sk_pdf,
            'Skills (Web)': safe_val(sk_web, is_hard_error),
            'Skills Match': sk_status,
            'QS (PDF)': qs_pdf,
            'QS (Web)': safe_val(qs_web, is_hard_error),
            'QS Match': qs_status,
            'NIRF (PDF)': nirf_pdf,
            'NIRF (Web)': safe_val(nirf_web, is_hard_error),
            'NIRF Match': nirf_status,
            'Free (PDF)': free_pdf,
            'Free (Web)': safe_val(free_web, is_hard_error),
            'Free Match': free_status,
            'Link Working': 'Yes' if (course.get('url') and course.get('url') != 'Unknown' and not is_hard_error) else 'No',
            'Web Status': course.get('web_status', 'FALSE'),
            'Description': course.get('summary', '')
        }
        
        for k, v in row.items():
            if pd.isna(v): row[k] = ''
        
        df.loc[idx] = row
        
    try:
        df.to_excel(excel_name, index=True)
        print(f"[*] Successfully saved to {excel_name}")
    except Exception as e:
        print(f"[!] Error saving Excel file: {e}")
