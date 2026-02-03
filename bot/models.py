from sqlalchemy import Column, Integer, String, DateTime, Boolean, ForeignKey, Text
from sqlalchemy.orm import relationship
from .setup import Base
from datetime import datetime

class Patungan(Base):
    __tablename__ = 'patungan'
    
    id = Column(Integer, primary_key=True)
    product_name = Column(String, unique=True)
    price = Column(Integer)
    total_slots = Column(Integer)
    current_slots = Column(Integer, default=0)
    status = Column(String, default='open')
    
    # Discord Info
    discord_channel_id = Column(String, nullable=True)
    discord_role_id = Column(String, nullable=True)
    message_id = Column(String, nullable=True)
    
    # Deadlines
    deadline_start = Column(DateTime, nullable=True)
    deadline_end = Column(DateTime, nullable=True)
    
    # New Fields
    use_script = Column(String, default="Yes")
    start_mode = Column(String, default="full_slot")
    duration_hours = Column(Integer, default=24)
    start_schedule = Column(DateTime, nullable=True)
    
    @property
    def display_name(self):
        return self.product_name
        
    @property
    def price_per_slot(self):
        return self.price

class UserTicket(Base):
    __tablename__ = 'user_tickets'
    
    id = Column(Integer, primary_key=True)
    discord_user_id = Column(String)
    discord_username = Column(String)
    ticket_channel_id = Column(String)
    ticket_status = Column(String, default='open')
    
    opened_at = Column(DateTime, default=datetime.now)
    last_activity = Column(DateTime, default=datetime.now)
    close_reason = Column(String, nullable=True)
    closed_at = Column(DateTime, nullable=True)
    
    slots = relationship("UserSlot", back_populates="ticket")

class UserSlot(Base):
    __tablename__ = 'user_slots'
    
    id = Column(Integer, primary_key=True)
    ticket_id = Column(Integer, ForeignKey('user_tickets.id'))
    
    patungan_version = Column(String)
    slot_number = Column(Integer)
    
    game_username = Column(String)
    display_name = Column(String)
    
    locked_price = Column(Integer)
    slot_status = Column(String, default='booked')
    
    payment_deadline = Column(DateTime, nullable=True)
    payment_verified = Column(Boolean, default=False)
    verified_by = Column(String, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    
    ticket = relationship("UserTicket", back_populates="slots")

class PaymentRecord(Base):
    __tablename__ = 'payment_records'
    
    id = Column(Integer, primary_key=True)
    slot_id = Column(Integer, ForeignKey('user_slots.id'))
    user_id = Column(String)
    
    expected_amount = Column(Integer)
    paid_amount = Column(Integer)
    amount_difference = Column(Integer)
    
    proof_image_url = Column(String)
    payment_status = Column(String, default='pending')
    notes = Column(String, nullable=True)
    
    detected_at = Column(DateTime, default=datetime.now)
    verified_at = Column(DateTime, nullable=True)
    verified_by = Column(String, nullable=True)

class SystemLog(Base):
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True)
    log_type = Column(String)
    log_level = Column(String)
    patungan_version = Column(String, nullable=True)
    user_id = Column(String, nullable=True)
    action = Column(String)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class Setting(Base):
    __tablename__ = 'settings'
    
    key = Column(String, primary_key=True)
    value = Column(String)