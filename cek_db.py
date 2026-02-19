import sqlite3

# Koneksi ke DB
conn = sqlite3.connect('patungan.db')
cursor = conn.cursor()

# Liat ada tabel apa aja
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
tables = cursor.fetchall()

print("=== DAFTAR TABEL ===")
for table in tables:
    print(f"- {table[0]}")
    
    # Liat kolom di dalem tabel itu
    cursor.execute(f"PRAGMA table_info({table[0]})")
    columns = cursor.fetchall()
    for col in columns:
        print(f"   Column: {col[1]} (Tipe: {col[2]})")

conn.close()
