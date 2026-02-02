import discord
from discord.ext import commands
import asyncio
import random
import json
import os

def load_config():
    try:
        if not os.path.exists('config.json'):
            print("❌ File config.json tidak ditemukan!")
            return None
        with open('config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Gagal baca config.json: {e}")
        return None

config_awal = load_config()
if not config_awal:
    input("Tekan Enter untuk keluar...")
    exit()

TOKEN = config_awal['token']
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

    targets = load_config()['targets']
    for t in targets:
        bot.loop.create_task(iklan_otomatis(t['id']))

bot.run(TOKEN)