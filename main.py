# main.py
import discord
from discord.ext import commands, tasks
import asyncio
import sys
import traceback
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
    
    @tasks.loop(minutes=5)
    async def stock_monitor_task(self):
        """Auto update stock dashboard every 5 minutes"""
        if not self.config.DASHBOARD_CHANNEL_ID:
            return

        logger.info("🔄 Running Stock Monitor Task...")
        try:
            channel = self.get_channel(self.config.DASHBOARD_CHANNEL_ID)
            if not channel:
                return

            raw_data = await asyncio.to_thread(self.winter_api.fetch_data)
            if raw_data:
                processed = process_data(raw_data)
                embed = ui.create_dashboard_embed(processed)
                
                # Cari pesan terakhir dari bot untuk di-edit (agar tidak spam)
                last_msg = None
                async for msg in channel.history(limit=10):
                    if msg.author == self.user:
                        last_msg = msg
                        break
                
                if last_msg:
                    await last_msg.edit(embed=embed)
                else:
                    await channel.send(embed=embed)
                logger.info("✅ Dashboard updated successfully.")
        except Exception as e:
            logger.error(f"❌ Error in stock monitor task: {e}")

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
                logger.info(f"📸 Processing payment proof in ticket: {message.channel.name}")
                await self.payment_processor.process_payment_proof(message)
        
        # Check for Stock Ticket (Category Check)
        elif self.config.STOCK_CATEGORY_ID and message.channel.category and message.channel.category.id == self.config.STOCK_CATEGORY_ID:
            if message.attachments:
                await ui.handle_stock_payment(message)
        
        # Manual Command: !qr (QRIS Image - Admin Only)
        if message.content.lower() == '!qr':
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    embed = discord.Embed(title="💳 QRIS Payment", color=self.config.COLOR_INFO)
                    embed.set_image(url=self.config.QRIS_IMAGE_URL)
                    await message.channel.send(embed=embed)

        # Manual Command: !ps (Private Server Link - Admin Only)
        if message.content.lower() == '!ps':
            if isinstance(message.author, discord.Member):
                user_roles = [r.id for r in message.author.roles]
                allowed_roles = [self.config.SERVER_OVERLORD_ROLE_ID, self.config.SERVER_WARDEN_ROLE_ID]
                
                if any(role_id in user_roles for role_id in allowed_roles):
                    await message.channel.send(f"🔗 **Private Server Link:**\n{self.config.PRIVATE_SERVER_LINK}")
        
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