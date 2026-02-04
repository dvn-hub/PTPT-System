import discord
from discord import app_commands
import logging
import re
from config import Config, Emojis
from database.models import UserSlot
from sqlalchemy import select

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

    async def approve_payment(self, interaction: discord.Interaction, product_name: str, user: discord.Member, slots_count: int = 1):
        """
        Handle logic saat payment diapprove:
        1. Buat/Cek Group Channel (Shared)
        2. Add User ke Group Channel
        """
        # --- SETUP AWAL ---
        guild = interaction.guild
        if not guild:
            print("[ERROR] Guild is None")
            return None

        # Permission Setup (User & Bot)
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(read_messages=False),
            guild.me: discord.PermissionOverwrite(read_messages=True, send_messages=True, manage_channels=True),
            user: discord.PermissionOverwrite(read_messages=True, send_messages=True)
        }
        
        # Add Admin Roles (Overlord & Warden)
        SERVER_OVERLORD_ID = 1448349975560982628
        SERVER_WARDEN_ID = 1448569110899195914
        
        overlord = guild.get_role(SERVER_OVERLORD_ID)
        warden = guild.get_role(SERVER_WARDEN_ID)
        
        if overlord:
            overwrites[overlord] = discord.PermissionOverwrite(read_messages=True, send_messages=True)
        if warden:
            overwrites[warden] = discord.PermissionOverwrite(read_messages=True, send_messages=True)

        # Bersihkan nama channel
        clean_name = re.sub(r'[^a-z0-9]', '-', product_name.lower()).strip('-')
        channel_name = f"{clean_name}-vip"

        # 1. Tentukan KATEGORI TARGET
        # Prioritas: Cari by Name "『 𝙋𝙏𝙋𝙏 𝙓8 』" -> Cari by ID -> Buat Baru
        CATEGORY_NAME = "『 𝙋𝙏𝙋𝙏 𝙓8 』"
        target_category = discord.utils.get(guild.categories, name=CATEGORY_NAME)
        
        if not target_category:
            # Fallback ID (Old Category)
            GROUP_CATEGORY_ID = 1467454477337362516
            target_category = guild.get_channel(GROUP_CATEGORY_ID)
        
        # 2. PRINT DEBUG
        print(f"[DEBUG] Mencoba buat channel: {channel_name}")
        print(f"[DEBUG] Target Category: {target_category} (None artinya tidak ketemu)")
        
        # 3. LOGIC PEMBUATAN CHANNEL (Anti-Crash)
        new_channel = None
        try:
            # Cek dulu channel sudah ada atau belum
            existing_channel = discord.utils.get(guild.text_channels, name=channel_name)
            
            if existing_channel:
                print(f"[DEBUG] Channel sudah ada: {existing_channel.name}")
                new_channel = existing_channel
            else:
                # KALAU BELUM ADA -> BUAT BARU
                if target_category:
                    # Skenario A: Kategori Ketemu -> Buat di dalamnya
                    print("[DEBUG] Membuat channel DI DALAM Kategori.")
                    new_channel = await target_category.create_text_channel(
                        name=channel_name,
                        overwrites=overwrites,
                        topic=f"Group Chat untuk {product_name}"
                    )
                else:
                    # Skenario B: Kategori Hilang -> Buat Kategori Baru lalu buat channel
                    print(f"[WARNING] Kategori '{CATEGORY_NAME}' tidak ada. Membuat baru...")
                    try:
                        target_category = await guild.create_category(CATEGORY_NAME)
                        new_channel = await target_category.create_text_channel(
                            name=channel_name,
                            overwrites=overwrites,
                            topic=f"Group Chat untuk {product_name}"
                        )
                    except Exception as e:
                        print(f"[ERROR] Gagal buat kategori: {e}. Fallback ke Root.")
                        new_channel = await interaction.guild.create_text_channel(
                            name=channel_name,
                            overwrites=overwrites,
                            topic=f"Group Chat untuk {product_name}"
                        )
                
                # Send Welcome Header for new channel
                embed = discord.Embed(
                    title=f"{Emojis.CONFETTI_POPPER} WELCOME TO {product_name.upper()} GROUP",
                    description=f"Channel ini adalah grup chat khusus untuk **VIP Member {product_name}**.\nSilakan berdiskusi dan tunggu instruksi admin.",
                    color=self.config.COLOR_GOLD
                )
                await new_channel.send(embed=embed)
            
            # 4. TAMBAHKAN USER KE CHANNEL (Apapun skenarionya)
            if user and new_channel:
                await new_channel.set_permissions(user, read_messages=True, send_messages=True)
                await new_channel.send(f"Selamat datang {user.mention} di grup patungan! Anda memiliki **{slots_count}** slot.")
                print(f"[SUCCESS] User {user.display_name} ditambahkan ke {new_channel.name}")
            
            return new_channel
            
        except Exception as e:
            print(f"[CRITICAL ERROR] Gagal buat channel peserta: {e}")
            # Lanjut codingan, jangan return. Biar database tetap ke-update.
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

            # 2. Update Status Slot -> 'kicked' (Cancelled)
            slot.slot_status = 'kicked'
            
            # 3. Update Jumlah Slot di Patungan
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

            # 4. Refresh List Channel
            await self.bot.patungan_manager.update_list_channel()

            await interaction.followup.send(f"✅ Member **{username}** berhasil dihapus dari slot **{product_name}**.", ephemeral=True)
            logger.info(f"Admin {interaction.user.name} removed participant {username} from {product_name}")

        except Exception as e:
            logger.error(f"Error removing participant: {e}")
            await interaction.followup.send(f"❌ Terjadi kesalahan: {str(e)}", ephemeral=True)