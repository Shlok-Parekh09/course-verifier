import os
from pymongo import MongoClient

def check_mongo_status():
    if not os.path.exists('mongo_uri.txt'):
        print("Error: mongo_uri.txt not found. Please ensure it exists with the connection string.")
        return

    with open('mongo_uri.txt', 'r') as f:
        mongo_uri = f.read().strip()

    try:
        print("Connecting to MongoDB...")
        client = MongoClient(mongo_uri, serverSelectionTimeoutMS=5000)
        # Force a connection test
        client.admin.command('ping')
        db = client['course_verifier']
        courses_collection = db['courses']
        print("Connected successfully!\n")

        total_courses = courses_collection.count_documents({})
        verified_courses = courses_collection.count_documents({"status": "Verified"})
        website_issues = courses_collection.count_documents({"issue_category": "website_issue"})

        print("--- MongoDB Status Report ---")
        print(f"Total number of courses: {total_courses}")
        print(f"Total verified courses:  {verified_courses}")
        print(f"Total website issues:    {website_issues}")
        print("-----------------------------")

    except Exception as e:
        print(f"An error occurred while connecting or querying MongoDB: {e}")

if __name__ == "__main__":
    check_mongo_status()
