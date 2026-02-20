# database/models.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Float, Text, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import pytz

Base = declarative_base()

class Patungan(Base):
    __tablename__ = 'patungan'
    
    id = Column(Integer, primary_key=True)
    product_name = Column(String(100), unique=True, nullable=False) # Previously version
    display_name = Column(String(100), nullable=True)
    price = Column(Integer, nullable=False) # Previously price_per_slot
    total_slots = Column(Integer, default=19) # Previously max_slots
    current_slots = Column(Integer, default=0)
    status = Column(String(20), default='open')
    
    # Discord Info
    message_id = Column(String(50), nullable=True)
    discord_channel_id = Column(String(50), nullable=True)
    discord_role_id = Column(String(50), nullable=True)
    
    # Configuration
    use_script = Column(String, default="Yes")
    start_mode = Column(String, default="full_slot")
    duration_hours = Column(Integer, default=24)
    start_schedule = Column(DateTime, nullable=True)
    
    # Deadlines
    deadline_start = Column(DateTime, nullable=True)
    deadline_end = Column(DateTime, nullable=True)
    
    description = Column(Text, nullable=True)
    
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    updated_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')), onupdate=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    
    # Relationships
    slots = relationship("UserSlot", back_populates="patungan")
    price_history = relationship("PriceHistory", back_populates="patungan")

    @property
    def price_per_slot(self):
        return self.price
        
    @property
    def max_slots(self):
        return self.total_slots
        
    @property
    def version(self):
        return self.product_name

class UserTicket(Base):
    __tablename__ = 'user_tickets'
    
    id = Column(Integer, primary_key=True)
    discord_user_id = Column(String(50), nullable=False)
    discord_username = Column(String(100), nullable=False)
    ticket_channel_id = Column(String(50), unique=True, nullable=False)
    ticket_status = Column(String(20), default='open')  # open, closed, archived
    opened_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    last_activity = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    closed_at = Column(DateTime, nullable=True)
    close_reason = Column(String(200), nullable=True)
    
    # Relationships
    slots = relationship("UserSlot", back_populates="ticket")

class UserSlot(Base):
    __tablename__ = 'user_slots'
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('user_tickets.id'), nullable=False)
    patungan_version = Column(String(100), ForeignKey('patungan.product_name'), nullable=False)
    slot_number = Column(Integer, nullable=False)  # 1-19 global
    game_username = Column(String(50), nullable=False)
    display_name = Column(String(50), nullable=True)
    slot_status = Column(String(20), default='booked')  # booked, waiting_payment, paid, kicked
    locked_price = Column(Integer, nullable=False)  # Harga terkunci saat booking
    booked_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    payment_deadline = Column(DateTime, nullable=True)
    payment_type = Column(String(20), default='normal')  # normal, instant
    payment_verified = Column(Boolean, default=False)
    verified_by = Column(String(100), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    
    # Relationships
    ticket = relationship("UserTicket", back_populates="slots")
    patungan = relationship("Patungan", back_populates="slots")
    payments = relationship("PaymentRecord", back_populates="slot")

class PaymentRecord(Base):
    __tablename__ = 'payment_records'
    
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey('user_slots.id'), nullable=False)
    expected_amount = Column(Integer, nullable=False)  # Nominal yang seharusnya
    paid_amount = Column(Integer, nullable=False)  # Nominal yang dibayar
    amount_difference = Column(Integer, default=0)  # Selisih
    proof_image_url = Column(Text, nullable=False)
    payment_status = Column(String(20), default='pending')  # pending, verified, rejected, partial
    is_topup = Column(Boolean, default=False)
    parent_payment_id = Column(Integer, nullable=True)  # Untuk grouping
    verified_by = Column(String(100), nullable=True)
    verified_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    detected_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    
    # Relationships
    slot = relationship("UserSlot", back_populates="payments")

class PriceHistory(Base):
    __tablename__ = 'price_history'
    
    id = Column(Integer, primary_key=True)
    patungan_version = Column(String(100), ForeignKey('patungan.product_name'), nullable=False)
    old_price = Column(Integer, nullable=False)
    new_price = Column(Integer, nullable=False)
    changed_by = Column(String(100), nullable=False)
    changed_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    reason = Column(Text, nullable=True)
    effective_for_new = Column(Boolean, default=True)
    
    # Relationships
    patungan = relationship("Patungan", back_populates="price_history")

class SystemLog(Base):
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True)
    log_type = Column(String(50), nullable=False)
    log_level = Column(String(20), nullable=False)  # info, warning, error
    patungan_version = Column(String(10), nullable=True)
    user_id = Column(String(50), nullable=True)
    action = Column(String(200), nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))

class BotSetting(Base):
    __tablename__ = 'bot_settings'
    
    key = Column(String(50), primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')), onupdate=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))

class ActionQueue(Base):
    __tablename__ = 'action_queue'
    
    id = Column(Integer, primary_key=True)
    action_type = Column(String(50), nullable=False) # create_patungan, delete_patungan, remove_member
    payload = Column(Text, nullable=False) # JSON data
    status = Column(String(20), default='pending') # pending, processing, completed, failed
    created_by = Column(String(100))
    created_at = Column(DateTime, default=lambda: datetime.now(pytz.timezone('Asia/Jakarta')))
    processed_at = Column(DateTime, nullable=True)