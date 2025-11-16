# debug_db.py
import os
import psycopg2
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL")

def test_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        # בדוק אם הטבלאות קיימות
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public';
        """)
        
        tables = cur.fetchall()
        print("📊 Tables in database:", [table[0] for table in tables])
        
        if not tables:
            print("🚨 No tables found! Creating schema...")
            # הרץ את יצירת הטבלאות כאן
            from db import init_schema
            init_schema()
            print("✅ Schema creation attempted")
        
        cur.close()
        conn.close()
        
    except Exception as e:
        print(f"❌ Database error: {e}")

if __name__ == "__main__":
    test_db_connection()
