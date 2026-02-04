# database/crud.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_
from sqlalchemy.orm import selectinload
from .models import Patungan, UserTicket, UserSlot, PaymentRecord, PriceHistory, SystemLog, BotSetting
from datetime import datetime
import pytz
import logging

logger = logging.getLogger(__name__)

# Timezone
tz = pytz.timezone('Asia/Jakarta')

# PATUNGAN OPERATIONS
async def create_patungan(
    session: AsyncSession,
    version: str,
    display_name: str,
    duration_hours: int,
    price_per_slot: int,
    max_slots: int = 19,
    description: str = None,
    admin_id: str = None
):
    """Create new patungan"""
    try:
        patungan = Patungan(
            product_name=version,
            display_name=display_name,
            duration_hours=duration_hours,
            price=price_per_slot,
            total_slots=max_slots,
            description=description
        )
        
        session.add(patungan)
        await session.commit()
        
        # Log price history
        price_history = PriceHistory(
            patungan_version=version,
            old_price=0,
            new_price=price_per_slot,
            changed_by=admin_id or 'system',
            reason='Initial price'
        )
        session.add(price_history)
        
        # Log system action
        log = SystemLog(
            log_type='patungan_created',
            log_level='info',
            patungan_version=version,
            user_id=admin_id,
            action=f'Created patungan {version}',
            details=f'Price: Rp {price_per_slot:,}'
        )
        session.add(log)
        
        await session.commit()
        
        return True, patungan
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating patungan: {e}")
        return False, str(e)

async def get_patungan(session: AsyncSession, product_name: str):
    """Get patungan by product_name"""
    try:
        stmt = select(Patungan).where(Patungan.product_name == product_name)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting patungan: {e}")
        return None

async def get_available_patungans(session: AsyncSession):
    """Get all available patungans"""
    try:
        stmt = select(Patungan).where(
            Patungan.status == 'open'
        ).order_by(Patungan.created_at)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting available patungans: {e}")
        return []

# TICKET OPERATIONS
async def create_user_ticket(
    session: AsyncSession,
    discord_user_id: str,
    discord_username: str,
    ticket_channel_id: str
):
    """Create new user ticket"""
    try:
        ticket = UserTicket(
            discord_user_id=discord_user_id,
            discord_username=discord_username,
            ticket_channel_id=ticket_channel_id
        )
        
        session.add(ticket)
        await session.commit()
        return True, ticket
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating ticket: {e}")
        return False, str(e)

# SLOT OPERATIONS
async def create_user_slot(
    session: AsyncSession,
    user_id: str,
    username: str,
    ticket_channel_id: str,
    patungan_version: str,
    slot_number: int,
    game_username: str,
    display_name: str = None,
    locked_price: int = None
):
    """Create user slot"""
    try:
        # Get or create ticket
        stmt = select(UserTicket).where(UserTicket.ticket_channel_id == ticket_channel_id)
        result = await session.execute(stmt)
        ticket = result.scalar_one_or_none()
        
        if not ticket:
            ticket = UserTicket(
                discord_user_id=user_id,
                discord_username=username,
                ticket_channel_id=ticket_channel_id
            )
            session.add(ticket)
            await session.flush()
        
        # Get patungan to get price if not provided
        if locked_price is None:
            patungan = await get_patungan(session, patungan_version)
            if patungan:
                locked_price = patungan.price_per_slot
        
        # Create slot
        slot = UserSlot(
            ticket_id=ticket.id,
            patungan_version=patungan_version,
            slot_number=slot_number,
            game_username=game_username,
            display_name=display_name or game_username,
            locked_price=locked_price
        )
        
        session.add(slot)
        await session.commit()
        
        # Log system action
        log = SystemLog(
            log_type='slot_created',
            log_level='info',
            patungan_version=patungan_version,
            user_id=user_id,
            action=f'Booked slot {slot_number}',
            details=f'Game: {game_username}, Price: Rp {locked_price:,}'
        )
        session.add(log)
        
        await session.commit()
        return True, slot
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating slot: {e}")
        return False, str(e)

async def get_user_slots(
    session: AsyncSession,
    user_id: str,
    status: str = None,
    patungan_version: str = None
):
    """Get user slots with optional filters"""
    try:
        stmt = select(UserSlot).join(UserTicket).where(
            UserTicket.discord_user_id == user_id
        )
        
        if status:
            stmt = stmt.where(UserSlot.slot_status == status)
        
        if patungan_version:
            stmt = stmt.where(UserSlot.patungan_version == patungan_version)
        
        stmt = stmt.order_by(UserSlot.booked_at)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting user slots: {e}")
        return []

# PAYMENT OPERATIONS
async def create_payment_record(
    session: AsyncSession,
    slot_id: int,
    expected_amount: int,
    paid_amount: int,
    amount_difference: int,
    proof_image_url: str,
    payment_status: str = 'pending',
    notes: str = None,
    user_id: str = None
):
    """Create payment record"""
    try:
        payment = PaymentRecord(
            slot_id=slot_id,
            expected_amount=expected_amount,
            paid_amount=paid_amount,
            amount_difference=amount_difference,
            proof_image_url=proof_image_url,
            payment_status=payment_status,
            notes=notes
        )
        
        session.add(payment)
        await session.commit()
        
        # Log system action
        log = SystemLog(
            log_type='payment_created',
            log_level='info',
            user_id=user_id,
            action='Payment submitted',
            details=f'Paid: Rp {paid_amount:,}, Expected: Rp {expected_amount:,}'
        )
        session.add(log)
        
        await session.commit()
        return payment
        
    except Exception as e:
        await session.rollback()
        logger.error(f"Error creating payment: {e}")
        raise e

async def get_pending_payments(session: AsyncSession):
    """Get all pending payments"""
    try:
        stmt = select(PaymentRecord).where(
            PaymentRecord.payment_status == 'pending'
        ).options(
            selectinload(PaymentRecord.slot).selectinload(UserSlot.ticket),
            selectinload(PaymentRecord.slot).selectinload(UserSlot.patungan)
        ).order_by(PaymentRecord.detected_at)
        
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting pending payments: {e}")
        return []

async def get_all_patungans(session: AsyncSession):
    """Get all patungans"""
    try:
        stmt = select(Patungan).order_by(Patungan.created_at)
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting all patungans: {e}")
        return []

async def get_unpaid_slots(session: AsyncSession, version: str = None):
    """Get unpaid slots"""
    try:
        stmt = select(UserSlot).join(Patungan).where(
            UserSlot.slot_status.in_(['booked', 'waiting_payment'])
        )
        
        if version:
            stmt = stmt.where(UserSlot.patungan_version == version)
        
        stmt = stmt.options(
            selectinload(UserSlot.ticket),
            selectinload(UserSlot.patungan)
        )
        
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting unpaid slots: {e}")
        return []

async def get_patungans_with_deadlines(session: AsyncSession):
    """Get patungans with active deadlines"""
    try:
        from datetime import datetime
        stmt = select(Patungan).where(
            Patungan.deadline_end.is_not(None),
            Patungan.deadline_end > datetime.now()
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting patungans with deadlines: {e}")
        return []

async def get_upcoming_schedules(session: AsyncSession):
    """Get patungans with upcoming schedules"""
    try:
        from datetime import datetime
        stmt = select(Patungan).where(
            Patungan.start_schedule.is_not(None),
            Patungan.start_schedule > datetime.now()
        )
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting upcoming schedules: {e}")
        return []

async def get_slot_by_username(session: AsyncSession, version: str, username: str):
    """Get slot by username in patungan"""
    try:
        stmt = select(UserSlot).where(
            UserSlot.patungan_version == version,
            UserSlot.game_username == username
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting slot by username: {e}")
        return None

async def create_system_log(
    session: AsyncSession,
    log_type: str,
    log_level: str,
    patungan_version: str = None,
    user_id: str = None,
    action: str = None,
    details: str = None
):
    """Create system log"""
    try:
        log = SystemLog(
            log_type=log_type,
            log_level=log_level,
            patungan_version=patungan_version,
            user_id=user_id,
            action=action,
            details=details
        )
        session.add(log)
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Error creating system log: {e}")
        return False

async def get_ticket_by_channel(session, channel_id: str):
    """Get ticket by channel ID"""
    from .models import UserTicket
    from sqlalchemy import select
    
    try:
        stmt = select(UserTicket).where(UserTicket.ticket_channel_id == channel_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except:
        return None

async def get_user_active_ticket(session, user_id: str):
    """Get user's active ticket"""
    from .models import UserTicket
    from sqlalchemy import select
    
    try:
        stmt = select(UserTicket).where(
            UserTicket.discord_user_id == user_id,
            UserTicket.ticket_status == 'open'
        ).order_by(UserTicket.opened_at.desc())
        
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except:
        return None

async def get_inactive_tickets(session, hours: int = 24):
    """Get tickets inactive for specified hours"""
    from .models import UserTicket
    from sqlalchemy import select
    from datetime import datetime, timedelta
    
    try:
        cutoff_time = datetime.now() - timedelta(hours=hours)
        
        stmt = select(UserTicket).where(
            UserTicket.ticket_status == 'open',
            UserTicket.last_activity < cutoff_time
        )
        
        result = await session.execute(stmt)
        return result.scalars().all()
    except Exception as e:
        logger.error(f"Error getting inactive tickets: {e}")
        return []

async def update_patungan_status(session: AsyncSession, version: str, status: str):
    """Update patungan status"""
    try:
        patungan = await get_patungan(session, version)
        if patungan:
            patungan.status = status
            await session.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating patungan status: {e}")
        return False

async def get_slot(session: AsyncSession, slot_id: int):
    """Get slot by ID"""
    try:
        stmt = select(UserSlot).where(UserSlot.id == slot_id).options(
            selectinload(UserSlot.ticket),
            selectinload(UserSlot.patungan)
        )
        result = await session.execute(stmt)
        return result.scalar_one_or_none()
    except Exception as e:
        logger.error(f"Error getting slot: {e}")
        return None

async def update_payment_status(
    session: AsyncSession,
    payment_id: int,
    status: str,
    verified_by: str = None,
    verified_at: datetime = None
):
    """Update payment status"""
    try:
        stmt = select(PaymentRecord).where(PaymentRecord.id == payment_id)
        result = await session.execute(stmt)
        payment = result.scalar_one_or_none()
        
        if payment:
            payment.payment_status = status
            if verified_by:
                payment.verified_by = verified_by
            if verified_at:
                payment.verified_at = verified_at
            await session.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating payment status: {e}")
        return False

async def update_ticket_status(session: AsyncSession, channel_id: str, status: str, reason: str = None):
    """Update ticket status"""
    try:
        ticket = await get_ticket_by_channel(session, channel_id)
        if ticket:
            ticket.ticket_status = status
            if reason:
                ticket.close_reason = reason
            if status == 'closed':
                ticket.closed_at = datetime.now()
            await session.commit()
            return True
        return False
    except Exception as e:
        logger.error(f"Error updating ticket status: {e}")
        return False

async def delete_patungan_by_version(session: AsyncSession, product_name: str):
    """Delete patungan and all related data"""
    try:
        # Get slots to delete payments
        stmt_slots = select(UserSlot.id).where(UserSlot.patungan_version == product_name)
        result = await session.execute(stmt_slots)
        slot_ids = result.scalars().all()
        
        if slot_ids:
            # Delete payments
            stmt_payments = delete(PaymentRecord).where(PaymentRecord.slot_id.in_(slot_ids))
            await session.execute(stmt_payments)
            
            # Delete slots
            stmt_del_slots = delete(UserSlot).where(UserSlot.patungan_version == product_name)
            await session.execute(stmt_del_slots)
            
        # Delete patungan (New Model)
        stmt_master = delete(Patungan).where(Patungan.product_name == product_name)
        await session.execute(stmt_master)
        
        await session.commit()
        return True
    except Exception as e:
        await session.rollback()
        logger.error(f"Error deleting patungan: {e}")
        return False

async def get_setting(session: AsyncSession, key: str, default=None):
    """Get bot setting"""
    try:
        stmt = select(BotSetting).where(BotSetting.key == key)
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        return setting.value if setting else default
    except Exception as e:
        logger.error(f"Error getting setting {key}: {e}")
        return default

async def set_setting(session: AsyncSession, key: str, value: str):
    """Set bot setting"""
    try:
        stmt = select(BotSetting).where(BotSetting.key == key)
        result = await session.execute(stmt)
        setting = result.scalar_one_or_none()
        
        if setting:
            setting.value = value
        else:
            setting = BotSetting(key=key, value=value)
            session.add(setting)
            
        await session.commit()
        return True
    except Exception as e:
        logger.error(f"Error setting {key}: {e}")
        return False