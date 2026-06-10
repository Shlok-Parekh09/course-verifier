"""
Database Manager for Course Verifier
Handles SQLite operations for ranking data and course information
"""

import sqlite3
import os
from typing import Optional, List, Tuple
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
        
        # QS Rankings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS qs_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                university_name TEXT NOT NULL UNIQUE,
                rank_position INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on university_name for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_qs_university_name 
            ON qs_rankings(university_name)
        ''')
        
        # NIRF Rankings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS nirf_rankings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                university_name TEXT NOT NULL UNIQUE,
                rank_position INTEGER,
                rank_category TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on university_name for fast lookups
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_nirf_university_name 
            ON nirf_rankings(university_name)
        ''')
        
        # Course data table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS course_data (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                course_title TEXT NOT NULL,
                university_name TEXT NOT NULL,
                fee REAL,
                duration_months INTEGER,
                mode TEXT,
                skills TEXT,
                url TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Create index on course_title and university_name
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_course_university 
            ON course_data(course_title, university_name)
        ''')
        
        conn.commit()
        print("[✓] Database schema initialized successfully")
    
    @classmethod
    def insert_qs_ranking(cls, university_name: str, rank_position: Optional[int] = None):
        """Insert or update QS ranking"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO qs_rankings (university_name, rank_position)
                VALUES (?, ?)
            ''', (university_name, rank_position))
            conn.commit()
        except Exception as e:
            print(f"[!] Error inserting QS ranking: {e}")
    
    @classmethod
    def insert_nirf_ranking(cls, university_name: str, rank_position: Optional[int] = None, rank_category: Optional[str] = None):
        """Insert or update NIRF ranking"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            cursor.execute('''
                INSERT OR REPLACE INTO nirf_rankings (university_name, rank_position, rank_category)
                VALUES (?, ?, ?)
            ''', (university_name, rank_position, rank_category))
            conn.commit()
        except Exception as e:
            print(f"[!] Error inserting NIRF ranking: {e}")
    
    @classmethod
    def lookup_qs_ranking(cls, university_name: str) -> Optional[Tuple]:
        """Fast lookup for QS ranking using indexed query - O(log n)"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            # Exact match first (fastest)
            cursor.execute('''
                SELECT rank_position FROM qs_rankings 
                WHERE LOWER(university_name) = LOWER(?)
                LIMIT 1
            ''', (university_name,))
            
            row = cursor.fetchone()
            if row:
                return row[0]
            
            # Partial match if exact match fails (still indexed)
            cursor.execute('''
                SELECT rank_position FROM qs_rankings 
                WHERE LOWER(university_name) LIKE LOWER(?)
                LIMIT 1
            ''', (f'%{university_name}%',))
            
            row = cursor.fetchone()
            return row[0] if row else None
            
        except Exception as e:
            print(f"[!] Error looking up QS ranking: {e}")
            return None
    
    @classmethod
    def lookup_nirf_ranking(cls, university_name: str) -> Optional[Tuple]:
        """Fast lookup for NIRF ranking using indexed query - O(log n)"""
        conn = cls.get_connection()
        cursor = conn.cursor()
        
        try:
            # Exact match first (fastest)
            cursor.execute('''
                SELECT rank_position, rank_category FROM nirf_rankings 
                WHERE LOWER(university_name) = LOWER(?)
                LIMIT 1
            ''', (university_name,))
            
            row = cursor.fetchone()
            if row:
                return dict(row) if row else None
            
            # Partial match if exact match fails (still indexed)
            cursor.execute('''
                SELECT rank_position, rank_category FROM nirf_rankings 
                WHERE LOWER(university_name) LIKE LOWER(?)
                LIMIT 1
            ''', (f'%{university_name}%',))
            
            row = cursor.fetchone()
            return dict(row) if row else None
            
        except Exception as e:
            print(f"[!] Error looking up NIRF ranking: {e}")
            return None
    
    @classmethod
    def is_qs_ranked(cls, university_name: str) -> bool:
        """Check if university is in QS rankings"""
        result = cls.lookup_qs_ranking(university_name)
        return result is not None
    
    @classmethod
    def is_nirf_ranked(cls, university_name: str) -> bool:
        """Check if university is in NIRF rankings"""
        result = cls.lookup_nirf_ranking(university_name)
        return result is not None
    
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
