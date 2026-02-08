import discord
from discord import app_commands
import logging
import re
from config import Config, Emojis
from database.models import UserSlot
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from bot.views import MainTicketView, TicketPanelView, RatingView

logger = logging.getLogger(__name__)

class AdminHandler:
    """Handler for admin specific commands"""
    
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.register_commands()

    def register_commands(self):
        """Register admin commands to bot tree"""
        
        @self.bot.tree.command(name="update_panel", description="Update tampilan panel tanpa hapus pesan")
        @app_commands.describe(
            panel_type="Jenis panel yang mau diupdate",
            message_id="ID Pesan (Optional, auto-detect last bot msg if empty)",
            channel_id="ID Channel (Optional, override default)"
        )
        @app_commands.choices(panel_type=[
            app_commands.Choice(name="Admin Dashboard", value="dashboard"),
            app_commands.Choice(name="Ticket Menu", value="ticket_menu"),
            app_commands.Choice(name="QRIS Info", value="qris_info")
        ])
        async def update_panel(interaction: discord.Interaction, panel_type: app_commands.Choice[str], message_id: str = None, channel_id: str = None):
            # 1. Permission Check
            user_roles = [r.id for r in interaction.user.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
            
            if not any(role_id in user_roles for role_id in allowed_roles):
                embed = discord.Embed(
                    title=f"{Emojis.BAN} **ACCESS DENIED**",
                    description="Maaf, fitur ini hanya untuk Admin.",
                    color=self.config.COLOR_ERROR
                )
                await interaction.response.send_message(embed=embed, ephemeral=True)
                return

            await interaction.response.defer(ephemeral=True)
            
            try:
                # 2. Determine Channel
                target_channel_id = None
                if channel_id:
                    target_channel_id = int(channel_id)
                else:
                    if panel_type.value == "dashboard":
                        target_channel_id = self.config.ADMIN_DASHBOARD_CHANNEL_ID
                    elif panel_type.value == "ticket_menu":
                        target_channel_id = self.config.OPEN_TICKET_CHANNEL_ID
                    elif panel_type.value == "qris_info":
                        # QRIS info usually doesn't have a fixed channel, so channel_id is preferred
                        # If not provided, try current channel
                        target_channel_id = interaction.channel_id

                channel = self.bot.get_channel(target_channel_id)
                if not channel:
                    await interaction.followup.send(f"❌ Channel tidak ditemukan (ID: {target_channel_id})", ephemeral=True)
                    return

                # 3. Determine Message
                target_message = None
                if message_id:
                    try:
                        target_message = await channel.fetch_message(int(message_id))
                    except discord.NotFound:
                        await interaction.followup.send("❌ Pesan tidak ditemukan dengan ID tersebut.", ephemeral=True)
                        return
                else:
                    # Auto-detect last message by bot
                    async for msg in channel.history(limit=10):
                        if msg.author == self.bot.user:
                            target_message = msg
                            break
                    
                    if not target_message:
                        await interaction.followup.send("❌ Tidak dapat menemukan pesan bot di channel ini. Silakan input message_id.", ephemeral=True)
                        return

                # 4. Generate New Content
                new_embed = None
                new_view = None

                if panel_type.value == "dashboard":
                    new_embed, new_view = self.bot.patungan_manager.get_admin_dashboard_data()
                
                elif panel_type.value == "ticket_menu":
                    new_embed, new_view = self.bot.ticket_handler.get_ticket_panel_data()
                
                elif panel_type.value == "qris_info":
                    new_embed = discord.Embed(title=f"{Emojis.MONEY_BAG} **PAYMENT GATEWAY**", color=self.config.COLOR_INFO)
                    new_embed.description = "**Total Tagihan: Sesuai Form**"
                    new_embed.set_image(url=self.config.QRIS_IMAGE_URL)
                    new_embed.add_field(
                        name="Instruksi Pembayaran", 
                        value="1. Scan QRIS di bawah\n2. Transfer Nominal PAS\n3. Upload Bukti di sini.", 
                        inline=False
                    )
                    # QRIS info usually doesn't have a view, or we can add one if needed
                    new_view = None 

                # 5. Update Message
                if new_embed:
                    await target_message.edit(embed=new_embed, view=new_view)
                    await interaction.followup.send(f"{Emojis.CHECK_YES_2} Panel **{panel_type.name}** berhasil diupdate!\n🔗 {target_message.jump_url}", ephemeral=True)
                    logger.info(f"Panel {panel_type.value} updated by {interaction.user} in {channel.name}")
                else:
                    await interaction.followup.send("❌ Gagal generate data panel.", ephemeral=True)

            except Exception as e:
                logger.error(f"Error updating panel: {e}")
                await interaction.followup.send(f"❌ Terjadi kesalahan: {str(e)}", ephemeral=True)

        @self.bot.tree.command(name="import_legacy", description="Import patungan lama dari channel list")
        async def import_legacy(interaction: discord.Interaction):
            # Permission check
            user_roles = [r.id for r in interaction.user.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
            if not any(role_id in user_roles for role_id in allowed_roles):
                await interaction.response.send_message("❌ Access Denied", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            count, msg = await self.bot.patungan_manager.sync_legacy_patungan(self.config.LIST_PTPT_CHANNEL_ID)
            await interaction.followup.send(f"✅ {msg}")

        @self.bot.tree.command(name="import_specific", description="Import patungan spesifik by Message ID")
        async def import_specific(interaction: discord.Interaction, message_id: str):
            # Permission check
            user_roles = [r.id for r in interaction.user.roles]
            allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
            if not any(role_id in user_roles for role_id in allowed_roles):
                await interaction.response.send_message("❌ Access Denied", ephemeral=True)
                return
            
            await interaction.response.defer(ephemeral=True)
            try:
                channel = self.bot.get_channel(self.config.LIST_PTPT_CHANNEL_ID)
                if not channel:
                    await interaction.followup.send("❌ Channel List PTPT tidak ditemukan.", ephemeral=True)
                    return

                msg = await channel.fetch_message(int(message_id))
                success = await self.bot.patungan_manager.import_patungan_from_message(msg)
                
                if success:
                    await interaction.followup.send(f"✅ Berhasil import patungan dari pesan {message_id}", ephemeral=True)
                else:
                    await interaction.followup.send(f"❌ Gagal import (Mungkin format salah atau sudah ada).", ephemeral=True)
            except Exception as e:
                await interaction.followup.send(f"❌ Error: {str(e)}", ephemeral=True)

    async def approve_payment(self, interaction: discord.Interaction, product_name: str, user: discord.Member, slots_count: int = 1):
        """
        Handle logic saat payment diapprove:
        1. Assign Role ke User
        2. Add User ke Channel (via Role/Overwrite)
        
        Note: Channel & Role harus sudah dibuat saat Create Patungan.
        """
        try:
            # Call manager to grant access (Role + Channel)
            channel = await self.bot.patungan_manager.grant_patungan_access(str(user.id), product_name, slots_count)
            
            if channel:
                print(f"[SUCCESS] User {user.display_name} access granted to {channel.name}")
                return channel
            else:
                print(f"[WARNING] Failed to grant access for {product_name}. Check if Role/Channel exists.")
                return None

        except Exception as e:
            logger.error(f"Error in approve_payment: {e}")
            return None

    async def remove_participant_slot(self, interaction: discord.Interaction, product_name: str, username: str):
        """
        Logic untuk menghapus peserta dari slot (Cancel Slot)
        """
        await interaction.response.defer(ephemeral=True)
        try:
            # 1. Cari Slot di Database
            # Mencocokkan nama produk dan username (game_username atau display_name)
            stmt = select(UserSlot).where(
                UserSlot.patungan_version == product_name,
                (UserSlot.game_username == username) | (UserSlot.display_name == username),
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            )
            result = await self.bot.session.execute(stmt)
            slot = result.scalar_one_or_none()

            if not slot:
                await interaction.followup.send(f"❌ Member **{username}** tidak ditemukan di patungan **{product_name}**.", ephemeral=True)
                return

            # Capture slot number for shifting
            removed_slot_number = slot.slot_number

            # 2. Update Status Slot -> 'kicked' (Cancelled)
            slot.slot_status = 'kicked'
            slot.slot_number = 0 # Remove from sequence
            
            # 3. Shift Up Slots (Slot 3 -> 2, etc)
            stmt_shift = select(UserSlot).where(
                UserSlot.patungan_version == product_name,
                UserSlot.slot_number > removed_slot_number,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            ).order_by(UserSlot.slot_number)
            result_shift = await self.bot.session.execute(stmt_shift)
            slots_to_shift = result_shift.scalars().all()
            
            for s in slots_to_shift:
                s.slot_number -= 1

            # 4. Update Jumlah Slot di Patungan
            from database.crud import get_patungan
            patungan = await get_patungan(self.bot.session, product_name)
            if patungan:
                try:
                    # Refresh object to ensure attributes are loaded
                    await self.bot.session.refresh(patungan)
                    if hasattr(patungan, 'current_slots'):
                        patungan.current_slots = max(0, patungan.current_slots - 1)
                except Exception as e:
                    logger.error(f"Error updating slots for {product_name}: {e}")
            
            await self.bot.session.commit()

            # 5. Refresh List Channel
            await self.bot.patungan_manager.update_list_channel()

            await interaction.followup.send(f"✅ Member **{username}** berhasil dihapus dari slot **{product_name}**. Slot dibawahnya telah dinaikkan.", ephemeral=True)
            logger.info(f"Admin {interaction.user.name} removed participant {username} from {product_name} (Slot {removed_slot_number})")

        except Exception as e:
            logger.error(f"Error removing participant: {e}")
            await interaction.followup.send(f"❌ Terjadi kesalahan: {str(e)}", ephemeral=True)

    async def cancel_slot_by_number(self, product_name: str, slot_number: int, admin_user: discord.User):
        """
        Logic untuk membatalkan slot berdasarkan nomor slot.
        """
        try:
            # 1. Cari Slot di Database
            stmt = select(UserSlot).options(selectinload(UserSlot.ticket)).where(
                UserSlot.patungan_version == product_name,
                UserSlot.slot_number == slot_number,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            )
            result = await self.bot.session.execute(stmt)
            slot = result.scalar_one_or_none()

            if not slot:
                return False, f"❌ Slot **#{slot_number}** tidak ditemukan atau sudah dibatalkan di patungan **{product_name}**."

            game_username = slot.game_username

            # 2. Update Status Slot -> 'kicked'
            slot.slot_status = 'kicked'
            slot.slot_number = 0 # Remove from sequence
            
            # 3. Shift Up Slots
            stmt_shift = select(UserSlot).where(
                UserSlot.patungan_version == product_name,
                UserSlot.slot_number > slot_number,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            ).order_by(UserSlot.slot_number)
            result_shift = await self.bot.session.execute(stmt_shift)
            slots_to_shift = result_shift.scalars().all()
            
            for s in slots_to_shift:
                s.slot_number -= 1
            
            # 4. Update Jumlah Slot di Patungan (to be consistent)
            from database.crud import get_patungan
            patungan = await get_patungan(self.bot.session, product_name)
            if patungan:
                try:
                    # Refresh object to ensure attributes are loaded
                    await self.bot.session.refresh(patungan)
                    if hasattr(patungan, 'current_slots'):
                        patungan.current_slots = max(0, patungan.current_slots - 1)
                except Exception as e:
                    logger.error(f"Error updating slots for {product_name}: {e}")
            
            # 5. Commit changes to DB
            await self.bot.session.commit()

            # 6. Refresh List Channel
            await self.bot.patungan_manager.update_list_channel()

            logger.info(f"Admin {admin_user.name} cancelled slot #{slot_number} ({game_username}) from {product_name}")
            
            # 7. Notify user in ticket
            try:
                if slot.ticket and slot.ticket.ticket_channel_id:
                    ticket_channel = self.bot.get_channel(int(slot.ticket.ticket_channel_id))
                    if ticket_channel:
                        await ticket_channel.send(f"ℹ️ Slot **#{slot_number}** ({game_username}) untuk patungan **{product_name}** telah dibatalkan oleh admin {admin_user.mention}.")
            except Exception as e:
                logger.error(f"Failed to send cancellation notice to ticket channel: {e}")

            return True, f"✅ Slot **#{slot_number}** ({game_username}) di patungan **{product_name}** berhasil dibatalkan dan slot dirapikan."

        except Exception as e:
            logger.error(f"Error cancelling slot by number: {e}")
            await self.bot.session.rollback()
            return False, f"❌ Terjadi kesalahan: {str(e)}"

    async def handle_setup_tutorial_command(self, message: discord.Message):
        """Handle .setup_tutorial command"""
        # Permission check
        user_roles = [r.id for r in message.author.roles]
        allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
        if not any(role_id in user_roles for role_id in allowed_roles):
            await message.channel.send("❌ Access Denied")
            return
        
        channel = self.bot.get_channel(self.config.TUTORIAL_CHANNEL_ID)
        if not channel:
            await message.channel.send(f"❌ Channel Tutorial tidak ditemukan (ID: {self.config.TUTORIAL_CHANNEL_ID})")
            return

        # Optional: Purge old messages to keep it clean
        try:
            await channel.purge(limit=10)
        except:
            pass

        # Create Multiple Embeds (Cards style)
        embeds = []

        # 1. Header
        embed_header = discord.Embed(
            title="📚 PANDUAN LENGKAP ORDER PTPT X8",
            description="Ikuti langkah-langkah di bawah ini untuk memesan slot Patungan (PTPT).",
            color=self.config.COLOR_GOLD
        )
        embeds.append(embed_header)
        
        # 2. Step 1
        embed1 = discord.Embed(
            title="1️⃣ BUAT TICKET",
            description=f"• Pergi ke channel <#{self.config.OPEN_TICKET_CHANNEL_ID}>\n• Klik tombol **`🎫 Buat Ticket`**\n• Pilih produk yang tersedia (V1, V2, dll)",
            color=self.config.COLOR_INFO
        )
        embeds.append(embed1)
        
        # 3. Step 2
        embed2 = discord.Embed(
            title="2️⃣ DAFTAR SLOT",
            description="• Masuk ke channel ticket yang baru dibuat\n• Klik tombol **`📝 Daftar Slot`**\n• Isi **Username Roblox** & **Display Name**\n• Pilih jumlah slot",
            color=self.config.COLOR_INFO
        )
        embeds.append(embed2)
        
        # 4. Step 3
        embed3 = discord.Embed(
            title="3️⃣ PEMBAYARAN (PAYMENT)",
            description="• Klik tombol **`💳 Payment`**\n• Pilih metode (QRIS / Bank)\n• Transfer nominal **PAS** (sesuai tagihan)\n• **Upload Bukti Transfer** di chat ticket",
            color=self.config.COLOR_INFO
        )
        embeds.append(embed3)
        
        # 5. Step 4
        embed4 = discord.Embed(
            title="4️⃣ VERIFIKASI",
            description="• Tunggu Admin memverifikasi pembayaran\n• Jika valid, Bot akan memberikan Role & Akses Channel\n• Selesai! Tunggu jadwal main.",
            color=self.config.COLOR_SUCCESS
        )
        embed4.set_footer(text="DVN Store System • Ikuti aturan agar transaksi lancar")
        embeds.append(embed4)
            
        # Send all embeds in one message
        await channel.send(embeds=embeds)
        
        await message.channel.send(f"✅ Tutorial berhasil dikirim ke {channel.mention}")