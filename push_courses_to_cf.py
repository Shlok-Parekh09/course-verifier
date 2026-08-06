"""
push_courses_to_cf.py
======================
Pushes the local frontend/1.json as courses.json to Cloudflare KV
using the existing /api/kv-push endpoint (already deployed).
This updates the live website immediately.
"""

import json
import os
import requests
from dotenv import load_dotenv

load_dotenv()

CF_WORKER_URL = os.environ.get("CF_WORKER_URL", "https://course-verifier-api.shlokparekh08.workers.dev")
CF_KV_PUSH_KEY = os.environ.get("CF_KV_PUSH_KEY", "courseverify_secure_push_key_2026")

INPUT_JSON = "frontend/course_catalog.json"

def main():
    print(f"[*] Loading {INPUT_JSON}...")
    with open(INPUT_JSON, "r", encoding="utf-8") as f:
        raw = f.read()
    data = json.loads(raw)
    print(f"    {len(data)} courses loaded ({len(raw) / 1024 / 1024:.1f} MB).")

    print(f"\n[*] Pushing to Cloudflare KV as 'courses.json'...")
    headers = {
        "Authorization": f"Bearer {CF_KV_PUSH_KEY}",
        "Content-Type": "application/json",
        "X-Endpoint": "courses.json",
    }

    resp = requests.post(
        f"{CF_WORKER_URL}/api/kv-push",
        data=raw.encode("utf-8"),
        headers=headers,
        timeout=120,
    )

    print(f"  Response: {resp.status_code} - {resp.text}")

    if resp.status_code == 200:
        print(f"\n[OK] courses.json pushed to Cloudflare successfully!")
        print(f"     Live site will reflect the updated domains within ~60 seconds (CDN cache TTL).")
    else:
        print(f"\n[!] Push failed. Check auth key and Worker URL.")

if __name__ == "__main__":
    main()
