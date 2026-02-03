# bot/forms.py
import discord
from discord import ui
from discord.ext import commands
from config import Config, Emojis
from database.crud import create_patungan, get_patungan, get_setting, set_setting
from utils.validators import validate_price
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class CreatePatunganForm(ui.Modal, title='➕ Buat Patungan Baru'):
    def __init__(self, bot, use_script, start_mode):
        super().__init__(timeout=300)
        self.bot = bot
        self.config = Config()
        self.use_script = use_script
        self.start_mode = start_mode
        
        # Product Name
        self.product_name = ui.TextInput(
            label='Versi (V1, V2, ...)',
            placeholder='Contoh: V1, V2, HIGGS-1M',
            style=discord.TextStyle.short,
            required=True,
            max_length=100
        )
        self.add_item(self.product_name)
        
        
        # HARGA PER SLOT (Admin menentukan)
        self.price = ui.TextInput(
            label='Harga per Slot (Rp)',
            placeholder='500000',
            style=discord.TextStyle.short,
            required=True,
            max_length=10
        )
        self.add_item(self.price)
        
        # Max Slots
        self.max_slots = ui.TextInput(
            label='Max Slot',
            placeholder='19',
            style=discord.TextStyle.short,
            required=True,
            default='19',
            max_length=2
        )
        self.add_item(self.max_slots)

        # Duration
        self.duration = ui.TextInput(
            label='Durasi (Jam)',
            placeholder='Contoh: 24',
            style=discord.TextStyle.short,
            required=True,
            default='24',
            max_length=3
        )
        self.add_item(self.duration)

        # Schedule (Only if start_mode is schedule, but we add it anyway as optional if modal allows, or just required if mode is schedule)
        if self.start_mode == 'schedule':
            self.schedule_input = ui.TextInput(
                label='Jadwal Start (YYYY-MM-DD HH:MM) WIB',
                placeholder='2024-12-31 20:00',
                style=discord.TextStyle.short,
                required=True,
                max_length=20
            )
            self.add_item(self.schedule_input)
    
    async def on_submit(self, interaction: discord.Interaction):
        """Handle form submission"""
        try:
            product_name = self.product_name.value.strip().upper()
            
            # Validate and parse price
            price_str = self.price.value.replace('.', '').replace(',', '').strip()
            if not price_str.isdigit():
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Harga harus berupa angka!",
                    ephemeral=True
                )
                return
            
            price = int(price_str)
            
            # Validate price
            price_valid, price_msg = validate_price(price)
            if not price_valid:
                await interaction.response.send_message(
                    f"{Emojis.WARNING} {price_msg}",
                    ephemeral=True
                )
                return
            
            max_slots = int(self.max_slots.value)
            duration_hours = int(self.duration.value)
            
            start_schedule = None
            if self.start_mode == 'schedule':
                try:
                    start_schedule = datetime.strptime(self.schedule_input.value, "%Y-%m-%d %H:%M")
                except ValueError:
                    await interaction.response.send_message(f"{Emojis.WARNING} Format tanggal salah! Gunakan YYYY-MM-DD HH:MM", ephemeral=True)
                    return
            
            # Defer response because creating multiple might take time
            await interaction.response.defer(ephemeral=True)
            
            # Create Patungan in DB
            from database.models import Patungan
            
            # Create Patungan directly (Force save new fields)
            new_patungan = Patungan(
                product_name=product_name,
                price=price,
                total_slots=max_slots,
                status='open',
                use_script=self.use_script,
                start_mode=self.start_mode,
                duration_hours=duration_hours,
                start_schedule=start_schedule
            )
            self.bot.session.add(new_patungan)
            await self.bot.session.commit()
            
            # 1. Send Announcement
            announcement_channel = interaction.guild.get_channel(self.config.ANNOUNCEMENTS_CHANNEL_ID)
            if announcement_channel:
                embed = discord.Embed(
                    title=f"{Emojis.ANNOUNCEMENTS} **NEW SESSION OPENED**",
                    description=f"{Emojis.FIRE_LIGHT_BLUE} **{product_name}** TELAH DIBUKA!\n**LIMITED SLOT** • **FAST RESPONSE** {Emojis.ROCKET}",
                    color=self.config.COLOR_GOLD
                )
                embed.add_field(name=f"{Emojis.MONEY_BAG} **Price:**", value=f"Rp {price:,}", inline=True)
                embed.add_field(name=f"{Emojis.ANIMATED_ARROW_BLUE} **Slot:**", value=f"{max_slots} Slot Available", inline=True)
                
                script_text = f"{Emojis.CHECK_YES_2} Yes" if self.use_script == "Yes" else f"{Emojis.BAN} No"
                embed.add_field(name="📜 **Script:**", value=script_text, inline=True)
                embed.add_field(name="⏳ **Durasi:**", value=f"{duration_hours} Jam", inline=True)
                
                await announcement_channel.send(embed=embed)
            
            # 2. Update List
            await self.bot.patungan_manager.update_list_channel()
            
            # Build result embed
            embed = discord.Embed(
                title=f"{Emojis.VERIFIED_2} Patungan Dibuat",
                description=f"Produk: {product_name}\nHarga: {price}\nSlot: {max_slots}",
                color=self.config.COLOR_SUCCESS
            )
            
            await interaction.followup.send(embed=embed)
                
        except ValueError as e:
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{Emojis.WARNING} Input tidak valid: {str(e)}", ephemeral=True)
            else:
                await interaction.followup.send(f"{Emojis.WARNING} Input tidak valid: {str(e)}")
        except Exception as e:
            logger.error(f"Error creating patungan: {e}")
            await self.bot.session.rollback()
            if not interaction.response.is_done():
                await interaction.response.send_message(f"{Emojis.WARNING} Terjadi kesalahan.", ephemeral=True)
            else:
                await interaction.followup.send(f"{Emojis.WARNING} Terjadi kesalahan.")

class DaftarSlotModal(ui.Modal, title='📝 Daftar Slot'):
    """Form untuk user mendaftar slot"""
    def __init__(self, bot, product_name):
        super().__init__(timeout=300)
        self.bot = bot
        self.config = Config()
        self.product_name = product_name
        
        # Jumlah Slot
        self.slot_count = ui.TextInput(
            label='Jumlah Slot',
            placeholder='1',
            style=discord.TextStyle.short,
            required=True,
            max_length=2,
            default='1'
        )
        self.add_item(self.slot_count)
        
        # Username Roblox
        self.roblox_user = ui.TextInput(
            label='Username Roblox (@user1, @user2)',
            placeholder='@user1 atau @user1, @user2',
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.roblox_user)
        
        # Display Name
        self.display_name = ui.TextInput(
            label='Display Name (nick1, nick2)',
            placeholder='Nickname atau nick1, nick2',
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.display_name)
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            product_name = self.product_name
            
            # Validate slot count
            if not self.slot_count.value.isdigit():
                await interaction.response.send_message(f"{Emojis.WARNING} Jumlah slot harus angka!", ephemeral=True)
                return
            
            count = int(self.slot_count.value)
            if count < 1:
                await interaction.response.send_message(f"{Emojis.WARNING} Minimal 1 slot!", ephemeral=True)
                return

            # Parse usernames (comma separated)
            raw_roblox = self.roblox_user.value.strip()
            roblox_users = [u.strip() for u in raw_roblox.split(',')]
            
            # Parse display names (comma separated)
            raw_display = self.display_name.value.strip()
            display_names = [d.strip() for d in raw_display.split(',')]
            
            # Validate count match if multiple provided
            if len(roblox_users) > 1 and len(roblox_users) != count:
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Jumlah username ({len(roblox_users)}) tidak sesuai dengan jumlah slot ({count})!", 
                    ephemeral=True
                )
                return
            
            # Get patungan info (New Model)
            from database.models import Patungan, UserSlot
            from sqlalchemy import select, func
            
            stmt = select(Patungan).where(Patungan.product_name == product_name)
            result = await self.bot.session.execute(stmt)
            patungan = result.scalar_one_or_none()
            
            if not patungan:
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Patungan tidak ditemukan!",
                    ephemeral=True
                )
                return
            if patungan.status != 'open':
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Patungan {product_name} sedang {patungan.status}",
                    ephemeral=True
                )
                return
            
            # Check slots availability (Count existing slots)
            stmt_count = select(func.count(UserSlot.id)).where(UserSlot.patungan_version == product_name)
            res_count = await self.bot.session.execute(stmt_count)
            current_slots = res_count.scalar() or 0

            if current_slots + count > patungan.total_slots:
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Slot tidak cukup! Tersisa: {patungan.total_slots - current_slots}",
                    ephemeral=True
                )
                return
            
            # Register slot
            from database.crud import create_user_slot
            from bot.patungan_manager import PatunganManager
            
            manager = PatunganManager(self.bot)
            
            created_slots = []
            
            for i in range(count):
                slot_number = current_slots + 1 + i
                
                # Determine username for this slot
                if len(roblox_users) == 1:
                    u_name = roblox_users[0]
                else:
                    u_name = roblox_users[i]
                
                # Determine display name
                if len(display_names) == 1:
                    d_name = display_names[0]
                elif len(display_names) == len(roblox_users):
                    d_name = display_names[i]
                else:
                    d_name = u_name # Fallback
                
                success, slot = await create_user_slot(
                    session=self.bot.session,
                    user_id=str(interaction.user.id),
                    username=interaction.user.name,
                    ticket_channel_id=str(interaction.channel.id),
                    patungan_version=product_name, # Mapping product_name to version field
                    slot_number=slot_number,
                    game_username=u_name, # Using roblox user as game username
                    display_name=d_name,
                    locked_price=patungan.price
                )
                
                if success:
                    created_slots.append(slot_number)
            
            await self.bot.session.commit()
            
            if created_slots:
                slot_str = ", ".join(map(str, created_slots))
                
                # Send confirmation embed
                embed = discord.Embed(
                    title=f'{Emojis.CHECK_YES_2} SLOT TERDAFTAR',
                    description=f'Berhasil memesan {count} slot.',
                    color=self.config.COLOR_SUCCESS
                )
                embed.add_field(name='Patungan', value=product_name, inline=True)
                embed.add_field(name='Nomor Slot', value=slot_str, inline=True)
                price_display = f"Rp {patungan.price:,}" if patungan.price > 0 else "GRATIS"
                embed.add_field(name='Harga/Slot', value=price_display, inline=True)
                
                # Show usernames
                users_str = ", ".join(roblox_users) if len(roblox_users) > 1 else roblox_users[0]
                embed.add_field(name='Roblox User', value=users_str, inline=False)
                
                # Check for instant payment slots (11-19)
                instant_pay = any(11 <= s <= 19 for s in created_slots)
                if instant_pay:
                    embed.add_field(name=f"{Emojis.WARNING} PERHATIAN", value="Slot 11-19 WAJIB bayar langsung!", inline=False)
                
                await interaction.response.send_message(embed=embed)
                
                # Update list channel
                # FIX: Ensure list is updated on add-on
                await manager.update_list_channel()
                
            else:
                await interaction.response.send_message(
                    f"{Emojis.WARNING} Gagal mendaftar. Silakan coba lagi.",
                    ephemeral=True
                )
                
        except Exception as e:
            logger.error(f"Error in registration: {e}")
            await interaction.response.send_message(
                f"{Emojis.WARNING} Terjadi kesalahan saat mendaftar.",
                ephemeral=True
            )

class PaymentFormView(ui.View):
    """View untuk tombol bayar sekarang (Instant Payment)"""
    def __init__(self, bot, slots):
        super().__init__(timeout=60)
        self.bot = bot
        self.slots = slots
    
    @ui.button(label=f"{Emojis.PRICE_TAG_USD} Bayar Sekarang", style=discord.ButtonStyle.success)
    async def pay_now(self, interaction: discord.Interaction, button: ui.Button):
        form = PaymentForm(self.bot, self.slots)
        await interaction.response.send_modal(form)

class SetPaymentImageForm(ui.Modal, title='🖼️ Set Payment Image'):
    """Form to set payment image URL"""
    def __init__(self, bot):
        super().__init__(timeout=300)
        self.bot = bot
        
        self.image_url = ui.TextInput(
            label='Image URL',
            placeholder='https://...',
            style=discord.TextStyle.short,
            required=True
        )
        self.add_item(self.image_url)
        
    async def on_submit(self, interaction: discord.Interaction):
        try:
            url = self.image_url.value.strip()
            await set_setting(self.bot.session, 'payment_image_url', url)
            await interaction.response.send_message(f"{Emojis.CHECK_YES_2} Payment image updated!\nPreview: {url}", ephemeral=True)
        except Exception as e:
            logger.error(f"Error setting payment image: {e}")
            await interaction.response.send_message(f"{Emojis.WARNING} Error saving setting.", ephemeral=True)