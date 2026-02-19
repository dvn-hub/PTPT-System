import sqlite3
import os

DB_FILE = 'patungan.db'

def migrate():
    if not os.path.exists(DB_FILE):
        print(f"Database {DB_FILE} not found.")
        return

    print(f"Checking database: {DB_FILE}")
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    try:
        # Check columns in patungan table
        cursor.execute("PRAGMA table_info(patungan)")
        columns = [info[1] for info in cursor.fetchall()]
        print(f"Existing columns: {columns}")
        
        if 'discord_channel_id' not in columns:
            print("Adding discord_channel_id to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN discord_channel_id VARCHAR(50)")
            
        if 'discord_role_id' not in columns:
            print("Adding discord_role_id to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN discord_role_id VARCHAR(50)")

        if 'use_script' not in columns:
            print("Adding use_script to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN use_script VARCHAR(10)")

        if 'start_mode' not in columns:
            print("Adding start_mode to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN start_mode VARCHAR(20)")

        if 'duration_hours' not in columns:
            print("Adding duration_hours to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN duration_hours INTEGER DEFAULT 24")

        if 'start_schedule' not in columns:
            print("Adding start_schedule to patungan table...")
            cursor.execute("ALTER TABLE patungan ADD COLUMN start_schedule TIMESTAMP")
            
        conn.commit()
        print("Migration completed successfully.")
        
    except Exception as e:
        print(f"Error during migration: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()