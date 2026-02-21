# bot/views.py
import discord
from discord import ui
from bot.forms import CreatePatunganForm, DaftarSlotModal, SetPaymentImageForm, PaymentForm
from database.crud import get_user_slots, update_payment_status, get_slot, get_available_patungans, get_all_patungans, get_ticket_by_channel
from config import Config, Emojis
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

def is_admin(interaction: discord.Interaction, config: Config) -> bool:
    """Check if user has admin privileges (Admin, Overlord, or Warden)"""
    user_role_ids = [r.id for r in interaction.user.roles]
    allowed_ids = config.ADMIN_ROLE_IDS + [
        config.SERVER_OVERLORD_ROLE_ID,
        config.SERVER_WARDEN_ROLE_ID
    ]
    return any(rid in user_role_ids for rid in allowed_ids)

class MainTicketView(ui.View):
    """Main view for ticket channels"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = Config()
    
    @ui.button(label='📝 Daftar Slot', style=discord.ButtonStyle.primary, custom_id='daftar_slot')
    async def daftar_slot(self, interaction: discord.Interaction, button: ui.Button):
        """Show registration modal"""
        try:
            channel_name = interaction.channel.name
            
            # Verify patungan exists
            from database.models import Patungan
            from sqlalchemy import select
            
            # Get all patungans to match against channel name
            stmt = select(Patungan)
            result = await self.bot.session.execute(stmt)
            patungans = result.scalars().all()
            
            patungan = None
            # Sort by length descending to match longest prefix first (e.g. HIGGS-1M vs HIGGS)
            for p in sorted(patungans, key=lambda x: len(x.product_name), reverse=True):
                # Discord replaces spaces with hyphens in channel names
                sanitized_product_name = p.product_name.lower().replace(' ', '-')
                prefix = f"{sanitized_product_name}-"
                if channel_name.startswith(prefix):
                    patungan = p
                    break

            if not patungan:
                await interaction.response.send_message(
                    "❌ Patungan tidak ditemukan untuk channel ini.",
                    ephemeral=True
                )
                return

            # Calculate available slots
            from database.models import UserSlot
            from sqlalchemy import select, func
            stmt_count = select(func.count(UserSlot.id)).where(
                UserSlot.patungan_version == patungan.product_name,
                UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
            )
            res_count = await self.bot.session.execute(stmt_count)
            current_slots = res_count.scalar() or 0
            remaining = patungan.total_slots - current_slots
            
            # Show Select View instead of Modal directly
            view = SelectSlotCountView(self.bot, patungan.product_name, remaining)
            await interaction.response.send_message("Mau daftar berapa slot?", view=view, ephemeral=True)
            
        except Exception as e:
            logger.error(f"Error showing daftar slot modal: {e}")
            await interaction.response.send_message(
                "❌ Terjadi kesalahan.",
                ephemeral=True
            )
    
    @ui.button(label='💳 Payment', style=discord.ButtonStyle.success, custom_id='payment_button')
    async def payment_button(self, interaction: discord.Interaction, button: ui.Button):
        """Show payment method selection"""
        # Calculate total amount for display
        from database.models import UserSlot
        from sqlalchemy import select

        # Try to get slots specific to this ticket channel first
        ticket = await get_ticket_by_channel(self.bot.session, str(interaction.channel_id))
        slots = []
        
        if ticket:
             stmt = select(UserSlot).where(
                UserSlot.ticket_id == ticket.id,
                UserSlot.slot_status == 'booked'
            )
             result = await self.bot.session.execute(stmt)
             slots = result.scalars().all()
        else:
             # Fallback to global user slots if not in a ticket channel (unlikely for this view)
             slots = await get_user_slots(self.bot.session, str(interaction.user.id), status='booked')

        if not slots:
            await interaction.response.send_message(
                f"{Emojis.WARNING} **Anda belum terdaftar di slot manapun atau tagihan sudah lunas.**\nSilakan klik tombol **📝 Daftar Slot** terlebih dahulu jika belum mendaftar.",
                ephemeral=True
            )
            return

        total_amount = sum(s.locked_price for s in slots)
        
        view = PaymentMethodView(self.bot, total_amount)
        await interaction.response.send_message(
            "Silakan transfer dengan nominal pas. Mau transfer via apa?",
            view=view,
            ephemeral=True
        )
    
    @ui.button(label='🔒 Close Ticket', style=discord.ButtonStyle.danger, custom_id='close_ticket_btn')
    async def close_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Handle close ticket button"""
        await self.bot.ticket_handler.handle_admin_close_ticket(interaction)

class SelectSlotCountView(ui.View):
    """View to select number of slots before registration"""
    def __init__(self, bot, product_name, max_slots):
        super().__init__(timeout=60)
        self.bot = bot
        self.product_name = product_name
        
        # Limit to 2 because Modal max components = 5
        # We need 2 fields per slot (Username + Display), so max 2 slots = 4 fields
        limit = min(max_slots, 2)
        
        options = []
        if limit < 1:
            options.append(discord.SelectOption(label="Full", value="0", description="Slot Penuh"))
        else:
            for i in range(1, limit + 1):
                options.append(discord.SelectOption(
                    label=f"{i} Slot",
                    value=str(i),
                    description=f"Daftar {i} slot sekaligus"
                ))
            
        select = ui.Select(placeholder="Pilih Jumlah Slot...", options=options, disabled=(limit < 1))
        select.callback = self.callback
        self.add_item(select)
        
    async def callback(self, interaction: discord.Interaction):
        count = int(interaction.data['values'][0])
        if count > 0:
            modal = DaftarSlotModal(self.bot, self.product_name, count)
            await interaction.response.send_modal(modal)
        else:
            await interaction.response.send_message("Slot penuh!", ephemeral=True)

class PaymentMethodView(ui.View):
    """View to select payment method"""
    def __init__(self, bot, total_amount=0):
        super().__init__(timeout=60)
        self.bot = bot
        self.total_amount = total_amount
        self.config = Config()

    @ui.button(label='QRIS', style=discord.ButtonStyle.primary)
    async def qris_method(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(title=f"{Emojis.MONEY_BAG} **PAYMENT GATEWAY**", color=self.config.COLOR_INFO)
        
        amount_display = f"Rp {self.total_amount:,}" if self.total_amount > 0 else "Sesuai Tagihan"
        embed.description = f"**Total Tagihan: {amount_display}**"
        
        embed.set_image(url=self.config.QRIS_IMAGE_URL)
        
        embed.add_field(
            name="Instruksi Pembayaran", 
            value="1. Scan QRIS di bawah\n2. Transfer Nominal PAS\n3. Upload Bukti di sini.", 
            inline=False
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @ui.button(label='Bank Transfer', style=discord.ButtonStyle.secondary)
    async def bank_method(self, interaction: discord.Interaction, button: ui.Button):
        embed = discord.Embed(title="BANK TRANSFER", color=self.config.COLOR_INFO)
        embed.add_field(name="Rekening", value=self.config.DEFAULT_BANK_ACCOUNT)
        embed.add_field(name="Instruksi", value="1. Transfer ke rekening di atas\n2. Transfer nominal PAS\n3. Upload bukti screenshot di channel ini.")
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

class ProductSelectView(ui.View):
    """View to select product before opening ticket"""
    def __init__(self, bot, options):
        super().__init__(timeout=60)
        self.bot = bot
        
        select = ui.Select(
            placeholder="Pilih Produk...",
            options=options,
            min_values=1,
            max_values=1
        )
        select.callback = self.callback
        self.add_item(select)
    
    async def callback(self, interaction: discord.Interaction):
        version = interaction.data['values'][0]
        await interaction.response.defer(ephemeral=True)
        await self.bot.ticket_handler.create_ticket_with_product(interaction, version)

class AdminDashboardView(ui.View):
    """Admin dashboard view"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @ui.button(label='➕ Buat Patungan', style=discord.ButtonStyle.success, custom_id='admin_create_patungan')
    async def create_patungan(self, interaction: discord.Interaction, button: ui.Button):
        """Show create patungan form"""
        # Check admin permission
        if not is_admin(interaction, self.bot.config):
            await interaction.response.send_message(
                "❌ Hanya admin yang bisa menggunakan fitur ini.",
                ephemeral=True
            )
            return
        
        view = CreatePatunganWizardView(self.bot)
        await interaction.response.send_message("Silakan pilih konfigurasi patungan:", view=view, ephemeral=True)
    
    @ui.button(label='📋 Kelola Patungan', style=discord.ButtonStyle.primary, custom_id='admin_manage_patungan')
    async def manage_patungan(self, interaction: discord.Interaction, button: ui.Button):
        """Show manage patungan view"""
        from bot.patungan_manager import PatunganManager
        manager = PatunganManager(self.bot)
        
        embed = await manager.get_admin_patungan_list()
        view = ManagePatunganView(self.bot)
        
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    
    @ui.button(label='💰 Verifikasi Pembayaran', style=discord.ButtonStyle.primary, custom_id='admin_verify_payments')
    async def verify_payments(self, interaction: discord.Interaction, button: ui.Button):
        """Show pending payments"""
        from database.crud import get_pending_payments
        from bot.payment_processor import PaymentProcessor
        from bot.payment_processor import PaymentVerificationView
        
        processor = PaymentProcessor(self.bot)
        payments = await get_pending_payments(self.bot.session)
        
        if not payments:
            await interaction.response.send_message(
                "✅ Tidak ada pembayaran pending.",
                ephemeral=True
            )
            return
        
        # Show first payment
        payment = payments[0]
        embed = await processor.create_payment_embed(payment)
        view = PaymentVerificationView(self.bot, payment, payments)
        
        await interaction.response.send_message(embed=embed, view=view)
    
    @ui.button(label='🔄 Refresh List PTPT', style=discord.ButtonStyle.secondary, custom_id='admin_refresh_list', row=1)
    async def refresh_list(self, interaction: discord.Interaction, button: ui.Button):
        """Refresh list channel"""
        from bot.patungan_manager import PatunganManager
        manager = PatunganManager(self.bot)
        await manager.update_list_channel()
        await interaction.response.send_message("✅ List PTPT refreshed!", ephemeral=True)

    @ui.button(label='🖼️ Set Payment Image', style=discord.ButtonStyle.secondary, custom_id='admin_set_payment_image', row=1)
    async def set_payment_image(self, interaction: discord.Interaction, button: ui.Button):
        """Set payment image URL"""
        # Check admin permission
        if not is_admin(interaction, self.bot.config):
            await interaction.response.send_message("❌ Hanya admin.", ephemeral=True)
            return
            
        form = SetPaymentImageForm(self.bot)
        await interaction.response.send_modal(form)

    @ui.button(label='🗑️ Hapus Member', style=discord.ButtonStyle.danger, custom_id='admin_remove_participant', row=2)
    async def remove_participant(self, interaction: discord.Interaction, button: ui.Button):
        """Show remove member selection"""
        # Check admin permission
        if not is_admin(interaction, self.bot.config):
            await interaction.response.send_message("❌ Hanya admin.", ephemeral=True)
            return
            
        # Get all patungans
        patungans = await get_all_patungans(self.bot.session)
        if not patungans:
            await interaction.response.send_message("❌ Tidak ada patungan.", ephemeral=True)
            return
            
        # Menggunakan View Select Product yang baru
        view = RemoveParticipantSelectProductView(self.bot, patungans)
        await interaction.response.send_message("Pilih patungan:", view=view, ephemeral=True)

    @ui.button(label='🗑️ Hapus Patungan', style=discord.ButtonStyle.danger, custom_id='admin_delete_patungan', row=1)
    async def delete_patungan(self, interaction: discord.Interaction, button: ui.Button):
        """Delete patungan menu"""
        # Check admin permission
        if not is_admin(interaction, self.bot.config):
            await interaction.response.send_message("❌ Hanya admin yang bisa menggunakan fitur ini.", ephemeral=True)
            return
            
        # FIX: Gunakan get_all_patungans agar bisa hapus patungan yang statusnya running/closed juga
        patungans = await get_all_patungans(self.bot.session)
        
        if not patungans:
            await interaction.response.send_message(
                "❌ Tidak ada data patungan di database.\n"
                "💡 **Tips:** Jika ini patungan lama, gunakan `/import_legacy` atau `/import_specific` dulu.", 
                ephemeral=True
            )
            return
            
        view = DeletePatunganSelectView(self.bot, patungans)
        await interaction.response.send_message("Pilih patungan yang akan dihapus:", view=view, ephemeral=True)

class ManagePatunganView(ui.View):
    """View untuk mengelola patungan (Placeholder)"""
    def __init__(self, bot):
        super().__init__(timeout=60)
        self.bot = bot
    
    @ui.button(label='❌ Tutup Menu', style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.message.delete()

class TicketPanelView(ui.View):
    """View untuk panel pembuatan ticket"""
    def __init__(self, bot):
        super().__init__(timeout=None)
        self.bot = bot
    
    @ui.button(label='Buat Ticket', emoji=discord.PartialEmoji.from_str(Emojis.TICKET), style=discord.ButtonStyle.primary, custom_id='create_ticket_panel')
    async def create_ticket(self, interaction: discord.Interaction, button: ui.Button):
        """Handle create ticket button"""
        # Fetch available products
        from database.models import Patungan, UserSlot
        from sqlalchemy import select, func
        # FIX: Allow 'running' status as well, so users can join late if slots available
        stmt = select(Patungan).where(Patungan.status.in_(['open', 'running']))
        result = await self.bot.session.execute(stmt)
        patungans = result.scalars().all()

        if not patungans:
            await interaction.response.send_message("❌ Belum ada produk/patungan yang tersedia.", ephemeral=True)
            return

        options = []
        seen = set()
        for p in patungans:
            # Filter produk stock (biasanya slot 9999) agar tidak muncul di menu PTPT
            if p.total_slots >= 9000:
                continue
            
            if p.product_name not in seen:
                # Calculate current slots dynamically
                stmt_count = select(func.count(UserSlot.id)).where(
                    UserSlot.patungan_version == p.product_name,
                    UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
                )
                res_count = await self.bot.session.execute(stmt_count)
                current_slots = res_count.scalar() or 0

                # Filter full slots
                if current_slots >= p.total_slots:
                    continue
                    
                options.append(discord.SelectOption(
                    label=f"{p.product_name}",
                    value=p.product_name,
                    description=f"Harga: Rp {p.price:,} | Slot: {current_slots}/{p.total_slots}"
                ))
                seen.add(p.product_name)
                if len(options) >= 25:
                    break
        
        if not options:
            await interaction.response.send_message("❌ Mohon maaf, semua slot patungan saat ini **PENUH**.", ephemeral=True)
            return
        
        view = ProductSelectView(self.bot, options)
        await interaction.response.send_message("Silakan pilih produk terlebih dahulu:", view=view, ephemeral=True)

class DeletePatunganSelectView(ui.View):
    """View untuk memilih patungan yang akan dihapus"""
    def __init__(self, bot, patungans):
        super().__init__(timeout=60)
        self.bot = bot
        
        options = []
        seen = set()
        for p in patungans:
            if p.product_name not in seen:
                options.append(discord.SelectOption(
                    label=f"{p.product_name}",
                    value=p.product_name,
                    description=f"Total Slots: {p.total_slots}"
                ))
                seen.add(p.product_name)
                if len(options) >= 25:
                    break
            
        select = ui.Select(placeholder="Pilih patungan untuk dihapus...", options=options)
        select.callback = self.callback
        self.add_item(select)
        
    async def callback(self, interaction: discord.Interaction):
        version = interaction.data['values'][0]
        view = DeletePatunganConfirmView(self.bot, version)
        await interaction.response.edit_message(
            content=f"⚠️ **PERINGATAN KERAS** ⚠️\n\nAnda akan menghapus patungan **{version}**.\nIni akan menghapus:\n- Channel Discord\n- Role Discord\n- Data Slot & Pembayaran\n\nTindakan ini TIDAK BISA DIBATALKAN.",
            view=view,
            embed=None
        )

class DeletePatunganConfirmView(ui.View):
    """View konfirmasi hapus patungan"""
    def __init__(self, bot, version):
        super().__init__(timeout=60)
        self.bot = bot
        self.version = version
        
    @ui.button(label="💣 YA, HAPUS SEMUANYA", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.defer(ephemeral=True)
        from bot.patungan_manager import PatunganManager
        manager = PatunganManager(self.bot)
        success, msg = await manager.delete_patungan_fully(self.version, interaction.user.name)
        if success:
            await interaction.followup.send(f"✅ {msg}", ephemeral=True)
        else:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            
    @ui.button(label="Batal", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: ui.Button):
        await interaction.response.edit_message(content="❌ Penghapusan dibatalkan.", view=None)

class RatingModal(ui.Modal, title="Berikan Ulasan Anda"):
    feedback = ui.TextInput(
        label="Your feedback here...",
        style=discord.TextStyle.paragraph,
        required=False,
        max_length=500
    )

    def __init__(self, bot, rating, ticket_name, admin_name, original_interaction):
        super().__init__()
        self.bot = bot
        self.rating = rating
        self.ticket_name = ticket_name
        self.admin_name = admin_name
        self.original_interaction = original_interaction
        self.config = Config()

    async def on_submit(self, interaction: discord.Interaction):
        stars = "⭐" * self.rating
        feedback_text = self.feedback.value if self.feedback.value else "Tidak ada pesan."
        
        # Edit DM Message
        embed = self.original_interaction.message.embeds[0]
        embed.title = f"{Emojis.CHECK_YES_2} **THANK YOU**"
        embed.description = "Terima kasih! Feedback Anda telah tersimpan."
        embed.color = self.config.COLOR_SUCCESS
        embed.clear_fields() # Clear previous fields to make it clean
        await interaction.response.edit_message(embed=embed, view=None)
        
        # Send Log to Server
        log_channel = self.bot.get_channel(self.config.RATING_LOG_CHANNEL_ID)
        if log_channel:
            log_embed = discord.Embed(title=f"{Emojis.SPARKLE_1} **NEW USER FEEDBACK**", color=self.config.COLOR_GOLD)
            log_embed.description = f"Rating: {stars}"
            log_embed.add_field(name="User", value=interaction.user.name, inline=True)
            log_embed.add_field(name="Ticket", value=self.ticket_name, inline=True)
            log_embed.add_field(name="Feedback Message", value=feedback_text, inline=False)
            log_embed.set_footer(text=f"Handled by {self.admin_name} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            await log_channel.send(embed=log_embed)

class RatingView(ui.View):
    """View for Ticket Rating in DM"""
    def __init__(self, bot, ticket_name, admin_name):
        super().__init__(timeout=None)
        self.bot = bot
        self.ticket_name = ticket_name
        self.admin_name = admin_name
        self.config = Config()

    async def handle_rating(self, interaction: discord.Interaction, rating: int):
        # Open Modal instead of direct submit
        modal = RatingModal(self.bot, rating, self.ticket_name, self.admin_name, interaction)
        await interaction.response.send_modal(modal)

    @ui.button(label='⭐', style=discord.ButtonStyle.secondary)
    async def rate_1(self, interaction: discord.Interaction, button: ui.Button): await self.handle_rating(interaction, 1)
    @ui.button(label='⭐⭐', style=discord.ButtonStyle.secondary)
    async def rate_2(self, interaction: discord.Interaction, button: ui.Button): await self.handle_rating(interaction, 2)
    @ui.button(label='⭐⭐⭐', style=discord.ButtonStyle.secondary)
    async def rate_3(self, interaction: discord.Interaction, button: ui.Button): await self.handle_rating(interaction, 3)
    @ui.button(label='⭐⭐⭐⭐', style=discord.ButtonStyle.secondary)
    async def rate_4(self, interaction: discord.Interaction, button: ui.Button): await self.handle_rating(interaction, 4)
    @ui.button(label='⭐⭐⭐⭐⭐', style=discord.ButtonStyle.secondary)
    async def rate_5(self, interaction: discord.Interaction, button: ui.Button): await self.handle_rating(interaction, 5)
    @ui.button(label='No Thanks', style=discord.ButtonStyle.danger)
    async def no_thanks(self, interaction: discord.Interaction, button: ui.Button): await interaction.message.delete()

class RemoveParticipantSelectProductView(ui.View):
    """View untuk memilih produk sebelum hapus member"""
    def __init__(self, bot, patungans):
        super().__init__(timeout=60)
        self.bot = bot
        
        options = []
        seen = set()
        for p in patungans:
            if p.total_slots >= 9000:
                continue
            
            if p.product_name not in seen:
                options.append(discord.SelectOption(
                    label=p.product_name,
                    value=p.product_name
                ))
                seen.add(p.product_name)
                if len(options) >= 25: break
        
        select = ui.Select(placeholder="Pilih Produk...", options=options)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        product_name = interaction.data['values'][0]
        
        # Fetch slots
        from database.models import UserSlot
        from sqlalchemy import select
        
        stmt = select(UserSlot).where(
            UserSlot.patungan_version == product_name,
            UserSlot.slot_status.in_(['booked', 'waiting_payment', 'paid'])
        ).order_by(UserSlot.slot_number)
        
        result = await self.bot.session.execute(stmt)
        slots = result.scalars().all()
        
        if not slots:
            await interaction.response.send_message(f"❌ Tidak ada member aktif di {product_name}.", ephemeral=True)
            return
            
        view = RemoveParticipantSelectSlotView(self.bot, product_name, slots)
        await interaction.response.send_message(f"Pilih member yang akan dihapus dari **{product_name}**:", view=view, ephemeral=True)

class RemoveParticipantSelectSlotView(ui.View):
    """View untuk memilih slot user yang akan dihapus"""
    def __init__(self, bot, product_name, slots):
        super().__init__(timeout=60)
        self.bot = bot
        self.product_name = product_name
        
        options = []
        for slot in slots:
            label = f"Slot {slot.slot_number}: {slot.game_username}"
            if len(label) > 100: label = label[:97] + "..."
            
            options.append(discord.SelectOption(
                label=label,
                value=slot.game_username,
                description=f"Status: {slot.slot_status.upper()}"
            ))
            if len(options) >= 25: break
            
        select = ui.Select(placeholder="Pilih Member...", options=options)
        select.callback = self.callback
        self.add_item(select)

    async def callback(self, interaction: discord.Interaction):
        username = interaction.data['values'][0]
        await self.bot.admin_handler.remove_participant_slot(
            interaction, 
            self.product_name, 
            username
        )

class RemoveParticipantModal(ui.Modal, title="🗑️ Hapus Member (Cancel Slot)"):
    """Modal untuk menghapus member dari slot"""
    product_name = ui.TextInput(
        label="Nama Produk", 
        placeholder="Contoh: V1, HIGGS-1M",
        required=True
    )
    username = ui.TextInput(
        label="Username Roblox/Discord", 
        placeholder="Username member yang terdaftar",
        required=True
    )

    def __init__(self, bot):
        super().__init__()
        self.bot = bot

    async def on_submit(self, interaction: discord.Interaction):
        # Panggil logic di AdminHandler
        await self.bot.admin_handler.remove_participant_slot(
            interaction, 
            self.product_name.value.strip().upper(), 
            self.username.value.strip()
        )

class CreatePatunganWizardView(ui.View):
    """Wizard View untuk setup awal patungan (Script & Start Mode)"""
    def __init__(self, bot):
        super().__init__(timeout=120)
        self.bot = bot
        self.use_script = "Yes" # Default
        self.start_mode = "full_slot" # Default

    @ui.select(placeholder="Pilih Opsi Script...", options=[
        discord.SelectOption(label="Script", value="Yes", description="Produk ini menggunakan Script", emoji="📜"),
        discord.SelectOption(label="No Script", value="No", description="Produk ini TANPA Script", emoji="🚫")
    ])
    async def select_script(self, interaction: discord.Interaction, select: ui.Select):
        self.use_script = select.values[0]
        await interaction.response.defer()

    @ui.select(placeholder="Pilih Opsi Start...", options=[
        discord.SelectOption(label="Full Slot", value="full_slot", description="Start otomatis saat slot penuh", emoji="🌕"),
        discord.SelectOption(label="Jadwal Tertentu", value="schedule", description="Start sesuai tanggal/jam", emoji="📅")
    ])
    async def select_start(self, interaction: discord.Interaction, select: ui.Select):
        self.start_mode = select.values[0]
        await interaction.response.defer()

    @ui.button(label="Lanjut ke Detail", style=discord.ButtonStyle.primary, emoji="➡️")
    async def next_step(self, interaction: discord.Interaction, button: ui.Button):
        form = CreatePatunganForm(self.bot, self.use_script, self.start_mode)
        await interaction.response.send_modal(form)