from sqlalchemy import Column, Integer, String, Date, DateTime, Boolean, Enum, ForeignKey, DECIMAL
from sqlalchemy.orm import relationship
from .database import Base
import enum

class UserType(enum.Enum):
    employee = "employee"
    student = "student"
    other = "other"

class User(Base):
    __tablename__ = "users"
    telegram_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    phone_number = Column(String(20))
    user_type = Column(Enum(UserType), nullable=False)
    sessions = relationship("Session", back_populates="user", foreign_keys='Session.booked_user_id')
    payments = relationship("Payment", back_populates="user", foreign_keys='Payment.user_id')

class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_date = Column(Date, nullable=False)
    time_slot = Column(String(20), nullable=False)
    available = Column(Boolean, default=True)
    booked_user_id = Column(Integer, ForeignKey("users.telegram_id"))
    cost = Column(DECIMAL(10,2), nullable=False)
    user = relationship("User", back_populates="sessions", foreign_keys=[booked_user_id])
    payments = relationship("Payment", back_populates="session", foreign_keys='Payment.session_id')

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.telegram_id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    payment_date = Column(DateTime, nullable=False)
    amount = Column(DECIMAL(10,2), nullable=False)
    user = relationship("User", back_populates="payments", foreign_keys=[user_id])
    session = relationship("Session", back_populates="payments", foreign_keys=[session_id])