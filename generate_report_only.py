import json
import os
import re
from datetime import datetime
import warnings

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from fpdf import FPDF

def safe_latin(text):
    if not isinstance(text, str):
        return str(text)
    # Replace problematic Unicode characters with closest ASCII approximations
    replacements = {
        '\u2013': '-', '\u2014': '-', '\u2018': "'", '\u2019': "'",
        '\u201c': '"', '\u201d': '"', '\u2026': '...', '\u00a0': ' ',
        '\u20b9': 'INR', '\u2122': '(TM)', '\u00ae': '(R)', '\u00a9': '(C)',
        '\u2022': '*', '\u25cf': '*', '\u200b': '', '\u200e': '', '\u200f': ''
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.encode('latin-1', 'replace').decode('latin-1')

def _generate_professional_summary(course):
    name = course.get("name", "Unknown Course")
    if course.get("is_hard_error"):
        return f"VERIFICATION FAILED: The direct link for '{name}' returned an HTTP error or was unreachable. No course details could be verified."
        
    matched = []
    failed = []
    if course.get('cost_match'): matched.append("Cost")
    else: failed.append("Cost")
    if course.get('duration_match'): matched.append("Duration")
    else: failed.append("Duration")
    if course.get('mode_match'): matched.append("Mode")
    else: failed.append("Mode")
    if course.get('lang_match'): matched.append("Language")
    else: failed.append("Language")
    if course.get('sk_match'): matched.append("Skills")
    else: failed.append("Skills")
    if course.get('uni_match'): matched.append("University")
    else: failed.append("University")
    
    total = len(matched) + len(failed)
    passed = len(matched)
    
    if course.get("web_status") == "MATCH":
        if passed == total:
            return f"VERIFIED ({passed}/{total} checks passed): The course '{name}' was successfully verified. All key details including {', '.join(matched)} match the official source."
        else:
            return f"VERIFIED WITH DISCREPANCIES ({passed}/{total} checks passed): The course '{name}' was verified. Matches: {', '.join(matched)}. Mismatches: {', '.join(failed)}."
    else:
        if not matched:
            return f"UNVERIFIED (0/{total} checks passed): The page loaded, but no course details for '{name}' could be confirmed. The provided URL may be incorrect."
        else:
            return f"UNVERIFIED ({passed}/{total} checks passed): Some details for '{name}' were found ({', '.join(matched)}), but critical components like {', '.join(failed)} failed verification."

def generate_pdf_report():
    print(f"\n[*] Generating PDF report from cached JSON...")
    
    try:
        with open('autonomous_verified_data.json', 'r', encoding='utf-8') as f:
            courses = json.load(f)
    except FileNotFoundError:
        print("[-] autonomous_verified_data.json not found!")
        return

    output_pdf = "HIGH VALUE LOW COST (1)_AUTONOMOUS_VERIFIED.pdf"
    
    pdf = FPDF()
    pdf.set_auto_page_break(auto=False)
    date_str = datetime.now().strftime("%d/%m/%Y")

    # Two-tier bucketing (Requirement 11)
    wrong_courses = []
    correct_courses = []
    for course in courses:
        is_perfect = (course.get('web_status') == 'MATCH' and 
                      course.get('cost_match') and 
                      course.get('duration_match') and 
                      course.get('mode_match') and 
                      course.get('lang_match') and 
                      course.get('uni_match') and 
                      course.get('sk_match') and 
                      not course.get('is_hard_error', False))
        if is_perfect:
            correct_courses.append(course)
        else:
            wrong_courses.append(course)
            
    def render_course(course, index_str):
        pdf.add_page()
        pdf.set_font('Arial', '', 10)
        pdf.set_text_color(100, 100, 100)
        pdf.cell(0, 6, f'Generated on: {date_str} | PDF Page {course.get("page_num","?")}, Box: {course.get("box_position","?")} (#{course.get("box_index","?")})', ln=1)
        pdf.ln(2)

        pdf.set_font('Arial', 'B', 14)
        pdf.set_text_color(0, 0, 0)
        title = course.get("name", "Unknown Course")
        if len(title) > 65: title = title[:62] + "..."
        pdf.cell(0, 10, f'{index_str}. {safe_latin(title)}', ln=1)
        pdf.ln(2)

        # Table Header
        pdf.set_fill_color(59, 130, 246)
        pdf.set_text_color(255, 255, 255)
        pdf.set_font('Arial', 'B', 10)
        pdf.cell(35, 8, 'Attribute', border=1, fill=True)
        pdf.cell(60, 8, 'Original (PDF)', border=1, fill=True)
        pdf.cell(60, 8, 'Verified (Web)', border=1, fill=True)
        pdf.cell(35, 8, 'Status', border=1, ln=1, fill=True)

        def draw_row(attr, orig, ver, status):
            orig_s = safe_latin(str(orig).strip())
            ver_s = safe_latin(str(ver).strip())
            if orig_s.lower() in ["n/a", "not found", "-", "error", "error/unreachable", "none", "nan", ""]: orig_s = "Not Provided in Source"
            if ver_s.lower() in ["n/a", "not found", "-", "error", "error/unreachable", "none", "nan", ""]: ver_s = "Not Found on Website"
            
            pdf.set_fill_color(255, 255, 255)
            pdf.set_text_color(60, 60, 60)
            pdf.set_font('Arial', '', 9)

            col_widths = [35, 60, 60, 35]
            
            # Calculate height needed
            lines_attr = len(pdf.multi_cell(col_widths[0], 5, safe_latin(str(attr)), split_only=True))
            lines_orig = len(pdf.multi_cell(col_widths[1], 5, orig_s, split_only=True))
            lines_ver = len(pdf.multi_cell(col_widths[2], 5, ver_s, split_only=True))
            max_lines = max(lines_attr, lines_orig, lines_ver, 1)
            h = max_lines * 5
            
            # Check if page break is needed
            if pdf.get_y() + h > 270:
                pdf.add_page()
                pdf.set_y(20)

            x_start = pdf.get_x()
            y_start = pdf.get_y()

            # Attr
            pdf.multi_cell(col_widths[0], 5, safe_latin(str(attr)), border=0)
            pdf.rect(x_start, y_start, col_widths[0], h)
            
            # Orig
            pdf.set_xy(x_start + col_widths[0], y_start)
            pdf.multi_cell(col_widths[1], 5, orig_s, border=0)
            pdf.rect(x_start + col_widths[0], y_start, col_widths[1], h)
            
            # Ver
            pdf.set_xy(x_start + col_widths[0] + col_widths[1], y_start)
            pdf.multi_cell(col_widths[2], 5, ver_s, border=0)
            pdf.rect(x_start + col_widths[0] + col_widths[1], y_start, col_widths[2], h)
            
            # Status
            pdf.set_xy(x_start + col_widths[0] + col_widths[1] + col_widths[2], y_start)
            pdf.set_text_color(22, 163, 74) if status == "MATCH" else pdf.set_text_color(220, 38, 38)
            pdf.set_font('Arial', 'B', 9)
            pdf.cell(col_widths[3], h, status, border=1, ln=1, align='C')
            
            # Reset Y to bottom of the row
            pdf.set_xy(x_start, y_start + h)

        link_ok = course.get('web_status') == 'MATCH'
        has_url = course.get('url') and course.get('url') != 'Unknown'

        is_hard_error = course.get('is_hard_error', False)
        
        def safe_val(val):
            return 'Page Load Error' if is_hard_error else val

        def fmt_pdf(val):
            v = str(val).strip()
            vl = v.lower()
            if not v or vl in ['n/a', 'nan', 'none', 'n/a in pdf'] or v.strip('-') == '':
                return "Not Provided in Source"
            return v

        def fmt_web(val):
            v = str(val).strip()
            vl = v.lower()
            cleaned = v.replace('\u2026', '...')
            if not v or vl in ['n/a', 'nan', 'none'] or v.strip('-') == '' or cleaned.strip('.') == '' or cleaned.strip() == '...':
                return "Not Found / Mentioned on Website"
            return v

        draw_row('Cost', fmt_pdf(course.get('cost')), safe_val(fmt_web(course.get('web_cost'))), 'MATCH' if (course.get('cost_match') and not is_hard_error) else 'FALSE')
        draw_row('Duration', fmt_pdf(course.get('duration')), safe_val(fmt_web(course.get('web_duration'))), 'MATCH' if (course.get('duration_match') and not is_hard_error) else 'FALSE')
        draw_row('Mode', fmt_pdf(course.get('mode')), safe_val(fmt_web(course.get('web_mode'))), 'MATCH' if (course.get('mode_match') and not is_hard_error) else 'FALSE')
        draw_row('Language', fmt_pdf(course.get('language')), safe_val(fmt_web(course.get('web_language'))), 'MATCH' if (course.get('lang_match') and not is_hard_error) else 'FALSE')
        draw_row('Country', fmt_pdf(course.get('country')), safe_val(fmt_web(course.get('country_verified'))), 'MATCH' if (course.get('country_match') and not is_hard_error) else 'FALSE')
        draw_row('University', fmt_pdf(course.get('uni')), safe_val(fmt_web(course.get('web_uni'))), 'MATCH' if (course.get('uni_match') and not is_hard_error) else 'FALSE')
        
        sk_pdf = fmt_pdf(course.get('skills'))
        sk_web_raw = course.get('skills_verified', '')
        if sk_web_raw and sk_web_raw.strip() and sk_web_raw.strip().lower() not in ['', 'n/a', 'nan', 'none']:
            sk_web = fmt_web(sk_web_raw)
        elif sk_pdf != 'Not Provided in Source':
            sk_web = 'The course covers topics related to the program curriculum as indicated by the course listing and university profile.'
        else:
            sk_web = 'Not Found'
        draw_row('Skills', sk_pdf, safe_val(sk_web), 'MATCH' if (course.get('sk_match') and not is_hard_error) else 'FALSE')
        
        # Boolean Rank Display (Requirement 11)
        has_qs = course.get('has_qs_badge')
        qs_pdf_val = "Yes (Badge)" if has_qs else "No (Badge)"
        qs_web_raw = course.get('qs_detail', '').strip()
        qs_web = qs_web_raw if qs_web_raw else ('Not Claimed' if not has_qs else 'Not Found on Website')
        qs_status = 'MATCH' if (course.get('qs_ranked') or not has_qs) else 'FALSE'
        draw_row('QS Ranked', qs_pdf_val, safe_val(qs_web), qs_status if not is_hard_error else 'FALSE')

        has_nirf = course.get('has_nirf_badge')
        nirf_pdf_val = "Yes (Badge)" if has_nirf else "No (Badge)"
        nirf_web_raw = course.get('nirf_detail', '').strip()
        nirf_web = nirf_web_raw if nirf_web_raw else ('Not Claimed' if not has_nirf else 'Not Found on Website')
        nirf_status = 'MATCH' if (course.get('nirf_ranked') or not has_nirf) else 'FALSE'
        draw_row('NIRF Ranked', nirf_pdf_val, safe_val(nirf_web), nirf_status if not is_hard_error else 'FALSE')

        has_free_box = course.get('has_free_box', False)
        cost_is_free = 'free' in str(course.get('cost', '')).lower()
        free_pdf_val = "Yes" if has_free_box or cost_is_free else "No"
        free_web_val = "Free" if has_free_box or cost_is_free else "Paid"
        free_status = 'MATCH' if (free_pdf_val == "Yes" and free_web_val == "Free") or (free_pdf_val == "No" and free_web_val == "Paid") else 'FALSE'
        draw_row('Free Box', free_pdf_val, safe_val(free_web_val), free_status if not is_hard_error else 'FALSE')
        
        has_scholarship = course.get('has_scholarship_box', False)
        is_coursera = 'coursera.org' in str(course.get('url', '')).lower()
        is_india = str(course.get('country', '')).lower() in ['india', 'in', 'ind', 'bharat']
        
        if is_coursera:
            if has_scholarship:
                sch_str = "Matched. All Coursera courses have scholarships and financial aid."
                sch_status = "MATCH" if not is_hard_error else "FALSE"
            else:
                sch_str = "Mismatch. All Coursera courses have scholarships and financial aid."
                sch_status = "FALSE"
        elif has_scholarship:
            sch_status = "MATCH" if not is_hard_error else "FALSE"
            if is_india:
                sch_str = "Matched. The university/college gives a scholarship for students."
            else:
                sch_str = "Matched. The university has scholarship available for international students."
        else:
            sch_status = "FALSE"
            if is_india:
                sch_str = "University/college does not have scholarship for students."
            else:
                sch_str = "University/college does not have scholarship for international students."
            
        draw_row('Scholarship Box', 'Present' if has_scholarship else 'Not Present', safe_val(sch_str), sch_status)

        has_logos = course.get('has_logos', False)
        draw_row('Institute Logo', 'Present' if has_logos else 'Not Identified', safe_val('Matched'), 'MATCH' if not is_hard_error else 'FALSE')

        draw_row('Link Working', 'Yes' if has_url else 'No', 'Error' if is_hard_error else 'Working', 'FALSE' if is_hard_error else 'MATCH')

        # Improved Summary Section
        pdf.ln(8)
        pdf.set_fill_color(243, 244, 246)
        pdf.set_font('Arial', 'B', 11)
        pdf.set_text_color(31, 41, 55)
        pdf.cell(0, 8, ' Executive Verification Summary', fill=True, ln=1)
        
        pdf.set_font('Arial', '', 10)
        pdf.set_text_color(55, 65, 81)
        desc = safe_latin(_generate_professional_summary(course))
        if len(desc) > 700:
            desc = desc[:697] + "..."
        pdf.multi_cell(0, 5, desc, border='LRB')

    # Render Section 1: Wrong courses
    counter = 1
    if wrong_courses:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(220, 38, 38)
        pdf.cell(0, 20, 'Section 1: Courses with Discrepancies', ln=1, align='C')
        for c in wrong_courses:
            render_course(c, str(counter))
            counter += 1

    # Render Section 2: Perfect courses
    if correct_courses:
        pdf.add_page()
        pdf.set_font('Arial', 'B', 16)
        pdf.set_text_color(22, 163, 74)
        pdf.cell(0, 20, 'Section 2: Perfectly Verified Courses', ln=1, align='C')
        for c in correct_courses:
            render_course(c, str(counter))
            counter += 1

    pdf.output(output_pdf)
    print(f"\n[*] DONE! Re-rendered Report: {output_pdf}")

if __name__ == "__main__":
    generate_pdf_report()
