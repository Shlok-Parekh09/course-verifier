import json
with open('autonomous_verified_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)
for i, d in enumerate(data):
    print(f"{i+1}. {d.get('name')}")
