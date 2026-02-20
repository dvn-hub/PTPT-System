import sqlite3
import os

DB_PATH = 'patungan.db'

def fix_db():
    if not os.path.exists(DB_PATH):
        print(f"❌ Database {DB_PATH} tidak ditemukan!")
        return

    print(f"🔧 Memperbaiki database: {DB_PATH}")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    try:
        # 1. Enable WAL Mode (Biar gak locking/crash saat akses barengan)
        c.execute("PRAGMA journal_mode=WAL;")
        print("✅ WAL Mode enabled.")

        # 2. Cek Tabel Patungan (Untuk error di halaman Kelola Slot)
        print("Checking table 'patungan'...")
        c.execute("PRAGMA table_info(patungan)")
        columns = [row['name'] for row in c.fetchall()]
        
        if 'status' not in columns:
            print("➕ Adding column 'status'...")
            c.execute("ALTER TABLE patungan ADD COLUMN status VARCHAR(20) DEFAULT 'open'")
        
        if 'discord_channel_id' not in columns:
            print("➕ Adding column 'discord_channel_id'...")
            c.execute("ALTER TABLE patungan ADD COLUMN discord_channel_id VARCHAR(50)")
            
        if 'discord_role_id' not in columns:
            print("➕ Adding column 'discord_role_id'...")
            c.execute("ALTER TABLE patungan ADD COLUMN discord_role_id VARCHAR(50)")

        # 3. Cek Tabel Payment Records (Untuk error di halaman Home/Omzet)
        print("Checking table 'payment_records'...")
        c.execute("PRAGMA table_info(payment_records)")
        columns = [row['name'] for row in c.fetchall()]
        
        if 'paid_amount' not in columns:
            print("➕ Adding column 'paid_amount'...")
            c.execute("ALTER TABLE payment_records ADD COLUMN paid_amount INTEGER DEFAULT 0")
            
        if 'amount_difference' not in columns:
            print("➕ Adding column 'amount_difference'...")
            c.execute("ALTER TABLE payment_records ADD COLUMN amount_difference INTEGER DEFAULT 0")
            
        if 'notes' not in columns:
            print("➕ Adding column 'notes'...")
            c.execute("ALTER TABLE payment_records ADD COLUMN notes TEXT")

        conn.commit()
        print("✅ Database repair finished successfully!")

    except Exception as e:
        print(f"❌ Error: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    fix_db()