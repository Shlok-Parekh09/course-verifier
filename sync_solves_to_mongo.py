import urllib.request
import json
import os
from pymongo import MongoClient

# Configuration
CLOUDFLARE_API_BASE = "https://course-verifier-api.shlokparekh08.workers.dev"
MONGO_URI = ""

# Load MongoDB URI from file if it exists
try:
    with open("mongo_uri.txt", "r") as f:
        for line in f:
            if line.startswith("mongodb+srv://"):
                MONGO_URI = line.strip()
                break
except FileNotFoundError:
    pass

if not MONGO_URI:
    print("Error: Could not find MongoDB URI in mongo_uri.txt")
    exit(1)

def sync_solves():
    print("Checking Cloudflare for pending solves...")
    try:
        req = urllib.request.Request(f"{CLOUDFLARE_API_BASE}/api/pending_solves")
        with urllib.request.urlopen(req) as response:
            data = json.loads(response.read().decode())
    except Exception as e:
        print(f"Failed to fetch pending solves from Cloudflare: {e}")
        return

    pending = data.get("pending_solves", [])
    if not pending:
        print("No pending solves found on Cloudflare.")
        return

    print(f"Found {len(pending)} pending solves. Syncing to MongoDB...")
    
    try:
        client = MongoClient(MONGO_URI)
        db = client['course_verifier']
        collection = db['courses']
        
        synced_count = 0
        for solve in pending:
            course_id = solve.get("id")
            update_obj = solve.get("update")
            if course_id and update_obj:
                # Format update safely (expecting $set or similar MongoDB operators)
                if not any(k.startswith('$') for k in update_obj.keys()):
                    update_obj = {"$set": update_obj}
                    
                res = collection.update_one(
                    {"id": {"$in": [int(course_id), str(course_id)]}}, 
                    update_obj
                )
                if res.modified_count > 0 or res.matched_count > 0:
                    synced_count += 1
                else:
                    print(f"  Warning: Course {course_id} not found in MongoDB.")
                    
        print(f"Successfully synced {synced_count}/{len(pending)} courses to MongoDB.")
        
        # Clear the queue on Cloudflare
        print("Clearing Cloudflare pending queue...")
        req_clear = urllib.request.Request(f"{CLOUDFLARE_API_BASE}/api/clear_pending_solves", method="POST")
        with urllib.request.urlopen(req_clear) as response_clear:
            clear_res = json.loads(response_clear.read().decode())
            if clear_res.get("status") == "success":
                print("Queue cleared successfully. Sync complete!")
            else:
                print(f"Warning: Failed to clear queue: {clear_res}")
                
    except Exception as e:
        print(f"MongoDB Sync Error: {e}")

if __name__ == "__main__":
    sync_solves()
