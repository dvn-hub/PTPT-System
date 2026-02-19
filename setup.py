# setup.py
import asyncio
import discord
from discord.ext import commands
from config import Config
from database.setup import init_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def setup_bot():
    """Setup bot for first run"""
    config = Config()
    
    # Initialize database
    logger.info("Initializing database...")
    await init_db()
    logger.info("Database initialized!")
    
    # Create bot instance to setup channels
    intents = discord.Intents.default()
    intents.message_content = True
    intents.members = True
    intents.guilds = True
    
    bot = commands.Bot(command_prefix='!', intents=intents)
    
    @bot.event
    async def on_ready():
        logger.info(f"Bot ready as {bot.user}")
        
        # Setup channels and roles
        guild = bot.get_guild(config.SERVER_ID)
        if not guild:
            logger.error("Guild not found!")
            return
        
        # Create category if not exists
        category = discord.utils.get(guild.categories, name="『 𝙋𝙏𝙋𝙏 𝙓8 』")
        if not category:
            category = await guild.create_category("『 𝙋𝙏𝙋𝙏 𝙓8 』")
            logger.info(f"Created category: {category.name}")
        
        # Create channels
        channels_to_create = [
            ("🎫│open-ticket", "Ticket opening channel"),
            ("📋│list-ptpt-x8", "Patungan list and progress"),
            ("💰│payment-log", "Payment verification log"),
            ("📜│transaction-history", "Approved transaction history"),
            ("🔔│announcements", "System announcements"),
            ("📊│admin-dashboard", "Admin control panel"),
            ("📦│stock-dvn-store", "Live Stock Monitor")
        ]
        
        for channel_name, topic in channels_to_create:
            channel = discord.utils.get(guild.text_channels, name=channel_name)
            if not channel:
                channel = await category.create_text_channel(
                    name=channel_name,
                    topic=topic
                )
                logger.info(f"Created channel: {channel.name}")
        
        # Create admin role if not exists
        admin_role = discord.utils.get(guild.roles, name="Admin")
        if not admin_role:
            admin_role = await guild.create_role(
                name="Admin",
                color=discord.Color.red(),
                permissions=discord.Permissions.all(),
                reason="Admin role for patungan system"
            )
            logger.info(f"Created role: {admin_role.name}")
        
        logger.info("Setup completed!")
        await bot.close()
    
    await bot.start(config.DISCORD_TOKEN)

if __name__ == "__main__":
    asyncio.run(setup_bot())