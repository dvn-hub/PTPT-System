import discord
from discord.ext import commands
import asyncio
import random
import json
import os
import sys
from dotenv import load_dotenv

# Setup Base Directory (Agar file dibaca dari folder bot_iklan, bukan folder root)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, 'config.json')

# Load .env
# Cari .env di beberapa lokasi kemungkinan
possible_env_paths = [
    os.path.join(BASE_DIR, '..', '.env'),              # Root folder (Standard)
    os.path.join(BASE_DIR, '..', 'bot_script', '.env') # Folder bot_script (Alternative)
]

for env_path in possible_env_paths:
    if os.path.exists(env_path):
        load_dotenv(env_path, override=True)
        print(f"DEBUG: Loaded .env from {env_path}")
        break

def load_config():
    try:
        if not os.path.exists(CONFIG_PATH):
            print(f"❌ File config.json tidak ditemukan di: {CONFIG_PATH}")
            return None
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Gagal baca config.json: {e}")
        return None

config_awal = load_config()
if not config_awal:
    print("❌ Config gagal dimuat. Keluar.")
    sys.exit(1)

# Prioritas Token: .env (ADS_TOKEN) -> .env (TOKEN) -> config.json
# Pastikan token tidak hardcoded agar aman saat push ke GitHub
TOKEN = os.getenv('ADS_TOKEN') or config_awal.get('token')

if TOKEN:
    TOKEN = TOKEN.strip() # Hapus spasi/newline di awal/akhir
    # Hapus tanda kutip jika ada (fix common .env issue)
    if TOKEN.startswith('"') and TOKEN.endswith('"'): TOKEN = TOKEN[1:-1]
    if TOKEN.startswith("'") and TOKEN.endswith("'"): TOKEN = TOKEN[1:-1]
    print(f"DEBUG: Token loaded (Length: {len(TOKEN)})")

if not TOKEN or "TOKEN_DISINI" in TOKEN:
    print(f"❌ Token tidak ditemukan atau masih default ('{TOKEN}'). Cek .env (ADS_TOKEN) atau config.json")
    sys.exit(1)

print(f"DEBUG: Discord Library Version: {discord.__version__}")

if hasattr(discord, 'Intents'):
    intents = discord.Intents.default()
    intents.message_content = True
    bot = commands.Bot(command_prefix=".", self_bot=True, intents=intents, chunk_guilds_at_startup=False)
else:
    print("⚠️ Warning: discord.Intents not found. Using legacy bot initialization.")
    bot = commands.Bot(command_prefix=".", self_bot=True)

has_started = False

async def iklan_otomatis(target_id):
    await bot.wait_until_ready()
    await asyncio.sleep(random.randint(5, 15))

    print(f"✅ Task dimulai untuk ID: {target_id}")

    while not bot.is_closed():
        try:
            # 1. BACA CONFIG TERBARU
            data = load_config()
            if not data:
                await asyncio.sleep(60)
                continue
            
            # 2. CARI DATA TARGET
            target_data = None
            for item in data['targets']:
                if item['id'] == target_id:
                    target_data = item
                    break
            
            if not target_data:
                print(f"❓ ID {target_id} dihapus. Stop.")
                break 

            # 3. PILIH PESAN
            if "pesan_khusus" in target_data:
                isi_pesan = "\n".join(target_data['pesan_khusus'])
                tipe_pesan = "KHUSUS"
            else:
                isi_pesan = "\n".join(data['pesan_default'])
                tipe_pesan = "UMUM"

            # 4. KIRIM PESAN
            channel = bot.get_channel(target_id)
            if not channel:
                print(f"❌ Channel {target_id} ({target_data.get('nama')}) tidak terdeteksi.")
                await asyncio.sleep(60)
                continue

            print(f"🚀 [{tipe_pesan}] Mengirim ke #{channel.name} ({target_data.get('nama')})...")
            await channel.send(isi_pesan)

            # 5. LOGIC WAKTU (BARU)
            delay = channel.slowmode_delay
            tunggu = delay + random.randint(15, 60)
            
            # Ambil batas minimal dari config (kalau gak ada, default 3600/1 jam)
            batas_min = target_data.get('delay_min', 3600)

            if tunggu < batas_min:
                tunggu = batas_min

            print(f"⏳ #{channel.name}: Slowmode {delay}s. Tidur {tunggu}s (Min: {batas_min}s)...")
            await asyncio.sleep(tunggu)

        except discord.Forbidden:
            print(f"⛔ DITOLAK di channel {target_id}. Cek Izin!")
            await asyncio.sleep(3600)
        except Exception as e:
            print(f"⚠️ Error di {target_id}: {e}")
            await asyncio.sleep(600)

@bot.event
async def on_ready():
    global has_started
    print("---------------------------------------")
    print(f"✅ LOGIN SUKSES: {bot.user.name}")
    print(f"📂 Mode: Custom Delay Per Channel")
    print("---------------------------------------")
    
    if has_started:
        return
    has_started = True

    data = load_config()
    if data and 'targets' in data:
        for t in data['targets']:
            bot.loop.create_task(iklan_otomatis(t['id']))
            # Tambahkan jeda 5-10 detik antar task agar tidak kena Rate Limit saat startup
            await asyncio.sleep(random.randint(5, 10))
    else:
        print("❌ Gagal memuat target. Cek config.json")

try:
    bot.run(TOKEN)
except discord.errors.LoginFailure:
    print("\n❌ FATAL ERROR: Token Ditolak Discord (401 Unauthorized).")
    print("👉 Token akun user (self-bot) sering expired/reset otomatis oleh Discord jika bot sering restart.")
    print("👉 SOLUSI: Ambil token BARU dari browser (Inspect Element) dan ganti di .env VPS.\n")
except Exception as e:
    print(f"❌ Error Runtime: {e}")