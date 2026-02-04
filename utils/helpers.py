import discord
import asyncio
import logging
import re
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
from config import Config

logger = logging.getLogger(__name__)

class Helpers:
    """Utility helper functions"""
    
    def __init__(self):
        self.config = Config()
    
    def setup_logging(self) -> logging.Logger:
        """Setup logging configuration"""
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('patungan_bot.log', encoding='utf-8'),
                logging.StreamHandler()
            ]
        )
        return logging.getLogger('patungan_bot')
    
    def format_currency(self, amount: int) -> str:
        """Format currency to Indonesian format"""
        return f"Rp {amount:,}"
    
    def format_duration(self, hours: int) -> str:
        """Format duration to readable string"""
        if hours < 24:
            return f"{hours} jam"
        else:
            days = hours // 24
            remaining_hours = hours % 24
            if remaining_hours > 0:
                return f"{days} hari {remaining_hours} jam"
            return f"{days} hari"
    
    def calculate_time_left(self, end_time: datetime) -> str:
        """Calculate time left until deadline"""
        if not end_time:
            return "Tidak ada deadline"
        
        now = datetime.now()
        if end_time < now:
            return "Deadline telah lewat"
        
        time_left = end_time - now
        hours = int(time_left.total_seconds() // 3600)
        minutes = int((time_left.total_seconds() % 3600) // 60)
        
        if hours > 0:
            return f"{hours} jam {minutes} menit"
        else:
            return f"{minutes} menit"
    
    def validate_username(self, username: str) -> tuple[bool, str]:
        """Validate game username"""
        if not username:
            return False, "Username tidak boleh kosong"
        
        if len(username) < 3:
            return False, "Username minimal 3 karakter"
        
        if len(username) > 30:
            return False, "Username maksimal 30 karakter"
        
        # Allow alphanumeric and some special characters
        if not re.match(r'^[a-zA-Z0-9_.-]+$', username):
            return False, "Username hanya boleh mengandung huruf, angka, titik, dash, atau underscore"
        
        return True, "Username valid"
    
    def validate_display_name(self, display_name: str) -> tuple[bool, str]:
        """Validate display name"""
        if not display_name:
            return True, "Display name kosong, akan menggunakan username"  # Optional
        
        if len(display_name) > 50:
            return False, "Display name maksimal 50 karakter"
        
        return True, "Display name valid"
    
    def create_progress_bar(self, current: int, total: int, length: int = 10) -> str:
        """Create progress bar visualization"""
        if total == 0:
            return "░" * length
        
        percent = (current / total) * 100
        filled = int(length * current / total)
        bar = "█" * filled + "░" * (length - filled)
        return f"{bar} {percent:.1f}%"
    
    async def send_dm(self, user: discord.User, embed: discord.Embed) -> bool:
        """Send DM to user with error handling"""
        try:
            await user.send(embed=embed)
            return True
        except discord.Forbidden:
            logger.warning(f"Cannot send DM to {user.name}, DMs are closed")
            return False
        except Exception as e:
            logger.error(f"Error sending DM to {user.name}: {e}")
            return False
    
    async def wait_for_response(
        self, 
        ctx, 
        check_func, 
        timeout: int = 300,
        timeout_message: str = "⏰ Waktu habis!"
    ) -> Optional[discord.Message]:
        """Wait for user response with timeout"""
        try:
            response = await ctx.bot.wait_for(
                'message',
                timeout=timeout,
                check=check_func
            )
            return response
        except asyncio.TimeoutError:
            await ctx.send(timeout_message)
            return None
    
    def extract_user_id_from_channel_name(self, channel_name: str) -> Optional[str]:
        """Extract user ID from ticket channel name (patungan-123456789-abc)"""
        try:
            # Format: patungan-{user_id}-{random}
            parts = channel_name.split('-')
            if len(parts) >= 2 and parts[0] == 'patungan':
                user_id = parts[1]
                if user_id.isdigit():
                    return user_id
        except:
            pass
        return None
    
    def get_status_emoji(self, status: str) -> str:
        """Get emoji for status"""
        status_emojis = {
            'open': '🟢',
            'closed': '🔴',
            'paused': '🟡',
            'running': '🎯',
            'booked': '📅',
            'waiting_payment': '⏳',
            'paid': '✅',
            'kicked': '❌',
            'pending': '⏳',
            'verified': '✅',
            'rejected': '❌'
        }
        return status_emojis.get(status, '❓')
    
    def get_status_color(self, status: str) -> int:
        """Get color for status"""
        status_colors = {
            'open': 0x2ecc71,      # Green
            'closed': 0xe74c3c,    # Red
            'paused': 0xf39c12,    # Orange
            'running': 0x9b59b6,   # Purple
            'booked': 0x3498db,    # Blue
            'paid': 0x2ecc71,      # Green
            'kicked': 0xe74c3c,    # Red
            'pending': 0xf39c12,   # Orange
            'verified': 0x2ecc71,  # Green
            'rejected': 0xe74c3c   # Red
        }
        return status_colors.get(status, 0x95a5a6)  # Default gray
    
    async def create_confirmation_embed(
        self, 
        title: str, 
        description: str, 
        fields: Dict[str, str] = None,
        color: int = None
    ) -> discord.Embed:
        """Create confirmation embed"""
        if color is None:
            color = self.config.COLOR_SUCCESS
        
        embed = discord.Embed(
            title=title,
            description=description,
            color=color
        )
        
        if fields:
            for name, value in fields.items():
                embed.add_field(name=name, value=value, inline=True)
        
        embed.timestamp = datetime.now()
        return embed
    
    async def create_error_embed(self, error_message: str, details: str = None) -> discord.Embed:
        """Create error embed"""
        embed = discord.Embed(
            title="<a:07warning:1454839380769378405> ERROR",
            description=error_message,
            color=self.config.COLOR_ERROR
        )
        
        if details:
            embed.add_field(name="Detail", value=details, inline=False)
        
        embed.timestamp = datetime.now()
        return embed
    
    async def create_warning_embed(self, warning_message: str, details: str = None) -> discord.Embed:
        """Create warning embed"""
        embed = discord.Embed(
            title="<a:07warning:1454839380769378405> PERINGATAN",
            description=warning_message,
            color=self.config.COLOR_WARNING
        )
        
        if details:
            embed.add_field(name="Detail", value=details, inline=False)
        
        embed.timestamp = datetime.now()
        return embed
    
    def parse_duration(self, duration_str: str) -> Optional[int]:
        """Parse duration string to hours"""
        try:
            if 'jam' in duration_str:
                hours = int(duration_str.replace('jam', '').strip())
                return hours
            elif 'hari' in duration_str:
                days = int(duration_str.replace('hari', '').strip())
                return days * 24
            else:
                # Assume it's already in hours
                return int(duration_str)
        except:
            return None
    
    def parse_date_time(self, date_str: str, time_str: str) -> Optional[datetime]:
        """Parse date and time string to datetime"""
        try:
            # Format: YYYY-MM-DD HH:MM
            datetime_str = f"{date_str} {time_str}"
            return datetime.strptime(datetime_str, "%Y-%m-%d %H:%M")
        except:
            try:
                # Alternative format: DD/MM/YYYY HH:MM
                datetime_str = f"{date_str} {time_str}"
                return datetime.strptime(datetime_str, "%d/%m/%Y %H:%M")
            except:
                return None
    
    def format_datetime(self, dt: datetime) -> str:
        """Format datetime to readable string"""
        return dt.strftime("%A, %d %B %Y %H:%M")
    
    def format_datetime_short(self, dt: datetime) -> str:
        """Format datetime to short string"""
        return dt.strftime("%d/%m %H:%M")
    
    async def check_permissions(self, member: discord.Member, required_permissions: List[str]) -> bool:
        """Check if member has required permissions"""
        try:
            for permission in required_permissions:
                if not getattr(member.guild_permissions, permission, False):
                    return False
            return True
        except:
            return False
    
    async def is_admin(self, member: discord.Member) -> bool:
        """Check if member is admin"""
        try:
            for role_id in self.config.ADMIN_ROLE_IDS:
                role = member.guild.get_role(role_id)
                if role and role in member.roles:
                    return True
            return False
        except:
            return False
    
    def generate_ticket_id(self, user_id: str) -> str:
        """Generate ticket ID"""
        import random
        import string
        random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
        return f"patungan-{user_id}-{random_suffix}"
    
    async def archive_channel(self, channel: discord.TextChannel) -> bool:
        """Archive a channel by renaming it"""
        try:
            new_name = f"archived-{channel.name}"
            await channel.edit(name=new_name)
            
            # Remove send permissions for everyone
            await channel.set_permissions(
                channel.guild.default_role,
                send_messages=False,
                read_messages=False
            )
            
            return True
        except Exception as e:
            logger.error(f"Error archiving channel: {e}")
            return False
    
    async def cleanup_old_channels(self, guild: discord.Guild, days: int = 7) -> int:
        """Cleanup old archived channels"""
        try:
            count = 0
            for channel in guild.text_channels:
                if channel.name.startswith('archived-'):
                    # Check last message time
                    try:
                        async for message in channel.history(limit=1):
                            if (datetime.now() - message.created_at).days > days:
                                await channel.delete()
                                count += 1
                    except:
                        # If no messages, check channel creation time
                        if (datetime.now() - channel.created_at).days > days:
                            await channel.delete()
                            count += 1
            return count
        except Exception as e:
            logger.error(f"Error cleaning up old channels: {e}")
            return 0
    
    def validate_price(self, price_str: str) -> tuple[bool, Optional[int], str]:
        """Validate price input"""
        try:
            # Remove dots and commas
            clean_price = price_str.replace('.', '').replace(',', '').strip()
            
            if not clean_price.isdigit():
                return False, None, "Harga harus berupa angka"
            
            price = int(clean_price)
            
            # Allow 0 (Free)
            if price == 0:
                return True, 0, "Harga valid (Gratis)"
            
            if price < 2000:
                return False, None, "Harga minimal Rp 2,000"
            
            if price > 10000000:
                return False, None, "Harga maksimal Rp 10,000,000"
            
            return True, price, "Harga valid"
            
        except Exception as e:
            return False, None, f"Error validasi harga: {str(e)}"
    
    def format_slot_list(self, slots: List[Dict]) -> str:
        """Format slot list to string"""
        if not slots:
            return "Tidak ada slot"
        
        result = ""
        for slot in slots:
            status_emoji = self.get_status_emoji(slot.get('status', ''))
            result += f"{status_emoji} **{slot.get('username', 'Unknown')}**"
            
            if slot.get('display_name'):
                result += f" ({slot.get('display_name')})"
            
            result += f" - Rp {slot.get('price', 0):,}\n"
            result += f"  Status: {slot.get('status', 'unknown').upper()}\n\n"
        
        return result
    
    async def create_pagination_embed(
        self,
        title: str,
        items: List[Any],
        page: int,
        items_per_page: int = 10,
        formatter=None
    ) -> discord.Embed:
        """Create pagination embed"""
        total_pages = (len(items) + items_per_page - 1) // items_per_page
        
        if page < 1 or page > total_pages:
            page = 1
        
        start_idx = (page - 1) * items_per_page
        end_idx = start_idx + items_per_page
        page_items = items[start_idx:end_idx]
        
        embed = discord.Embed(
            title=f"{title} (Halaman {page}/{total_pages})",
            color=self.config.COLOR_INFO
        )
        
        if formatter:
            for item in page_items:
                embed.add_field(
                    name=formatter(item).get('name', 'Item'),
                    value=formatter(item).get('value', ''),
                    inline=False
                )
        else:
            for i, item in enumerate(page_items, start=start_idx + 1):
                embed.add_field(
                    name=f"Item #{i}",
                    value=str(item),
                    inline=False
                )
        
        if not page_items:
            embed.description = "Tidak ada data"
        
        embed.set_footer(text=f"Total: {len(items)} item")
        
        return embed
    
    def calculate_payment_summary(self, payments: List[Dict]) -> Dict[str, Any]:
        """Calculate payment summary"""
        total_expected = sum(p.get('expected', 0) for p in payments)
        total_paid = sum(p.get('paid', 0) for p in payments)
        total_difference = sum(p.get('difference', 0) for p in payments)
        
        return {
            'total_expected': total_expected,
            'total_paid': total_paid,
            'total_difference': total_difference,
            'payment_count': len(payments),
            'is_complete': total_difference >= 0
        }

# Singleton instance
helpers = Helpers()

# Utility functions
def setup_logging():
    """Setup logging"""
    return helpers.setup_logging()

def format_currency(amount: int) -> str:
    """Format currency"""
    return helpers.format_currency(amount)

def validate_username(username: str) -> tuple[bool, str]:
    """Validate username"""
    return helpers.validate_username(username)