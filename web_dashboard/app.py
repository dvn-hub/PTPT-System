from flask import Flask, render_template, request, redirect, session, url_for, g, flash
import os, requests, json, secrets
from datetime import datetime
import concurrent.futures
import sys
# Add parent directory to path to import modules from root
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..'))
from models import db, UserTicket, UserSlot, Patungan, PaymentRecord, CustomCommand, ActionQueue, BotSettings
from api import WinterAPI, process_data

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
FILE_BROADCASTS = os.path.join(PARENT_DIR, 'bot_iklan', 'broadcasts.json')
FILE_CONFIG_IKLAN = os.path.join(PARENT_DIR, 'bot_iklan', 'config.json')

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

def load_broadcasts():
    templates = []
    
    # 1. Cek file dedicated broadcasts.json (Prioritas Utama - Data yang sudah disave user)
    if os.path.exists(FILE_BROADCASTS):
        try:
            with open(FILE_BROADCASTS, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception as e:
            print(f"❌ Error loading broadcasts.json: {e}")

    # 2. Jika kosong, coba import dari config.json (Auto-Import dari Bot Iklan)
    if os.path.exists(FILE_CONFIG_IKLAN):
        try:
            with open(FILE_CONFIG_IKLAN, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
                
                # Helper normalize
                def normalize(item, idx_or_key):
                    if not isinstance(item, (str, dict)): return None
                    if isinstance(item, (bool, int, float)): return None
                    if isinstance(item, str) and len(item) < 5: return None
                    
                    template = {
                        "id": str(idx_or_key),
                        "name": f"Imported {idx_or_key}",
                        "title": "📢 Broadcast",
                        "description": "",
                        "color": "#3498db",
                        "channels": "",
                        "image_url": ""
                    }
                    
                    if isinstance(item, str):
                        template["description"] = item
                    elif isinstance(item, dict):
                        if 'id' in item: template['id'] = str(item['id'])
                        if 'name' in item: template['name'] = item['name']
                        if 'title' in item: template['title'] = item['title']
                        if 'color' in item: template['color'] = item['color']
                        if 'channels' in item: template['channels'] = item['channels']
                        if 'image' in item: template['image_url'] = item['image']
                        if 'image_url' in item: template['image_url'] = item['image_url']
                        
                        for k in ['description', 'content', 'text', 'body', 'message']:
                            if k in item and item[k]:
                                template['description'] = item[k]
                                break
                        
                        if 'embed' in item and isinstance(item['embed'], dict):
                            embed = item['embed']
                            if template['title'] == "📢 Broadcast": template['title'] = embed.get('title', "📢 Broadcast")
                            if not template['description']: template['description'] = embed.get('description', '')
                            if template['color'] == "#3498db":
                                col = embed.get('color')
                                if col:
                                    try:
                                        if isinstance(col, int): template['color'] = f"#{col:06x}"
                                        else: template['color'] = str(col)
                                    except: pass
                            if not template['image_url']:
                                img = embed.get('image')
                                if isinstance(img, dict): template['image_url'] = img.get('url', '')
                                elif isinstance(img, str): template['image_url'] = img

                    if not template['description'] and not template['image_url'] and template['title'] == "📢 Broadcast":
                        return None
                    return template

                # Extraction Logic
                if isinstance(data, list):
                    for i, item in enumerate(data):
                        norm = normalize(item, i)
                        if norm: templates.append(norm)
                elif isinstance(data, dict):
                    # Check specific keys first
                    target_list = None
                    for key in ['messages', 'broadcasts', 'ads', 'promos', 'embeds']:
                        if key in data and isinstance(data[key], list):
                            target_list = data[key]
                            break
                    
                    if target_list:
                        for i, item in enumerate(target_list):
                            norm = normalize(item, i)
                            if norm: templates.append(norm)
                    else:
                        # Iterate values
                        for k, v in data.items():
                            norm = normalize(v, k)
                            if norm: templates.append(norm)
                            
        except Exception as e:
            print(f"❌ Error importing from config.json: {e}")

    # Fallback: Ambil dari pesan.txt jika json kosong/gagal
    if not templates and os.path.exists(FILE_PROMO):
        try:
            with open(FILE_PROMO, 'r', encoding='utf-8-sig') as f:
                content = f.read().strip()
                if content:
                    templates.append({
                        "id": "legacy_promo",
                        "name": "Legacy Promo (pesan.txt)",
                        "channels": "",
                        "title": "📢 BROADCAST",
                        "description": content,
                        "image_url": "",
                        "color": "#3498db"
                    })
        except: pass
            
    return templates

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
        pending = PaymentRecord.query.filter_by(payment_status='pending').all()
        
        # Ambil daftar custom commands
        commands = CustomCommand.query.order_by(CustomCommand.created_at.desc()).all()

        # Hitung Omzet Real (Total uang masuk status PAID)
        # FIX: Filter angka tidak masuk akal (> 1 Triliun) agar ID transaksi tidak terhitung
        omzet = db.session.query(db.func.sum(PaymentRecord.paid_amount)).filter(
            PaymentRecord.payment_status.in_(['PAID', 'verified']),
            PaymentRecord.paid_amount < 1000000000000 
        ).scalar() or 0

        # Hitung Statistik untuk Chart
        paid_count = PaymentRecord.query.filter(PaymentRecord.payment_status.in_(['PAID', 'verified'])).count()
        rejected_count = PaymentRecord.query.filter(PaymentRecord.payment_status.in_(['REJECTED', 'rejected'])).count()
        
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
    slot_number = request.form.get('slot_number')
    
    new_action = ActionQueue(
        action_type='remove_member',
        payload=json.dumps({"product_name": product_name, "slot_number": slot_number}),
        created_by=session['username']
    )
    db.session.add(new_action)
    db.session.commit()
    
    flash(f"Perintah Kick Slot {slot_number} dari {product_name} dikirim!", "warning")
    return redirect(url_for('admin_actions'))

@app.route('/admin/get_members/<product_name>')
def get_members(product_name):
    if not session.get('logged_in'): return "Unauthorized", 403
    slots = UserSlot.query.filter_by(patungan_version=product_name).filter(UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])).all()
    data = [{"username": s.game_username, "slot": s.slot_number} for s in slots]
    return json.dumps(data)

@app.route('/admin/get_patungan_slots/<product_name>')
def get_patungan_slots(product_name):
    if not session.get('logged_in'): return "Unauthorized", 403
    
    # Ambil semua slot (termasuk yang kicked/inactive jika masih ada di DB)
    slots = UserSlot.query.filter_by(patungan_version=product_name).order_by(UserSlot.slot_number).all()
    
    data = []
    for s in slots:
        # Hanya tampilkan slot yang valid (nomor > 0)
        if s.slot_number > 0:
            data.append({
                "slot_number": s.slot_number,
                "game_username": s.game_username,
                "display_name": s.display_name,
                "status": s.slot_status
            })
    return json.dumps(data)

@app.route('/slots')
def manage_slots():
    if not session.get('logged_in'): return redirect('/')
    # Ambil semua patungan aktif
    # Filter stock items (total_slots 9999) agar tidak muncul di kelola slot karena approvalnya di Home
    patungans = Patungan.query.filter(Patungan.status != 'archived', Patungan.total_slots < 9000).all()
    return render_template('manage_slots.html', admin=session, patungans=patungans)

@app.route('/commands')
def custom_commands():
    if not session.get('logged_in'): return redirect('/')
    
    # Ambil Custom Commands
    commands = CustomCommand.query.order_by(CustomCommand.created_at.desc()).all()
    
    # Ambil System Settings (.ps, .qr)
    ps_link = BotSettings.query.get('private_server_link')
    qris_url = BotSettings.query.get('qris_image_url')
    
    settings = {
        'ps_link': ps_link.value if ps_link else '',
        'qris_url': qris_url.value if qris_url else ''
    }
    
    return render_template('commands.html', admin=session, commands=commands, settings=settings)

@app.route('/save_settings', methods=['POST'])
def save_settings():
    if not session.get('logged_in'): return redirect('/')
    
    ps_link = request.form.get('ps_link')
    qris_url = request.form.get('qris_url')
    
    # Helper function to save/update
    def save_key(key, val):
        setting = BotSettings.query.get(key)
        if not setting: db.session.add(BotSettings(key=key, value=val))
        else: setting.value = val
    
    save_key('private_server_link', ps_link)
    save_key('qris_image_url', qris_url)
    db.session.commit()
    
    flash("System Settings (.ps & .qr) berhasil diupdate!", "success")
    return redirect(url_for('custom_commands'))

@app.route('/add_command', methods=['POST'])
def add_command():
    if not session.get('logged_in'): return redirect('/')
    name = request.form.get('name').lower().strip() # Force lowercase & strip
    response = request.form.get('response')
    
    # Cek duplikat
    existing = CustomCommand.query.filter_by(name=name).first()
    if existing:
        flash(f"Command !{name} sudah ada!", "warning")
        return redirect(url_for('custom_commands'))

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
    
    # Ambil data transaksi yang sudah verified/paid
    # Urutkan dari yang terbaru
    payments = PaymentRecord.query.filter(
        PaymentRecord.payment_status.in_(['verified', 'paid'])
    ).order_by(PaymentRecord.verified_at.desc()).all()
    
    # Grouping by Date (YYYY-MM-DD)
    history = {}
    for p in payments:
        try:
            # Skip orphaned payments (slot deleted)
            if not p.slot or not p.slot.ticket: continue

            # Fallback jika verified_at kosong (pakai detected_at atau now)
            dt = p.verified_at or p.detected_at or datetime.now()
            
            # Safety check: Konversi string ke datetime jika SQLite mengembalikan string
            if isinstance(dt, str):
                try:
                    dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S.%f')
                except ValueError:
                    try:
                        dt = datetime.strptime(dt, '%Y-%m-%d %H:%M:%S')
                    except ValueError:
                        dt = datetime.now()

            date_key = dt.strftime('%Y-%m-%d')
            
            if date_key not in history:
                history[date_key] = {'total_omzet': 0, 'items': []}
            
            history[date_key]['items'].append(p)
            
            # Safe addition (handle string/None)
            amount = int(p.paid_amount) if p.paid_amount else 0
            history[date_key]['total_omzet'] += amount
        except Exception as e:
            print(f"Skipping corrupt payment record {p.id}: {e}")
            continue
        
    return render_template('transactions.html', admin=session, history=history)

@app.route('/broadcast')
def broadcast():
    if not session.get('logged_in'): return redirect('/')
    templates = load_broadcasts()
    return render_template('broadcast.html', admin=session, templates=templates)

@app.route('/save_broadcast', methods=['POST'])
def save_broadcast():
    if not session.get('logged_in'): return redirect('/')
    
    # Pastikan folder bot_iklan ada
    os.makedirs(os.path.dirname(FILE_BROADCASTS), exist_ok=True)
    
    template_id = request.form.get('template_id') or secrets.token_hex(4)
    data = {
        'id': template_id,
        'name': request.form.get('name'),
        'channels': request.form.get('channels'),
        'title': request.form.get('title'),
        'description': request.form.get('description'),
        'image_url': request.form.get('image_url'),
        'color': request.form.get('color', '#3498db')
    }
    
    templates = load_broadcasts()
    # Update existing or add new
    updated = False
    for i, t in enumerate(templates):
        if t['id'] == template_id:
            templates[i] = data
            updated = True
            break
    if not updated:
        templates.append(data)
        
    with open(FILE_BROADCASTS, 'w', encoding='utf-8') as f:
        json.dump(templates, f, indent=4)
        
    flash("Template broadcast berhasil disimpan!", "success")
    return redirect(url_for('broadcast'))

@app.route('/delete_broadcast/<id>', methods=['POST'])
def delete_broadcast(id):
    if not session.get('logged_in'): return redirect('/')
    templates = load_broadcasts()
    templates = [t for t in templates if t['id'] != id]
    with open(FILE_BROADCASTS, 'w', encoding='utf-8') as f:
        json.dump(templates, f, indent=4)
    flash("Template berhasil dihapus.", "success")
    return redirect(url_for('broadcast'))

@app.route('/send_broadcast/<id>', methods=['POST'])
def send_broadcast(id):
    if not session.get('logged_in'): return redirect('/')
    templates = load_broadcasts()
    template = next((t for t in templates if t['id'] == id), None)
    
    if template:
        payload = {
            'channels': template['channels'],
            'embed': {
                'title': template['title'],
                'description': template['description'],
                'image': template['image_url'],
                'color': template['color'].replace('#', '0x')
            }
        }
        
        new_action = ActionQueue(
            action_type='broadcast',
            payload=json.dumps(payload),
            created_by=session['username']
        )
        db.session.add(new_action)
        db.session.commit()
        flash(f"Broadcast '{template['name']}' sedang dikirim oleh bot!", "success")
    else:
        flash("Template tidak ditemukan.", "danger")
        
    return redirect(url_for('broadcast'))

@app.route('/stock')
def stock_panel():
    if not session.get('logged_in'): return redirect('/')
    
    data = None
    try:
        print("DEBUG: Fetching stock data from API...")
        api = WinterAPI()
        
        # Use ThreadPoolExecutor to add timeout (Fix Stuck Loading)
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(api.fetch_data)
            try:
                raw_data = future.result(timeout=25) # Increased timeout to 25s
                print(f"DEBUG: API Response received. Data: {'Yes' if raw_data else 'No'}")
                if raw_data:
                    data = process_data(raw_data)
                    
                    # Sort secrets for display (High Tier)
                    if 'secrets' in data:
                        items = []
                        for name, info in data['secrets'].items(): items.append((name, info))
                        normals = [x for x in items if not x[1]['is_mutation']]
                        mutations = [x for x in items if x[1]['is_mutation']]
                        normals.sort(key=lambda x: x[0])
                        mutations.sort(key=lambda x: x[0])
                        data['sorted_secrets'] = normals + mutations
            except concurrent.futures.TimeoutError:
                print("❌ API Request Timed Out")
                flash("Gagal mengambil data stock: Waktu habis (API WinterCode lambat atau data terlalu banyak). Silakan refresh halaman.", "danger")
            except Exception as e:
                print(f"❌ API Error: {e}")
                flash(f"Gagal mengambil data stock: {str(e)}", "danger")
                
    except Exception as e:
        print(f"Error fetching stock: {e}")
        flash(f"Gagal mengambil data stock: {str(e)}", "danger")
        
    return render_template('stock_panel.html', admin=session, data=data)

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
        # FIX: Jika paid_amount 0 (OCR gagal), set ke expected_amount saat approve
        if payment.paid_amount == 0:
            payment.paid_amount = payment.expected_amount
            payment.amount_difference = 0
            
        payment.payment_status = 'verified'
        
        # Update slot status juga agar user terhitung PAID di bot
        if payment.slot:
            payment.slot.slot_status = 'paid'
            payment.slot.payment_verified = True
            payment.slot.verified_by = session.get('username', 'Web Admin')
            payment.slot.verified_at = datetime.now()
            
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
        payment.payment_status = 'rejected'
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
