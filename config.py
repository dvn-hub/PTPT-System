# config.py
import os
from dotenv import load_dotenv
from pathlib import Path

# Load .env explicitly from the project root directory
load_dotenv(dotenv_path=Path(__file__).parent / '.env')

def get_int_env(key, default=0):
    val = os.getenv(key)
    if val and val.strip().isdigit():
        return int(val.strip())
    return default

class Emojis:
    BEST_BUY = "<:000bestbuy:1455059284764266681>"
    CASH_MONEY = "<:000cashmoney:1455058817162412212>"
    DESIGN = "<:000design:1456187932489814168>"
    DESIGN_1 = "<:000design1:1456187984511766608>"
    ICON_LUCKY = "<:000iconlucky:1455059401860976767>"
    NEW = "<:000new:1455059106330316978>"
    OPEN_SIGN = "<:000opensign:1454851061310558268>"
    PRICE_TAG_USD = "<:000pricetagusd:1454851056944156836>"
    ROBUX = "<:000robux:1455058778666958918>"
    TICKET = "<:000ticket:1455058348012474428>"
    A_100 = "<a:00100:1455059437990711327>"
    BLUE = "<a:00blue:1455058702271910040>"
    CONFETTI_POPPER = "<a:00confettipopper:1455058437544349899>"
    DISCORD_CHRISTMAS = "<a:00discordchristmas:1455059665359736977>"
    DISCORD_CROWN = "<a:00discordcrown:1455058032764391519>"
    FISH_SPINNING = "<a:00fishspinning:1455059587328774175>"
    GIFT = "<a:00gift:1455058632529149972>"
    LIGHT_BLUE_SNOWFLAKE = "<a:00lightbluesnowflake:1455059010582483040>"
    LOADING_CIRCLE = "<a:00loadingcircle:1455057982651109510>"
    NETHERITE_PICKAXE = "<a:00netheritepickaxe:1455057642220163073>"
    PENGU_FISHING_ROD_2 = "<a:00pengufishingrod2:1455058735993979033>"
    ROBLOX_RAINBOW = "<a:00robloxrainbow:1454839467176100044>"
    ROCKET = "<a:00rocket:1455057768309461064>"
    SPECIAL = "<a:00special:1455057738496344156>"
    TYPING = "<a:00typing:1455059334017843242>"
    WAVEY = "<a:00wavey:1455058532444672083>"
    ANIMATED_ARROW_BLUE = "<a:02animatedarrowblue:1455058410994401436>"
    ANIMATED_ARROW_BLUE_LITE = "<a:02animatedarrowbluelite:1455057954469318717>"
    ANIMATED_ARROW_GREEN = "<a:02animatedarrowgreen:1455058232442748999>"
    ARROW = "<a:02arrow:1455057711073988723>"
    BLUE_ARROW_SPIN = "<a:02bluearrowspin:1455058084643737713>"
    CHECK_YES_2 = "<a:04checkyes2:1455057928263303221>"
    VERIFIED = "<a:04verified:1455057674449195098>"
    VERIFIED_2 = "<a:04verified_2:1455059203218477209>"
    VIP = "<a:04vip:1455058113932558426>"
    BLUE_PRESENT = "<a:05bluepresent:1455059517929816309>"
    GD_GOLDEN_COIN_SPIN = "<a:05gdgoldencoinspin:1454839174200033392>"
    IMPULSO = "<a:05impulso:1455057796415361163>"
    LIGHT_BLUE_HEART_COIN = "<a:05lightblueheartcoin:1455059556693577879>"
    MONEY_BAG = "<a:05moneybag:1455058386097016937>"
    RAINBOW_BOOST = "<a:05rainbowboost:1455057895191216183>"
    FIRE_BLUE = "<a:06fireblue:1454839205313118289>"
    FIRE_DARK_RED = "<a:06firedarkred:1454839345910513798>"
    FIRE_HOT_PINK = "<a:06firehotpink:1454839305397866546>"
    FIRE_LIGHT_BLUE = "<a:06firelightblue:1454839283436355584>"
    FIRE_ORANGE = "<a:06fireorange:1454839242818584698>"
    ALARM = "<a:07alarm:1454839148413456464>"
    ALERT_BLUE = "<a:07alertblue:1454839436117540874>"
    ANNOUNCEMENT = "<a:07announcement:1455058499376648242>"
    ANNOUNCEMENTS = "<a:07announcements:1455059472274817065>"
    ANNOUNCES = "<a:07announces:1454839405863768176>"
    PING = "<a:07ping:1454839491817898035>"
    RING_BELL = "<a:07ringbell:1454839090364026970>"
    WARNING = "<a:07warning:1454839380769378405>"
    SPARKLE_1 = "<a:505993sparkle1:1455059056455847949>"
    BAN = "<a:607449ban:1455059174911377458>"

class Config:
    # Discord
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN')
    SERVER_ID = get_int_env('SERVER_ID')
    ROBLOX_COOKIE = os.getenv('ROBLOX_COOKIE')
    
    # Support multiple Admin IDs (comma separated)
    _admin_role_env = os.getenv('ADMIN_ROLE_ID', '')
    ADMIN_ROLE_IDS = [int(x.strip()) for x in _admin_role_env.split(',') if x.strip().isdigit()]
    
    # Backward compatibility (ambil ID pertama atau 0)
    ADMIN_ROLE_ID = ADMIN_ROLE_IDS[0] if ADMIN_ROLE_IDS else 0
    
    TICKET_CATEGORY_ID = 1467544947333791824
    GROUP_CATEGORY_ID = 1467454477337362516
    
    # Special Roles
    SERVER_OVERLORD_ROLE_ID = 1448349975560982628
    SERVER_WARDEN_ROLE_ID = 1448569110899195914
    PTPT_HUNTER_ROLE_ID = 1463989922699673855
    
    # Channels
    OPEN_TICKET_CHANNEL = '🎫│open-ticket'
    # Channel IDs (Hardcoded)
    ADMIN_DASHBOARD_CHANNEL_ID = 1467454488855183442
    ANNOUNCEMENTS_CHANNEL_ID = 1467454486413840436
    PAYMENT_LOG_CHANNEL_ID = 1467454484170014732
    LIST_PTPT_CHANNEL_ID = 1467454482638962973
    OPEN_TICKET_CHANNEL_ID = 1467454480793735231
    TRANSACTION_HISTORY_CHANNEL_ID = 1448335870909485248
    RATING_LOG_CHANNEL_ID = 1449842645802287134
    TUTORIAL_CHANNEL_ID = 1448334225542615201
    
    # Database
    DATABASE_URL = os.getenv('DATABASE_URL', 'sqlite:///patungan.db')
    
    # WinterCode API (Stock Monitor)
    WC_USERNAME = os.getenv('WC_USERNAME')
    WC_PASSWORD = os.getenv('WC_PASSWORD')
    LOGIN_URL = os.getenv('WC_LOGIN_URL', 'https://apiweb.wintercode.dev/api/auth/login') # Updated URL
    API_URL = os.getenv('WC_API_URL', 'https://apiweb.wintercode.dev/api/player-data/batch')     # Updated URL
    
    # Workers List
    WORKERS = [
        # --- GENERATE OTOMATIS PEKERJA ---
        *[f"pekerjadvn{i}" for i in range(1, 36)],   "pekerjadvn306",
        *[f"pekerjadvn{i}" for i in range(37, 62)],  "pekerjadvn602",
        *[f"pekerjadvn{i}" for i in range(63, 69)],  "pekerjadvn609",
        *[f"pekerjadvn{i}" for i in range(70, 88)],  "pekerjadvn808",
        *[f"pekerjadvn{i}" for i in range(89, 91)],
        
        # --- WORKER DIVINE ---
        *[f"workerdivine{i:02d}" for i in range(1, 69)], "workerdivine609",
        *[f"workerdivine{i:02d}" for i in range(70, 81)],
        
        # --- AKUN LAINNYA ---
        "gajahduduxx", "cend0l_2nd", "cend0l_3", "gajahnjungkel",
        *[f"cend0l_{i:02d}" for i in range(5, 11)], # cend0l_05 s/d 10
        "ur_baeee8", "cend0lseger", "dvn_store", "dvn_store1"
    ]
    
    DASHBOARD_CHANNEL_ID = get_int_env('DASHBOARD_CHANNEL_ID')
    DASHBOARD_CHANNEL_NAME = "📦│stock-dvn-store"
    STOCK_CATEGORY_ID = get_int_env('STOCK_CATEGORY_ID')
    PRIVATE_SERVER_LINK = os.getenv('PRIVATE_SERVER_LINK', 'https://www.roblox.com/games/')

    # Payment
    DEFAULT_BANK_ACCOUNT = "BCA: 4400-1-9922-7 (A/N: MUHAMMAD IISA IBROHIM)"
    QRIS_IMAGE_URL = "https://cdn.discordapp.com/attachments/1451798194928353437/1467542255614169192/QR_NEW.png?ex=6980c2bb&is=697f713b&hm=20a597349a9994925525343cab03cc549f24c07bf9283406ef9178fba358c404&"
    PAYMENT_TIMEOUT = 300  # 5 minutes
    DEADLINE_HOURS = 6
    
    # OCR Configuration
    ENABLE_OCR = True
    TESSERACT_PATH = os.getenv('TESSERACT_PATH', r'C:\Program Files\Tesseract-OCR\tesseract.exe' if os.name == 'nt' else '/usr/bin/tesseract')
    
    # Timezone
    TIMEZONE = 'Asia/Jakarta'
    
    # Colors
    COLOR_SUCCESS = 0x00FF00  # Bright Green
    COLOR_WARNING = 0xf39c12  # Orange
    COLOR_ERROR = 0xe74c3c    # Red
    COLOR_INFO = 0x3498db     # Blue
    COLOR_NEUTRAL = 0x95a5a6  # Gray
    COLOR_GOLD = 0xFFD700     # Gold (New for Premium Ticket)
    
    # Backward compatibility aliases (mapped to new class)
    EMOJI_CROWN = Emojis.DISCORD_CROWN
    EMOJI_DIAMOND = Emojis.VIP
    EMOJI_MONEY = Emojis.MONEY_BAG
    EMOJI_VERIFIED = Emojis.VERIFIED
    EMOJI_LOADING = Emojis.LOADING_CIRCLE
    EMOJI_ANNOUNCE = Emojis.ANNOUNCEMENTS
    EMOJI_TICKET = Emojis.TICKET
    EMOJI_FIRE = Emojis.FIRE_BLUE
    EMOJI_WARNING = Emojis.WARNING
    EMOJI_PICKAXE = Emojis.NETHERITE_PICKAXE
    EMOJI_ARROW = Emojis.ANIMATED_ARROW_BLUE
    EMOJI_CHECK = Emojis.CHECK_YES_2
    EMOJI_SPECIAL = Emojis.SPECIAL
    EMOJI_SPARKLE = Emojis.SPARKLE_1