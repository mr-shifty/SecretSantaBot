from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
)
from sqlalchemy.ext.declarative import declarative_base
import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True, nullable=False, index=True)
    telegram_username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Route1Entry(Base):
    """Full route: requires email, full address, delivery method and wishlist."""
    __tablename__ = "route1_entries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String, nullable=False)
    full_address = Column(Text, nullable=False)
    delivery_method = Column(String, nullable=True)
    wishlist = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending/completed/cancelled
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Route2Entry(Base):
    """Simple route: only email is required."""
    __tablename__ = "route2_entries"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    email = Column(String, nullable=False)
    status = Column(String, default="pending")
    started_at = Column(DateTime, default=datetime.datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)


class Assignment(Base):
    """Assignment of giver -> receiver for a given route."""
    __tablename__ = "assignments"
    id = Column(Integer, primary_key=True)
    giver_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    receiver_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    route_type = Column(Integer)  # 1 or 2
    assigned_at = Column(DateTime, default=datetime.datetime.utcnow)
    sent_status = Column(String, default="pending")  # pending/sent/failed


class NotificationLog(Base):
    """Log of notifications (reminders, admin messages)."""
    __tablename__ = "notification_logs"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True, index=True)
    channel = Column(String, nullable=False)  # telegram/email
    notif_type = Column(String, nullable=False)  # reminder/manual/assignment
    payload = Column(Text, nullable=True)
    status = Column(String, default="pending")  # pending/sent/failed
    sent_at = Column(DateTime, nullable=True)

