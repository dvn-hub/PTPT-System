import discord
import sys
import os
import json
import io
import asyncio
import requests
import math
import re
from discord.ext import commands
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

# ==========================================
# 1. KONFIGURASI UMUM
# ==========================================

# Fix Encoding untuk VPS/Linux agar tidak error saat print emoji/nama user
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', line_buffering=True)

# Setup Base Directory agar file bisa dibaca dari mana saja
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(BASE_DIR, '..', '.env')

print(f"DEBUG: Loading .env from {ENV_PATH}")
if os.path.exists(ENV_PATH):
    print("DEBUG: .env file found!")
else:
    print("DEBUG: .env file NOT found!")

load_dotenv(ENV_PATH, override=True) # Coba load dari folder parent (root)
load_dotenv(override=True) # Fallback ke CWD

# --- MANUAL FALLBACK FOR CHANNEL_ID ---
# Kadang load_dotenv gagal jika ada karakter aneh atau format tidak standar
if not os.getenv('CHANNEL_ID') and os.path.exists(ENV_PATH):
    print("DEBUG: CHANNEL_ID not found via load_dotenv. Attempting manual parse...")
    try:
        with open(ENV_PATH, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()
            print(f"DEBUG: Read {len(lines)} lines from .env")
            for line in lines:
                # Hapus whitespace dan comment
                clean_line = line.strip()
                if '=' in clean_line:
                    key, val = clean_line.split('=', 1)
                    if key.strip() == 'CHANNEL_ID':
                        val = val.strip().strip("'").strip('"').split('#')[0].strip()
                        os.environ['CHANNEL_ID'] = val
                        print(f"DEBUG: Manually loaded CHANNEL_ID: {val}")
                        break
    except Exception as e:
        print(f"DEBUG: Manual parse failed: {e}")

TOKEN = os.getenv('TOKEN') or os.getenv('DISCORD_TOKEN')

NONE_STR = 'None'


try:
    raw_id = os.getenv('CHANNEL_ID')
    print(f"DEBUG: Raw CHANNEL_ID from .env: '{raw_id}'")

    if raw_id:
        cleaned_id = raw_id.strip()
        if cleaned_id.isdigit():
           CHANNEL_ID = int(cleaned_id)
           print(f"DEBUG: Parsed CHANNEL_ID: {CHANNEL_ID}")
        elif cleaned_id.upper() == NONE_STR.upper():
             print(f"❌ Error: CHANNEL_ID is explicitly set to '{raw_id}' in .env. It should be a numerical channel ID.")
             CHANNEL_ID = 0
        else:
           print(f"❌ Error: CHANNEL_ID is not a digit: '{cleaned_id}'")
           CHANNEL_ID = 0
    else:
        print("❌ Error: CHANNEL_ID is not set in .env. Please set it to a numerical channel ID.")
        CHANNEL_ID = 0
except Exception as e:
    print(f"DEBUG: Error parsing CHANNEL_ID: {e}")
    CHANNEL_ID = 0

# --- KONFIGURASI KATALOG (ICE BLUE THEME) ---
WIDTH = 1080
PADDING = 24
COL_BG    = (11, 19, 32)
COL_CARD  = (17, 27, 46)
COL_NEON  = (94, 235, 255)
COL_TEXT  = (234, 251, 255)
COL_LINE  = (46, 232, 255)

# --- SETUP BOT ---
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# ==========================================
# 2. FUNGSI HELPER (KATALOG & DATABASE)
# ==========================================

# --- A. LOAD DATABASE SCRIPT ---
def load_scripts():
    scripts = {}
    path = os.path.join(BASE_DIR, 'scripts.json')
    if os.path.exists(path):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, dict):
                    scripts = data
                else:
                    print("⚠️ scripts.json format salah (List), auto-reset ke Dictionary.")
                    scripts = {}
        except Exception as e:
            print(f"❌ Error loading scripts.json: {e}")

    # Hardcoded Webhooks (Requested Update)
    hardcoded = {
        "WEBHOOK_REJOIN": "https://discordapp.com/api/webhooks/1471138893599477996/P26JJx9PCpz9K11n5_NZepDg07fjeu56J84f9vwzweWU4aTwQH8UEqikHWioKtxak4GU",
        "WEBHOOK_EXPIRED": "https://discordapp.com/api/webhooks/1471139017792815247/I06eihIpk8USa91MnwJoJXW-3MOKaDPFC5-FBy87w4uOAcg7tYEICYYgfPUyKf0m5um3",
        
        # --- DEFAULT SCRIPTS (Biar gak error kalau JSON kosong) ---
        "DVN_ACCEPT_GIFT": "-- Script DVN Accept Gift belum di-set di Dashboard.\nprint('DVN Accept Gift Placeholder')",
        "DVN_FISHIT": "loadstring(game:HttpGet('https://raw.githubusercontent.com/Example/Script/main/FishIt.lua'))()",
        "DVN_LOGGER": "-- Script Logger belum di-set.",
        "DVN_AUTOEXE": "-- Script Auto Exe belum di-set.",
        "DVN_LOG_FM": "-- Script Log FM belum di-set.",
        "DVN_AUTO_GIFT": "-- Script Auto Gift belum di-set.",
        "WINTER_KAITUN": "loadstring(game:HttpGet('https://raw.githubusercontent.com/Winter/Hub/main/Kaitun.lua'))()",
        "WINTER_DASH": "-- Winter Dashboard belum di-set.",
        "ATOMIC": "loadstring(game:HttpGet('https://atomic-hub.net/script'))()",
        "SERAPHIN": "-- Seraphin Script belum di-set.",
        "LIME": "-- Lime Script belum di-set.",
        "CHLOE": "-- Chloe Script belum di-set.",
        "WEBHOOK_DVN": "https://discord.com/api/webhooks/...",
        "WEBHOOK_FISHIT": "https://discord.com/api/webhooks/...",
        "WEBHOOK_MONITOR": "https://discord.com/api/webhooks/..."
    }
    
    for k, v in hardcoded.items():
        if k not in scripts:
            scripts[k] = v
            
    # Migration: Kaeru -> Monitor
    if "WEBHOOK_MONITOR" not in scripts and "WEBHOOK_KAERU" in scripts:
        scripts["WEBHOOK_MONITOR"] = scripts["WEBHOOK_KAERU"]
        
    return scripts

# --- B. FUNGSI IMAGE PROCESSING (KATALOG) ---
def format_k(n):
    try:
        val = float(n) / 1000
        return f"{int(val)}K" if val.is_integer() else f"{val}K"
    except:
        return str(n)

def load_img(url, size):
    r = requests.get(url, timeout=10)
    img = Image.open(io.BytesIO(r.content)).convert("RGBA")
    img.thumbnail(size)
    return img

def render_row(img, draw, y, row, font_name, font_price, font_stock):
    mode = row["mode"]
    items = row["items"]
    gap = 16
    cols = mode
    card_w = (WIDTH - PADDING*2 - gap*(cols-1)) // cols
    card_h = 500

    for i, p in enumerate(items):
        x = PADDING + i*(card_w + gap)
        draw.rounded_rectangle([x, y, x+card_w, y+card_h], radius=18, fill=COL_CARD)

        # Gambar Produk
        try:
            pi = load_img(p["img"], (card_w-30, 220))
            ix = x + (card_w - pi.width) // 2
            iy = y + 20
            img.paste(pi, (ix, iy), pi)
        except:
            pass # Skip jika gambar gagal load

        # Nama Produk (Word Wrap)
        max_name_width = card_w - 40
        original_name = p['nama']
        lines = []
        if font_name.getlength(original_name) <= max_name_width:
            lines.append(original_name)
        else:
            words = original_name.split(' ')
            line1 = ""
            line2_words = []
            for word in words:
                if font_name.getlength(line1 + word + " ") < max_name_width:
                    line1 += word + " "
                else:
                    line2_words.append(word)
            lines.append(line1.strip())
            if line2_words:
                line2 = " ".join(line2_words)
                while font_name.getlength(line2 + '...') > max_name_width and len(line2) > 0:
                    line2 = line2[:-1]
                lines.append(line2 + "..." if len(line2_words) > 3 else line2)

        name_y_start = y + 265
        line_height = font_name.getbbox('A')[3]
        for i, line in enumerate(lines[:2]): # Max 2 baris
            line_w = draw.textbbox((0,0), line, font=font_name)[2]
            draw.text((x + (card_w - line_w) / 2, name_y_start + (i * (line_height + 8))), line, fill=COL_TEXT, font=font_name)

        # Harga
        price_y = y + 380
        price_text = f"IDR {format_k(p['harga'])}"
        price_w = draw.textbbox((0, 0), price_text, font=font_price)[2]
        draw.text((x + (card_w - price_w) / 2, price_y), price_text, fill=COL_NEON, font=font_price)

        # Stock
        stock_y = y + 440
        stock_text = f"Stock: {p['stock']}"
        stock_w = draw.textbbox((0, 0), stock_text, font=font_stock)[2]
        draw.text((x + (card_w - stock_w) / 2, stock_y), stock_text, fill=(180, 180, 180), font=font_stock)

        # Badge HABIS
        if int(p["stock"]) <= 0:
            badge_w, badge_h = 100, 34
            bx, by = x + card_w - 30 - badge_w, y + 20
            draw.rounded_rectangle([bx, by, bx+badge_w, by+badge_h], radius=8, fill=(220, 50, 50))
            draw.text((bx + (badge_w - 55)/2, by + 2), "HABIS", fill="white", font=font_stock)

    return y + card_h + 24

def generate_catalog(store, rows):
    header_h = 250
    footer_h = 90
    temp_height = header_h + footer_h + len(rows)*540
    img = Image.new("RGB", (WIDTH, temp_height), COL_BG)
    draw = ImageDraw.Draw(img)

    try:
        font_path = os.path.join(BASE_DIR, "fonts", "arialbd.ttf")
        f_title = ImageFont.truetype(font_path, 60)
        f_subtitle = ImageFont.truetype(font_path, 24)
        f_name = ImageFont.truetype(font_path, 40)
        f_price = ImageFont.truetype(font_path, 45)
        f_stock = ImageFont.truetype(font_path, 28)
        f_footer = ImageFont.truetype(font_path, 32)
    except OSError:
        print("⚠️ Font tidak ditemukan, menggunakan default.")
        f_title = f_subtitle = f_name = f_price = f_stock = f_footer = ImageFont.load_default()

    # Header
    logo_path = os.path.join(BASE_DIR, "logo.png")
    if os.path.exists(logo_path):
        logo = Image.open(logo_path).resize((180, 180))
        img.paste(logo, (PADDING, 34), logo if logo.mode=="RGBA" else None)
    else:
        draw.rectangle([PADDING, 34, PADDING+180, 34+180], fill=COL_NEON)

    text_x = PADDING + 180 + 30
    draw.text((text_x, 60), "OFFICIAL CATALOG - AMANAH * CEPAT * MURAH", fill=COL_NEON, font=f_subtitle)
    draw.text((text_x, 90), store, fill=COL_TEXT, font=f_title)
    draw.line((PADDING, header_h-12, WIDTH-PADDING, header_h-12), fill=COL_LINE, width=2)

    y = header_h + PADDING
    for r in rows:
        y = render_row(img, draw, y, r, f_name, f_price, f_stock)

    final_h = y + footer_h
    img = img.crop((0,0,WIDTH,final_h))
    draw = ImageDraw.Draw(img)

    # Footer
    fy = final_h - footer_h
    draw.line((PADDING, fy, WIDTH-PADDING, fy), fill=COL_LINE, width=2)
    t1 = "🛒 Order via Discord • DVN COMMUNITY • 🍀PTPTX8🍀 • 🎁GIG🎁"
    t2 = "SIAP REKBER MIDMAN TERPERCAYA"
    w1 = draw.textbbox((0,0), t1, font=f_footer)[2]
    w2 = draw.textbbox((0,0), t2, font=f_footer)[2]
    draw.text(((WIDTH - w1) / 2, fy+20), t1, fill=COL_NEON, font=f_footer)
    draw.text(((WIDTH - w2) / 2, fy+55), t2, fill=COL_TEXT, font=f_footer)

    out = "catalog_result.jpg"
    img.save(out, "JPEG", quality=95, subsampling=0)
    return out

# ==========================================
# 3. UI KELAS (DROPDOWN & VIEW)
# ==========================================
class ScriptDropdown(discord.ui.Select):
    def __init__(self):
        options = [
            # --- DVN SERIES ---
            discord.SelectOption(label="DVN Fish It", value="DVN_FISHIT", description="Auto Farm Fish It Terbaru", emoji="🦈"),
            discord.SelectOption(label="DVN Logger", value="DVN_LOGGER", description="Logger Pro Feature", emoji="📝"),
            discord.SelectOption(label="DVN Log Caught AutoExe", value="DVN_AUTOEXE", description="Script Auto Execute", emoji="⚙️"),
            discord.SelectOption(label="DVN Log FM Auto Exe", value="DVN_LOG_FM", description="Auto Execute Log FM", emoji="⚙️"),
            discord.SelectOption(label="DVN Accept Gift", value="DVN_ACCEPT_GIFT", description="Auto Accept Gift", emoji="🎁"),
            discord.SelectOption(label="DVN Auto Gift", value="DVN_AUTO_GIFT", description="Auto Send Gift", emoji="🎁"),
            
            # --- WINTER SERIES ---
            discord.SelectOption(label="Winter Kaitun", value="WINTER_KAITUN", description="Winter Hub Kaitun", emoji="❄️"),
            discord.SelectOption(label="Winter Dashboard", value="WINTER_DASH", description="Winter Dashboard", emoji="📊"),

            # --- OTHER HUBS ---
            discord.SelectOption(label="Atomic Hub", value="ATOMIC", description="Atomic Script", emoji="⚛️"),
            discord.SelectOption(label="Seraphin Hub", value="SERAPHIN", description="Seraphin Script", emoji="🌑"),
            discord.SelectOption(label="Lime Hub", value="LIME", description="Lime Script", emoji="🟢"),
            discord.SelectOption(label="Chloe Hub", value="CHLOE", description="Chloe Script", emoji="🌸"),

            # --- WEBHOOKS ---
            discord.SelectOption(label="Webhook DVN", value="WEBHOOK_DVN", description="Link Webhook DVN", emoji="🔗"),
            discord.SelectOption(label="Webhook Fish It", value="WEBHOOK_FISHIT", description="Link Webhook Fish It", emoji="🔗"),
            discord.SelectOption(label="Webhook Monitor", value="WEBHOOK_MONITOR", description="Link Webhook Monitor", emoji="🔗"),
            discord.SelectOption(label="Webhook Rejoin Log", value="WEBHOOK_REJOIN", description="Link Webhook Rejoin Log", emoji="🔗"),
            discord.SelectOption(label="Webhook Key Expired", value="WEBHOOK_EXPIRED", description="Link Webhook Key Expired", emoji="🔗"),
        ]
        
        super().__init__(
            placeholder="👉 Klik di sini untuk memilih Script...", 
            min_values=1, 
            max_values=1, 
            options=options,
            custom_id="dropdown_script_menu" 
        )

    async def callback(self, interaction: discord.Interaction):
        try:
            # Defer interaction agar tidak "Interaction Failed"
            await interaction.response.defer(ephemeral=True, thinking=True)
            
            try:
                print(f"DEBUG: Interaction received from {interaction.user.name} for {self.values[0]}")
            except:
                print(f"DEBUG: Interaction received (Name Encode Error) for {self.values[0]}")

            key_name = self.values[0]
            scripts = load_scripts()
            script_content = scripts.get(key_name)
            
            selected_option = next((opt for opt in self.options if opt.value == key_name), None)
            display_name = selected_option.label if selected_option else key_name

            # --- KIRIM DATA ---
            if not script_content:
                await interaction.followup.send(f"❌ Script **{display_name}** tidak ditemukan di database.", ephemeral=True)
                return

            if len(script_content) > 1950:
                file_data = io.BytesIO(script_content.encode('utf-8'))
                file = discord.File(fp=file_data, filename=f"{display_name}.lua")
                await interaction.followup.send(content=f"📦 **{display_name}**", file=file, ephemeral=True)
            else:
                embed = discord.Embed(title=f"📜 {display_name}", description=f"```lua\n{script_content}\n```", color=0x00FF00)
                await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception as e:
            try:
                print(f"❌ Error in callback: {e}")
            except:
                pass
            try:
                await interaction.followup.send(f"❌ Terjadi kesalahan: {e}", ephemeral=True)
            except:
                pass

class ScriptControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(ScriptDropdown())

# ==========================================
# 4. COMMANDS & EVENTS
# ==========================================

# --- A. COMMAND KATALOG ---
@bot.command()
async def katalog(ctx, *, args):
    """
    Format: !katalog Nama Store | [Mode] Data...
    """
    await ctx.send("🎨 **Sedang memproses gambar...** Mohon tunggu sebentar.")
    try:
        store, body = args.split("|", 1)
        blocks = body.strip().split("\n\n")
        rows = []
        for b in blocks:
            lines = [l.strip() for l in b.splitlines() if l.strip()]
            mode = int(lines[0].replace("[","").replace("]",""))
            items = []
            for l in lines[1:]:
                nama, harga, stock, url = [x.strip() for x in l.split(",")]
                items.append({"nama": nama, "harga": harga, "stock": stock, "img": url})
            rows.append({"mode": mode, "items": items})
    except Exception as e:
        return await ctx.send(f"❌ Format salah: {e}")

    # Jalankan generate_catalog di thread terpisah agar tidak memblokir bot
    loop = asyncio.get_running_loop()
    path = await loop.run_in_executor(None, generate_catalog, store.strip(), rows)
    
    await ctx.send("✅ **Selesai!** Ketik ID Channel tujuan (atau `here`).")

    def check(m): return m.author == ctx.author and m.channel == ctx.channel
    target_channel = ctx.channel
    try:
        msg = await bot.wait_for("message", check=check, timeout=30.0)
        content = msg.content.strip()
        if content.lower() != "here" and content.isdigit():
            c = bot.get_channel(int(content))
            if c: target_channel = c
            else: await ctx.send("⚠️ Channel tidak ketemu, kirim disini.")
    except asyncio.TimeoutError:
        await ctx.send("⏱️ Kelamaan bang, kirim disini aja.")

    await target_channel.send(file=discord.File(path))
    if target_channel != ctx.channel:
        await ctx.send(f"✅ Terkirim ke {target_channel.mention}")

# --- B. EVENT ON READY (AUTO SEND PANEL) ---
@bot.event
async def on_ready():
    print(f"🔥 Login Berhasil: {bot.user}")
    
    # Check scripts.json on startup
    script_path = os.path.join(BASE_DIR, 'scripts.json')
    if os.path.exists(script_path):
        try:
            with open(script_path, 'r', encoding='utf-8') as f:
                json.load(f)
            print(f"✅ scripts.json loaded successfully from {script_path}")
        except Exception as e:
            print(f"❌ scripts.json is INVALID: {e}")
    else:
        print(f"⚠️ scripts.json NOT FOUND at {script_path}")
    
    # Load View agar aktif terus (Persistent)
    bot.add_view(ScriptControlView())

    # Auto Send Panel DVN
    channel = bot.get_channel(CHANNEL_ID)
    if channel and isinstance(channel, discord.TextChannel):
        print(f"✅ Mengirim Panel ke: {channel.name}")
        embed = discord.Embed(
            title="Script Control Panel",
            description="Manage your script access for DVN Project.\nPilih script melalui menu dropdown di bawah.",
            color=0x2B2D31 
        )
        embed.set_thumbnail(url="https://cdn.discordapp.com/attachments/1452251463337377902/1456009509632737417/DVN_New.png")
        embed.set_footer(text="DVN HUB • Est. 2026", icon_url="https://cdn.discordapp.com/attachments/1452251463337377902/1456009509632737417/DVN_New.png")

        try:
            # Hapus pesan lama bot sebelum kirim baru (Anti-Spam)
            async for msg in channel.history(limit=10):
                if msg.author == bot.user: await msg.delete()
            
            await channel.send(embed=embed, view=ScriptControlView())
            
            print("🚀 Panel Rapi Terkirim!")
        except Exception as e:
             print(f"❌ Error kirim pesan: {e}")
    elif not channel:
        print(f"❌ Gagal kirim panel. Cek CHANNEL_ID di .env: {CHANNEL_ID}")

# ==========================================
# 5. EXECUTION
# ==========================================
if __name__ == "__main__":
    if TOKEN:
        print(f"✅ Starting Bot Script...")
        bot.run(TOKEN)
    else:
        print(f"❌ Token hilang. Cek file .env di {ENV_PATH}")
        sys.exit(1)