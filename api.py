import requests
from config import Config

class WinterAPI:
    def __init__(self):
        self.token = None

    def login(self):
        print("🔄 Sedang mencoba login ke Wintercode...")
        try:
            payload = {"username": Config.WC_USERNAME, "password": Config.WC_PASSWORD}
            r = requests.post(Config.LOGIN_URL, json=payload, timeout=10)
            if r.status_code == 200:
                data = r.json()
                self.token = data.get('token')
                if self.token:
                    print("✅ Login Berhasil! Token diperbarui.")
                    return True
            
            raise Exception(f"Login Gagal: {r.status_code} | {r.text}")
        except Exception as e:
            print(f"❌ Error Login: {e}")
            raise e

    def fetch_data(self):
        # Auto Login jika belum punya token
        if not self.token:
            self.login() # Akan raise Exception jika gagal

        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }

        # --- SISTEM BATCH ---
        all_player_data = {}
        batch_size = 25
        workers = Config.WORKERS
        total_batches = (len(workers) + batch_size - 1) // batch_size
        
        print(f"⏳ Memproses {len(workers)} akun (Total {total_batches} Batch)...")

        for i in range(0, len(workers), batch_size):
            batch_nicknames = workers[i : i + batch_size]
            payload = { "nicknames": batch_nicknames }
            
            try:
                # print(f"   -> Request Batch {i//batch_size + 1}/{total_batches}...")
                r = requests.post(Config.API_URL, json=payload, headers=headers, timeout=20)
                
                # Handle 401 (Expired)
                if r.status_code == 401:
                    print("⚠️ Token Expired. Login ulang...")
                    if self.login():
                        headers["Authorization"] = f"Bearer {self.token}"
                        r = requests.post(Config.API_URL, json=payload, headers=headers, timeout=20)

                if r.status_code == 200:
                    data = r.json().get('data', {})
                    all_player_data.update(data)
                else:
                    print(f"❌ Batch Gagal: {r.status_code}")
            
            except Exception as e:
                print(f"❌ Error Koneksi Batch: {e}")

        if all_player_data:
            print("✅ Semua Batch Selesai!")
            return {"success": True, "data": all_player_data}
        
        raise Exception("Data kosong. Cek list WORKERS di config.py atau status API.")

def get_ansi_color(variant_id):
    v = str(variant_id).lower() if variant_id else ""
    if "albino" in v or "stone" in v: return "[2;37m"
    if "dark" in v or "midnight" in v or "blue" in v: return "[2;34m"
    if "toxic" in v or "radioactive" in v: return "[2;32m"
    if "solar" in v or "gold" in v or "sandy" in v: return "[2;33m"
    if "volcanic" in v or "blood" in v or "red" in v: return "[2;31m"
    return "[0;37m"

def process_data(api_response):
    report = { 
        "ruby": 0, "squid": 0, "enchant_stone": 0, "evolved_stone": 0, 
        "secrets": {}, "sc_low_total": 0, "total_coins": 0, "mythic_value": 0 
    }
    
    sc_low_list = [
        "bone whale", "depthseeker ray", "elshark", "gran maja", "giant squid", 
        "gladiator shark", "great whale", "king crab", "king jelly", "monster shark", 
        "mosasaur shark", "queen crab", "robot kraken", "skeleton narwhal", 
        "viridis lurker", "worm fish", "panther eel", "cryoshade glider", 
        "blob shark", "frostborn shark", "thin armor shark", "scare"
    ]

    players = api_response.get('data', {})
    
    for username, info in players.items():
        coins = info.get('coins', 0)
        report['total_coins'] += coins
        
        inv = info.get('inventory') or info.get('Inventory') or {}

        # Cek Batu
        stone_list = inv.get('Enchant Stones', [])
        for item in stone_list:
            s_name = item.get('Name', '')
            s_qty = item.get('Quantity', 0)
            if s_name == "Enchant Stone": report['enchant_stone'] += s_qty
            elif s_name == "Evolved Enchant Stone": report['evolved_stone'] += s_qty

        # Cek Ikan
        fish_list = inv.get('Fish') or inv.get('fish') or []
        for item in fish_list:
            name = item.get('Name', 'Unknown')
            qty = item.get('Quantity', 1)
            tier = item.get('TierName', 'Common')
            price = item.get('SellPrice', 0)
            
            meta = item.get('Metadata')
            variant = meta.get('VariantId') if isinstance(meta, dict) else None

            if name == "Ruby" and variant and "gemstone" in str(variant).lower(): report['ruby'] += qty
            if "Sacred Guardian Squid" in name: report['squid'] += qty
            if tier == "Mythic": report['mythic_value'] += (price * qty)
            
            if "secret" in str(tier).lower():
                is_low = any(low in name.lower() for low in sc_low_list)
                if is_low:
                    report['sc_low_total'] += qty
                else:
                    full_name = f"[{variant}] {name}" if variant else name
                    if full_name not in report['secrets']:
                        report['secrets'][full_name] = { "count": 0, "ansi": get_ansi_color(variant), "is_mutation": bool(variant) }
                    report['secrets'][full_name]["count"] += qty
    return report