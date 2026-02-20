from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()

class Patungan(db.Model):
    __tablename__ = 'patungan'
    id = db.Column(db.Integer, primary_key=True)
    product_name = db.Column(db.String(100), unique=True, nullable=False)
    display_name = db.Column(db.String(100))
    price = db.Column(db.Integer, nullable=False)
    total_slots = db.Column(db.Integer)
    current_slots = db.Column(db.Integer)
    status = db.Column(db.String(20))
    message_id = db.Column(db.String(50))
    discord_channel_id = db.Column(db.String(50))
    discord_role_id = db.Column(db.String(50))
    use_script = db.Column(db.String)
    start_mode = db.Column(db.String(20))
    duration_hours = db.Column(db.Integer)
    start_schedule = db.Column(db.DateTime)
    deadline_start = db.Column(db.DateTime)
    deadline_end = db.Column(db.DateTime)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserTicket(db.Model):
    __tablename__ = 'user_tickets'
    id = db.Column(db.Integer, primary_key=True)
    discord_user_id = db.Column(db.String(50), nullable=False)
    discord_username = db.Column(db.String(100), nullable=False)
    ticket_channel_id = db.Column(db.String(50), unique=True, nullable=False)
    ticket_status = db.Column(db.String(20))
    opened_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity = db.Column(db.DateTime)
    closed_at = db.Column(db.DateTime)
    close_reason = db.Column(db.String(200))

class SystemLog(db.Model):
    __tablename__ = 'system_logs'
    id = db.Column(db.Integer, primary_key=True)
    log_type = db.Column(db.String(50), nullable=False)
    log_level = db.Column(db.String(20), nullable=False)
    patungan_version = db.Column(db.String(10))
    user_id = db.Column(db.String(50))
    action = db.Column(db.String(200), nullable=False)
    details = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

class BotSettings(db.Model):
    __tablename__ = 'bot_settings'
    key = db.Column(db.String(50), primary_key=True)
    value = db.Column(db.Text)
    updated_at = db.Column(db.DateTime)

class UserSlot(db.Model):
    __tablename__ = 'user_slots'
    id = db.Column(db.Integer, primary_key=True)
    ticket_id = db.Column(db.Integer, db.ForeignKey('user_tickets.id'), nullable=False)
    patungan_version = db.Column(db.String(100), db.ForeignKey('patungan.product_name'), nullable=False)
    slot_number = db.Column(db.Integer, nullable=False)
    game_username = db.Column(db.String(50), nullable=False)
    display_name = db.Column(db.String(50))
    slot_status = db.Column(db.String(20))
    locked_price = db.Column(db.Integer, nullable=False)
    booked_at = db.Column(db.DateTime, default=datetime.utcnow)
    payment_deadline = db.Column(db.DateTime)
    payment_type = db.Column(db.String(20))
    payment_verified = db.Column(db.Boolean)
    verified_by = db.Column(db.String(100))
    verified_at = db.Column(db.DateTime)

class PriceHistory(db.Model):
    __tablename__ = 'price_history'
    id = db.Column(db.Integer, primary_key=True)
    patungan_version = db.Column(db.String(100), db.ForeignKey('patungan.product_name'), nullable=False)
    old_price = db.Column(db.Integer, nullable=False)
    new_price = db.Column(db.Integer, nullable=False)
    changed_by = db.Column(db.String(100), nullable=False)
    changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    reason = db.Column(db.Text)
    effective_for_new = db.Column(db.Boolean)

class PaymentRecord(db.Model):
    __tablename__ = 'payment_records'
    id = db.Column(db.Integer, primary_key=True)
    slot_id = db.Column(db.Integer, db.ForeignKey('user_slots.id'), nullable=False)
    expected_amount = db.Column(db.Integer, nullable=False)
    paid_amount = db.Column(db.Integer, nullable=False)
    amount_difference = db.Column(db.Integer)
    proof_image_url = db.Column(db.Text, nullable=False)
    payment_status = db.Column(db.String(20))
    is_topup = db.Column(db.Boolean)
    parent_payment_id = db.Column(db.Integer)
    verified_by = db.Column(db.String(100))
    verified_at = db.Column(db.DateTime)
    notes = db.Column(db.Text)
    detected_at = db.Column(db.DateTime, default=datetime.utcnow)

class CustomCommand(db.Model):
    __tablename__ = 'custom_commands'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String, unique=True)
    response = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)