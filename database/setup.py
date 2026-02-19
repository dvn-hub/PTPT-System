from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text, inspect
from config import Config
from database.models import Base
import logging

logger = logging.getLogger(__name__)

engine = None
AsyncSessionLocal = None

def check_and_migrate_tables(conn):
    """Check and migrate database tables"""
    inspector = inspect(conn)
    if 'patungan' in inspector.get_table_names():
        columns = [c['name'] for c in inspector.get_columns('patungan')]
        
        if 'discord_channel_id' not in columns:
            logger.info("Migrating: Adding discord_channel_id to patungan table")
            conn.execute(text("ALTER TABLE patungan ADD COLUMN discord_channel_id VARCHAR(50)"))
            
        if 'discord_role_id' not in columns:
            logger.info("Migrating: Adding discord_role_id to patungan table")
            conn.execute(text("ALTER TABLE patungan ADD COLUMN discord_role_id VARCHAR(50)"))

async def init_db():
    global engine, AsyncSessionLocal
    config = Config()
    
    # Get database URL
    db_url = config.DATABASE_URL
    
    # Ensure async driver
    if 'sqlite' in db_url and 'aiosqlite' not in db_url:
        db_url = db_url.replace('sqlite://', 'sqlite+aiosqlite://')
    elif 'mysql' in db_url and 'aiomysql' not in db_url:
        db_url = db_url.replace('mysql://', 'mysql+aiomysql://')
        
    logger.info(f"Initializing database...")
    
    try:
        engine = create_async_engine(db_url, echo=False)
        
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.run_sync(check_and_migrate_tables)
            
        AsyncSessionLocal = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Database initialized successfully")
    except Exception as e:
        logger.error(f"Failed to initialize database: {e}")
        raise e

def get_session():
    if AsyncSessionLocal is None:
        return None
    return AsyncSessionLocal()