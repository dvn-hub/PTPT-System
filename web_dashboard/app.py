from flask import Flask, render_template, request, redirect, session, url_for, g, flash
import os, requests, json, secrets
from datetime import datetime
from models import db, UserTicket, UserSlot, Patungan, PaymentRecord, CustomCommand, ActionQueue

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
FILE_PANELS = os.path.join(PARENT_DIR, 'panels.json')

# --- DEBUG PATH DATABASE (Cek Terminal/Log) ---
print(f"--> DEBUG DB PATH: {DB_PATH}")
if os.path.exists(DB_PATH):
    print(f"--> DB FOUND. Size: {os.path.getsize(DB_PATH)} bytes")
else:
    print("--> DB NOT FOUND! Flask akan membuat file baru kosong.")

# --- KONFIGURASI DATABASE ---
app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{DB_PATH}'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['TEMPLATES_AUTO_RELOAD'] = True
db.init_app(app)

# --- AUTO CREATE TABLES (FIX ERROR NO SUCH TABLE) ---
with app.app_context():
    db.create_all()

# --- HELPER: LOAD PANELS ---
def load_panels():
    defaults = {
        "dashboard": {
            "title": "👑 DVN COMMAND CENTER",
            "description": "Panel kontrol eksekutif untuk manajemen transaksi Patungan X8.\n\n**📋 Menu Admin:**\n⛏️ **Buat Patungan** - Membuat patungan baru (V1, V2, dll)\n⛏️ **Kelola Patungan** - Lihat status dan edit patungan\n⛏️ **Verifikasi Pembayaran** - Cek pembayaran pending"
        },
        "ticket": {
            "title": "🍀 OPEN SLOT PTPT & X8 LUCK 🍀",
            "description": "✨ **Halo Fisherman!** Ingin join slot Patungan (PTPT) Boost Luck?\n\n**Cara Order:**\n1️⃣ Klik tombol **🎫 Buat Ticket** di bawah.\n2️⃣ Pilih **Server / Jenis Layanan** yang kamu inginkan.\n3️⃣ Lakukan pembayaran sesuai instruksi bot.\n\n*⚠️ Pastikan slot masih tersedia di channel Info Slot!*"
        }
    }
    if os.path.exists(FILE_PANELS):
        try:
            with open(FILE_PANELS, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return {**defaults, **data} # Merge defaults with loaded data
        except:
            return defaults
    return defaults

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
        # Tampilkan error di Dashboard agar ketahuan masalahnya
        flash(f"Gagal Baca Database: {str(e)} | Path: {DB_PATH}", "danger")
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

# --- ROUTES BARU UNTUK SIDEBAR ---

@app.route('/panel')
def panel_ptpt():
    if not session.get('logged_in'): return redirect('/')
    panels = load_panels()
    return render_template('panel.html', admin=session, panels=panels)

@app.route('/panel/action', methods=['POST'])
def panel_action():
    if not session.get('logged_in'): return redirect('/')
    action = request.form.get('action')
    flash(f"Perintah '{action}' berhasil dikirim ke sistem.", "success")
    return redirect(url_for('panel_ptpt'))

@app.route('/save_panel', methods=['POST'])
def save_panel():
    if not session.get('logged_in'): return redirect('/')
    
    panel_type = request.form.get('panel_type')
    title = request.form.get('title')
    description = request.form.get('description')
    
    panels = load_panels()
    if panel_type:
        panels[panel_type] = {"title": title, "description": description}
        with open(FILE_PANELS, 'w', encoding='utf-8') as f:
            json.dump(panels, f, indent=4, ensure_ascii=False)
        flash(f"Panel {panel_type} berhasil diupdate!", "success")
    
    return redirect(url_for('panel_ptpt'))

# --- ROUTES ADMIN ACTIONS (REMOTE CONTROL) ---

@app.route('/admin/actions')
def admin_actions():
    if not session.get('logged_in'): return redirect('/')
    
    # Ambil data untuk dropdown
    patungans = Patungan.query.filter(Patungan.status != 'archived').all()
    
    return render_template('admin_actions.html', admin=session, patungans=patungans)

@app.route('/admin/create_patungan', methods=['POST'])
def admin_create_patungan():
    if not session.get('logged_in'): return redirect('/')
    
    payload = {
        "product_name": request.form.get('product_name').upper(),
        "price": int(request.form.get('price')),
        "max_slots": int(request.form.get('max_slots')),
        "duration": int(request.form.get('duration')),
        "use_script": request.form.get('use_script'),
        "start_mode": request.form.get('start_mode'),
        "schedule": request.form.get('schedule')
    }
    
    new_action = ActionQueue(
        action_type='create_patungan',
        payload=json.dumps(payload),
        created_by=session['username']
    )
    db.session.add(new_action)
    db.session.commit()
    
    flash(f"Perintah Buat Patungan {payload['product_name']} dikirim ke Bot!", "success")
    return redirect(url_for('admin_actions'))

@app.route('/admin/delete_patungan', methods=['POST'])
def admin_delete_patungan():
    if not session.get('logged_in'): return redirect('/')
    
    product_name = request.form.get('product_name')
    new_action = ActionQueue(
        action_type='delete_patungan',
        payload=json.dumps({"product_name": product_name}),
        created_by=session['username']
    )
    db.session.add(new_action)
    db.session.commit()
    
    flash(f"Perintah Hapus Patungan {product_name} dikirim ke Bot!", "warning")
    return redirect(url_for('admin_actions'))

@app.route('/admin/remove_member', methods=['POST'])
def admin_remove_member():
    if not session.get('logged_in'): return redirect('/')
    
    product_name = request.form.get('product_name')
    username = request.form.get('username')
    
    new_action = ActionQueue(
        action_type='remove_member',
        payload=json.dumps({"product_name": product_name, "username": username}),
        created_by=session['username']
    )
    db.session.add(new_action)
    db.session.commit()
    
    flash(f"Perintah Kick Member {username} dari {product_name} dikirim!", "warning")
    return redirect(url_for('admin_actions'))

@app.route('/admin/get_members/<product_name>')
def get_members(product_name):
    if not session.get('logged_in'): return "Unauthorized", 403
    slots = UserSlot.query.filter_by(patungan_version=product_name).filter(UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])).all()
    data = [{"username": s.game_username, "slot": s.slot_number} for s in slots]
    return json.dumps(data)

@app.route('/slots')
def manage_slots():
    if not session.get('logged_in'): return redirect('/')
    # Ambil semua patungan aktif
    patungans = Patungan.query.filter(Patungan.status != 'archived').all()
    return render_template('manage_slots.html', admin=session, patungans=patungans)

@app.route('/commands')
def custom_commands():
    if not session.get('logged_in'): return redirect('/')
    commands = CustomCommand.query.order_by(CustomCommand.created_at.desc()).all()
    return render_template('commands.html', admin=session, commands=commands)

@app.route('/add_command', methods=['POST'])
def add_command():
    if not session.get('logged_in'): return redirect('/')
    name = request.form.get('name')
    response = request.form.get('response')
    new_cmd = CustomCommand(name=name, response=response)
    db.session.add(new_cmd)
    db.session.commit()
    flash(f"Command !{name} berhasil ditambahkan!", "success")
    return redirect(url_for('custom_commands'))

@app.route('/delete_command/<int:id>', methods=['POST'])
def delete_command(id):
    if not session.get('logged_in'): return redirect('/')
    CustomCommand.query.filter_by(id=id).delete()
    db.session.commit()
    flash("Command berhasil dihapus!", "success")
    return redirect(url_for('custom_commands'))

@app.route('/transactions')
def transaction_history():
    if not session.get('logged_in'): return redirect('/')
    return "<h1>Halaman Riwayat Transaksi (Dalam Perbaikan)</h1><a href='/'>Kembali ke Home</a>"

@app.route('/broadcast')
def broadcast():
    if not session.get('logged_in'): return redirect('/')
    return "<h1>Halaman Broadcast Iklan (Dalam Perbaikan)</h1><a href='/'>Kembali ke Home</a>"

@app.route('/stock')
def stock_panel():
    if not session.get('logged_in'): return redirect('/')
    return "<h1>Halaman Stock Panel (Dalam Perbaikan)</h1><a href='/'>Kembali ke Home</a>"

@app.route('/check_db')
def check_db():
    if not session.get('logged_in'): return redirect('/')
    
    import sqlite3
    info = []
    info.append(f"<h3>Database Debug Info</h3>")
    info.append(f"<b>Configured Path:</b> {DB_PATH}")
    
    if os.path.exists(DB_PATH):
        size = os.path.getsize(DB_PATH)
        info.append(f"<b>Status:</b> File FOUND ✅")
        info.append(f"<b>Size:</b> {size} bytes")
        try:
            info.append(f"<b>Permissions:</b> {oct(os.stat(DB_PATH).st_mode)[-3:]}")
        except:
            info.append(f"<b>Permissions:</b> Unknown")
        
        try:
            # Cek isi tabel via Raw SQLite
            conn = sqlite3.connect(DB_PATH)
            cursor = conn.cursor()
            
            # List Tables
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = [t[0] for t in cursor.fetchall()]
            info.append(f"<b>Tables in DB:</b> {', '.join(tables)}")
            
            # Cek jumlah data
            stats = []
            for table in ['patungan', 'user_tickets', 'payment_records']:
                if table in tables:
                    cursor.execute(f"SELECT count(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    stats.append(f"{table}: {count} rows")
                else:
                    stats.append(f"{table}: MISSING ❌")
            
            info.append(f"<b>Data Counts:</b> <br>" + "<br>".join(stats))
            conn.close()
            
        except Exception as e:
            info.append(f"<b>Error Reading DB:</b> {str(e)}")
    else:
        info.append(f"<b>Status:</b> File NOT FOUND ❌")
        info.append("Flask mungkin membuat file database baru yang kosong.")
        
    return "<br>".join(info)

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
