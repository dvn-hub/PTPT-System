import discord
import re
from discord.ext import commands, tasks
from config import Config, Emojis
from database.crud import (
    get_patungan, get_all_patungans, update_patungan_status,
    get_user_slots, get_unpaid_slots, create_system_log,
    get_ticket_by_channel
)
from database.models import SystemLog, Patungan, ActionQueue, UserSlot, UserTicket
import asyncio
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)

class PatunganManager:
    """Manager untuk handle semua operasi patungan"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.deadline_check_running = False
        self.schedule_check_running = False
        self.action_check.start()
        
    async def setup_channels(self):
        """Setup initial channels and roles"""
        guild = self.bot.get_guild(self.config.SERVER_ID)
        if not guild:
            logger.error("Guild not found!")
            return
        
        # Ensure list channel exists
        list_channel = guild.get_channel(self.config.LIST_PTPT_CHANNEL_ID)
        if not list_channel:
            category = discord.utils.get(guild.categories, name="『 𝙋𝙏𝙋𝙏 𝙓8 』")
            if not category:
                category = await guild.create_category("『 𝙋𝙏𝙋𝙏 𝙓8 』")
            
            list_channel = await category.create_text_channel(
                name="list-ptpt-x8",
                topic="Live progress semua patungan"
            )
            logger.info(f"Created list channel: {list_channel.name}")
        
        # Create initial embed
        await self.update_list_channel()
        logger.info(f"{Emojis.CHECK_YES_2} Channel setup completed")
    
    def get_admin_dashboard_data(self):
        """Get embed and view for admin dashboard"""
        # Default values
        title = f"{Emojis.DISCORD_CROWN} **DVN COMMAND CENTER**"
        desc = "Panel kontrol eksekutif untuk manajemen transaksi Patungan X8.\n\n**📋 Menu Admin:**\n⛏️ **Buat Patungan** - Membuat patungan baru (V1, V2, dll)\n⛏️ **Kelola Patungan** - Lihat status dan edit patungan\n⛏️ **Verifikasi Pembayaran** - Cek pembayaran pending"

        # Load from panels.json if exists
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'panels.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'dashboard' in data:
                        title = data['dashboard']['title']
                        desc = data['dashboard']['description']
        except Exception as e:
            logger.error(f"Error loading panels.json: {e}")

        embed = discord.Embed(
            title=title,
            description=desc,
            color=0x2C2F33 # Dark Grey / Gold-ish accent via fields
        )
        
        from bot.views import AdminDashboardView
        view = AdminDashboardView(self.bot)
        return embed, view

    async def setup_admin_dashboard(self):
        """Setup admin dashboard panel"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild: return
            
            channel = guild.get_channel(self.config.ADMIN_DASHBOARD_CHANNEL_ID)
            if not channel: return
            
            # Refresh panel
            await channel.purge(limit=10)
            
            embed, view = self.get_admin_dashboard_data()
            await channel.send(embed=embed, view=view)
            logger.info(f"{Emojis.CHECK_YES_2} Admin dashboard setup completed")
            
        except Exception as e:
            logger.error(f"Error setting up admin dashboard: {e}")

    async def initialize_patungan(self, version: str) -> bool:
        """Initialize patungan: Create channel/role and update DB"""
        try:
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                logger.error(f"Patungan {version} not found")
                return False

            # Create channel and role
            channel_id, role_id = await self.create_patungan_channel_role(version, patungan.price_per_slot)
            
            if channel_id and role_id:
                patungan.discord_channel_id = str(channel_id)
                patungan.discord_role_id = str(role_id)
                await self.bot.session.commit()
                logger.info(f"Initialized patungan {version} with Channel {channel_id} and Role {role_id}")
                return True
            return False
        except Exception as e:
            logger.error(f"Error initializing patungan: {e}")
            return False

    async def create_patungan_channel_role(self, version: str, price: int) -> tuple:
        """Create channel and role for patungan"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return None, None
            
            # Create role
            role_name = f"{version}-vip"
            role = discord.utils.get(guild.roles, name=role_name)
            
            if not role:
                role = await guild.create_role(
                    name=role_name,
                    color=discord.Color.blue(),
                    mentionable=True,
                    reason=f"Role untuk VIP Member patungan {version}"
                )
                logger.info(f"Created role: {role.name}")
            
            # Create channel
            # FIX: Sanitize channel name (lowercase, no spaces)
            sanitized_name = re.sub(r'[^a-z0-9]', '-', version.lower()).strip('-')
            channel_name = f"{sanitized_name}-vip"
            
            category = discord.utils.get(guild.categories, name="『 𝙋𝙏𝙋𝙏 𝙓8 』")
            if not category:
                category = await guild.create_category("『 𝙋𝙏𝙋𝙏 𝙓8 』")
            
            # Set permissions
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                role: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    read_message_history=True
                ),
                guild.me: discord.PermissionOverwrite(
                    read_messages=True,
                    send_messages=True,
                    manage_messages=True
                )
            }
            
            # Add admin role permission
            for role_id in [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS:
                admin_role = guild.get_role(role_id)
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(
                        read_messages=True,
                        send_messages=True,
                        manage_messages=True
                    )
            
            # Check if channel already exists
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if not channel:
                try:
                    channel = await category.create_text_channel(
                        name=channel_name,
                        topic=f"{Emojis.CASH_MONEY} Harga: Rp {price:,}/slot | Patungan {version}",
                        overwrites=overwrites
                    )
                    logger.info(f"Created channel: {channel.name}")
                except Exception as e:
                    logger.error(f"Failed to create channel {channel_name}: {e}")
                    print(f"CRITICAL ERROR: Failed to create channel {channel_name}. Reason: {e}")
                    return None, role.id if role else None
            
            # Send welcome message
            embed = discord.Embed(
                title=f"{Emojis.RING_BELL} SELAMAT DATANG DI {version}",
                description=f"Channel ini khusus untuk **VIP Member** patungan **{version}**",
                color=self.config.COLOR_INFO
            )
            
            embed.add_field(
                name=f"{Emojis.CASH_MONEY} Harga per Slot",
                value=f"Rp {price:,}",
                inline=True
            )
            
            embed.add_field(
                name="📋 Aturan Channel",
                value="• Diskusi eksklusif member\n• Info update prioritas\n• Saling menghormati",
                inline=False
            )
            
            await channel.send(embed=embed)
            
            return channel.id, role.id
            
        except Exception as e:
            logger.error(f"Error creating channel/role: {e}")
            return None, None
    
    async def update_list_channel(self):
        """Update the list channel with all patungan status"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            list_channel = guild.get_channel(self.config.LIST_PTPT_CHANNEL_ID)
            if not list_channel:
                logger.error("List channel not found")
                return
            
            # Force refresh data from DB to ensure latest updates (title, price, etc)
            self.bot.session.expire_all()
            
            # Get all active patungans from new model
            from sqlalchemy import select
            stmt = select(Patungan).where(Patungan.status != 'archived')
            result = await self.bot.session.execute(stmt)
            patungans = result.scalars().all()
            
            # Send each patungan
            for patungan in patungans:
                embed = await self.create_patungan_embed(patungan)
                
                if patungan.message_id:
                    try:
                        msg = await list_channel.fetch_message(int(patungan.message_id))
                        await msg.edit(embed=embed)
                    except discord.NotFound:
                        # Message deleted, resend
                        msg = await list_channel.send(embed=embed)
                        patungan.message_id = str(msg.id)
                        await self.bot.session.commit()
                else:
                    msg = await list_channel.send(embed=embed)
                    patungan.message_id = str(msg.id)
                    await self.bot.session.commit()
            
            logger.info(f"{Emojis.CHECK_YES_2} List channel updated (Edited)")
            
        except Exception as e:
            logger.error(f"Error updating list channel: {e}")
    
    async def update_announcement_message(self, version: str):
        """Update the announcement message for a specific version"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild: return
            
            channel = discord.utils.get(guild.text_channels, name=self.config.ANNOUNCEMENT_CHANNEL)
            if not channel: return
            
            patungan = await get_patungan(self.bot.session, version)
            if not patungan: return
            
            embed = await self.create_announcement_embed(patungan)
            
            # Search for the announcement message
            async for msg in channel.history(limit=50):
                if msg.author == self.bot.user and msg.embeds:
                    e = msg.embeds[0]
                    is_target = False
                    
                    # Check if it's the announcement for this version
                    # Match by Title "[V1]" or Initial Title "<a:00confettipopper:1455058437544349899> PATUNGAN BARU DIBUKA!" with Version field
                    if e.title and f"[{version}]" in e.title:
                        is_target = True
                    elif e.title == f"{Emojis.CONFETTI_POPPER} PATUNGAN BARU DIBUKA!":
                        for field in e.fields:
                            if field.name == "Version" and version in field.value:
                                is_target = True
                                break
                    
                    if is_target:
                        await msg.edit(embed=embed)
                        logger.info(f"Updated announcement for {version}")
                        break
                        
        except Exception as e:
            logger.error(f"Error updating announcement message: {e}")

    async def create_announcement_embed(self, patungan) -> discord.Embed:
        """Create simplified embed for announcement (Status Only)"""
        # Determine color based on status
        title_text = "NEW SESSION OPENED"
        if patungan.status == 'open':
            color = self.config.COLOR_SUCCESS
            status_emoji = "🟢"
        elif patungan.status == 'running':
            color = self.config.COLOR_INFO
            status_emoji = "🚀"
            title_text = "SESSION RUNNING"
        else:
            color = self.config.COLOR_ERROR
            status_emoji = "🔴"
            title_text = "SESSION CLOSED"
            
        # Use display_name if available for title
        display_title = patungan.display_name if patungan.display_name else patungan.product_name
        
        embed = discord.Embed(
            title=f"{Emojis.ANNOUNCEMENTS} **{title_text}**",
            description=f"{Emojis.FIRE_LIGHT_BLUE} **{display_title}**\n**STATUS:** {status_emoji} {patungan.status.upper()}",
            color=color
        )
        
        price_display = f"Rp {patungan.price_per_slot:,}" if patungan.price_per_slot > 0 else "GRATIS"
        embed.add_field(name=f"{Emojis.MONEY_BAG} **Price:**", value=price_display, inline=True)
        embed.add_field(name=f"{Emojis.ANIMATED_ARROW_BLUE} **Slot:**", value=f"{patungan.current_slots}/{patungan.max_slots}", inline=True)
        
        # Add new fields
        script_val = getattr(patungan, 'use_script', 'No')
        script_status = f"{Emojis.CHECK_YES_2} Yes" if script_val == "Yes" else f"{Emojis.BAN} No"
        embed.add_field(name="📜 **Script:**", value=script_status, inline=True)
        
        duration = getattr(patungan, 'duration_hours', 24)
        embed.add_field(name="⏳ **Durasi:**", value=f"{duration} Jam", inline=True)
        # embed.add_field(name="<:000iconlucky:1455059401860976767> Status", value=f"{status_emoji} {patungan.status.upper()}", inline=True) # Removed to match request fields
        
        # Add Start Info to Announcement
        start_mode = getattr(patungan, 'start_mode', 'full_slot')
        schedule_dt = getattr(patungan, 'start_schedule', None)
        
        # Robust handling for string/datetime
        if isinstance(schedule_dt, str):
            try:
                schedule_dt = datetime.strptime(schedule_dt, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                try:
                    schedule_dt = datetime.strptime(schedule_dt, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    schedule_dt = None
        
        if start_mode == 'schedule' and schedule_dt:
            start_display = f"📅 {schedule_dt.strftime('%d/%m %H:%M')} WIB"
        else:
            start_display = f"{Emojis.LOADING_CIRCLE} Full Slot"
            
        embed.add_field(name=f"{Emojis.ROCKET} **Start:**", value=start_display, inline=True)
        
        wib_now = datetime.utcnow() + timedelta(hours=7)
        embed.set_footer(text=f"Updated: {wib_now.strftime('%H:%M')} WIB")
        return embed

    async def create_patungan_embed(self, patungan) -> discord.Embed:
        """Create embed for a patungan"""
        # Calculate slots filled (Need to query UserSlots)
        from database.models import UserSlot
        from sqlalchemy import select, func
        
        stmt = select(func.count(UserSlot.id)).where(
            UserSlot.patungan_version == patungan.product_name,
            UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
        )
        result = await self.bot.session.execute(stmt)
        current_slots = result.scalar() or 0

        # Determine status display
        remaining_slots = patungan.total_slots - current_slots
        
        if patungan.status == 'closed':
            main_status_text = "CLOSED"
            status_emoji = Emojis.BAN
            color = self.config.COLOR_ERROR
        elif patungan.status == 'running':
            main_status_text = "RUNNING"
            status_emoji = Emojis.ROCKET
            color = self.config.COLOR_INFO
        elif current_slots >= patungan.total_slots:
            main_status_text = "FULL BOOKED"
            status_emoji = Emojis.BAN
            color = self.config.COLOR_ERROR
        elif patungan.status == 'open':
            main_status_text = f"OPEN - Sisa {remaining_slots} Slot"
            status_emoji = Emojis.OPEN_SIGN
            color = self.config.COLOR_SUCCESS
        else:
            main_status_text = patungan.status.upper()
            status_emoji = Emojis.LOADING_CIRCLE
            color = self.config.COLOR_NEUTRAL
        
        # Calculate progress
        progress_percent = int((current_slots / patungan.total_slots) * 100)
        progress_bar = self._create_progress_bar(progress_percent)
        
        # Fetch slots
        from sqlalchemy.orm import selectinload
        stmt_slots = select(UserSlot).where(
            UserSlot.patungan_version == patungan.product_name,
            UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
        ).options(selectinload(UserSlot.ticket)).order_by(UserSlot.slot_number)
        result_slots = await self.bot.session.execute(stmt_slots)
        slots = result_slots.scalars().all()

        participants_text = ""
        if slots:
            # Sort slots by slot_number
            sorted_slots = sorted(slots, key=lambda x: x.slot_number)
            
            for slot in sorted_slots:
                # Status Emoji
                status_map = {
                    'booked': Emojis.LOADING_CIRCLE,
                    'waiting_payment': Emojis.LOADING_CIRCLE,
                    'paid': Emojis.VERIFIED,
                    'kicked': Emojis.WARNING
                }
                
                if slot.slot_status == 'paid':
                    emoji = Emojis.VERIFIED
                    slot_status_text = "PAID"
                elif slot.slot_status == 'booked':
                    emoji = Emojis.LOADING_CIRCLE
                    slot_status_text = "BOOKED"
                else:
                    emoji = status_map.get(slot.slot_status, '❓')
                    slot_status_text = slot.slot_status.upper()
                
                discord_tag = f"<@{slot.ticket.discord_user_id}>" if slot.ticket else "Unknown"
                # Format: No. UsernameRoblox - || @DisplaynameDiscord || (STATUS) [EMOJI]
                participants_text += f"`{slot.slot_number}.` {slot.game_username} - || {discord_tag} || ({slot_status_text}) {emoji}\n"
            
            if len(participants_text) > 4096:
                participants_text = participants_text[:4093] + "..."
        else:
            participants_text = "Belum ada member"
        
        # Add Script & Start Info below list
        script_val = getattr(patungan, 'use_script', 'No')
        script_display = f"{Emojis.CHECK_YES_2} Yes" if script_val == "Yes" else f"{Emojis.BAN} No"
        
        start_mode = getattr(patungan, 'start_mode', 'full_slot')
        
        # Robust handling for start_schedule
        schedule_dt = getattr(patungan, 'start_schedule', None)
        if isinstance(schedule_dt, str):
            try:
                schedule_dt = datetime.strptime(schedule_dt, "%Y-%m-%d %H:%M:%S.%f")
            except ValueError:
                try:
                    schedule_dt = datetime.strptime(schedule_dt, "%Y-%m-%d %H:%M:%S")
                except ValueError:
                    schedule_dt = None

        if start_mode == 'schedule' and schedule_dt:
            start_display = f"📅 {schedule_dt.strftime('%d/%m %H:%M')} WIB"
        else:
            start_display = f"{Emojis.LOADING_CIRCLE} Full Slot"
            
        participants_text += f"\n\n📜 **Script:** {script_display}\n{Emojis.ROCKET} **Start:** {start_display}"
        
        duration = getattr(patungan, 'duration_hours', 24)
        
        # Use display_name if available for title
        display_title = patungan.display_name if patungan.display_name else patungan.product_name

        # Create embed
        embed = discord.Embed(
            title=f"{Emojis.FIRE_BLUE} **{display_title} - {duration} Jam**",
            description=participants_text,
            color=color
        )
        
        price_display = f"Rp {patungan.price:,}" if patungan.price > 0 else "GRATIS"
        embed.add_field(name=f"{Emojis.PRICE_TAG_USD} Harga", value=price_display, inline=True)
        embed.add_field(name=f"{Emojis.ICON_LUCKY} Slot", value=f"{current_slots}/{patungan.total_slots}", inline=True)
        
        embed.add_field(name=f"{Emojis.TYPING} Progress", value=f"{progress_bar} {progress_percent}%", inline=True)
        embed.add_field(name=f"{Emojis.RING_BELL} Status", value=f"{status_emoji} {main_status_text}", inline=True)
        
        wib_now = datetime.utcnow() + timedelta(hours=7)
        embed.set_footer(text=f"ID: {patungan.id} | Updated: {wib_now.strftime('%H:%M')} WIB")
        
        return embed
    
    def _create_progress_bar(self, percent: int, length: int = 10) -> str:
        """Create progress bar visualization"""
        filled = int(length * percent / 100)
        bar = "█" * filled + "░" * (length - filled)
        return bar
    
    async def trigger_deadline(self, version: str):
        """Trigger deadline for patungan when slot 10 is filled"""
        try:
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Set deadline (6 hours from now)
            deadline_start = datetime.now()
            deadline_end = deadline_start + timedelta(hours=self.config.DEADLINE_HOURS)
            
            patungan.deadline_start = deadline_start
            patungan.deadline_end = deadline_end
            
            await self.bot.session.commit()
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='deadline_triggered',
                log_level='info',
                patungan_version=version,
                action=f'Deadline triggered for {version}',
                details=f'Deadline: {deadline_end.strftime("%d/%m %H:%M")}'
            )
            
            # Send announcement
            await self.send_deadline_announcement(version, deadline_end)
            
            # Update list channel
            await self.update_list_channel()
            
            logger.info(f"Deadline triggered for {version}")
            
        except Exception as e:
            logger.error(f"Error triggering deadline: {e}")
    
    async def send_deadline_announcement(self, version: str, deadline_end: datetime):
        """Send deadline announcement to all relevant channels"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            # Get patungan info
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Create announcement embed
            embed = discord.Embed(
                title=f"{Emojis.ALARM} DEADLINE DIAKTIFKAN!",
                description=f"**Patungan {version} telah mencapai 10 slot!**",
                color=self.config.COLOR_WARNING
            )
            
            embed.add_field(name="Patungan", value=version, inline=True)
            price_display = f"Rp {patungan.price_per_slot:,}" if patungan.price_per_slot > 0 else "GRATIS"
            embed.add_field(name=f"{Emojis.CASH_MONEY} Harga per Slot", value=price_display, inline=True)
            # embed.add_field(name="<:000clock:1455058933367964723> Deadline", value=deadline_end.strftime("%d/%m %H:%M"), inline=True) # Removed raw emoji
            # embed.add_field(name="<a:07clock:1454839226998768670> Sisa Waktu", value="6 jam", inline=True) # Removed raw emoji
            
            embed.add_field(
                name=f"{Emojis.WARNING} PERHATIAN",
                value="Semua slot 1-10 harus bayar sebelum deadline!\n"
                      "Belum bayar = AUTO KICK & slot dikosongkan.",
                inline=False
            )
            
            # Send to announcement channel
            announcement_channel = discord.utils.get(
                guild.channels,
                name=self.config.ANNOUNCEMENT_CHANNEL
            )
            
            if announcement_channel:
                await announcement_channel.send(embed=embed)
            
            # Send to patungan channel
            patungan_channel = guild.get_channel(int(patungan.discord_channel_id)) if patungan.discord_channel_id else None
            if patungan_channel:
                await patungan_channel.send(embed=embed)
            
            # Send to all ticket channels with unpaid slots
            unpaid_slots = await get_unpaid_slots(self.bot.session, version)
            
            for slot in unpaid_slots:
                try:
                    ticket_channel = guild.get_channel(int(slot.ticket.ticket_channel_id))
                    if ticket_channel:
                        user_embed = discord.Embed(
                            title=f"{Emojis.ALARM} DEADLINE PEMBERITAHUAN",
                            description=f"Slot Anda di patungan **{version}** harus dibayar sebelum deadline!",
                            color=self.config.COLOR_WARNING
                        )
                        
                        user_embed.add_field(name="Slot", value=slot.game_username, inline=True)
                        user_embed.add_field(name="Harga", value=f"Rp {slot.locked_price:,}", inline=True)
                        user_embed.add_field(name="Deadline", value=deadline_end.strftime("%d/%m %H:%M") + " WIB", inline=True)
                        
                        await ticket_channel.send(embed=user_embed)
                except:
                    continue
            
        except Exception as e:
            logger.error(f"Error sending deadline announcement: {e}")
    
    async def notify_admin_schedule(self, version: str):
        """Notify admin to set schedule when slot 17 is reached"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            admin_roles = []
            for role_id in self.config.ADMIN_ROLE_IDS:
                role = guild.get_role(role_id)
                if role:
                    admin_roles.append(role)
            
            if not admin_roles:
                return
            
            # Get patungan info
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Create notification embed
            embed = discord.Embed(
                title=f"{Emojis.ANNOUNCEMENT} ADMIN REMINDER - BUAT JADWAL",
                description=f"**Patungan {version} telah mencapai 17 slot!**",
                color=self.config.COLOR_INFO
            )
            
            embed.add_field(name="Patungan", value=f"{version} - {patungan.display_name}", inline=True)
            embed.add_field(name="Slot Terisi", value=f"{patungan.current_slots}/{patungan.max_slots}", inline=True)
            price_display = f"Rp {patungan.price_per_slot:,}/slot" if patungan.price_per_slot > 0 else "GRATIS"
            embed.add_field(name="Harga", value=price_display, inline=True)
            
            embed.add_field(
                name="ACTION REQUIRED", # Removed raw emoji
                value="Silakan buat jadwal start untuk patungan ini.\n"
                      "Gunakan command: `/jadwal {version} [tanggal] [waktu]`\n"
                      "Contoh: `/jadwal V1 2024-03-25 20:00`",
                inline=False
            )
            
            # Send to admin dashboard
            dashboard_channel = discord.utils.get(
                guild.channels,
                name=self.config.ADMIN_DASHBOARD_CHANNEL
            )
            
            if dashboard_channel:
                mentions = " ".join([r.mention for r in admin_roles])
                await dashboard_channel.send(f"{mentions}", embed=embed)
            
            # Send DM to admins
            notified_members = set()
            for role in admin_roles:
                for member in role.members:
                    if member.id not in notified_members:
                        try:
                            await member.send(embed=embed)
                            notified_members.add(member.id)
                        except:
                            continue
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='schedule_reminder',
                log_level='info',
                patungan_version=version,
                action=f'Schedule reminder sent for {version}',
                details=f'Slot count: {patungan.current_slots}'
            )
            
        except Exception as e:
            logger.error(f"Error notifying admin: {e}")
    
    async def set_schedule(self, version: str, schedule_time: datetime, admin_id: str):
        """Set schedule for patungan start"""
        try:
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return False, "Patungan tidak ditemukan"
            
            patungan.start_schedule = schedule_time
            patungan.start_mode = 'schedule'
            
            await self.bot.session.commit()
            
            # Setup reminders
            await self.setup_schedule_reminders(version, schedule_time)
            
            # Send announcement
            await self.send_schedule_announcement(version, schedule_time)
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='schedule_set',
                log_level='info',
                patungan_version=version,
                user_id=admin_id,
                action=f'Schedule set for {version}',
                details=f'Schedule: {schedule_time.strftime("%d/%m %H:%M")}'
            )
            
            # Update list channel to reflect changes (Full Slot -> Date)
            await self.update_list_channel()
            
            return True, "Jadwal berhasil ditetapkan"
            
        except Exception as e:
            logger.error(f"Error setting schedule: {e}")
            return False, str(e)
    
    async def setup_schedule_reminders(self, version: str, schedule_time: datetime):
        """Setup auto reminders for schedule"""
        reminder_times = [
            (24, f"{Emojis.ALARM} REMINDER 24 JAM - Patungan {{version}} start besok!"),
            (6, f"{Emojis.ANNOUNCEMENT} REMINDER 6 JAM - Patungan {{version}} start hari ini!"),
            (1, f"{Emojis.ANNOUNCEMENTS} REMINDER 1 JAM - Siap-siap untuk start!"),
            (0.25, f"{Emojis.ALERT_BLUE} REMINDER 15 MENIT - Standby di channel!"),
        ]
        
        for hours_before, message_template in reminder_times:
            reminder_time = schedule_time - timedelta(hours=hours_before)
            
            if reminder_time > datetime.now():
                # Store reminder in database or schedule task
                await self.schedule_reminder(
                    version=version,
                    reminder_time=reminder_time,
                    message=message_template.format(version=version)
                )
    
    async def schedule_reminder(self, version: str, reminder_time: datetime, message: str):
        """Schedule a reminder"""
        delay = (reminder_time - datetime.now()).total_seconds()
        
        if delay > 0:
            await asyncio.sleep(delay)
            await self.send_reminder(version, message)
    
    async def send_reminder(self, version: str, message: str):
        """Send reminder to patungan participants"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            patungan = await get_patungan(self.bot.session, version)
            if not patungan or not patungan.discord_role_id:
                return
            
            role = guild.get_role(int(patungan.discord_role_id))
            if not role:
                return
            
            # Create reminder embed
            embed = discord.Embed(
                title=message.split(" - ")[0],
                description=message.split(" - ")[1] if " - " in message else message,
                color=self.config.COLOR_INFO
            )
            
            embed.add_field(name="Patungan", value=version, inline=True)
            embed.add_field(name="Role", value=role.mention, inline=True)
            
            # Send to patungan channel
            if patungan.discord_channel_id:
                channel = guild.get_channel(int(patungan.discord_channel_id))
                if channel:
                    await channel.send(f"{role.mention}", embed=embed)
            
            # Send to announcement channel
            announcement_channel = discord.utils.get(
                guild.channels,
                name=self.config.ANNOUNCEMENT_CHANNEL
            )
            
            if announcement_channel:
                await announcement_channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending reminder: {e}")
    
    async def send_schedule_announcement(self, version: str, schedule_time: datetime):
        """Send schedule announcement"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Create announcement embed
            embed = discord.Embed(
                title="📅 JADWAL START DITETAPKAN",
                description=f"Patungan **{version}** akan start pada:",
                color=self.config.COLOR_SUCCESS
            )
            
            embed.add_field(
                name="Tanggal & Waktu",
                value=schedule_time.strftime("%A, %d %B %Y %H:%M") + " WIB",
                inline=False
            )
            
            embed.add_field(
                name="Auto Reminder",
                value="Reminder otomatis akan dikirim:\n"
                      "• 24 jam sebelum start\n"
                      "• 6 jam sebelum start\n"
                      "• 1 jam sebelum start\n"
                      "• 15 menit sebelum start",
                inline=False
            )
            
            # Send to announcement channel
            announcement_channel = discord.utils.get(
                guild.channels,
                name=self.config.ANNOUNCEMENT_CHANNEL
            )
            
            if announcement_channel:
                await announcement_channel.send(embed=embed)
            
            # Send to patungan channel
            if patungan.discord_channel_id:
                channel = guild.get_channel(int(patungan.discord_channel_id))
                if channel and patungan.discord_role_id:
                    role = guild.get_role(int(patungan.discord_role_id))
                    if role:
                        await channel.send(f"{role.mention}", embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending schedule announcement: {e}")
    
    async def set_patungan_status(self, version: str, status: str, admin_name: str):
        """Set patungan status manually"""
        try:
            # Update DB
            success = await update_patungan_status(self.bot.session, version, status)
            if not success:
                return False, "Patungan tidak ditemukan."

            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='status_change',
                log_level='info',
                patungan_version=version,
                action=f'Status changed to {status} by {admin_name}',
                details=f'New status: {status}'
            )

            # Update List & Announcement
            await self.update_list_channel()
            await self.update_announcement_message(version)
            
            return True, f"Status patungan **{version}** berhasil diubah menjadi **{status.upper()}**."
        except Exception as e:
            logger.error(f"Error setting status: {e}")
            return False, str(e)

    async def grant_patungan_access(self, user_id: str, product_name: str, slots_count: int = 1):
        """Grant role and channel access to user"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return None
            
            # Try get_member first, then fetch_member to ensure we find the user
            try:
                member = guild.get_member(int(user_id))
                if not member:
                    member = await guild.fetch_member(int(user_id))
            except Exception as e:
                logger.error(f"Member {user_id} not found: {e}")
                return None
            
            # Ensure channel and role exist
            patungan = await get_patungan(self.bot.session, product_name)
            if not patungan:
                return None
            
            # The role and channel should have been created when the patungan was created.
            if not patungan.discord_role_id:
                logger.error(f"Role ID is missing for patungan '{product_name}'. Cannot grant access.")
                return None
            
            role = guild.get_role(int(patungan.discord_role_id))
            if not role:
                logger.error(f"Role {patungan.discord_role_id} not found")
                return None
            
            # Add role if not present
            if role not in member.roles:
                await member.add_roles(role)
                
                # Send DM confirmation only if role was just added
                try:
                    embed = discord.Embed(
                        title=f"{Emojis.CHECK_YES_2} AKSES DIBERIKAN",
                        description=f"Anda sekarang memiliki akses ke patungan **{product_name}**!",
                        color=self.config.COLOR_SUCCESS
                    )
                    
                    embed.add_field(name="Role", value=role.name, inline=True)
                    
                    if patungan.discord_channel_id:
                        channel = guild.get_channel(int(patungan.discord_channel_id))
                        if channel:
                            embed.add_field(name="Channel", value=channel.mention, inline=True)
                    
                    await member.send(embed=embed)
                except:
                    pass  # User might have DMs closed
            
            # Send welcome message in channel
            if patungan.discord_channel_id:
                channel = guild.get_channel(int(patungan.discord_channel_id))
                if channel:
                    await channel.send(f"Selamat bergabung {member.mention} di kloter **{product_name}**! Anda memiliki **{slots_count}** slot. {Emojis.CONFETTI_POPPER}")
                    return channel
            
            logger.info(f"Granted access to {user_id} for {product_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error granting access: {e}")
            return None
    
    async def revoke_patungan_access(self, user_id: str, product_name: str):
        """Revoke role and channel access from user"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            member = guild.get_member(int(user_id))
            if not member:
                return
            
            patungan = await get_patungan(self.bot.session, product_name)
            if not patungan or not patungan.discord_role_id:
                return
            
            role = guild.get_role(int(patungan.discord_role_id))
            if not role:
                return
            
            # Remove role
            if role in member.roles:
                await member.remove_roles(role)
            
            logger.info(f"Revoked access from {user_id} for {product_name}")
            
        except Exception as e:
            logger.error(f"Error revoking access: {e}")
    
    async def check_deadlines(self):
        """Background task to check deadlines"""
        if self.deadline_check_running:
            return
        
        self.deadline_check_running = True
        
        while True:
            try:
                # Check every minute
                await asyncio.sleep(60)
                
                # Get all patungans with active deadlines
                from database.crud import get_patungans_with_deadlines
                patungans = await get_patungans_with_deadlines(self.bot.session)
                
                for patungan in patungans:
                    if patungan.deadline_end and patungan.deadline_end < datetime.now():
                        # Deadline passed, process kicks
                        await self.process_deadline_kicks(patungan.version)
                
            except Exception as e:
                logger.error(f"Error in deadline check: {e}")
                await asyncio.sleep(300)  # Wait 5 minutes on error
    
    async def process_deadline_kicks(self, version: str):
        """Process auto kicks after deadline"""
        try:
            # Get all unpaid slots for this patungan
            unpaid_slots = await get_unpaid_slots(self.bot.session, version)
            
            if not unpaid_slots:
                return

            for slot in unpaid_slots:
                # Update slot status to kicked
                slot.slot_status = 'kicked'
                slot.slot_number = 0 # Remove from sequence
                
                # Send notification
                await self.send_kick_notification(slot)
            
            # Re-order remaining slots (Shift up)
            from database.models import UserSlot
            from sqlalchemy import select
            
            stmt = select(UserSlot).where(
                UserSlot.patungan_version == version,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            ).order_by(UserSlot.slot_number)
            
            result = await self.bot.session.execute(stmt)
            active_slots = result.scalars().all()
            
            # Re-assign numbers
            for i, slot in enumerate(active_slots, 1):
                slot.slot_number = i
            
            # Update patungan current_slots
            patungan = await get_patungan(self.bot.session, version)
            if patungan:
                patungan.current_slots = len(active_slots)
                
                # Reset deadline if slots < 10
                if patungan.current_slots < 10:
                    patungan.deadline_start = None
                    patungan.deadline_end = None

            await self.bot.session.commit()
            
            # Update list channel
            await self.update_list_channel()
            
            logger.info(f"Processed deadline kicks for {version}")
            
        except Exception as e:
            logger.error(f"Error processing deadline kicks: {e}")
    
    async def send_kick_notification(self, slot):
        """Send kick notification to user"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            # Send to ticket channel
            ticket_channel = guild.get_channel(int(slot.ticket.ticket_channel_id))
            if ticket_channel:
                embed = discord.Embed(
                    title="❌ SLOT DIKICK",
                    description=f"Slot **{slot.game_username}** telah dikick karena belum bayar setelah deadline.",
                    color=self.config.COLOR_ERROR
                )
                
                embed.add_field(name="Patungan", value=slot.patungan_version, inline=True)
                embed.add_field(name="Alasan", value="Melewati deadline pembayaran", inline=True)
                embed.add_field(name="Status", value="Slot dikosongkan", inline=True)
                
                await ticket_channel.send(embed=embed)
            
            # Send DM
            try:
                member = guild.get_member(int(slot.ticket.discord_user_id))
                if member:
                    dm_embed = discord.Embed(
                        title="❌ SLOT ANDA DIKICK",
                        description=f"Slot **{slot.game_username}** di patungan **{slot.patungan_version}** telah dikick.",
                        color=self.config.COLOR_ERROR
                    )
                    
                    dm_embed.add_field(
                        name="Alasan",
                        value="Belum membayar setelah deadline 6 jam",
                        inline=False
                    )
                    
                    dm_embed.add_field(
                        name="Info",
                        value="Slot telah dikosongkan dan bisa diisi oleh user lain.",
                        inline=False
                    )
                    
                    await member.send(embed=dm_embed)
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error sending kick notification: {e}")
    
    async def check_schedules(self):
        """Background task to check schedules"""
        if self.schedule_check_running:
            return
        
        self.schedule_check_running = True
        
        while True:
            try:
                # Check every 30 seconds
                await asyncio.sleep(30)
                
                # Get all patungans with upcoming schedules
                from database.crud import get_upcoming_schedules
                schedules = await get_upcoming_schedules(self.bot.session)
                
                for patungan in schedules:
                    start_schedule = getattr(patungan, 'start_schedule', None)
                    if start_schedule and start_schedule < datetime.now():
                        # Schedule time reached
                        # Use product_name as version if version attr missing
                        version = getattr(patungan, 'product_name', getattr(patungan, 'version', None))
                        if version:
                            await self.process_schedule_start(version)
                
            except Exception as e:
                logger.error(f"Error in schedule check: {e}")
                await asyncio.sleep(300)
    
    async def process_schedule_start(self, version: str):
        """Process patungan start when schedule time is reached"""
        try:
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Update patungan status
            patungan.status = 'running'
            await self.bot.session.commit()
            
            # Send start announcement
            await self.send_start_announcement(version)
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='patungan_started',
                log_level='info',
                patungan_version=version,
                action=f'Patungan {version} started',
                details=f'Scheduled start time reached'
            )
            
            logger.info(f"Patungan {version} started as scheduled")
            
        except Exception as e:
            logger.error(f"Error processing schedule start: {e}")
    
    async def send_start_announcement(self, version: str):
        """Send start announcement"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return
            
            patungan = await get_patungan(self.bot.session, version)
            if not patungan:
                return
            
            # Create announcement embed
            embed = discord.Embed(
                title="🎉 PATUNGAN DIMULAI!",
                description=f"**Patungan {version} sekarang LIVE!**",
                color=self.config.COLOR_SUCCESS
            )
            
            embed.add_field(name="Patungan", value=f"{version} - {patungan.display_name or patungan.product_name}", inline=True)
            embed.add_field(name="Durasi", value=f"{patungan.duration_hours} jam", inline=True)
            embed.add_field(name="Peserta", value=f"{patungan.current_slots} orang", inline=True)
            
            embed.add_field(
                name=f"{Emojis.PING} INFORMASI",
                value="Silakan koordinasi dengan admin untuk proses patungan.\n"
                      "Gunakan channel patungan untuk komunikasi.",
                inline=False
            )
            
            # Send to announcement channel
            announcement_channel = discord.utils.get(
                guild.channels,
                name=self.config.ANNOUNCEMENT_CHANNEL
            )
            
            if announcement_channel:
                await announcement_channel.send(embed=embed)
            
            # Send to patungan channel
            if patungan.discord_channel_id:
                channel = guild.get_channel(int(patungan.discord_channel_id))
                if channel and patungan.discord_role_id:
                    role = guild.get_role(int(patungan.discord_role_id))
                    if role:
                        await channel.send(f"{role.mention}", embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending start announcement: {e}")
    
    async def get_user_status_embed(self, user_id: str) -> discord.Embed:
        """Get user status embed"""
        try:
            slots = await get_user_slots(self.bot.session, user_id)
            
            if not slots:
                embed = discord.Embed(
                    title=f"{Emojis.LOADING_CIRCLE} STATUS ANDA",
                    description="Anda belum memiliki slot aktif.",
                    color=self.config.COLOR_NEUTRAL
                )
                return embed
            
            # Group by patungan
            slots_by_patungan = {}
            for slot in slots:
                if slot.patungan_version not in slots_by_patungan:
                    slots_by_patungan[slot.patungan_version] = []
                slots_by_patungan[slot.patungan_version].append(slot)
            
            # Create embed
            embed = discord.Embed(
                title=f"{Emojis.LOADING_CIRCLE} STATUS SLOT ANDA",
                color=self.config.COLOR_INFO
            )
            
            for version, slot_list in slots_by_patungan.items():
                field_value = ""
                
                for slot in slot_list:
                    status_emoji = {
                        'booked': Emojis.TYPING,
                        'waiting_payment': Emojis.LOADING_CIRCLE,
                        'paid': Emojis.CHECK_YES_2,
                        'kicked': Emojis.WARNING
                    }.get(slot.slot_status, '❓')
                    
                    field_value += f"{status_emoji} **{slot.game_username}**"
                    
                    if slot.display_name and slot.display_name != slot.game_username:
                        field_value += f" ({slot.display_name})"
                    
                    field_value += f" - Rp {slot.locked_price:,}\n"
                    field_value += f"   Status: {slot.slot_status.upper()}\n"
                    
                    if slot.payment_deadline and slot.slot_status == 'booked':
                        time_left = slot.payment_deadline - datetime.now()
                        if time_left.total_seconds() > 0:
                            hours = int(time_left.total_seconds() // 3600)
                            field_value += f"   ⏰ Deadline: {hours} jam lagi\n"
                    
                    field_value += "\n"
                
                embed.add_field(
                    name=f"🎣 {version}",
                    value=field_value or "Tidak ada slot",
                    inline=False
                )
            
            return embed
            
        except Exception as e:
            logger.error(f"Error getting user status: {e}")
            
            embed = discord.Embed(
                title="❌ ERROR",
                description="Terjadi kesalahan saat mengambil status.",
                color=self.config.COLOR_ERROR
            )
            return embed
    
    async def get_admin_patungan_list(self) -> discord.Embed:
        """Get patungan list for admin"""
        try:
            patungans = await get_all_patungans(self.bot.session)
            
            embed = discord.Embed(
                title="📋 DAFTAR PATUNGAN (ADMIN)",
                color=self.config.COLOR_INFO
            )
            
            for patungan in patungans:
                field_value = f"**Nama:** {patungan.product_name}\n"
                price_display = f"Rp {patungan.price:,}/slot" if patungan.price > 0 else "GRATIS"
                field_value += f"**{Emojis.CASH_MONEY} Harga:** {price_display}\n"
                field_value += f"** Slot:** {patungan.total_slots}\n"
                field_value += f"**{Emojis.ICON_LUCKY} Status:** {patungan.status.upper()}\n"
                
                embed.add_field(
                    name=f"{Emojis.ICON_LUCKY} {patungan.product_name}",
                    value=field_value,
                    inline=False
                )
            
            return embed
            
        except Exception as e:
            logger.error(f"Error getting admin patungan list: {e}")
            
            embed = discord.Embed(
                title=f"{Emojis.WARNING} ERROR",
                description="Terjadi kesalahan.",
                color=self.config.COLOR_ERROR
            )
            return embed

    async def delete_patungan_fully(self, product_name: str, admin_name: str):
        """Delete patungan, channels, roles, and DB data"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            patungan = await get_patungan(self.bot.session, product_name)
            
            if not patungan:
                return False, "Patungan tidak ditemukan"
            
            # Delete Channel & Role if they exist
            if patungan.discord_channel_id:
                channel = guild.get_channel(int(patungan.discord_channel_id))
                if channel:
                    await channel.delete(reason=f"Patungan deleted by {admin_name}")
                    logger.info(f"Deleted channel {channel.name}")
            
            if patungan.discord_role_id:
                role = guild.get_role(int(patungan.discord_role_id))
                if role:
                    await role.delete(reason=f"Patungan deleted by {admin_name}")
                    logger.info(f"Deleted role {role.name}")

            # Delete from DB
            from database.crud import delete_patungan_by_version
            success = await delete_patungan_by_version(self.bot.session, product_name)
            
            if success:
                await self.update_list_channel()
                
                # Log
                await create_system_log(
                    session=self.bot.session,
                    log_type='patungan_deleted',
                    log_level='warning',
                    patungan_version=product_name,
                    action=f'Patungan {product_name} deleted by {admin_name}',
                    details='All data, channels, and roles removed'
                )
                return True, f"Patungan {product_name} berhasil dihapus total."
            else:
                return False, "Gagal menghapus data dari database."

        except Exception as e:
            logger.error(f"Error deleting patungan: {e}")
            return False, str(e)

    async def sync_legacy_patungan(self, channel_id: int):
        """Sync patungan data from existing embeds in list channel"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return 0, "Channel not found"
            
            count = 0
            async for message in channel.history(limit=50):
                if message.author == self.bot.user and await self.import_patungan_from_message(message):
                    count += 1
            
            return count, f"Berhasil import {count} patungan lama."
        except Exception as e:
            logger.error(f"Error syncing legacy patungan: {e}")
            return 0, str(e)

    async def import_patungan_from_message(self, message: discord.Message) -> bool:
        """Import single patungan from message embed (Auto-Import for legacy)"""
        try:
            if not message.embeds: return False
            embed = message.embeds[0]
            title = embed.title
            if not title: return False

            # Regex logic: Lebih fleksibel membaca judul
            # 1. Format standar: "**V1 - 24 Jam**"
            match = re.search(r'\*\*(.+?)\s*-\s*(\d+)\s*Jam\*\*', title)
            if match:
                product_name = match.group(1).strip()
                duration = int(match.group(2))
            else:
                # 2. Format bold nama saja: "**V1**"
                match = re.search(r'\*\*(.+?)\*\*', title)
                if match:
                    product_name = match.group(1).strip()
                    duration = 24
                else:
                    # 3. Format teks biasa (Fallback)
                    # Hapus bintang, ambil kata pertama sebelum strip
                    clean = title.replace('*', '').strip()
                    if '-' in clean:
                        product_name = clean.split('-')[0].strip()
                    else:
                        product_name = clean
                    duration = 24
            
            if not product_name: return False

            # Check if exists
            from database.crud import get_patungan
            from database.models import Patungan, UserSlot, UserTicket
            from sqlalchemy import select

            existing = await get_patungan(self.bot.session, product_name)
            
            # Logic Baru: Jika sudah ada, tetap lanjut ke parsing slot (jangan return True dulu)
            # Ini memperbaiki masalah di mana patungan terdeteksi ada tapi slotnya kosong/belum masuk DB
            
            if not existing:
                # Parse Fields untuk data baru
                price = 0
                current_slots = 0
                total_slots = 19
                status = 'open'
                
                for field in embed.fields:
                    if 'Harga' in field.name:
                        val = field.value.replace('Rp', '').replace('.', '').replace(',', '').strip()
                        val = val.split('/')[0].strip()
                        if val.isdigit(): price = int(val)
                    elif 'Slot' in field.name:
                        try:
                            parts = field.value.split('/')
                            current_slots = int(parts[0].strip())
                            if len(parts) > 1: total_slots = int(parts[1].strip())
                        except: pass
                    elif 'Status' in field.name:
                        val = field.value.lower()
                        if 'running' in val: status = 'running'
                        elif 'closed' in val: status = 'closed'
                        else: status = 'open'
                
                # Create Patungan
                new_patungan = Patungan(
                    product_name=product_name,
                    display_name=product_name,
                    price=price,
                    total_slots=total_slots,
                    current_slots=current_slots,
                    status=status,
                    duration_hours=duration,
                    message_id=str(message.id)
                )
                
                # Try find channel/role
                guild = message.guild
                if guild:
                    sanitized_name = re.sub(r'[^a-z0-9]', '-', product_name.lower()).strip('-')
                    channel_name = f"{sanitized_name}-vip"
                    role_name = f"{product_name}-vip"
                    
                    found_channel = discord.utils.get(guild.text_channels, name=channel_name)
                    if found_channel: new_patungan.discord_channel_id = str(found_channel.id)
                    
                    found_role = discord.utils.get(guild.roles, name=role_name)
                    if found_role: new_patungan.discord_role_id = str(found_role.id)
                
                self.bot.session.add(new_patungan)
                await self.bot.session.flush()
                existing = new_patungan # Set existing to new object for slot linking
            else:
                if not existing.message_id:
                    existing.message_id = str(message.id)
            
            # ALWAYS Parse Slots (Idempotent Check)
            # Ini memastikan slot lama tetap terimport meskipun patungan sudah ada
            if embed.description:
                slot_lines = embed.description.split('\n')
                for line in slot_lines:
                    # Regex Flexible: Support format lama (tanpa spoiler/backtick)
                    # Format: 1. Username - <@ID> ...
                    # Tidak mewajibkan kurung status di akhir regex agar lebih aman
                    slot_match = re.search(r'(?:`?)(\d+)(?:`?)\.\s*(.+?)\s*-\s*(?:\|\|\s*)?<@(\d+)>', line)
                    if slot_match:
                        s_num = int(slot_match.group(1))
                        s_game_user = slot_match.group(2).strip()
                        s_discord_id = slot_match.group(3)
                        
                        # Detect status from the whole line
                        line_lower = line.lower()
                        
                        s_status = 'booked'
                        if 'paid' in line_lower: s_status = 'paid'
                        elif 'waiting' in line_lower: s_status = 'waiting_payment'
                        
                        # Cek apakah slot ini sudah ada di DB
                        stmt_slot = select(UserSlot).where(
                            UserSlot.patungan_version == product_name,
                            UserSlot.slot_number == s_num
                        )
                        res_slot = await self.bot.session.execute(stmt_slot)
                        slot_exists = res_slot.scalar_one_or_none()
                        
                        if not slot_exists:
                            # Find/Create Dummy Ticket for this user (Legacy)
                            stmt_t = select(UserTicket).where(
                                UserTicket.discord_user_id == s_discord_id,
                                UserTicket.ticket_channel_id == f"legacy-{s_discord_id}"
                            )
                            res_t = await self.bot.session.execute(stmt_t)
                            ticket = res_t.scalar_one_or_none()
                            
                            if not ticket:
                                ticket = UserTicket(
                                    discord_user_id=s_discord_id,
                                    discord_username="Legacy User",
                                    ticket_channel_id=f"legacy-{s_discord_id}",
                                    ticket_status='closed',
                                    close_reason='Legacy Import'
                                )
                                self.bot.session.add(ticket)
                                await self.bot.session.flush()
                            
                            # Create Slot
                            new_slot = UserSlot(
                                ticket_id=ticket.id,
                                patungan_version=product_name,
                                slot_number=s_num,
                                game_username=s_game_user,
                                display_name=s_game_user,
                                slot_status=s_status,
                                locked_price=existing.price
                            )
                            self.bot.session.add(new_slot)
            
            await self.bot.session.commit()
            logger.info(f"Auto-imported legacy patungan: {product_name}")
            return True
        except Exception as e:
            logger.error(f"Error importing single patungan: {e}")
            return False

    @tasks.loop(seconds=5)
    async def action_check(self):
        """Check for pending actions from Web Dashboard"""
        try:
            from sqlalchemy import select
            
            # Expire all to get fresh data
            self.bot.session.expire_all()
            
            stmt = select(ActionQueue).where(ActionQueue.status == 'pending').order_by(ActionQueue.created_at)
            result = await self.bot.session.execute(stmt)
            actions = result.scalars().all()

            if not actions:
                return

            for action in actions:
                try:
                    logger.info(f"Processing remote action: {action.action_type} (ID: {action.id})")
                    payload = json.loads(action.payload)
                    
                    if action.action_type == 'create_patungan':
                        # Logic Create Patungan
                        new_patungan = Patungan(
                            product_name=payload['product_name'],
                            display_name=payload['product_name'],
                            price=payload['price'],
                            total_slots=payload['max_slots'],
                            status='open',
                            use_script=payload['use_script'],
                            start_mode=payload['start_mode'],
                            duration_hours=payload['duration']
                        )
                        
                        if payload.get('schedule'):
                            try:
                                new_patungan.start_schedule = datetime.strptime(payload['schedule'], "%Y-%m-%dT%H:%M")
                            except:
                                pass
                        
                        self.bot.session.add(new_patungan)
                        await self.bot.session.flush()
                        
                        # Create Channel & Role
                        channel_id, role_id = await self.create_patungan_channel_role(
                            version=payload['product_name'],
                            price=payload['price']
                        )
                        
                        if channel_id and role_id:
                            new_patungan.discord_channel_id = str(channel_id)
                            new_patungan.discord_role_id = str(role_id)
                        
                        await self.update_list_channel()
                        await self.update_announcement_message(payload['product_name'])

                    elif action.action_type == 'delete_patungan':
                        # Logic Delete Patungan
                        await self.delete_patungan_fully(payload['product_name'], f"Web Admin ({action.created_by})")

                    elif action.action_type == 'remove_member':
                        # Logic Remove Member
                        # Kita gunakan logic manual karena AdminHandler butuh interaction
                        product_name = payload['product_name']
                        username = payload['username']
                        
                        # Cari slot
                        stmt_slot = select(UserSlot).where(
                            UserSlot.patungan_version == product_name,
                            (UserSlot.game_username == username) | (UserSlot.display_name == username),
                            UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
                        )
                        res_slot = await self.bot.session.execute(stmt_slot)
                        slot = res_slot.scalar_one_or_none()
                        
                        if slot:
                            # Capture slot number for shifting
                            removed_slot_number = slot.slot_number

                            # Update status
                            slot.slot_status = 'kicked'
                            slot.slot_number = 0 # Remove from sequence
                            
                            # Shift slots (Naikkan slot di bawahnya)
                            stmt_shift = select(UserSlot).where(
                                UserSlot.patungan_version == product_name,
                                UserSlot.slot_number > removed_slot_number,
                                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
                            ).order_by(UserSlot.slot_number)
                            
                            res_shift = await self.bot.session.execute(stmt_shift)
                            slots_to_shift = res_shift.scalars().all()
                            
                            for s in slots_to_shift:
                                s.slot_number -= 1
                                
                            # Update patungan count
                            patungan = await get_patungan(self.bot.session, product_name)
                            if patungan:
                                await self.bot.session.refresh(patungan)
                                if patungan.current_slots > 0:
                                    patungan.current_slots -= 1
                            
                            await self.bot.session.commit()
                            await self.update_list_channel()
                            logger.info(f"Remote action: Removed {username} from {product_name}")
                        else:
                            logger.warning(f"Remote action failed: Member {username} not found in {product_name}")

                    elif action.action_type == 'broadcast':
                        # Logic Broadcast
                        channel_ids = payload.get('channels', '').split(',')
                        embed_data = payload.get('embed', {})
                        
                        embed = discord.Embed(
                            title=embed_data.get('title'),
                            description=embed_data.get('description'),
                            color=int(embed_data.get('color', '0x3498db'), 16)
                        )
                        
                        if embed_data.get('image'):
                            embed.set_image(url=embed_data.get('image'))
                            
                        success_count = 0
                        for cid in channel_ids:
                            if not cid.strip(): continue
                            try:
                                channel = self.bot.get_channel(int(cid.strip()))
                                if channel:
                                    await channel.send(embed=embed)
                                    success_count += 1
                            except Exception as e:
                                logger.error(f"Failed to broadcast to {cid}: {e}")
                        
                        logger.info(f"Broadcast sent to {success_count} channels")

                    action.status = 'completed'
                    action.processed_at = datetime.now()
                    
                except Exception as e:
                    logger.error(f"Error processing action {action.id}: {e}")
                    action.status = 'failed'
            
            await self.bot.session.commit()
            
        except Exception as e:
            logger.error(f"Error in action_check loop: {e}")

    @action_check.before_loop
    async def before_action_check(self):
        await self.bot.wait_until_ready()

    async def sync_legacy_patungan(self, channel_id: int):
        """Sync patungan data from existing embeds in list channel"""
        try:
            channel = self.bot.get_channel(channel_id)
            if not channel:
                return 0, "Channel not found"
            
            count = 0
            from database.crud import get_patungan
            from database.models import Patungan, UserSlot, UserTicket
            from sqlalchemy import select
            
            # Iterate history
            async for message in channel.history(limit=50):
                if message.author != self.bot.user or not message.embeds:
                    continue
                
                embed = message.embeds[0]
                title = embed.title
                if not title: continue
                
                # Parse Title: "**V1 - 24 Jam**"
                match = re.search(r'\*\*(.+?)\s*-\s*(\d+)\s*Jam\*\*', title)
                if not match:
                    # Fallback: "**V1**"
                    match = re.search(r'\*\*(.+?)\*\*', title)
                    if not match: continue
                    product_name = match.group(1).strip()
                    duration = 24
                else:
                    product_name = match.group(1).strip()
                    duration = int(match.group(2))
                
                # Check if exists
                existing = await get_patungan(self.bot.session, product_name)
                if existing:
                    if not existing.message_id:
                        existing.message_id = str(message.id)
                        await self.bot.session.commit()
                    continue
                
                # Parse Fields
                price = 0
                current_slots = 0
                total_slots = 19
                status = 'open'
                
                for field in embed.fields:
                    if 'Harga' in field.name:
                        val = field.value.replace('Rp', '').replace('.', '').replace(',', '').strip()
                        val = val.split('/')[0].strip()
                        if val.isdigit(): price = int(val)
                    elif 'Slot' in field.name:
                        try:
                            parts = field.value.split('/')
                            current_slots = int(parts[0].strip())
                            if len(parts) > 1: total_slots = int(parts[1].strip())
                        except: pass
                    elif 'Status' in field.name:
                        val = field.value.lower()
                        if 'running' in val: status = 'running'
                        elif 'closed' in val: status = 'closed'
                        else: status = 'open'
                
                # Create Patungan
                new_patungan = Patungan(
                    product_name=product_name,
                    display_name=product_name,
                    price=price,
                    total_slots=total_slots,
                    current_slots=current_slots,
                    status=status,
                    duration_hours=duration,
                    message_id=str(message.id)
                )
                
                # Try find channel/role
                guild = channel.guild
                sanitized_name = re.sub(r'[^a-z0-9]', '-', product_name.lower()).strip('-')
                channel_name = f"{sanitized_name}-vip"
                role_name = f"{product_name}-vip"
                
                found_channel = discord.utils.get(guild.text_channels, name=channel_name)
                if found_channel: new_patungan.discord_channel_id = str(found_channel.id)
                
                found_role = discord.utils.get(guild.roles, name=role_name)
                if found_role: new_patungan.discord_role_id = str(found_role.id)
                
                self.bot.session.add(new_patungan)
                await self.bot.session.flush() # Get ID
                
                # Parse Slots from Description (PENTING: Agar slot tidak ter-reset jadi 0)
                if embed.description:
                    slot_lines = embed.description.split('\n')
                    for line in slot_lines:
                        # Regex: `1.` Username - || <@123> || (STATUS)
                        slot_match = re.search(r'`(\d+)\.`\s*(.+?)\s*-\s*\|\|\s*<@(\d+)>\s*\|\|\s*\((.+?)\)', line)
                        if slot_match:
                            s_num = int(slot_match.group(1))
                            s_game_user = slot_match.group(2).strip()
                            s_discord_id = slot_match.group(3)
                            s_status_raw = slot_match.group(4).lower()
                            
                            s_status = 'booked'
                            if 'paid' in s_status_raw: s_status = 'paid'
                            elif 'waiting' in s_status_raw: s_status = 'waiting_payment'
                            
                            # Find/Create Dummy Ticket for this user (Legacy)
                            stmt_t = select(UserTicket).where(
                                UserTicket.discord_user_id == s_discord_id,
                                UserTicket.ticket_channel_id == f"legacy-{s_discord_id}"
                            )
                            res_t = await self.bot.session.execute(stmt_t)
                            ticket = res_t.scalar_one_or_none()
                            
                            if not ticket:
                                ticket = UserTicket(
                                    discord_user_id=s_discord_id,
                                    discord_username="Legacy User",
                                    ticket_channel_id=f"legacy-{s_discord_id}",
                                    ticket_status='closed',
                                    close_reason='Legacy Import'
                                )
                                self.bot.session.add(ticket)
                                await self.bot.session.flush()
                            
                            # Create Slot
                            new_slot = UserSlot(
                                ticket_id=ticket.id,
                                patungan_version=product_name,
                                slot_number=s_num,
                                game_username=s_game_user,
                                display_name=s_game_user,
                                slot_status=s_status,
                                locked_price=price
                            )
                            self.bot.session.add(new_slot)
                
                count += 1
                logger.info(f"Imported legacy patungan: {product_name}")
            
            await self.bot.session.commit()
            return count, f"Berhasil import {count} patungan lama."
            
        except Exception as e:
            logger.error(f"Error syncing legacy patungan: {e}")
            return 0, str(e)

    async def import_patungan_from_message(self, message: discord.Message) -> bool:
        """Import single patungan from message embed (Auto-Import for legacy)"""
        try:
            if not message.embeds: return False
            embed = message.embeds[0]
            title = embed.title
            if not title: return False

            # Regex logic (same as sync_legacy)
            match = re.search(r'\*\*(.+?)\s*-\s*(\d+)\s*Jam\*\*', title)
            if match:
                product_name = match.group(1).strip()
                duration = int(match.group(2))
            else:
                match = re.search(r'\*\*(.+?)\*\*', title)
                if match:
                    product_name = match.group(1).strip()
                    duration = 24
                else:
                    # Fallback 3: Plain text (Hapus emoji/simbol)
                    product_name = title.split('-')[0].strip().replace('*', '')
                    duration = 24

            # Check if exists
            from database.crud import get_patungan
            existing = await get_patungan(self.bot.session, product_name)
            if existing:
                if not existing.message_id:
                    existing.message_id = str(message.id)
                    await self.bot.session.commit()
                return True # Already exists

            # Parse Fields
            price = 0
            current_slots = 0
            total_slots = 19
            status = 'open'
            
            for field in embed.fields:
                if 'Harga' in field.name:
                    val = field.value.replace('Rp', '').replace('.', '').replace(',', '').strip()
                    val = val.split('/')[0].strip()
                    if val.isdigit(): price = int(val)
                elif 'Slot' in field.name:
                    try:
                        parts = field.value.split('/')
                        current_slots = int(parts[0].strip())
                        if len(parts) > 1: total_slots = int(parts[1].strip())
                    except: pass
                elif 'Status' in field.name:
                    val = field.value.lower()
                    if 'running' in val: status = 'running'
                    elif 'closed' in val: status = 'closed'
                    else: status = 'open'
            
            # Create Patungan
            from database.models import Patungan, UserSlot, UserTicket
            from sqlalchemy import select

            new_patungan = Patungan(
                product_name=product_name,
                display_name=product_name,
                price=price,
                total_slots=total_slots,
                current_slots=current_slots,
                status=status,
                duration_hours=duration,
                message_id=str(message.id)
            )
            
            self.bot.session.add(new_patungan)
            await self.bot.session.flush()
            
            # Parse Slots
            if embed.description:
                slot_lines = embed.description.split('\n')
                for line in slot_lines:
                    slot_match = re.search(r'`(\d+)\.`\s*(.+?)\s*-\s*\|\|\s*<@(\d+)>\s*\|\|\s*\((.+?)\)', line)
                    if slot_match:
                        s_num = int(slot_match.group(1))
                        s_game_user = slot_match.group(2).strip()
                        s_discord_id = slot_match.group(3)
                        s_status_raw = slot_match.group(4).lower()
                        
                        s_status = 'booked'
                        if 'paid' in s_status_raw: s_status = 'paid'
                        elif 'waiting' in s_status_raw: s_status = 'waiting_payment'
                        
                        # Find/Create Dummy Ticket for this user (Legacy)
                        stmt_t = select(UserTicket).where(
                            UserTicket.discord_user_id == s_discord_id,
                            UserTicket.ticket_channel_id == f"legacy-{s_discord_id}"
                        )
                        res_t = await self.bot.session.execute(stmt_t)
                        ticket = res_t.scalar_one_or_none()
                        
                        if not ticket:
                            ticket = UserTicket(
                                discord_user_id=s_discord_id,
                                discord_username="Legacy User",
                                ticket_channel_id=f"legacy-{s_discord_id}",
                                ticket_status='closed',
                                close_reason='Legacy Import'
                            )
                            self.bot.session.add(ticket)
                            await self.bot.session.flush()
                        
                        # Create Slot
                        new_slot = UserSlot(
                            ticket_id=ticket.id,
                            patungan_version=product_name,
                            slot_number=s_num,
                            game_username=s_game_user,
                            display_name=s_game_user,
                            slot_status=s_status,
                            locked_price=price
                        )
                        self.bot.session.add(new_slot)
            
            await self.bot.session.commit()
            logger.info(f"Auto-imported legacy patungan: {product_name}")
            return True
        except Exception as e:
            logger.error(f"Error importing single patungan: {e}")
            return False