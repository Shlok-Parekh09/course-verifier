import json
import re

log_path = 'notebookba49e67478.log'
main_json_path = 'autonomous_verified_link_compile.pdf.json'
out_path = 'remaining_orphan_logs.txt'

# Load mapped courses to know what we already have
with open(main_json_path, 'r', encoding='utf-8') as f:
    courses = json.load(f)

# Collect all JSONs from log
in_json = False
current_json_buffer = []
all_jsons = []
all_json_strings = []

with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        line = line.strip()
        
        if 'DEBUG LLM OUTPUT:' in line:
            in_json = True
            current_json_buffer = []
            continue
            
        if in_json:
            match = re.search(r'\d+\.\d+s\s+\d+\s+(.*)', line)
            content = match.group(1) if match else line
            
            if content == '}' or content.endswith('}'):
                current_json_buffer.append('}')
                in_json = False
                
                json_str = '\n'.join(current_json_buffer)
                try:
                    parsed = json.loads(json_str)
                    all_jsons.append(parsed)
                    all_json_strings.append(json_str)
                except Exception as e:
                    pass
            else:
                current_json_buffer.append(content)

# Find which ones we already mapped
# We mapped them if the 'reasoning' matches
mapped_reasonings = set()
for c in courses:
    if c.get('processed_this_run', False):
        # We don't have the reasoning in the course dict, but we know 143 were mapped.
        # It's actually easier to just check if the found_cost and reason matches exactly?
        # Actually, let's just dump ALL unmapped ones by matching reasoning from the scripts.
        pass

# Since I don't have a direct link from course to the parsed json in the file,
# I will just write a script that does the exact same mapping logic as before,
# and whatever it CANNOT map, it writes to a text file!

# ---- LOGIC FROM V2 & V3 COMBINED ----

url_to_idx = {c['url'].strip(): i for i, c in enumerate(courses)}
shortname_to_urls = {}
for i, c in enumerate(courses):
    sn = c['name']
    if len(sn) > 40: sn = sn[:40] + '...'
    shortname_to_urls.setdefault(sn.strip(), []).append(c['url'].strip())

threads_current_idx = {} 
pending_threads_for_url = []
thread_start_regex = re.compile(r'\[Thread (\d+)\] Started verifying: (.*)')
url_regex = re.compile(r'\[(\d+)/\d+\] Investigating: (.*)')
worker_regex = re.compile(r'Worker (\d+) trying')
json_start_regex = re.compile(r'DEBUG LLM OUTPUT')

mapped_json_indices = set()
with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

in_json_map = {}
current_buffer_map = {}
json_counter = 0

for i, line in enumerate(lines):
    line = line.strip()
    m1 = thread_start_regex.search(line)
    if m1:
        tid = int(m1.group(1))
        sn = m1.group(2).strip()
        expected_urls = []
        for known_sn, urls in shortname_to_urls.items():
            if known_sn.startswith(sn.replace('...', '')) or sn.startswith(known_sn.replace('...', '')):
                expected_urls.extend(urls)
        pending_threads_for_url.append((tid, expected_urls))
        continue

    m2 = url_regex.search(line)
    if m2:
        cid = int(m2.group(1)) - 1
        url = m2.group(2).strip()
        found_tid = None
        for j, (tid, expected_urls) in enumerate(pending_threads_for_url):
            if url in expected_urls:
                found_tid = tid
                del pending_threads_for_url[j]
                break
        if found_tid is None and pending_threads_for_url:
            found_tid = pending_threads_for_url.pop(0)[0]
        if found_tid is not None:
            threads_current_idx[found_tid] = cid
        continue

    m3 = worker_regex.search(line)
    if m3:
        tid = int(m3.group(1))
        if i+1 < len(lines) and json_start_regex.search(lines[i+1]):
            in_json_map[tid] = True
            current_buffer_map[tid] = []
        continue

    for tid in list(in_json_map.keys()):
        if in_json_map[tid]:
            match = re.search(r'\d+\.\d+s\s+\d+\s+(.*)', line)
            content = match.group(1) if match else line
            if content == '}' or content.endswith('}'):
                current_buffer_map[tid].append('}')
                in_json_map[tid] = False
                json_str = '\n'.join(current_buffer_map[tid])
                try:
                    parsed = json.loads(json_str)
                    if tid in threads_current_idx and threads_current_idx[tid] is not None:
                        idx = threads_current_idx[tid]
                        if 0 <= idx < len(courses):
                            mapped_json_indices.add(json_counter)
                        threads_current_idx[tid] = None
                except: pass
                json_counter += 1
            elif content != 'DEBUG LLM OUTPUT:':
                current_buffer_map[tid].append(content)

# Now apply V3 (clue mapping) to the UNMAPPED ones
json_counter2 = 0
for parsed in all_jsons:
    if json_counter2 not in mapped_json_indices:
        reasoning = parsed.get('reasoning', '')
        cost_match = re.search(r'original cost.*?([£$\u20b9\u20a8]?[\d,]+)', reasoning)
        if cost_match:
            original_cost_str = cost_match.group(1).replace(',', '')
            candidates = []
            for c in courses:
                c_cost = str(c.get('cost', '')).replace(',', '')
                if original_cost_str in c_cost:
                    candidates.append(c)
            if len(candidates) == 1:
                mapped_json_indices.add(json_counter2)
    json_counter2 += 1

orphan_jsons = []
for i, json_str in enumerate(all_json_strings):
    if i not in mapped_json_indices:
        orphan_jsons.append(json_str)

with open(out_path, 'w', encoding='utf-8') as f:
    f.write("=== ORPHAN LOGS THAT COULD NOT BE AUTOMATICALLY MAPPED ===\n\n")
    for j in orphan_jsons:
        f.write(j + "\n\n-------------------------\n\n")

print(f"Exported {len(orphan_jsons)} orphan JSON blocks to {out_path}")
