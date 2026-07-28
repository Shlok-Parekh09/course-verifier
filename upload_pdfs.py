import fitz
import re
import requests
import os
from dotenv import load_dotenv

load_dotenv()

CF_WORKER_URL = os.environ.get('CF_WORKER_URL', 'https://course-verifier-api.shlokparekh08.workers.dev')
CF_KV_PUSH_KEY = os.environ.get('CF_KV_PUSH_KEY', 'courseverify_secure_push_key_2026')

def parse_pdf_for_solves(pdf_path, start_idx, end_idx):
    doc = fitz.open(pdf_path)
    current_idx = None
    current_statuses = []
    
    solves = []
    
    for page in doc:
        text = page.get_text()
        
        # Look for the index header
        match = re.search(r'^(\d+)\.\s+', text, re.MULTILINE)
        if match:
            if current_idx is not None and start_idx <= current_idx <= end_idx:
                if len(current_statuses) >= 13:
                    # In case there are extra, we take the FIRST 13 statuses found which correspond to the 13 attributes
                    solves.append({
                        "id": current_idx,
                        "update": current_statuses[:13],
                        "by": "AI"
                    })
                else:
                    print(f"Warning: Index {current_idx} has {len(current_statuses)} statuses instead of 13")
                    
            current_idx = int(match.group(1))
            current_statuses = []
            
        lines = text.split('\n')
        for line in lines:
            line = line.strip()
            if line == "MATCH" or line == "FALSE":
                current_statuses.append(line)
                
    if current_idx is not None and start_idx <= current_idx <= end_idx:
        if len(current_statuses) >= 13:
            solves.append({
                "id": current_idx,
                "update": current_statuses[:13],
                "by": "AI"
            })
        else:
            print(f"Warning: Index {current_idx} has {len(current_statuses)} statuses instead of 13")
            
    return solves

def upload_solves(solves):
    print(f"Uploading {len(solves)} solves to Cloudflare...")
    headers = {
        'Authorization': f'Bearer {CF_KV_PUSH_KEY}',
        'Content-Type': 'application/json'
    }
    
    chunk_size = 50
    for i in range(0, len(solves), chunk_size):
        chunk = solves[i:i+chunk_size]
        payload = {"solves": chunk}
        try:
            resp = requests.post(f"{CF_WORKER_URL}/api/solve_course", json=payload, headers=headers)
            print(f"Batch {i//chunk_size + 1}: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Error uploading batch: {e}")

if __name__ == "__main__":
    all_solves = []
    
    if os.path.exists("Foundational.pdf"):
        print("Parsing Foundational.pdf (337-444)...")
        solves_f = parse_pdf_for_solves("Foundational.pdf", 337, 444)
        all_solves.extend(solves_f)
    else:
        print("Foundational.pdf not found!")
        
    if os.path.exists("Network_and_Infra.pdf"):
        print("Parsing Network_and_Infra.pdf (1558-1585)...")
        solves_n = parse_pdf_for_solves("Network_and_Infra.pdf", 1558, 1585)
        all_solves.extend(solves_n)
    else:
        print("Network_and_Infra.pdf not found!")
        
    if all_solves:
        upload_solves(all_solves)
    else:
        print("No solves extracted!")
