import json

with open('autonomous_verified_data.json', 'r', encoding='utf-8') as f:
    courses = json.load(f)

with open('temp_table.md', 'w', encoding='utf-8') as out:
    out.write('| Course / Subject | University | Cost (Web) | Language (Status) | Link Working | Official Rankings |\n')
    out.write('|---|---|---|---|---|---|\n')
    
    for i, c in enumerate(courses):
        name = c.get('name', 'Unknown')
        uni = c.get('uni', 'Unknown')
        
        if 'network forensics' in name.lower() or 'punjabi' in uni.lower() or i == 33 or 'hopkins' in uni.lower() or 'irvine' in uni.lower() or i == 10:
            cost = c.get('web_cost', '')
            lang = f"{c.get('web_language', '')} (MATCH)"
            link = 'FALSE' if c.get('is_hard_error') else 'MATCH'
            ranks = []
            if c.get('qs_ranked'): ranks.append('QS')
            if c.get('nirf_ranked'): ranks.append('NIRF')
            rank_str = ', '.join(ranks) if ranks else 'None'
            
            # Clean up newlines for the markdown table
            name = name.replace('\n', ' ')
            uni = uni.replace('\n', ' ')
            cost = cost.replace('\n', ' ')
            
            out.write(f'| {name} | {uni} | {cost} | {lang} | {link} | {rank_str} |\n')
