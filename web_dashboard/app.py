from flask import Flask, render_template, request, redirect, session, url_for, g, flash
import os, requests, json, secrets
from datetime import datetime
from models import db, UserTicket, UserSlot, Patungan, PaymentRecord, CustomCommand

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

# --- KONFIGURASI DATABASE ---
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

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
    
    try:
        # Ambil omzet dan data lainnya
        pending = PaymentRecord.query.filter_by(payment_status='PENDING').all()
        
        # Ambil daftar custom commands
        commands = CustomCommand.query.order_by(CustomCommand.created_at.desc()).all()

        # Hitung Omzet Real (Total uang masuk status PAID)
        omzet = db.session.query(db.func.sum(PaymentRecord.paid_amount)).filter(PaymentRecord.payment_status == 'PAID').scalar() or 0

        # Hitung Statistik untuk Chart
        paid_count = PaymentRecord.query.filter_by(payment_status='PAID').count()
        rejected_count = PaymentRecord.query.filter_by(payment_status='REJECTED').count()
        
        # Statistik Baru (Sesuai Instruksi)
        total_tickets = UserTicket.query.count()
        open_tickets = UserTicket.query.filter(UserTicket.ticket_status != 'closed').count()
        total_services = Patungan.query.count()
    except Exception as e:
        print(f"Database Error: {e}")
        # Jika tabel belum ada, set default value biar gak error 500
        pending = []
        commands = []
        omzet = 0
        paid_count = 0
        rejected_count = 0
        total_tickets = 0
        open_tickets = 0
        total_services = 0

    # Baca file iklan
    teks_iklan = ""
    if os.path.exists(FILE_PROMO):
        with open(FILE_PROMO, 'r') as f: teks_iklan = f.read()

    return render_template('index.html', 
                           pending=pending, 
                           commands=commands, 
                           teks_iklan=teks_iklan, 
                           admin=session,
                           omzet=omzet,
                           paid_count=paid_count,
                           rejected_count=rejected_count,
                           total_tickets=total_tickets,
                           open_tickets=open_tickets,
                           total_services=total_services)

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
    
    # Load data lama dulu biar gak ilang
    current_data = {}
    if os.path.exists(FILE_SCRIPT):
        try:
            with open(FILE_SCRIPT, 'r') as f:
                data = json.load(f)
                if isinstance(data, dict): current_data = data
        except: pass

    # Update data (Simpan sebagai Dictionary)
    if request.form.get('script_blox'): current_data["Blox Fruit"] = request.form.get('script_blox')
    if request.form.get('script_pet'): current_data["Pet Simulator"] = request.form.get('script_pet')

    with open(FILE_SCRIPT, 'w') as f:
        json.dump(current_data, f, indent=4)
    return redirect(url_for('index'))

@app.route('/approve/<int:id>', methods=['POST'])
def approve_payment(id):
    if not session.get('logged_in'): return redirect('/')
    payment = PaymentRecord.query.get(id)
    if payment:
        payment.payment_status = 'PAID'
        db.session.commit()
        flash("Pembayaran disetujui!", "success")
    else:
        flash("Data pembayaran tidak ditemukan.", "danger")
    return redirect(url_for('index'))

@app.route('/reject/<int:id>', methods=['POST'])
def reject_payment(id):
    if not session.get('logged_in'): return redirect('/')
    payment = PaymentRecord.query.get(id)
    if payment:
        payment.payment_status = 'REJECTED'
        db.session.commit()
        flash("Pembayaran ditolak!", "danger")
    else:
        flash("Data pembayaran tidak ditemukan.", "danger")
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.clear()
    flash("Berhasil logout bang!", "success")
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
