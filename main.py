# main.py
import discord
from discord.ext import commands, tasks
import asyncio
import sys
import traceback
import re
from config import Config
from database.setup import init_db, get_session
from bot.patungan_manager import PatunganManager
from bot.ticket_handler import TicketHandler
from bot.admin_handler import AdminHandler
from bot.payment_processor import PaymentProcessor
from bot.views import MainTicketView, TicketPanelView, AdminDashboardView
from utils.helpers import setup_logging
import logging
from database.crud import get_ticket_by_channel
from api import WinterAPI, process_data
import ui

# Setup logging
logger = setup_logging()

class PatunganBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.guilds = True
        
        super().__init__(
            command_prefix='!',
            intents=intents,
            help_command=None
        )
        
        self.config = Config()
        self.session = get_session()
        self.patungan_manager = PatunganManager(self)
        self.ticket_handler = TicketHandler(self)
        self.payment_processor = PaymentProcessor(self)
        self.admin_handler = AdminHandler(self)
        self.winter_api = WinterAPI()
        
    async def setup_hook(self):
        """Setup bot extensions and database"""
        logger.info("Setting up bot...")
        
        # Initialize database
        await init_db()
        
        # Refresh session setelah database siap
        self.session = get_session()
        
        # Register persistent views (Agar tombol tidak mati saat restart)
        self.add_view(MainTicketView(self))
        self.add_view(TicketPanelView(self))
        self.add_view(AdminDashboardView(self))
        self.add_view(ui.StockTicketControlView(self))
        self.add_view(ui.StockPaymentAdminView(self))
        
        # Sync commands
        await self.tree.sync()
        
        # Start Stock Monitor Task
        self.stock_monitor_task.start()
        logger.info("Commands synced")
    
    async def on_ready(self):
        """Bot is ready"""
        logger.info(f'✅ Bot is ready as {self.user}')
        logger.info(f'📊 Guilds: {len(self.guilds)}')
        
        # Check OCR Status
        if self.config.ENABLE_OCR:
            if self.payment_processor.ocr and self.payment_processor.ocr.available:
                logger.info("📷 OCR System: ✅ ACTIVE")
            else:
                logger.warning("📷 OCR System: ⚠️ ENABLED BUT TESSERACT NOT FOUND")
        else:
            logger.info("📷 OCR System: ❌ DISABLED IN CONFIG")
        
        # Setup channels and roles
        await self.patungan_manager.setup_channels()
        await self.patungan_manager.setup_admin_dashboard()
        await self.ticket_handler.setup_ticket_panel()
        
        # Start background tasks
        self.loop.create_task(self.patungan_manager.check_deadlines())
        self.loop.create_task(self.patungan_manager.check_schedules())
        
        # Update status
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching,
                name="Patungan X8 System"
            )
        )
        
        logger.info("🚀 Bot is fully initialized and waiting for interactions!")
        
        # Jalankan update stock langsung saat bot siap (Startup)
        self.loop.create_task(self.update_stock_dashboard())
    
    async def update_stock_dashboard(self):
        """Core logic untuk update dashboard stock"""
        logger.info("🔄 Running Stock Update...")
        try:
            channel = None
            
            # 1. Coba cari pakai ID (jika ada di .env)
            if self.config.DASHBOARD_CHANNEL_ID:
                channel = self.get_channel(self.config.DASHBOARD_CHANNEL_ID)
            
            # 2. Jika tidak ketemu, cari pakai NAMA (Fallback)
            if not channel:
                for guild in self.guilds:
                    # Cari yang namanya MIRIP (mengandung kata kunci 'stock' dan 'dvn')
                    for ch in guild.text_channels:
                        if "stock" in ch.name.lower() and "dvn" in ch.name.lower():
                            channel = ch
                            break
                    if channel: break
            
            if not channel:
                logger.error(f"❌ Channel Dashboard tidak ditemukan. (ID: {self.config.DASHBOARD_CHANNEL_ID} | Name: {self.config.DASHBOARD_CHANNEL_NAME})")
                return

            raw_data = await asyncio.to_thread(self.winter_api.fetch_data)
            if raw_data:
                processed = process_data(raw_data)
                embed = ui.create_dashboard_embed(processed)
                view = ui.TicketView(self) # Attach View agar tombol Buy muncul
                
                # Cari pesan terakhir dari bot untuk di-edit (agar tidak spam)
                last_msg = None
                async for msg in channel.history(limit=10):
                    if msg.author == self.user:
                        last_msg = msg
                        break
                
                if last_msg:
                    await last_msg.edit(embed=embed, view=view)
                else:
                    await channel.send(embed=embed, view=view)
                logger.info("✅ Dashboard updated successfully.")
        except Exception as e:
            logger.error(f"❌ Stock update failed: {e}")

    @tasks.loop(minutes=5)
    async def stock_monitor_task(self):
        """Auto update stock dashboard every 5 minutes"""
        await self.update_stock_dashboard()

    @stock_monitor_task.before_loop
    async def before_stock_monitor_task(self):
        logger.info("⏳ Menunggu bot siap sebelum menjalankan Stock Monitor...")
        await self.wait_until_ready()

    async def on_message(self, message):
        """Handle messages"""
        # Ignore bot messages
        if message.author.bot:
            return
        
        # Check if this is a ticket channel (Database Check)
        # Menggunakan database check agar lebih akurat dan tidak bergantung pada Category ID di .env
        ticket = await get_ticket_by_channel(self.session, str(message.channel.id))
        
        if ticket:
            await self.ticket_handler.handle_ticket_message(message)
            
            if message.attachments:
                # Cek apakah ini Ticket Stock (Berdasarkan Kategori)
                is_stock_ticket = False
                if self.config.STOCK_CATEGORY_ID and message.channel.category and message.channel.category.id == self.config.STOCK_CATEGORY_ID:
                    is_stock_ticket = True
                
                if is_stock_ticket:
                    await ui.handle_stock_payment(self, message)
                else:
                    logger.info(f"📸 Processing payment proof in ticket: {message.channel.name}")
                    await self.payment_processor.process_payment_proof(message)
        
        # Check for Stock Ticket (Category Check) - Fallback
        elif self.config.STOCK_CATEGORY_ID and message.channel.category and message.channel.category.id == self.config.STOCK_CATEGORY_ID:
            if message.attachments:
                await ui.handle_stock_payment(self, message)
        
        # Manual Command: .qr (QRIS Image - Admin Only)
        if message.content.lower() == '.qr':
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    embed = discord.Embed(title="💳 QRIS Payment", color=self.config.COLOR_INFO)
                    embed.set_image(url=self.config.QRIS_IMAGE_URL)
                    await message.channel.send(embed=embed)

        # Manual Command: .ps (Private Server Link - Admin Only)
        if message.content.lower() == '.ps':
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    await message.channel.send(f"🔗 **Private Server Link:**\n{self.config.PRIVATE_SERVER_LINK}")
        
        # Manual Command: .run (Set status to running)
        if message.content.lower().startswith('.run'):
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    parts = message.content.split()
                    version = None
                    
                    if len(parts) >= 2:
                        version = parts[1].upper()
                    elif message.reference and message.channel.id == self.config.LIST_PTPT_CHANNEL_ID:
                        try:
                            replied_msg = await message.channel.fetch_message(message.reference.message_id)
                            if replied_msg.author == self.user and replied_msg.embeds:
                                title = replied_msg.embeds[0].title
                                match = re.search(r'\*\*(.*?)\s*-', title)
                                if match:
                                    version = match.group(1).strip()
                        except:
                            pass

                    if version:
                        success, msg = await self.patungan_manager.set_patungan_status(version, 'running', message.author.name)
                        await message.channel.send(f"{message.author.mention} {msg}", delete_after=10)
                        try: await message.delete()
                        except: pass
                    else:
                        await message.channel.send(f"{message.author.mention} ❌ Format: `.run <Versi>` atau Reply pesan di List PTPT.", delete_after=5)

        # Manual Command: .close (Ticket or Patungan)
        if message.content.lower().startswith('.close'):
            if isinstance(message.author, discord.Member):
                # 1. Ticket Close (Exact match .close, NOT in List Channel)
                if message.content.lower().strip() == '.close' and message.channel.id != self.config.LIST_PTPT_CHANNEL_ID:
                    await self.ticket_handler.handle_admin_close_ticket_from_message(message)
                    return

                # 2. Patungan Close (Admin Only)
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    parts = message.content.split()
                    version = None

                    if len(parts) >= 2:
                        version = parts[1].upper()
                    elif message.reference and message.channel.id == self.config.LIST_PTPT_CHANNEL_ID:
                        try:
                            replied_msg = await message.channel.fetch_message(message.reference.message_id)
                            if replied_msg.author == self.user and replied_msg.embeds:
                                title = replied_msg.embeds[0].title
                                match = re.search(r'\*\*(.*?)\s*-', title)
                                if match:
                                    version = match.group(1).strip()
                        except:
                            pass

                    if version:
                        success, msg = await self.patungan_manager.set_patungan_status(version, 'closed', message.author.name)
                        await message.channel.send(f"{message.author.mention} {msg}", delete_after=10)
                        try: await message.delete()
                        except: pass
                    elif message.channel.id == self.config.LIST_PTPT_CHANNEL_ID:
                        await message.channel.send(f"{message.author.mention} ❌ Format: `.close <Versi>` atau Reply pesan di List PTPT.", delete_after=5)
                    else:
                        pass

        # Manual Command: .cancel <slot_number> (in list-ptpt, as reply)
        if message.content.lower().startswith('.cancel'):
            # Only trigger in list-ptpt channel
            if message.channel.id != self.config.LIST_PTPT_CHANNEL_ID:
                return

            # Check Permission
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
                if not any(role_id in user_roles for role_id in allowed_roles):
                    return # Silently ignore if not admin
            
            try:
                # Delete the command message to keep channel clean
                await message.delete()

                parts = message.content.split()
                product_name = None
                slot_number = None

                # Case 1: Explicit .cancel V1 5
                if len(parts) == 3:
                    product_name = parts[1].upper()
                    if not parts[2].isdigit():
                         await message.channel.send(f"{message.author.mention} ❌ Slot harus angka.", delete_after=5)
                         return
                    slot_number = int(parts[2])

                # Case 2: Reply .cancel 5
                elif len(parts) == 2 and message.reference and message.reference.message_id:
                    if not parts[1].isdigit():
                         await message.channel.send(f"{message.author.mention} ❌ Slot harus angka.", delete_after=5)
                         return
                    slot_number = int(parts[1])
                    
                    # Fetch replied message to get product name
                    try:
                        replied_message = await message.channel.fetch_message(message.reference.message_id)
                        if replied_message.author == self.user and replied_message.embeds:
                            embed_title = replied_message.embeds[0].title
                            # Title format: "🔥 **V1 - 24 Jam**"
                            match = re.search(r'\*\*(.*?)\s*-', embed_title)
                            if match:
                                product_name = match.group(1).strip()
                    except:
                        pass
                
                if product_name and slot_number:
                     # Call handler
                    success, msg = await self.admin_handler.cancel_slot_by_number(product_name, slot_number, message.author)
                    await message.channel.send(f"{message.author.mention} {msg}", delete_after=20)
                else:
                    await message.channel.send(f"{message.author.mention} ❌ Format salah. Gunakan: `.cancel <NamaProduk> <NomorSlot>` atau Reply pesan dengan `.cancel <NomorSlot>`", delete_after=10)

            except Exception as e:
                logger.error(f"Error handling .cancel command: {e}")
                await message.channel.send(f"{message.author.mention} ❌ Terjadi kesalahan.", delete_after=10)

        # Manual Command: !setworkers (Update list workers dynamic)
        if message.content.lower().startswith('!setworkers'):
            # Check permission
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID] + self.config.ADMIN_ROLE_IDS
                if not any(role_id in user_roles for role_id in allowed_roles): return

            args = message.content[12:].strip()
            if not args:
                current_workers = ", ".join(self.config.WORKERS)
                await message.channel.send(f"⚠️ **List Workers Saat Ini:**\n`{current_workers}`\n\n**Cara Ganti:**\n`!setworkers user1, user2, user3`")
                return
            
            new_workers = [w.strip() for w in args.split(',') if w.strip()]
            if not new_workers:
                await message.channel.send("❌ List tidak boleh kosong.")
                return
            
            # Update Config Class (Static) agar terbaca di api.py
            Config.WORKERS = new_workers
            self.config.WORKERS = new_workers
            
            await message.channel.send(f"✅ **Berhasil Update Workers ({len(new_workers)} akun):**\n`{', '.join(new_workers)}`\n\n*Note: Update ini hanya sementara sampai bot restart. Tambahkan `WC_WORKERS` di .env agar permanen.*")

        await self.process_commands(message)
    
    async def on_interaction(self, interaction: discord.Interaction):
        """Log interactions to console"""
        if interaction.type == discord.InteractionType.component:
            logger.info(f"🔘 Button Clicked: {interaction.data.get('custom_id')} by {interaction.user}")
        elif interaction.type == discord.InteractionType.modal_submit:
            logger.info(f"📝 Modal Submitted: {interaction.data.get('custom_id')} by {interaction.user}")
    
    async def on_guild_channel_delete(self, channel):
        """Handle channel deletion"""
        if isinstance(channel, discord.TextChannel):
            await self.ticket_handler.handle_channel_deletion(str(channel.id))
    
    async def on_error(self, event, *args, **kwargs):
        """Handle errors"""
        logger.error(f'Error in event {event}: {traceback.format_exc()}')

def main():
    """Main entry point"""
    bot = PatunganBot()
    
    try:
        bot.run(bot.config.DISCORD_TOKEN)
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    except Exception as e:
        logger.error(f"Failed to start bot: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()