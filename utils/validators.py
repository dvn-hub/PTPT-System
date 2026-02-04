"""
Validation utilities for Patungan X8 System
Includes: username, price, payment, and other validations
"""
import re
import logging
from datetime import datetime, timedelta
from typing import Tuple, Optional, Dict, Any
from config import Config, Emojis

logger = logging.getLogger(__name__)

class Validators:
    """Validation utilities"""
    
    def __init__(self):
        self.config = Config()
    
    # ============================================
    # USERNAME & DISPLAY NAME VALIDATION
    # ============================================
    
    def validate_username(self, username: str) -> Tuple[bool, str]:
        """
        Validate game username
        Returns: (is_valid, message)
        """
        if not username:
            return False, "Username tidak boleh kosong"
        
        # Length validation
        if len(username) < 3:
            return False, "Username minimal 3 karakter"
        
        if len(username) > 25:
            return False, "Username maksimal 25 karakter"
        
        # Character validation
        # Allow: letters, numbers, underscore, dash, dot
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            return False, "Username hanya boleh mengandung:\n• Huruf (A-Z, a-z)\n• Angka (0-9)\n• Underscore (_)\n• Dash (-)\n• Titik (.)"
        
        # No consecutive special characters
        if re.search(r'[_.-]{2,}', username):
            return False, "Tidak boleh ada karakter khusus berurutan"
        
        # Must start with letter or number
        if not username[0].isalnum():
            return False, "Username harus dimulai dengan huruf atau angka"
        
        # No offensive words (basic check)
        offensive_words = ['admin', 'moderator', 'owner', 'system', 'bot', 'null', 'undefined']
        if username.lower() in offensive_words:
            return False, f"Username '{username}' tidak diizinkan"
        
        return True, f"{Emojis.CHECK_YES_2} Username valid"
    
    def validate_display_name(self, display_name: str) -> Tuple[bool, str]:
        """
        Validate display name (optional)
        Returns: (is_valid, message)
        """
        if not display_name or display_name.strip() == "":
            return True, "Display name kosong, akan menggunakan username"
        
        display_name = display_name.strip()
        
        # Length validation
        if len(display_name) < 2:
            return False, "Display name minimal 2 karakter"
        
        if len(display_name) > 30:
            return False, "Display name maksimal 30 karakter"
        
        # No excessive spaces
        if '  ' in display_name:
            return False, "Tidak boleh ada spasi ganda"
        
        # No special characters except basic punctuation
        if re.search(r'[<>{}[\]\\|]', display_name):
            return False, "Display name mengandung karakter khusus yang tidak diizinkan"
        
        # No offensive content (basic check)
        offensive_terms = ['admin', 'mod', 'owner', 'system']
        for term in offensive_terms:
            if term in display_name.lower():
                return False, f"Display name tidak boleh mengandung '{term}'"
        
        return True, f"{Emojis.VERIFIED} Display name valid"
    
    # ============================================
    # PRICE & PAYMENT VALIDATION
    # ============================================
    
    def validate_price(self, price: int) -> Tuple[bool, str]:
        """
        Validate price per slot
        Returns: (is_valid, message)
        """
        if not isinstance(price, int):
            return False, "Harga harus berupa angka bulat"
        
        # Allow 0 (Free)
        if price == 0:
            return True, f"{Emojis.VERIFIED_2} Harga valid (Gratis)"
        
        # Minimum price
        if price < 2000:
            return False, "Harga minimal Rp 2,000 (atau 0 untuk Gratis)"
        
        # Maximum price
        if price > 10000000:
            return False, "Harga maksimal Rp 10,000,000"
        
        # Must be divisible by 1000 (for easier payment)
        if price % 1000 != 0:
            return False, "Harga harus kelipatan 1,000 (contoh: 50,000, 100,000)"
        
        return True, f"{Emojis.VERIFIED_2} Harga valid"
    
    def validate_payment_amount(self, paid_amount: int, expected_amount: int) -> Tuple[bool, str, int]:
        """
        Validate payment amount vs expected amount
        Returns: (is_valid, message, difference)
        """
        if paid_amount <= 0:
            return False, f"{Emojis.WARNING} Nominal pembayaran tidak valid", expected_amount
        
        difference = paid_amount - expected_amount
        
        # Exact match
        if difference == 0:
            return True, f"{Emojis.VERIFIED_2} Nominal sesuai", 0
        
        # Within tolerance (+/- 10%)
        tolerance = expected_amount * 0.1  # 10% tolerance
        
        if abs(difference) <= tolerance:
            if difference > 0:
                return True, f"{Emojis.WARNING} Lebih Rp {difference:,} (dalam toleransi)", difference
            else:
                return True, f"{Emojis.WARNING} Kurang Rp {abs(difference):,} (dalam toleransi)", difference
        
        # Outside tolerance
        if difference > 0:
            return False, f"{Emojis.WARNING} Lebih Rp {difference:,} dari yang seharusnya", difference
        else:
            return False, f"{Emojis.WARNING} Kurang Rp {abs(difference):,} dari yang seharusnya", difference
    
    def parse_price_input(self, price_str: str) -> Tuple[bool, Optional[int], str]:
        """
        Parse price input string to integer
        Returns: (is_valid, price, message)
        """
        if not price_str:
            return False, None, "Harga tidak boleh kosong"
        
        try:
            # FIX: Gunakan REGEX untuk sanitasi agresif
            clean_str = price_str.strip()
            
            # Logic: Split dulu di tanda titik (.) terakhir untuk membuang desimal sen (jika ada)
            if '.' in clean_str:
                parts = clean_str.rsplit('.', 1)
                # Jika bagian setelah titik adalah 2 digit (asumsi sen), buang.
                if len(parts[1]) == 2 and parts[1].isdigit():
                    clean_str = parts[0]
            
            # Regex: Hapus SEMUA karakter selain angka 0-9
            clean_str = re.sub(r'[^0-9]', '', clean_str)
            
            if not clean_str:
                return False, None, "Harga harus berupa angka"
            
            price = int(clean_str)
            
            # Validate the price
            is_valid, message = self.validate_price(price)
            
            if is_valid:
                return True, price, message
            else:
                return False, None, message
                
        except ValueError:
            return False, None, "Format harga tidak valid"
        except Exception as e:
            logger.error(f"Error parsing price: {e}")
            return False, None, f"Error: {str(e)}"
    
    # ============================================
    # PATUNGAN VALIDATION
    # ============================================
    
    def validate_version_name(self, version: str) -> Tuple[bool, str]:
        """
        Validate patungan version name (V1, V2, etc)
        Returns: (is_valid, message)
        """
        if not version:
            return False, "Version tidak boleh kosong"
        
        version = version.strip().upper()
        
        # Must start with V followed by number
        if not re.match(r'^V[1-9][0-9]*$', version):
            return False, "Format version: V diikuti angka (contoh: V1, V2, V10)"
        
        # Max length
        if len(version) > 10:
            return False, "Version maksimal 10 karakter"
        
        # Check if number is reasonable
        version_num = int(version[1:])
        if version_num > 100:
            return False, "Version number terlalu besar"
        
        return True, f"{Emojis.VERIFIED} Version valid"
    
    def validate_patungan_name(self, name: str) -> Tuple[bool, str]:
        """
        Validate patungan display name
        Returns: (is_valid, message)
        """
        if not name:
            return False, "Nama patungan tidak boleh kosong"
        
        name = name.strip()
        
        # Length validation
        if len(name) < 5:
            return False, "Nama patungan minimal 5 karakter"
        
        if len(name) > 100:
            return False, "Nama patungan maksimal 100 karakter"
        
        # No special characters except basic punctuation
        if re.search(r'[<>{}[\]\\|]', name):
            return False, "Nama mengandung karakter khusus yang tidak diizinkan"
        
        # Must contain alphabets
        if not re.search(r'[a-zA-Z]', name):
            return False, "Nama harus mengandung huruf"
        
        return True, f"{Emojis.VERIFIED} Nama patungan valid"
    
    def validate_duration(self, duration_hours: int) -> Tuple[bool, str]:
        """
        Validate patungan duration
        Returns: (is_valid, message)
        """
        if not isinstance(duration_hours, int):
            return False, "Durasi harus berupa angka"
        
        # Minimum duration
        if duration_hours < 1:
            return False, "Durasi minimal 1 jam"
        
        # Maximum duration
        if duration_hours > 720:  # 30 days
            return False, "Durasi maksimal 720 jam (30 hari)"
        
        # Common durations check
        common_durations = [1, 2, 3, 6, 12, 24, 48, 72, 168]  # hours
        if duration_hours not in common_durations:
            return True, f"{Emojis.WARNING} Durasi tidak biasa, pastikan sudah benar"
        
        return True, f"{Emojis.VERIFIED} Durasi valid"
    
    def validate_max_slots(self, max_slots: int) -> Tuple[bool, str]:
        """
        Validate maximum slots
        Returns: (is_valid, message)
        """
        if not isinstance(max_slots, int):
            return False, "Max slots harus berupa angka"
        
        # Minimum slots
        if max_slots < 1:
            return False, "Minimal 1 slot"
        
        # Maximum slots (Discord role limit consideration)
        if max_slots > 100:
            return False, "Maksimal 100 slot"
        
        # Recommended to be divisible by 3 (for multi-slot per user)
        if max_slots % 3 != 0:
            return True, f"{Emojis.WARNING} Jumlah slot tidak kelipatan 3 (rekomendasi: 3, 6, 9, 12, 15, 18, 21, 24)"
        
        return True, f"{Emojis.VERIFIED} Max slots valid"
    
    # ============================================
    # SCHEDULE & DEADLINE VALIDATION
    # ============================================
    
    def validate_schedule_time(self, schedule_str: str) -> Tuple[bool, Optional[datetime], str]:
        """
        Validate schedule time input
        Returns: (is_valid, datetime, message)
        """
        if not schedule_str:
            return False, None, "Waktu schedule tidak boleh kosong"
        
        # Try different date formats
        date_formats = [
            "%Y-%m-%d %H:%M",    # 2024-03-25 20:00
            "%d/%m/%Y %H:%M",    # 25/03/2024 20:00
            "%d-%m-%Y %H:%M",    # 25-03-2024 20:00
            "%Y/%m/%d %H:%M",    # 2024/03/25 20:00
        ]
        
        for date_format in date_formats:
            try:
                schedule_time = datetime.strptime(schedule_str, date_format)
                
                # Must be in the future
                if schedule_time <= datetime.now():
                    return False, None, "Schedule harus di waktu yang akan datang"
                
                # Not too far in the future (max 1 year)
                if schedule_time > datetime.now() + timedelta(days=365):
                    return False, None, "Schedule maksimal 1 tahun dari sekarang"
                
                return True, schedule_time, f"{Emojis.VERIFIED} Schedule valid"
                
            except ValueError:
                continue
        
        return False, None, "Format waktu tidak valid. Gunakan: YYYY-MM-DD HH:MM atau DD/MM/YYYY HH:MM"
    
    def validate_deadline(self, deadline: datetime, schedule_time: Optional[datetime] = None) -> Tuple[bool, str]:
        """
        Validate deadline
        Returns: (is_valid, message)
        """
        if not deadline:
            return False, "Deadline tidak boleh kosong"
        
        # Must be in the future
        if deadline <= datetime.now():
            return False, "Deadline harus di waktu yang akan datang"
        
        # Not too far in the future (max 1 week for deadlines)
        if deadline > datetime.now() + timedelta(days=7):
            return False, "Deadline maksimal 7 hari dari sekarang"
        
        # If schedule exists, deadline must be before schedule
        if schedule_time and deadline >= schedule_time:
            return False, "Deadline harus sebelum waktu start patungan"
        
        return True, f"{Emojis.VERIFIED} Deadline valid"
    
    # ============================================
    # SLOT NUMBER VALIDATION
    # ============================================
    
    def validate_slot_number(self, slot_number: int, max_slots: int) -> Tuple[bool, str]:
        """
        Validate slot number
        Returns: (is_valid, message)
        """
        if not isinstance(slot_number, int):
            return False, "Slot number harus angka"
        
        if slot_number < 1:
            return False, "Slot number minimal 1"
        
        if slot_number > max_slots:
            return False, f"Slot number maksimal {max_slots}"
        
        return True, f"{Emojis.VERIFIED} Slot number valid"
    
    def validate_slot_type(self, slot_number: int) -> Tuple[str, str]:
        """
        Determine slot type based on slot number
        Returns: (slot_type, description)
        """
        if 1 <= slot_number <= 10:
            return "normal", "Slot 1-10: Booking biasa, bayar sebelum deadline"
        elif 11 <= slot_number <= 19:
            return "instant", "Slot 11-19: Instant payment, bayar langsung"
        else:
            return "unknown", "Slot tidak dikenal"
    
    # ============================================
    # PAYMENT PROOF VALIDATION
    # ============================================
    
    def validate_image_url(self, url: str) -> Tuple[bool, str]:
        """
        Validate image URL for payment proof
        Returns: (is_valid, message)
        """
        if not url:
            return False, "URL gambar tidak boleh kosong"
        
        # Check if it's a Discord CDN URL
        if 'cdn.discordapp.com' not in url and 'media.discordapp.net' not in url:
            return True, f"{Emojis.WARNING} URL bukan dari Discord CDN, pastikan aman"
        
        # Check file extension
        valid_extensions = ['.jpg', '.jpeg', '.png', '.gif', '.webp']
        if not any(url.lower().endswith(ext) for ext in valid_extensions):
            return False, "Format gambar tidak didukung. Gunakan: JPG, PNG, GIF, WebP"
        
        return True, f"{Emojis.VERIFIED} URL gambar valid"
    
    # ============================================
    # BULK VALIDATION FUNCTIONS
    # ============================================
    
    def validate_registration_data(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validate all registration data at once
        Returns: (is_valid, validated_data, message)
        """
        try:
            validated = {}
            
            # Validate version
            version = data.get('version', '').upper()
            is_valid, message = self.validate_version_name(version)
            if not is_valid:
                return False, {}, f"Version: {message}"
            validated['version'] = version
            
            # Validate username
            username = data.get('username', '').strip()
            is_valid, message = self.validate_username(username)
            if not is_valid:
                return False, {}, f"Username: {message}"
            validated['username'] = username
            
            # Validate display name (optional)
            display_name = data.get('display_name', '').strip()
            if display_name:
                is_valid, message = self.validate_display_name(display_name)
                if not is_valid:
                    return False, {}, f"Display name: {message}"
                validated['display_name'] = display_name
            else:
                validated['display_name'] = username
            
            return True, validated, f"{Emojis.VERIFIED} Semua data valid"
            
        except Exception as e:
            logger.error(f"Error validating registration data: {e}")
            return False, {}, f"Error validasi: {str(e)}"
    
    def validate_patungan_creation_data(self, data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
        """
        Validate all patungan creation data
        Returns: (is_valid, validated_data, message)
        """
        try:
            validated = {}
            
            # Validate version
            version = data.get('version', '').upper()
            is_valid, message = self.validate_version_name(version)
            if not is_valid:
                return False, {}, f"Version: {message}"
            validated['version'] = version
            
            # Validate name
            name = data.get('name', '').strip()
            is_valid, message = self.validate_patungan_name(name)
            if not is_valid:
                return False, {}, f"Nama: {message}"
            validated['name'] = name
            
            # Validate duration
            duration = int(data.get('duration', 0))
            is_valid, message = self.validate_duration(duration)
            if not is_valid:
                return False, {}, f"Durasi: {message}"
            validated['duration'] = duration
            
            # Validate price
            price_str = str(data.get('price', '0'))
            is_valid, price, message = self.parse_price_input(price_str)
            if not is_valid:
                return False, {}, f"Harga: {message}"
            validated['price'] = price
            
            # Validate max slots
            max_slots = int(data.get('max_slots', 19))
            is_valid, message = self.validate_max_slots(max_slots)
            if not is_valid:
                return False, {}, f"Max slots: {message}"
            validated['max_slots'] = max_slots
            
            # Description (optional, no validation)
            validated['description'] = data.get('description', '').strip()
            
            return True, validated, f"{Emojis.VERIFIED} Data patungan valid"
            
        except Exception as e:
            logger.error(f"Error validating patungan data: {e}")
            return False, {}, f"Error validasi: {str(e)}"
    
    # ============================================
    # HELPER FUNCTIONS
    # ============================================
    
    def format_validation_errors(self, errors: Dict[str, str]) -> str:
        """
        Format validation errors for display
        """
        if not errors:
            return f"{Emojis.VERIFIED} Tidak ada error"
        
        error_list = []
        for field, error in errors.items():
            error_list.append(f"• **{field}**: {error}")
        
        return "\n".join(error_list)
    
    def get_price_tiers(self) -> Dict[str, int]:
        """
        Get recommended price tiers
        """
        return {
            "Basic": 100000,
            "Standard": 250000,
            "Premium": 500000,
            "VIP": 1000000,
            "VVIP": 2500000,
        }
    
    def get_duration_options(self) -> Dict[str, int]:
        """
        Get recommended duration options
        """
        return {
            "1 Jam": 1,
            "3 Jam": 3,
            "6 Jam": 6,
            "12 Jam": 12,
            "24 Jam": 24,
            "3 Hari": 72,
            "7 Hari": 168,
        }

# Singleton instance for easy access
validators = Validators()

# ============================================
# CONVENIENCE FUNCTIONS (for backward compatibility)
# ============================================

def validate_username(username: str) -> Tuple[bool, str]:
    """Validate username"""
    return validators.validate_username(username)

def validate_price(price: int) -> Tuple[bool, str]:
    """Validate price"""
    return validators.validate_price(price)

def validate_payment_amount(paid_amount: int, expected_amount: int) -> Tuple[bool, str, int]:
    """Validate payment amount"""
    return validators.validate_payment_amount(paid_amount, expected_amount)

def validate_version_name(version: str) -> Tuple[bool, str]:
    """Validate version name"""
    return validators.validate_version_name(version)

def parse_price_input(price_str: str) -> Tuple[bool, Optional[int], str]:
    """Parse price input"""
    return validators.parse_price_input(price_str)

def validate_registration_data(data: Dict[str, Any]) -> Tuple[bool, Dict[str, Any], str]:
    """Validate registration data"""
    return validators.validate_registration_data(data)