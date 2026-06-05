import json
import os

if os.path.exists('url_cache.json'):
    with open('url_cache.json', 'r', encoding='utf-8') as f:
        cache = json.load(f)
    
    to_delete = []
    for k, v in cache.items():
        # Check if description has leaked prompt
        has_leak = False
        for field in ['web_cost', 'web_duration', 'web_mode', 'web_language', 'web_country', 'skills_verified']:
            val = str(v.get(field, ''))
            if '* Original' in val or 'Course Name:' in val or 'Cost:' in val:
                has_leak = True
                break
        
        # Also remove course 17, 18 which had N/A issue
        if v.get('web_duration') == 'N/A' or v.get('web_language') == 'N/A':
            has_leak = True
            
        if has_leak:
            to_delete.append(k)
            
    for k in to_delete:
        print(f"Deleting cache for: {cache[k].get('name', k)}")
        del cache[k]
        
    with open('url_cache.json', 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=4)
    print(f'Deleted {len(to_delete)} corrupted cache entries.')
else:
    print('No cache found.')
