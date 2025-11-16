# nuclear_reset.py
import os
import psycopg2
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def check_bot_token(token):
    """בודק אם הטוקן תקין"""
    try:
        url = f"https://api.telegram.org/bot{token}/getMe"
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            print("✅ Bot token is valid")
            return True
        else:
            print(f"❌ Bot token invalid: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        print(f"❌ Error checking bot token: {e}")
        return False

def nuclear_reset():
    print("🚀 Starting NUCLEAR RESET...")
    
    DATABASE_URL = os.environ.get("DATABASE_URL")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    WEBHOOK_URL = os.environ.get("WEBHOOK_URL")
    
    # בדוק את הטוקן קודם
    if not check_bot_token(BOT_TOKEN):
        print("❌ Cannot proceed - invalid bot token")
        return
    
    try:
        # 1. אפס webhook קודם
        print("🔄 Clearing webhook...")
        requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url=")
        
        # 2. נסה להתחבר ל-DB
        print("🗃️ Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        cur = conn.cursor()
        
        # 3. מחק את כל הטבלאות
        print("🧨 Dropping all tables...")
        cur.execute("""
            DO $$ DECLARE
                r RECORD;
            BEGIN
                FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname = 'public') LOOP
                    EXECUTE 'DROP TABLE IF EXISTS ' || quote_ident(r.tablename) || ' CASCADE';
                    RAISE NOTICE 'Dropped table: %', r.tablename;
                END LOOP;
            END $$;
        """)
        
        print("✅ All tables dropped!")
        
        cur.close()
        conn.close()
        
        # 4. הגדר webhook מחדש
        print("🔗 Setting new webhook...")
        response = requests.get(f"https://api.telegram.org/bot{BOT_TOKEN}/setWebhook?url={WEBHOOK_URL}")
        print(f"Webhook response: {response.status_code}")
        
        print("🎉 NUCLEAR RESET COMPLETED!")
        print("📋 Now restart your bot service...")
        
    except Exception as e:
        print(f"❌ Error: {e}")

if __name__ == "__main__":
    nuclear_reset()
