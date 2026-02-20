import discord
from discord import ui
from discord.ext import commands, tasks
from config import Config, Emojis
from database.crud import (
    create_user_ticket, get_ticket_by_channel, update_ticket_status, get_patungan,
    get_user_active_ticket, create_system_log
)
from database.models import UserTicket, Patungan
from utils.helpers import helpers
from bot.views import MainTicketView, TicketPanelView, RatingView
import asyncio
import logging
from datetime import datetime, timedelta
import random
import os
import json
import string

logger = logging.getLogger(__name__)

class TicketHandler:
    """Handler untuk semua operasi ticket"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.helpers = helpers
    
    async def handle_new_ticket(self, channel: discord.TextChannel):
        """Handle new ticket creation by Ticket King"""
        try:
            # Extract user ID from channel name
            user_id = self.helpers.extract_user_id_from_channel_name(channel.name)
            
            if not user_id:
                logger.error(f"Cannot extract user ID from channel name: {channel.name}")
                return
            
            # Get user
            guild = channel.guild
            user = guild.get_member(int(user_id))
            
            if not user:
                logger.error(f"User {user_id} not found in guild")
                return
            
            
            # Create ticket in database
            success, ticket = await create_user_ticket(
                session=self.bot.session,
                discord_user_id=user_id,
                discord_username=user.name,
                ticket_channel_id=str(channel.id)
            )
            
            if not success:
                logger.error(f"Failed to create ticket for user {user_id}")
                return
            
            # Send welcome message
            await self.send_welcome_message(channel, user)
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='ticket_created',
                log_level='info',
                user_id=user_id,
                action='Ticket created',
                details=f'Channel: {channel.name}'
            )
            
            logger.info(f"Ticket created for user {user.name} ({user_id})")
            
        except Exception as e:
            logger.error(f"Error handling new ticket: {e}")
    
    async def send_welcome_message(self, channel: discord.TextChannel, user: discord.Member, product_name: str = None):
        """Send welcome message to ticket channel"""
        try:
            # Extract product name from channel name (format: product-user)
            if not product_name:
                product_name = channel.name.split('-')[0].upper()
            
            embed = discord.Embed(
                title=f"{Emojis.VIP} **DVN PREMIUM SUITE**",
                description=f"Selamat datang di layanan prioritas. Silakan ikuti instruksi di bawah.\n\n"
                            f"{Emojis.SPARKLE_1} **INFORMASI & PERATURAN**\n"
                            f"> {Emojis.VIP} **Fixed Price:** Harga mutlak (No Nego).\n"
                            f"> {Emojis.MONEY_BAG} **Payment:** Slot 11-19 Wajib Lunas di awal.\n"
                            f"> {Emojis.WARNING} **Deadline:** Maksimal 6 Jam setelah Slot 10 terisi.\n"
                            f"> {Emojis.VERIFIED} **Verification:** Upload bukti transfer HD.\n\n"
                            f"**Status:** {Emojis.LOADING_CIRCLE} *Menunggu Input User...*",
                color=self.config.COLOR_GOLD
            )
            
            embed.set_footer(text=f"User: {user.name} | Ticket: {product_name}")
            
            # Create view with buttons
            view = MainTicketView(self.bot)
            
            # Pings for User and Admins
            overlord_ping = f"<@&{self.config.SERVER_OVERLORD_ROLE_ID}>"
            warden_ping = f"<@&{self.config.SERVER_WARDEN_ROLE_ID}>"
            content = f"{user.mention} {overlord_ping} {warden_ping}"
            
            await channel.send(content=content, embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error sending welcome message: {e}")
    
    async def handle_ticket_message(self, message: discord.Message):
        """Handle messages in ticket channels"""
        try:
            # Update last activity
            ticket = await get_ticket_by_channel(self.bot.session, str(message.channel.id))
            
            if ticket:
                ticket.last_activity = datetime.now()
                await self.bot.session.commit()
            
            # Handle specific commands if forms fail
            if message.content.startswith('!'):
                await self.handle_fallback_commands(message)
            
        except Exception as e:
            logger.error(f"Error handling ticket message: {e}")
    
    async def handle_fallback_commands(self, message: discord.Message):
        """Handle fallback commands if forms fail"""
        try:
            content = message.content.lower().strip()
            user_id = str(message.author.id)
            
            match content:
                case '!help':
                    await self.send_help_message(message.channel)
                case '!status':
                    await self.show_user_status(message)
                case '!batal':
                    await self.handle_cancel_request(message)
                case '!admin':
                    await self.request_admin_assistance(message)
                case _ if content.startswith('!daftar'):
                    await self.handle_fallback_register(message)
                case _ if content.startswith('!bayar'):
                    await self.handle_fallback_payment(message)
            
        except Exception as e:
            logger.error(f"Error handling fallback commands: {e}")
    
    async def send_help_message(self, channel: discord.TextChannel):
        """Send help message"""
        embed = discord.Embed(
            title="🆘 BANTUAN - COMMANDS FALLBACK",
            description="Jika button tidak bekerja, gunakan commands berikut:",
            color=self.config.COLOR_INFO
        )
        
        embed.add_field(
            name="📋 DAFTAR",
            value="`!daftar V1 username:Player1`\nContoh: `!daftar V1 username:ProPlayer`",
            inline=False
        )
        
        embed.add_field(
            name="💰 BAYAR",
            value="`!bayar slot:1` atau `!bayar all`\nSetelah itu upload bukti TF",
            inline=False
        )
        
        embed.add_field(
            name="📊 STATUS",
            value="`!status` - Lihat status slot Anda",
            inline=False
        )
        
        embed.add_field(
            name=f"{Emojis.WARNING} BATAL",
            value="`!batal` - Batalkan ticket\n`!batal slot:1` - Batalkan slot tertentu",
            inline=False
        )
        
        embed.add_field(
            name="🆘 ADMIN",
            value="`!admin` - Minta bantuan admin",
            inline=False
        )
        
        await channel.send(embed=embed)
    
    async def show_user_status(self, message: discord.Message):
        """Show user status using fallback command"""
        try:
            from bot.patungan_manager import PatunganManager
            manager = PatunganManager(self.bot)
            
            embed = await manager.get_user_status_embed(str(message.author.id))
            await message.channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error showing user status: {e}")
            await message.channel.send(f"{Emojis.WARNING} Terjadi kesalahan saat mengambil status.")
    
    async def handle_fallback_register(self, message: discord.Message):
        """Handle fallback registration"""
        try:
            # Parse command: !daftar V1 username:Player1 display:Pro
            parts = message.content.split()
            
            if len(parts) < 3:
                await message.channel.send(
                    f"{Emojis.WARNING} Format salah! Gunakan: `!daftar V1 username:Player1`"
                )
                return
            
            version = parts[1].upper()
            username = None
            display_name = None
            
            # Parse parameters
            for part in parts[2:]:
                if part.startswith('username:'):
                    username = part.split(':', 1)[1]
                elif part.startswith('display:'):
                    display_name = part.split(':', 1)[1]
            
            if not username:
                await message.channel.send(
                    f"{Emojis.WARNING} Username diperlukan! `!daftar V1 username:Player1`"
                )
                return
            
            # Validate username
            is_valid, msg = self.helpers.validate_username(username)
            if not is_valid:
                await message.channel.send(f"{Emojis.WARNING} {msg}")
                return
            
            # Get patungan info
            from database.crud import get_patungan
            patungan = await get_patungan(self.bot.session, version)
            
            if not patungan:
                await message.channel.send(f"{Emojis.WARNING} Patungan {version} tidak ditemukan!")
                return
            
            # Check availability
            if patungan.current_slots >= patungan.max_slots:
                await message.channel.send(f"{Emojis.WARNING} Slot sudah penuh!")
                return
            
            # Check if username exists
            from database.crud import get_slot_by_username
            existing = await get_slot_by_username(self.bot.session, version, username)
            
            if existing:
                await message.channel.send("❌ Username sudah terdaftar di patungan ini!")
                return
            
            # Create slot
            from database.crud import create_user_slot
            from bot.patungan_manager import PatunganManager
            
            manager = PatunganManager(self.bot)
            slot_number = patungan.current_slots + 1
            
            success, slot = await create_user_slot(
                session=self.bot.session,
                user_id=str(message.author.id),
                username=message.author.name,
                ticket_channel_id=str(message.channel.id),
                patungan_version=version,
                slot_number=slot_number,
                game_username=username,
                display_name=display_name or username,
                locked_price=patungan.price_per_slot
            )
            
            if success:
                # Update patungan
                patungan.current_slots += 1
                await self.bot.session.commit()
                
                # Send confirmation
                embed = discord.Embed(
                    title=f"{Emojis.CHECK_YES_2} DAFTAR BERHASIL",
                    description=f"Slot berhasil dipesan menggunakan command!",
                    color=self.config.COLOR_SUCCESS
                )
                
                embed.add_field(name="Patungan", value=version, inline=True)
                embed.add_field(name="Slot", value=f"{slot_number}/{patungan.max_slots}", inline=True)
                embed.add_field(name="Harga", value=f"Rp {patungan.price_per_slot:,}", inline=True)
                embed.add_field(name="Username", value=username, inline=False)
                
                if 1 <= slot_number <= 10:
                    embed.add_field(name="Status", value="BOOKED - Bayar sebelum deadline", inline=False)
                elif 11 <= slot_number <= 19:
                    embed.add_field(name="Status", value="INSTANT PAYMENT - Bayar sekarang!", inline=False)
                    embed.add_field(
                        name="Instruksi",
                        value="Gunakan `!bayar all` untuk bayar slot ini",
                        inline=False
                    )
                
                await message.channel.send(embed=embed)
                
                # Trigger checks
                if slot_number == 10:
                    await manager.trigger_deadline(version)
                if slot_number == 17:
                    await manager.notify_admin_schedule(version)
                
                await manager.update_list_channel()
                
            else:
                await message.channel.send("❌ Gagal mendaftar. Silakan coba lagi.")
            
        except Exception as e:
            logger.error(f"Error in fallback register: {e}")
            await message.channel.send("❌ Terjadi kesalahan. Format: `!daftar V1 username:Player1`")
    
    async def handle_fallback_payment(self, message: discord.Message):
        """Handle fallback payment command"""
        try:
            # Parse command: !bayar slot:1 atau !bayar all
            content = message.content.lower().strip()
            
            # Get user's unpaid slots
            from database.crud import get_user_slots
            slots = await get_user_slots(
                self.bot.session,
                str(message.author.id),
                status='booked'
            )
            
            if not slots:
                await message.channel.send("✅ Semua slot Anda sudah lunas!")
                return
            
            if 'all' in content:
                # Pay all slots
                selected_slots = slots
            else:
                # Parse slot number
                slot_num = None
                if 'slot:' in content:
                    try:
                        slot_num = int(content.split('slot:')[1].split()[0])
                    except:
                        pass
                
                if slot_num:
                    selected_slots = [s for s in slots if s.slot_number == slot_num]
                    if not selected_slots:
                        await message.channel.send(f"❌ Slot {slot_num} tidak ditemukan!")
                        return
                else:
                    await message.channel.send(
                        "❌ Format salah! Gunakan: `!bayar slot:1` atau `!bayar all`"
                    )
                    return
            
            # Show payment instructions
            total = sum(s.locked_price for s in selected_slots)
            version = selected_slots[0].patungan_version
            
            embed = discord.Embed(
                title="💰 PEMBAYARAN DIBUTUHKAN",
                description=f"Total: **Rp {total:,}**",
                color=self.config.COLOR_WARNING
            )
            
            slot_list = "\n".join([f"• {s.game_username} - Rp {s.locked_price:,}" for s in selected_slots])
            embed.add_field(name="Slot", value=slot_list, inline=False)
            embed.add_field(name="Patungan", value=version, inline=True)
            embed.add_field(name="Rekening", value=self.config.DEFAULT_BANK_ACCOUNT, inline=False)
            
            embed.add_field(
                name="Instruksi",
                value="1. Transfer sesuai nominal di atas\n"
                      "2. Upload bukti TF di channel ini\n"
                      "3. Tunggu verifikasi admin",
                inline=False
            )
            
            await message.channel.send(embed=embed)
            
            # Store payment context
            self.bot.payment_processor.pending_payments[str(message.author.id)] = {
                'slots': selected_slots,
                'channel_id': message.channel.id,
                'notes': 'Payment via fallback command',
                'timestamp': message.created_at
            }
            
        except Exception as e:
            logger.error(f"Error in fallback payment: {e}")
            await message.channel.send("❌ Terjadi kesalahan. Gunakan: `!bayar slot:1` atau `!bayar all`")
    
    async def handle_cancel_request(self, message: discord.Message):
        """Handle cancel request"""
        try:
            embed = discord.Embed(
                title="❌ BATAL TICKET",
                description="Apakah Anda yakin ingin membatalkan ticket ini?",
                color=self.config.COLOR_WARNING
            )
            
            embed.add_field(
                name="Konsekuensi",
                value="• Semua slot akan dibatalkan\n• Data akan dihapus\n• Tidak bisa dikembalikan",
                inline=False
            )
            
            class ConfirmView(ui.View):
                def __init__(self, handler):
                    super().__init__(timeout=60)
                    self.handler = handler
                
                @ui.button(label="✅ Ya, Batalkan", style=discord.ButtonStyle.danger)
                async def confirm(self, interaction: discord.Interaction, button: ui.Button):
                    if interaction.user.id != message.author.id:
                        await interaction.response.send_message(
                            "❌ Hanya pemilik ticket yang bisa membatalkan!",
                            ephemeral=True
                        )
                        return
                    
                    await self.handler.process_cancellation(interaction)
                
                @ui.button(label="❌ Tidak", style=discord.ButtonStyle.secondary)
                async def cancel(self, interaction: discord.Interaction, button: ui.Button):
                    await interaction.response.edit_message(
                        content=f"{Emojis.CHECK_YES_2} Pembatalan dibatalkan.",
                        embed=None,
                        view=None
                    )
            
            view = ConfirmView(self)
            await message.channel.send(embed=embed, view=view)
            
        except Exception as e:
            logger.error(f"Error handling cancel request: {e}")
    
    async def process_cancellation(self, interaction: discord.Interaction):
        """Process ticket cancellation"""
        try:
            # Get user slots
            from database.crud import get_user_slots, update_slot_status
            
            slots = await get_user_slots(
                self.bot.session,
                str(interaction.user.id),
                patungan_version=None  # All versions
            )
            
            # Check cancellation rules (Slot 17 Rule)
            for slot in slots:
                if slot.slot_status in ['waiting_payment', 'paid']:
                    patungan = await get_patungan(self.bot.session, slot.patungan_version)
                    if patungan and patungan.current_slots >= 17:
                        await interaction.response.send_message(
                            f"{Emojis.WARNING} **GAGAL MEMBATALKAN**\n"
                            f"Slot **{slot.patungan_version}** tidak bisa dibatalkan karena peserta sudah mencapai 17++.\n"
                            f"Silakan hubungi Admin untuk bantuan.",
                            ephemeral=True
                        )
                        return
            
            # Update each slot status
            for slot in slots:
                slot.slot_status = 'kicked'
                
            
            # Update ticket status
            ticket = await get_ticket_by_channel(self.bot.session, str(interaction.channel.id))
            if ticket:
                ticket.ticket_status = 'closed'
                ticket.close_reason = 'Dibatalkan oleh user'
                ticket.closed_at = datetime.now()
            
            await self.bot.session.commit()
            
            # Send confirmation
            embed = discord.Embed(
                title=f"{Emojis.CHECK_YES_2} TICKET DIBATALKAN",
                description="Ticket dan semua slot telah dibatalkan.",
                color=self.config.COLOR_SUCCESS
            )
            
            embed.add_field(
                name="Info",
                value=f"Total slot dibatalkan: {len(slots)}\nChannel akan dihapus dalam 10 detik.",
                inline=False
            )
            
            await interaction.response.edit_message(embed=embed, view=None)
            
            # Update list channel
            from bot.patungan_manager import PatunganManager
            manager = PatunganManager(self.bot)
            await manager.update_list_channel()
            
            # Delete channel after delay
            await asyncio.sleep(10)
            await interaction.channel.delete()
            
        except Exception as e:
            logger.error(f"Error processing cancellation: {e}")
            await interaction.response.send_message(
                f"{Emojis.WARNING} Terjadi kesalahan saat membatalkan.",
                ephemeral=True
            )
    
    async def request_admin_assistance(self, message: discord.Message):
        """Request admin assistance"""
        try:
            # Get admin role
            guild = message.guild
            admin_roles = []
            for role_id in self.config.ADMIN_ROLE_IDS:
                role = guild.get_role(role_id)
                if role:
                    admin_roles.append(role)
            
            if not admin_roles:
                await message.channel.send(f"{Emojis.WARNING} Role admin tidak ditemukan!")
                return
            
            # Create request embed
            embed = discord.Embed(
                title=f"{Emojis.RING_BELL} PERMINTAAN BANTUAN ADMIN",
                description=f"User {message.author.mention} membutuhkan bantuan!",
                color=self.config.COLOR_WARNING
            )
            
            embed.add_field(name="User", value=message.author.name, inline=True)
            embed.add_field(name="Ticket", value=message.channel.mention, inline=True)
            embed.add_field(name="Waktu", value=datetime.now().strftime("%H:%M") + " WIB", inline=True)
            
            # Send to admin dashboard
            dashboard_channel = discord.utils.get(
                guild.channels,
                name=self.config.ADMIN_DASHBOARD_CHANNEL
            )
            
            if dashboard_channel:
                mentions = " ".join([r.mention for r in admin_roles])
                await dashboard_channel.send(f"{mentions}", embed=embed)
            
            # Confirm to user
            user_embed = discord.Embed(
                title=f"{Emojis.CHECK_YES_2} PERMINTAAN TERKIRIM",
                description="Permintaan bantuan telah dikirim ke admin.",
                color=self.config.COLOR_SUCCESS
            )
            
            user_embed.add_field(
                name="Info",
                value="Admin akan menghubungi Anda segera.\n"
                      "Silakan tunggu di ticket ini.",
                inline=False
            )
            
            await message.channel.send(embed=user_embed)
            
            # Log
            await create_system_log(
                session=self.bot.session,
                log_type='admin_request',
                log_level='info',
                user_id=str(message.author.id),
                action='Admin assistance requested',
                details=f'Ticket: {message.channel.name}'
            )
            
        except Exception as e:
            logger.error(f"Error requesting admin assistance: {e}")
            await message.channel.send("❌ Gagal mengirim permintaan bantuan.")
    
    async def close_ticket(self, channel_id: str, reason: str = "Ditutup oleh admin"):
        """Close a ticket"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild:
                return False
            
            channel = guild.get_channel(int(channel_id))
            if not channel:
                return False
            
            # Update database
            ticket = await get_ticket_by_channel(self.bot.session, channel_id)
            if ticket:
                ticket.ticket_status = 'closed'
                ticket.close_reason = reason
                ticket.closed_at = datetime.now()
                await self.bot.session.commit()
            
            # Send closing message
            embed = discord.Embed(
                title="🔒 TICKET DITUTUP",
                description=f"Ticket ini telah ditutup.\n**Alasan:** {reason}",
                color=self.config.COLOR_NEUTRAL
            )
            
            await channel.send(embed=embed)
            
            # Delete channel after delay
            await asyncio.sleep(10)
            await channel.delete()
            
            return True
            
        except Exception as e:
            logger.error(f"Error closing ticket: {e}")
            return False
    
    async def get_ticket_info(self, channel_id: str) -> dict | None:
        """Get ticket information"""
        try:
            ticket = await get_ticket_by_channel(self.bot.session, channel_id)
            
            if not ticket:
                return None
            
            # Get user slots
            from database.crud import get_user_slots
            slots = await get_user_slots(
                self.bot.session,
                ticket.discord_user_id
            )
            
            return {
                'user_id': ticket.discord_user_id,
                'username': ticket.discord_username,
                'opened_at': ticket.opened_at,
                'last_activity': ticket.last_activity,
                'status': ticket.ticket_status,
                'slots': [
                    {
                        'version': s.patungan_version,
                        'slot_number': s.slot_number,
                        'game_username': s.game_username,
                        'status': s.slot_status,
                        'price': s.locked_price
                    }
                    for s in slots
                ]
            }
            
        except Exception as e:
            logger.error(f"Error getting ticket info: {e}")
            return None
    
    async def send_ticket_summary(self, channel: discord.TextChannel):
        """Send ticket summary"""
        try:
            info = await self.get_ticket_info(str(channel.id))
            
            if not info:
                await channel.send(f"{Emojis.WARNING} Tidak dapat mengambil info ticket.")
                return
            
            embed = discord.Embed(
                title="📊 SUMMARY TICKET",
                color=self.config.COLOR_INFO
            )
            
            embed.add_field(name="User", value=f"<@{info['user_id']}>", inline=True)
            embed.add_field(name="Status", value=info['status'].upper(), inline=True)
            embed.add_field(name="Dibuka", value=info['opened_at'].strftime("%d/%m %H:%M") + " WIB", inline=True)
            
            if info['slots']:
                slot_info = ""
                for slot in info['slots']:
                    status_emoji = self.helpers.get_status_emoji(slot['status'])
                    slot_info += f"{status_emoji} **{slot['game_username']}** ({slot['version']})\n"
                    slot_info += f"  Slot #{slot['slot_number']} - Rp {slot['price']:,}\n"
                    slot_info += f"  Status: {slot['status'].upper()}\n\n"
                
                embed.add_field(name="📋 SLOT", value=slot_info, inline=False)
            else:
                embed.add_field(name="📋 SLOT", value="Belum ada slot", inline=False)
            
            await channel.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Error sending ticket summary: {e}")

    async def handle_channel_deletion(self, channel_id: str):
        """Handle manual channel deletion"""
        try:
            await update_ticket_status(
                self.bot.session,
                channel_id,
                'closed',
                'Channel deleted manually'
            )
        except Exception as e:
            logger.error(f"Error handling channel deletion: {e}")

    async def handle_admin_close_ticket(self, interaction: discord.Interaction):
        """Handle ticket closing by admin with rating system"""
        try:
            # 1. VALIDASI PERMISSION
            user_roles = [r.id for r in interaction.user.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
            
            if not any(role_id in user_roles for role_id in allowed_roles):
                embed = discord.Embed(
                    title=f"{Emojis.BAN} **ACCESS DENIED**",
                    description="Maaf, fitur ini hanya untuk Admin.",
                    color=self.config.COLOR_ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer()
            
            # Get ticket info before deletion
            channel = interaction.channel
            ticket = await get_ticket_by_channel(self.bot.session, str(channel.id))
            
            ticket_name = channel.name
            admin_name = interaction.user.name
            ticket_owner_id = ticket.discord_user_id if ticket else None
            
            # 2. DELETE CHANNEL
            await channel.delete()
            
            # Update DB
            if ticket:
                ticket.ticket_status = 'closed'
                ticket.close_reason = f'Closed by {admin_name}'
                ticket.closed_at = datetime.now()
                await self.bot.session.commit()
                
            # 3. KIRIM DM KE USER (RATING)
            if ticket_owner_id:
                try:
                    guild = interaction.guild
                    member = guild.get_member(int(ticket_owner_id))
                    if member:
                        view = RatingView(self.bot, ticket_name, admin_name)
                        embed = discord.Embed(title="Ticket Closed", description=f"Please rate your experience handled by **{admin_name}**.", color=self.config.COLOR_INFO)
                        embed.add_field(name="Ticket Name", value=ticket_name, inline=True)
                        embed.add_field(name="Server", value="DVN", inline=True)
                        await member.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Failed to send rating DM: {e}")
                    
        except Exception as e:
            logger.error(f"Error in admin close ticket: {e}")

    async def handle_admin_close_ticket(self, interaction: discord.Interaction):
        """Handle ticket closing by admin with rating system"""
        try:
            # 1. VALIDASI PERMISSION
            user_roles = [r.id for r in interaction.user.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
            
            if not any(role_id in user_roles for role_id in allowed_roles):
                await interaction.response.send_message("<a:07warning:1454839380769378405> Hanya Admin yang bisa tutup ticket.", ephemeral=True)
                return

            await interaction.response.defer()
            
            # Get ticket info before deletion
            channel = interaction.channel
            ticket = await get_ticket_by_channel(self.bot.session, str(channel.id))
            
            ticket_name = channel.name
            admin_name = interaction.user.name
            ticket_owner_id = ticket.discord_user_id if ticket else None
            
            # 2. DELETE CHANNEL
            await channel.delete()
            
            # Update DB
            if ticket:
                ticket.ticket_status = 'closed'
                ticket.close_reason = f'Closed by {admin_name}'
                ticket.closed_at = datetime.now()
                await self.bot.session.commit()
                
            # 3. KIRIM DM KE USER (RATING)
            if ticket_owner_id:
                try:
                    guild = interaction.guild
                    member = guild.get_member(int(ticket_owner_id))
                    if member:
                        view = RatingView(self.bot, ticket_name, admin_name)
                        embed = discord.Embed(title=f"{Emojis.CHECK_YES_2} **TICKET CLOSED • SESSION ENDED**", 
                                            description=f"Terima kasih telah mempercayai {Emojis.FIRE_BLUE} **DVN Store**.\n"
                                                        f"Sesi tiket Anda telah diselesaikan oleh Admin.\n\n"
                                                        f"{Emojis.ANNOUNCEMENTS} **Bantu kami meningkatkan layanan dengan memberi rating:**\n\n"
                                                        f"**📊 TICKET SUMMARY**\n"
                                                        f"{Emojis.TICKET} **Ticket ID:** `{ticket_name}`\n"
                                                        f"{Emojis.DISCORD_CHRISTMAS} **Server:** DVN Official\n"
                                                        f"{Emojis.VERIFIED_2} **Handled By:** `{admin_name}`",
                                            color=self.config.COLOR_SUCCESS)
                        await member.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Failed to send rating DM: {e}")
                    
        except Exception as e:
            logger.error(f"Error in admin close ticket: {e}")

    async def handle_admin_close_ticket_from_message(self, message: discord.Message):
        """Handle ticket closing by admin via command .close"""
        try:
            # 1. VALIDASI PERMISSION
            user_roles = [r.id for r in message.author.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
            
            if not any(role_id in user_roles for role_id in allowed_roles):
                await message.channel.send(f"{Emojis.WARNING} Hanya Admin yang bisa tutup ticket.")
                return

            # Get ticket info before deletion
            channel = message.channel
            ticket = await get_ticket_by_channel(self.bot.session, str(channel.id))
            
            if not ticket:
                await message.channel.send("❌ Channel ini bukan ticket yang terdaftar di database.")
                return

            ticket_name = channel.name
            admin_name = message.author.name
            ticket_owner_id = ticket.discord_user_id
            
            # 2. DELETE CHANNEL
            await channel.delete()
            
            # Update DB
            ticket.ticket_status = 'closed'
            ticket.close_reason = f'Closed by {admin_name} (.close)'
            ticket.closed_at = datetime.now()
            await self.bot.session.commit()
                
            # 3. KIRIM DM KE USER (RATING)
            if ticket_owner_id:
                try:
                    guild = message.guild
                    member = guild.get_member(int(ticket_owner_id))
                    if member:
                        view = RatingView(self.bot, ticket_name, admin_name)
                        embed = discord.Embed(title=f"{Emojis.CHECK_YES_2} **TICKET CLOSED • SESSION ENDED**", 
                                            description=f"Terima kasih telah mempercayai {Emojis.FIRE_BLUE} **DVN Store**.\n"
                                                        f"Sesi tiket Anda telah diselesaikan oleh Admin.\n\n"
                                                        f"{Emojis.ANNOUNCEMENTS} **Bantu kami meningkatkan layanan dengan memberi rating:**\n\n"
                                                        f"**📊 TICKET SUMMARY**\n"
                                                        f"{Emojis.TICKET} **Ticket ID:** `{ticket_name}`\n"
                                                        f"{Emojis.DISCORD_CHRISTMAS} **Server:** DVN Official\n"
                                                        f"{Emojis.VERIFIED_2} **Handled By:** `{admin_name}`",
                                            color=self.config.COLOR_SUCCESS)
                        await member.send(embed=embed, view=view)
                except Exception as e:
                    logger.error(f"Failed to send rating DM: {e}")
                    
        except Exception as e:
            logger.error(f"Error in admin close ticket message: {e}")

    async def create_ticket_with_product(self, interaction: discord.Interaction, product_name: str):
        """Create ticket after product selection"""
        try:
            user = interaction.user
            guild = interaction.guild
            
            # 1. CEK DUPLICATE TICKET
            # Prioritas: ID -> Nama -> Buat Baru
            category = discord.utils.get(guild.categories, id=self.config.TICKET_CATEGORY_ID)
            
            if not category:
                category = discord.utils.get(guild.categories, name="『 𝙏𝙄𝘾𝙆𝙀𝙏 𝙋𝙏𝙋𝙏 』")
            
            if not category:
                try:
                    category = await guild.create_category("『 𝙏𝙄𝘾𝙆𝙀𝙏 𝙋𝙏𝙋𝙏 』")
                except Exception as e:
                    logger.warning(f"Failed to create category: {e}")
            
            existing_channel = None
            
             # Clean username to be channel-safe
            safe_username = "".join(c for c in user.name if c.isalnum()).lower()
            # Expected channel name for this specific product
            expected_channel_name = f"{product_name.lower().replace(' ', '-')}-{safe_username}"
            
            if category:
                for ch in category.text_channels:
                    # Check by Topic (ID) or Name (Username)
                    is_user_channel = (ch.topic and str(user.id) in ch.topic) or (f"-{safe_username}" in ch.name)
                    
                    # Check if it matches the CURRENT product
                    is_user_channel = (ch.topic and str(user.id) in ch.topic) or (f"-{safe_username}" in ch.name)
                    
                    # Check if it matches the CURRENT product exactly
                    if is_user_channel and ch.name == expected_channel_name:
                        existing_channel = ch
                        break
            
            if existing_channel:
                    embed = discord.Embed(
                        title=f"{Emojis.BAN} **ACTION DENIED**",
                        description=f"⚠️ Kamu sudah punya tiket aktif untuk **{product_name}** di {existing_channel.mention}.",
                        color=self.config.COLOR_ERROR
                    )
                    await interaction.edit_original_response(content=None, embed=embed, view=None)
                    return
            
            # Check if patungan is full
            patungan = await get_patungan(self.bot.session, product_name)
            
            # Calculate current slots dynamically
            from database.models import UserSlot
            from sqlalchemy import select, func
            stmt_count = select(func.count(UserSlot.id)).where(
                UserSlot.patungan_version == product_name,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            )
            res_count = await self.bot.session.execute(stmt_count)
            current_slots = res_count.scalar() or 0

            if patungan and current_slots >= patungan.total_slots:
                embed = discord.Embed(
                    title=f"{Emojis.BAN} **FULL BOOKED**",
                    description=f"Mohon maaf, patungan **{product_name}** sudah penuh ({current_slots}/{patungan.total_slots}).\n"
                                f"Silakan tunggu kloter berikutnya atau pilih produk lain.",
                    color=self.config.COLOR_ERROR
                )
                await interaction.edit_original_response(content=None, embed=embed, view=None)
                return

            # Format: (nama_produk)-displayname_user
            # Clean username to be channel-safe
            channel_name = f"{product_name.lower().replace(' ', '-')}-{safe_username}"
            
            # Create channel
            overwrites = {
                guild.default_role: discord.PermissionOverwrite(read_messages=False),
                user: discord.PermissionOverwrite(read_messages=True, send_messages=True, attach_files=True),
                guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True)
            }
            
            # Add admin role
            for role_id in self.config.ADMIN_ROLE_IDS:
                admin_role = guild.get_role(role_id)
                if admin_role:
                    overwrites[admin_role] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
            
            channel = await guild.create_text_channel(
                name=channel_name,
                category=category,
                overwrites=overwrites,
                topic=f"Ticket for {user.name} | ID: {user.id}" # Set topic for ID detection
            )
            
            # Register in DB
            await create_user_ticket(self.bot.session, str(user.id), user.name, str(channel.id))
            
            # Send welcome
            await self.send_welcome_message(channel, user, product_name)
            
            await interaction.edit_original_response(content=f"{Emojis.CHECK_YES_2} Ticket dibuat: {channel.mention}", view=None)
            logger.info(f"{Emojis.CHECK_YES_2} Ticket created: {channel.name} for {user.name}")
            
        except Exception as e:
            logger.error(f"Error creating ticket from interaction: {e}")
            await interaction.followup.send(f"{Emojis.WARNING} Gagal membuat ticket.", ephemeral=True)

    def get_ticket_panel_data(self):
        """Get embed and view for ticket panel"""
        # Default values
        title = f"{Emojis.ICON_LUCKY} **OPEN SLOT PTPT & X8 LUCK** {Emojis.ICON_LUCKY}"
        desc = f"{Emojis.SPARKLE_1} **Halo Fisherman!** Ingin join slot Patungan (PTPT) Boost Luck?\n\n**Cara Order:**\n1️⃣ Klik tombol **{Emojis.TICKET} Buat Ticket** di bawah.\n2️⃣ Pilih **Server / Jenis Layanan** yang kamu inginkan.\n3️⃣ Lakukan pembayaran sesuai instruksi bot.\n\n*{Emojis.WARNING} Pastikan slot masih tersedia di channel Info Slot!*"

        # Load from panels.json if exists
        try:
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'panels.json')
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if 'ticket' in data:
                        title = data['ticket']['title']
                        desc = data['ticket']['description']
        except Exception as e:
            logger.error(f"Error loading panels.json: {e}")

        embed = discord.Embed(
            title=title,
            description=desc,
            color=0x2ecc71 # Emerald Green
        )
        embed.set_footer(text="DVN PTPT SYSTEM | Auto-Management")
        view = TicketPanelView(self.bot)
        return embed, view

    async def setup_ticket_panel(self):
        """Setup ticket panel in open-ticket channel"""
        try:
            guild = self.bot.get_guild(self.config.SERVER_ID)
            if not guild: return
            
            channel = guild.get_channel(self.config.OPEN_TICKET_CHANNEL_ID)
            if not channel: return
            
            # Refresh panel
            await channel.purge(limit=10)
            
            embed, view = self.get_ticket_panel_data()
            await channel.send(embed=embed, view=view)
            logger.info(f"{Emojis.CHECK_YES_2} Ticket panel setup completed")
            
        except Exception as e:
            logger.error(f"Error setting up ticket panel: {e}")
