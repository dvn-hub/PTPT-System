# bot/payment_processor.py
import discord
from discord import ui
from config import Config, Emojis
from database.setup import get_session
from database.crud import create_payment_record, update_payment_status, get_slot, get_user_slots, get_setting, get_ticket_by_channel
try:
    from utils.ocr_processor import OCRProcessor
except (ImportError, ModuleNotFoundError):
    OCRProcessor = None
from utils.validators import validate_payment_amount
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class PaymentProcessor:
    def __init__(self, bot):
        self.bot = bot
        self.config = Config()
        self.pending_payments = {}  # user_id -> payment context
        
        # Initialize OCR
        self.ocr = None
        if self.config.ENABLE_OCR:
            if OCRProcessor:
                self.ocr = OCRProcessor()
            else:
                logger.warning("OCRProcessor disabled due to import error (likely numpy/pytesseract issue).")
    
    async def process_payment_proof(self, message: discord.Message):
        """Process payment proof image"""
        try:
            # Check if user has pending payment
            user_id = str(message.author.id)
            logger.info(f"Processing attachment from {message.author.name} ({user_id})")
            
            # Get proof URL
            proof_url = message.attachments[0].url
            proof_file = await message.attachments[0].to_file()
            
            # Create dedicated session for this operation to avoid concurrency errors
            session = get_session()
            if not session:
                logger.error("Failed to create database session")
                return

            async with session:
                # FIX: Scope slots to the current ticket channel (Bayar Gabungan Logic)
                from database.models import UserSlot
                from sqlalchemy import select
                
                ticket = await get_ticket_by_channel(session, str(message.channel.id))
                
                if ticket:
                    # Get all unpaid slots in this ticket (booked or waiting_payment)
                    stmt = select(UserSlot).where(
                        UserSlot.ticket_id == ticket.id,
                        UserSlot.slot_status.in_(['booked', 'waiting_payment'])
                    )
                    result = await session.execute(stmt)
                    slots = result.scalars().all()
                else:
                    # Fallback if not in ticket channel
                    slots = await get_user_slots(session, user_id, status='booked')
                
                if not slots:
                    logger.info(f"No unpaid slots found for {user_id} in this channel.")
                    return

                slot = slots[0]
                
                # Get expected amount (sum of all slots)
                expected_amount = sum(s.locked_price for s in slots)
                
                # OCR Processing
                paid_amount = 0
                notes = "Manual Verification Required"
                
                if self.config.ENABLE_OCR and self.ocr and self.ocr.available:
                    try:
                        detected_amount = await self.ocr.extract_amount_from_image(proof_url)
                        if detected_amount > 0:
                            paid_amount = detected_amount
                            notes = f"OCR Detected: Rp {paid_amount:,}"
                    except Exception as e:
                        logger.error(f"OCR failed: {e}")
                
                # Create payment record
                payment_record = await create_payment_record(
                    session=session,  # Use local session
                    slot_id=slot.id,
                    expected_amount=expected_amount,
                    paid_amount=paid_amount, # Use detected amount or 0
                    amount_difference=paid_amount - expected_amount if paid_amount > 0 else 0,
                    proof_image_url=proof_url,
                    payment_status='pending',
                    notes=notes,
                    user_id=user_id
                )
                
                # Update slot status to waiting_payment for all slots involved
                for s in slots:
                    s.slot_status = 'waiting_payment'
                await session.commit()
                
                # Update list channel
                if hasattr(self.bot, 'patungan_manager'):
                    await self.bot.patungan_manager.update_list_channel()
                
                # Send to payment log channel
                payment_log_channel = message.guild.get_channel(self.config.PAYMENT_LOG_CHANNEL_ID)
                
                if payment_log_channel:
                    # Create embed for admin
                    admin_embed = discord.Embed(
                        title="💰 NEW PAYMENT RECEIVED",
                        color=self.config.COLOR_WARNING
                    )
                    admin_embed.add_field(name="User", value=f"<@{user_id}>", inline=True)
                    admin_embed.add_field(name="Total Tagihan", value=f"Rp {expected_amount:,}", inline=True)
                    admin_embed.add_field(name="Jumlah Slot", value=str(len(slots)), inline=True)
                    admin_embed.set_image(url=proof_url)
                    
                    # PaymentVerificationView is defined in this file
                    view = PaymentVerificationView(self.bot, payment_record, [payment_record])
                    await payment_log_channel.send(embed=admin_embed, view=view)
                
                # Send confirmation to user
                user_embed = discord.Embed(
                    title=f'{Emojis.CHECK_YES_2} **PROOF RECEIVED**',
                    description='Mohon tunggu verifikasi admin.',
                    color=self.config.COLOR_INFO
                )
                # user_embed.add_field(name='Proses', value='Menunggu verifikasi admin', inline=False) # Removed to match simple desc
                
                await message.channel.send(embed=user_embed)
            
        except Exception as e:
            logger.error(f"Error processing payment proof: {e}")
    
    async def create_payment_embed(self, payment_record, session=None) -> discord.Embed:
        """Create embed for payment verification"""
        if session is None:
            session = self.bot.session
            
        slot = await get_slot(session, payment_record.slot_id)
        
        # Determine color based on amount difference
        if payment_record.amount_difference == 0:
            color = self.config.COLOR_SUCCESS
            amount_status = "✅ SESUAI"
        elif payment_record.amount_difference > 0:
            color = self.config.COLOR_WARNING
            amount_status = f"⚠️ LEBIH Rp {payment_record.amount_difference:,}"
        else:
            color = self.config.COLOR_ERROR
            amount_status = f"❌ KURANG Rp {abs(payment_record.amount_difference):,}"
        
        embed = discord.Embed(
            title='💰 PAYMENT DETECTED',
            color=color
        )
        
        embed.add_field(name='User', value=f'<@{slot.ticket.discord_user_id}>', inline=True)
        embed.add_field(name='Patungan', value=slot.patungan_version, inline=True)
        embed.add_field(name='Slot', value=slot.game_username, inline=True)
        
        embed.add_field(name='💰 Expected', value=f'Rp {payment_record.expected_amount:,}', inline=True)
        embed.add_field(name='💳 Paid', value=f'Rp {payment_record.paid_amount:,}', inline=True)
        embed.add_field(name='Status', value=amount_status, inline=True)
        
        embed.set_image(url=payment_record.proof_image_url)
        embed.add_field(name='Waktu', value=payment_record.detected_at.strftime('%d/%m %H:%M') + " WIB", inline=True)
        
        if payment_record.notes:
            embed.add_field(name='Catatan', value=payment_record.notes, inline=False)
        
        embed.set_footer(text=f'Payment ID: {payment_record.id}')
        
        return embed

class PaymentVerificationView(ui.View):
    """View for payment verification"""
    def __init__(self, bot, payment_record, all_pending_payments):
        super().__init__(timeout=None)
        self.bot = bot
        self.config = Config()
        self.payment_record = payment_record
        self.all_pending_payments = all_pending_payments
        self.current_index = all_pending_payments.index(payment_record)
    
    async def _update_all_slots_in_ticket(self, session, ticket_id, verified_by):
        """Helper to mark all unpaid slots in a ticket as paid"""
        from database.models import UserSlot
        from sqlalchemy import select
        
        # Get all slots in this ticket that are booked or waiting_payment
        stmt = select(UserSlot).where(
            UserSlot.ticket_id == ticket_id,
            UserSlot.slot_status.in_(['booked', 'waiting_payment'])
        )
        result = await session.execute(stmt)
        slots = result.scalars().all()
        
        for s in slots:
            s.slot_status = 'paid'
            s.payment_verified = True
            s.verified_by = verified_by
            s.verified_at = datetime.now()
            
    @ui.button(label='✅ Verify', style=discord.ButtonStyle.success, custom_id='verify_payment')
    async def verify_payment(self, interaction: discord.Interaction, button: ui.Button):
        """Verify payment"""
        await interaction.response.defer()
        
        try:
            # Check admin permission
            admin_role = interaction.guild.get_role(self.config.ADMIN_ROLE_ID)
            if not admin_role or admin_role not in interaction.user.roles:
                embed = discord.Embed(
                    title=f"{Emojis.BAN} **ACCESS DENIED**",
                    description="Maaf, fitur ini hanya untuk Admin.",
                    color=self.config.COLOR_ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return
            
            # FIX: Auto-fill paid_amount if 0 (OCR Failed) before verifying
            from database.models import PaymentRecord
            current_payment = await self.bot.session.get(PaymentRecord, self.payment_record.id)
            if current_payment and current_payment.paid_amount == 0:
                current_payment.paid_amount = current_payment.expected_amount
                current_payment.amount_difference = 0
                await self.bot.session.commit()

            # Update payment status
            await update_payment_status(
                session=self.bot.session,
                payment_id=self.payment_record.id,
                status='verified',
                verified_by=interaction.user.name,
                verified_at=datetime.now()
            )
            
            # Update slot status
            slot = await get_slot(self.bot.session, self.payment_record.slot_id)
            if not slot:
                await interaction.followup.send("❌ Data slot tidak ditemukan (Mungkin sudah dihapus).", ephemeral=True)
                return
            
            # PRE-FETCH DATA BEFORE COMMIT (Avoid Detached Instance Error)
            # Ensure ticket is loaded
            if not slot.ticket:
                from database.models import UserTicket
                ticket = await self.bot.session.get(UserTicket, slot.ticket_id)
                slot.ticket = ticket
            
            buyer_id = slot.ticket.discord_user_id if slot.ticket else "Unknown"
            item_name = slot.patungan_version
            ticket_id = slot.ticket_id
            game_username = slot.game_username

            # Fix: Update ALL unpaid slots in this ticket (Looping Update)
            await self._update_all_slots_in_ticket(self.bot.session, slot.ticket_id, interaction.user.name)
            await self.bot.session.commit()
            
            # Get all slots for this ticket to calculate total and list them
            from database.models import UserSlot
            from sqlalchemy import select
            stmt_slots = select(UserSlot).where(
                UserSlot.ticket_id == ticket_id,
                UserSlot.slot_status == 'paid'
            )
            result_slots = await self.bot.session.execute(stmt_slots)
            paid_slots = result_slots.scalars().all()
            
            # Grant role and channel access
            # Use existing manager if available to share state/config
            manager = getattr(self.bot, 'patungan_manager', None)
            if not manager:
                from bot.patungan_manager import PatunganManager
                manager = PatunganManager(self.bot)
            
            access_result = await manager.grant_patungan_access(
                user_id=buyer_id,
                product_name=item_name
            )
            
            if not access_result:
                await interaction.followup.send(f"⚠️ **WARNING:** Pembayaran verified, tapi GAGAL memberikan Role/Channel ke <@{buyer_id}>. Mohon cek manual (Role/Channel mungkin hilang).", ephemeral=True)
            
            # Update list channel
            await manager.update_list_channel()
            
            # Send success message
            embed = discord.Embed(
                title=f'{Emojis.VERIFIED} **PAYMENT VERIFIED**',
                description='Pembayaran valid. Slot Anda telah diamankan.',
                color=0x00FF00 # Bright Green
            )
            
            embed.add_field(name="━━━━━━━━━━━━━━", value="**DETAIL TRANSAKSI**", inline=False)
            embed.add_field(name='User', value=f'<@{buyer_id}>', inline=True)
            embed.add_field(name='Slot', value=game_username, inline=True)
            embed.add_field(name='Verified by', value=interaction.user.name, inline=True)
            
            await interaction.edit_original_response(embed=embed, view=None)
            
            # Log to transaction history
            history_channel = interaction.guild.get_channel(self.config.TRANSACTION_HISTORY_CHANNEL_ID)
            if history_channel:
                total_price = sum(s.locked_price for s in paid_slots)
                
                hist_embed = discord.Embed(title=f"{Emojis.VERIFIED} **SUCCESSFUL TRANSACTION**", color=self.config.COLOR_GOLD)
                hist_embed.add_field(name=f"{Emojis.TICKET} **Item:**", value=item_name, inline=True)
                hist_embed.add_field(name=f"{Emojis.DISCORD_CROWN} **Buyer:**", value=f"<@{buyer_id}>", inline=True)
                hist_embed.add_field(name=f"{Emojis.MONEY_BAG} **Price:**", value=f"Rp {total_price:,}", inline=True)
                hist_embed.add_field(name=f"{Emojis.NETHERITE_PICKAXE} **Handler:**", value=interaction.user.name, inline=True)
                if self.payment_record.proof_image_url:
                    hist_embed.set_image(url=self.payment_record.proof_image_url)
                hist_embed.set_footer(text="DVN Secure Transaction System")
                await history_channel.send(embed=hist_embed)

            # Send DM to user
            try:
                user = await interaction.guild.fetch_member(int(buyer_id))
                
                user_embed = discord.Embed(
                    title=f'{Emojis.ROCKET} **ORDER UPDATE**',
                    description=f'Halo kak! Pembayaran untuk slot **{item_name}** telah kami terima.',
                    color=self.config.COLOR_SUCCESS
                )
                
                slot_names = ", ".join([s.game_username for s in paid_slots])
                user_embed.add_field(name='Total Slot', value=str(len(paid_slots)), inline=True)
                user_embed.add_field(name='Username', value=slot_names, inline=True)
                user_embed.add_field(name='Status', value=f'{Emojis.CHECK_YES_2} **PAID / LUNAS**', inline=True)
                
                await user.send(embed=user_embed)
            except:
                pass
            
        except Exception as e:
            logger.error(f"Error verifying payment: {e}")
            await interaction.followup.send(
                "❌ Terjadi kesalahan.",
                ephemeral=True
            )
    
    @ui.button(label='❌ Reject', style=discord.ButtonStyle.danger, custom_id='reject_payment')
    async def reject_payment(self, interaction: discord.Interaction, button: ui.Button):
        """Reject payment"""
        await interaction.response.defer()
        
        try:
            admin_role = interaction.guild.get_role(self.config.ADMIN_ROLE_ID)
            if not admin_role or admin_role not in interaction.user.roles:
                embed = discord.Embed(
                    title=f"{Emojis.BAN} **ACCESS DENIED**",
                    description="Maaf, fitur ini hanya untuk Admin.",
                    color=self.config.COLOR_ERROR
                )
                await interaction.followup.send(embed=embed, ephemeral=True)
                return

            await update_payment_status(
                session=self.bot.session,
                payment_id=self.payment_record.id,
                status='rejected',
                verified_by=interaction.user.name,
                verified_at=datetime.now()
            )
            
            embed = discord.Embed(title="❌ PAYMENT REJECTED", color=self.config.COLOR_ERROR)
            embed.add_field(name="Rejected By", value=interaction.user.name)
            await interaction.edit_original_response(embed=embed, view=None)
            
        except Exception as e:
            logger.error(f"Error rejecting payment: {e}")