import fitz, re, json, time

t0 = time.time()
doc = fitz.open('jnd.pdf')
print(f"Pages: {len(doc)}")

all_courses = {}
for page_num in range(len(doc)):
    fitz_page = doc[page_num]
    text = fitz_page.get_text()
    if not text:
        continue
    
    match = re.search(r'^\s*(\d+)\.\s+(.+?)\s*$', text, re.MULTILINE)
    if not match:
        continue
    
    course_id = int(match.group(1))
    title = match.group(2).strip()
    
    tabs = fitz_page.find_tables()
    rows_data = []
    if tabs:
        table = tabs[0].extract()
        for row in table:
            if len(row) >= 4:
                attr = str(row[0]).strip().replace('\n', ' ')
                if attr.lower() == 'attribute':
                    continue
                original = str(row[1]).strip().replace('\n', ' ') if row[1] else ''
                verified = str(row[2]).strip().replace('\n', ' ') if row[2] else ''
                status = str(row[3]).strip().replace('\n', ' ') if row[3] else ''
                rows_data.append({
                    "attribute": attr,
                    "original": original,
                    "verified": verified,
                    "status": status
                })
    
    all_courses[course_id] = {
        'title': title,
        'rows': rows_data
    }

elapsed = time.time() - t0
print(f"Extracted {len(all_courses)} courses in {elapsed:.2f}s")

# Show first course details
for cid in sorted(all_courses.keys())[:2]:
    print(f"\n=== Course {cid}: {all_courses[cid]['title']} ===")
    for r in all_courses[cid]['rows']:
        print(f"  {r['attribute']:20s} | {r['original'][:30]:30s} | {r['status']}")
