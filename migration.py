"""
Migration script to convert CSV files to SQLite database (simple membership lists)
Handles UTF-16 and UTF-8 encoded CSV files
Run this once to initialize the database from existing CSV files
"""

import os
import sys
from db_manager import DatabaseManager

def migrate_qs_rankings():
    """Load QS rankings from CSV to SQLite (membership list only)"""
    csv_file = "qs_ranked.csv"
    
    if not os.path.exists(csv_file):
        print(f"[!] {csv_file} not found, skipping...")
        return
    
    print(f"[→] Migrating QS rankings from {csv_file}...")
    count = 0
    
    try:
        # Detect encoding: UTF-16 (Excel default) or UTF-8
        encoding = 'utf-8'
        with open(csv_file, 'rb') as f:
            raw = f.read(2)
            if raw == b'\xff\xfe' or raw == b'\xfe\xff':
                encoding = 'utf-16'
        
        print(f"  -> Detected encoding: {encoding}")
        
        with open(csv_file, 'r', encoding=encoding, errors='ignore') as f:
            for i, line in enumerate(f):
                if i == 0:  # Skip header
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                # Extract university name (ignore rank position if present)
                parts = line.split(',', 1)
                university_name = parts[-1].strip()
                
                if university_name:
                    DatabaseManager.insert_qs_ranking(university_name)
                    count += 1
                
                if count % 500 == 0:
                    print(f"  ✓ Inserted {count} QS rankings...")
        
        print(f"[✓] Successfully migrated {count} QS rankings to SQLite")
    
    except Exception as e:
        print(f"[!] Error migrating QS rankings: {e}")


def migrate_nirf_rankings():
    """Load NIRF rankings from CSV to SQLite (membership list only)"""
    csv_file = "nirf_ranked.csv"
    
    if not os.path.exists(csv_file):
        print(f"[!] {csv_file} not found, skipping...")
        return
    
    print(f"[→] Migrating NIRF rankings from {csv_file}...")
    count = 0
    
    try:
        # Detect encoding: UTF-16 (Excel default) or UTF-8
        encoding = 'utf-8'
        with open(csv_file, 'rb') as f:
            raw = f.read(2)
            if raw == b'\xff\xfe' or raw == b'\xfe\xff':
                encoding = 'utf-16'
        
        print(f"  -> Detected encoding: {encoding}")
        
        with open(csv_file, 'r', encoding=encoding, errors='ignore') as f:
            for i, line in enumerate(f):
                if i == 0:  # Skip header
                    continue
                
                line = line.strip()
                if not line:
                    continue
                
                # Extract university name (ignore rank position and category)
                parts = [p.strip() for p in line.split(',')]
                university_name = parts[0] if len(parts) > 0 else ""
                
                if university_name:
                    DatabaseManager.insert_nirf_ranking(university_name)
                    count += 1
                
                if count % 500 == 0:
                    print(f"  ✓ Inserted {count} NIRF rankings...")
        
        print(f"[✓] Successfully migrated {count} NIRF rankings to SQLite")
    
    except Exception as e:
        print(f"[!] Error migrating NIRF rankings: {e}")


def main():
    """Run all migrations"""
    print("\n" + "="*60)
    print("   Course Verifier Database Migration")
    print("   (Simple membership lists for ranking verification)")
    print("="*60 + "\n")
    
    # Initialize database schema
    DatabaseManager.initialize_db()
    
    # Run migrations
    print("\n[PHASE 1] Migrating QS Rankings...")
    migrate_qs_rankings()
    
    print("\n[PHASE 2] Migrating NIRF Rankings...")
    migrate_nirf_rankings()
    
    # Print summary
    print("\n" + "="*60)
    print("   Migration Summary")
    print("="*60)
    qs_count = DatabaseManager.get_table_count('qs_rankings')
    nirf_count = DatabaseManager.get_table_count('nirf_rankings')
    
    print(f"QS Rankings:      {qs_count:,} universities")
    print(f"NIRF Rankings:    {nirf_count:,} universities")
    print("="*60 + "\n")
    
    print("[✓] Migration complete! Database is ready for use.")
    print(f"[✓] Database file: {DatabaseManager.DB_PATH}")


if __name__ == "__main__":
    main()
