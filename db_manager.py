"""
Database Manager for Course Verifier
Handles SQLite operations for ranking membership lists (simple existence checks)
Simple schema: Just check if university exists in ranking system (no rank positions needed)
"""

import sqlite3
import os
from typing import Optional
import threading

class DatabaseManager:
    """Thread-safe SQLite database manager with connection pooling"""
    
    DB_PATH = "course_verifier.db"
    
    # Class-level connection pool
    _local = threading.local()
    
    @classmethod
    def get_connection(cls) -> sqlite3.Connection:
        """Get thread-local database connection with connection pooling"""
        if not hasattr(cls._local, 'connection') or cls._local.connection is None:
            cls._local.connection = sqlite3.connect(cls.DB_PATH, check_same_thread=False)
            cls._local.connection.row_factory = sqlite3.Row
        return cls._local.connection
    
    @classmethod
    def close_connection(cls):
        """Close thread-local connection"""
        if hasattr(cls._local, 'connection') and cls._local.connection:
            cls._local.connection.close()
            cls._local.connection = None
    
    @classmethod
    def initialize_db(cls):
        """Initialize database schema if it doesn't exist"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        # QS Rankings table - simple membership list (just university names)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qs_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                university_name TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on university_name for O(log n) lookup
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_qs_university_name 
            ON qs_rankings(university_name)
        ''')
        
        # NIRF Rankings table - simple membership list (just university names)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nirf_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                university_name TEXT NOT NULL UNIQUE,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on university_name for O(log n) lookup
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nirf_university_name 
            ON nirf_rankings(university_name)
        ''')
        
        conn.commit()
        print("[✓] Database schema initialized successfully")
    
    @classmethod
    def insert_qs_ranking(cls, university_name: str):
        """Insert university into QS rankings list"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO qs_rankings (university_name)
                VALUES (?)
            ''', (university_name,))
            conn.commit()
        except Exception as e:
            print(f"[!] Error inserting QS ranking: {e}")
    
    @classmethod
    def insert_nirf_ranking(cls, university_name: str):
        """Insert university into NIRF rankings list"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO nirf_rankings (university_name)
                VALUES (?)
            ''', (university_name,))
            conn.commit()
        except Exception as e:
            print(f"[!] Error inserting NIRF ranking: {e}")
    
    @classmethod
    def is_qs_ranked(cls, university_name: str) -> bool:
        """Check if university exists in QS rankings - O(log n) indexed lookup"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            # Exact match using index (fastest)
            cursor.execute('''
                SELECT 1 FROM qs_rankings 
                WHERE LOWER(university_name) = LOWER(?)
                LIMIT 1
            ''', (university_name,))
            
            if cursor.fetchone():
                return True
            
            # Partial match if exact match fails (still uses index for LIKE)
            cursor.execute('''
                SELECT 1 FROM qs_rankings 
                WHERE LOWER(university_name) LIKE LOWER(?)
                LIMIT 1
            ''', (f'%{university_name}%',))
            
            return cursor.fetchone() is not None
            
        except Exception as e:
            print(f"[!] Error looking up QS ranking: {e}")
            return False
    
    @classmethod
    def is_nirf_ranked(cls, university_name: str) -> bool:
        """Check if university exists in NIRF rankings - O(log n) indexed lookup"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            # Exact match using index (fastest)
            cursor.execute('''
                SELECT 1 FROM nirf_rankings 
                WHERE LOWER(university_name) = LOWER(?)
                LIMIT 1
            ''', (university_name,))
            
            if cursor.fetchone():
                return True
            
            # Partial match if exact match fails (still uses index for LIKE)
            cursor.execute('''
                SELECT 1 FROM nirf_rankings 
                WHERE LOWER(university_name) LIKE LOWER(?)
                LIMIT 1
            ''', (f'%{university_name}%',))
            
            return cursor.fetchone() is not None
            
        except Exception as e:
            print(f"[!] Error looking up NIRF ranking: {e}")
            return False
    
    @classmethod
    def get_table_count(cls, table_name: str) -> int:
        """Get count of records in a table"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f'SELECT COUNT(*) FROM {table_name}')
            return cursor.fetchone()[0]
        except Exception:
            return 0
    
    @classmethod
    def clear_table(cls, table_name: str):
        """Clear all records from a table"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute(f'DELETE FROM {table_name}')
            conn.commit()
            print(f"[✓] Cleared {table_name} table")
        except Exception as e:
            print(f"[!] Error clearing {table_name}: {e}")

if __name__ == "__main__":
    # Initialize database
    DatabaseManager.initialize_db()
    print("[✓] Database ready!")
