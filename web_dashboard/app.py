from flask import Flask, render_template, request, redirect, session, url_for, g
import sqlite3, os, requests, json, secrets
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'KUNCI_TETAP_DIVINEBLOX_123'
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
)

# --- KONFIGURASI (PASTIKAN TETAP TERISI) ---
DISCORD_CLIENT_ID = '1454379171072704675'
DISCORD_CLIENT_SECRET = 'gS7ZLoSZy_159ggoHr9OfZsfytlvDtnE'
DISCORD_REDIRECT_URI = 'https://panel.divineblox.com/callback'
ALLOWED_USER_IDS = ['554635001526747136', '718477976559288361', '890586988770656307'] #

# --- PATH FILE BOT ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PARENT_DIR = os.path.join(BASE_DIR, '..')
DB_PATH = os.path.join(PARENT_DIR, 'patungan.db')
FILE_PROMO = os.path.join(PARENT_DIR, 'bot_iklan', 'pesan.txt')
FILE_SCRIPT = os.path.join(PARENT_DIR, 'bot_script', 'scripts.json')

def get_db():
    db = getattr(g, '_database', None)
    if db is None:
        db = g._database = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
    return db

@app.teardown_appcontext
def close_connection(exception):
    db = getattr(g, '_database', None)
    if db is not None: db.close()

# --- ROUTES AUTH (SAMA KAYAK SEBELUMNYA) ---
@app.route('/login')
def login():
    url = f"https://discord.com/api/oauth2/authorize?client_id={DISCORD_CLIENT_ID}&redirect_uri={DISCORD_REDIRECT_URI}&response_type=code&scope=identify"
    return redirect(url)

@app.route('/callback')
def callback():
    code = request.args.get('code')
    data = {
        'client_id': DISCORD_CLIENT_ID,
        'client_secret': DISCORD_CLIENT_SECRET,
        'grant_type': 'authorization_code',
        'code': code,
        'redirect_uri': DISCORD_REDIRECT_URI
    }
    
    # 1. Ambil Token
    r_token = requests.post('https://discord.com/api/v10/oauth2/token', data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    token_data = r_token.json()
    token = token_data.get('access_token')

    if not token:
        return f"Gagal dapet token dari Discord! Error: {token_data.get('error_description', token_data)}"

    # 2. Ambil Data User
    r_user = requests.get('https://discord.com/api/v10/users/@me', headers={'Authorization': f'Bearer {token}'})
    user_data = r_user.json()

    if 'id' not in user_data:
        return f"Discord nggak ngasih data ID! Responnya: {user_data}"

    # 3. Cek apakah ID ada di daftar staff Isa
    if user_data['id'] not in ALLOWED_USER_IDS:
        return f"Akses Ditolak! ID {user_data['id']} nggak terdaftar di sistem DivineBlox.", 403

    # 4. Simpan ke Session
    session.permanent = True
    session.update({
        'logged_in': True, 
        'username': user_data['username'], 
        'avatar': f"https://cdn.discordapp.com/avatars/{user_data['id']}/{user_data['avatar']}.png"
    })
    return redirect(url_for('index'))

# --- HALAMAN UTAMA ---
@app.route('/')
def index():
    if not session.get('logged_in'): return render_template('login.html')
    conn = get_db()
    
    # Ambil omzet dan data lainnya
    pending = conn.execute("SELECT * FROM payment_records WHERE payment_status='PENDING'").fetchall()
    
    # Ambil daftar custom commands
    commands = conn.execute("SELECT * FROM custom_commands ORDER BY created_at DESC").fetchall()

    # Baca file iklan
    teks_iklan = ""
    if os.path.exists(FILE_PROMO):
        with open(FILE_PROMO, 'r') as f: teks_iklan = f.read()

    return render_template('index.html', 
                           pending=pending, 
                           commands=commands, 
                           teks_iklan=teks_iklan, 
                           admin=session,
                           omzet=0) #

# --- FITUR EDIT IKLAN ---
@app.route('/save_iklan', methods=['POST'])
def save_iklan():
    if not session.get('logged_in'): return redirect('/')
    teks_baru = request.form.get('isi_iklan')
    with open(FILE_PROMO, 'w') as f:
        f.write(teks_baru)
    return redirect(url_for('index'))

# --- FITUR EDIT SCRIPT ---
@app.route('/save_script', methods=['POST'])
def save_script():
    if not session.get('logged_in'): return redirect('/')
    # Ambil data dari form (misal script untuk Blox Fruit)
    updated_data = [
        {"game": "Blox Fruit", "script": request.form.get('script_blox')},
        {"game": "Pet Simulator", "script": request.form.get('script_pet')}
    ]
    with open(FILE_SCRIPT, 'w') as f:
        json.dump(updated_data, f, indent=4)
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
