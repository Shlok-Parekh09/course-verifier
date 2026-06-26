import os
import json
from pymongo import MongoClient

def main():
    print("Reading MongoDB URI...")
    with open("mongo_uri.txt", "r") as f:
        uri = f.read().strip()
    
    print("Connecting to MongoDB...")
    client = MongoClient(uri)
    db = client.get_database("course_verifier")
    
    print("Fetching courses from MongoDB...")
    # Fetch all courses, excluding _id to make it JSON serializable
    courses = list(db.courses.find({}, {"_id": 0}).sort("id", 1))
    print(f"Fetched {len(courses)} courses.")
    
    payload = {
        "status": "success",
        "courses": courses
    }
    
    print("Saving to latest_courses.json...")
    with open("latest_courses.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, separators=(',', ':'))
        
    print("Done! File size:", os.path.getsize("latest_courses.json"), "bytes")

if __name__ == "__main__":
    main()
