import requests
import sys
import time

# Flask API base
LOCAL_URL = "http://localhost:5000"

# Cloudflare Worker URL
CF_WORKER_URL = "https://course-verifier-api.shlokparekh08.workers.dev"
# Hardcoded secure push key matching worker/index.js
CF_KV_PUSH_KEY = "courseverify_secure_push_key_2026"

def push_to_kv(endpoint, payload):
    print(f"[*] Pushing {endpoint} to Cloudflare KV...")
    try:
        res = requests.post(
            f"{CF_WORKER_URL}/api/kv-push",
            headers={
                "Authorization": f"Bearer {CF_KV_PUSH_KEY}",
                "X-Endpoint": endpoint,
                "Content-Type": "application/json"
            },
            json=payload,
            timeout=60
        )
        if res.status_code == 200:
            print(f"    ✓ Success!")
        else:
            print(f"    ✗ Failed ({res.status_code}): {res.text}")
    except Exception as e:
        print(f"    ✗ Error: {e}")

def main():
    print("="*50)
    print(" Cloudflare KV Manual Sync Tool ")
    print("="*50)
    
    print("[*] Fetching latest data from local MongoDB/Flask server...")
    try:
        # data.json (analytics and stats)
        data_res = requests.get(f"{LOCAL_URL}/api/data.json", timeout=10)
        data_payload = data_res.json()
        
        # courses.json (full list of courses)
        courses_res = requests.get(f"{LOCAL_URL}/api/courses.json", timeout=10)
        courses_payload = courses_res.json()
        
        print(f"    ✓ Fetched {len(courses_payload.get('courses', []))} courses.")
        print(f"    ✓ Fetched data analytics.")
    except Exception as e:
        print(f"    ✗ Error fetching local data: {e}")
        print("    Please ensure 'python dashboard.py' is running!")
        sys.exit(1)

    print("\n[*] Uploading data to Cloudflare Edge Network...")
    push_to_kv("data.json", data_payload)
    time.sleep(1) # Small delay to ensure CF writes
    push_to_kv("courses.json", courses_payload)
    
    print("\n[*] Done! The live InfinityFree website is now fully synced.")

if __name__ == "__main__":
    main()
