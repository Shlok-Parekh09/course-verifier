import json
import os
import pymongo
from pymongo import MongoClient, UpdateOne

print("Starting MongoDB migration...")

# Read Mongo URI
if not os.path.exists('mongo_uri.txt'):
    print("Error: mongo_uri.txt not found. Create it and paste your connection string.")
    exit(1)

with open('mongo_uri.txt', 'r') as f:
    mongo_uri = f.read().strip()

if "<db_password>" in mongo_uri:
    print("Error: You forgot to replace <db_password> with your actual password in mongo_uri.txt!")
    exit(1)

# Read 1.json
if not os.path.exists('1.json'):
    print("Error: 1.json not found.")
    exit(1)

with open('1.json', 'r', encoding='utf-8') as f:
    courses = json.load(f)

print(f"Loaded {len(courses)} courses from 1.json")

# Connect to Mongo
try:
    print("Connecting to MongoDB...")
    client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
    client.admin.command('ping')
    db = client['course_verifier']
    print("Connected successfully!")
except Exception as e:
    print("Failed to connect to MongoDB:", e)
    exit(1)

# Bulk write
print("Uploading to MongoDB Atlas... This will only take a few seconds.")
operations = []
for c in courses:
    operations.append(UpdateOne({'id': int(c.get('id')) if str(c.get('id')).isdigit() else c.get('id')}, {'$set': c}, upsert=True))

if operations:
    result = db.courses.bulk_write(operations)
    print(f"Migration complete! Uploaded {len(operations)} courses.")
    print("You can now safely run dashboard.py!")
else:
    print("No courses to migrate.")
