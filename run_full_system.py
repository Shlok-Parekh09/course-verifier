import subprocess
import sys
import threading
from db_manager import DatabaseManager

def run_legacy_verifier():
    print("[Legacy System] Starting Autonomous Course Verifier...")
    subprocess.run([sys.executable, "autonomous_course_verifier.py"])
    print("[Legacy System] Completed.")

def run_fee_engine():
    print("[Fee Engine] Starting parallel Fee Intelligence Layer...")
    subprocess.run([sys.executable, "fee_engine/main.py"])
    print("[Fee Engine] Completed.")

if __name__ == "__main__":
    print("=== Enterprise AI Verification System ===")
    
    # Initialize database on startup
    print("[→] Initializing database...")
    DatabaseManager.initialize_db()
    
    print("Launching Main Verifier and Fee Engine in parallel...")
    
    t1 = threading.Thread(target=run_legacy_verifier)
    t2 = threading.Thread(target=run_fee_engine)
    
    t1.start()
    t2.start()
    
    t1.join()
    t2.join()
    
    print("=== All Pipeline Executions Finished ===")
