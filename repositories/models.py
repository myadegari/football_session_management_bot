import enum

from sqlalchemy import (
    DECIMAL,
    Boolean,
    Column,
    Date,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
import uuid

from sqlalchemy.orm import relationship

from .database import Base


class UserType(enum.Enum):
    EMPLOYEE = "EMPLOYEE"
    STUDENT = "STUDENT"
    GENERAL = "GENERAL"


class UserRole(enum.Enum):
    ADMIN = "ADMIN"
    USER = "USER"

class VerificationStatus(enum.Enum):
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"

class User(Base):
    __tablename__ = "users"
    user_id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    surname = Column(String(100), nullable=False)
    phone_number = Column(String(20))
    account_type = Column(Enum(UserType), nullable=False, default=UserType.GENERAL)
    is_active = Column(Boolean, default=True)
    is_verified = Column(Enum(VerificationStatus), nullable=False, default=VerificationStatus.REJECTED)
    role = Column(Enum(UserRole), nullable=False, default=UserRole.USER)
    veryfication_token = Column(String(100), nullable=True)
    sessions = relationship(
        "Session", back_populates="user", foreign_keys="Session.booked_user_id"
    )
    payments = relationship(
        "Payment", back_populates="user", foreign_keys="Payment.user_id"
    )


class PaymentCategory(Base):
    __tablename__ = "payment_categories"
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_type = Column(Enum(UserType), nullable=False)
    session_cost = Column(Integer, nullable=False)


class Session(Base):
    __tablename__ = "sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    session_date = Column(Date, nullable=False)
    time_slot = Column(String(20), nullable=False)
    available = Column(Boolean, default=True)
    booked_user_id = Column(Integer, ForeignKey("users.user_id"))
    cost = Column(Integer, nullable=False)
    user = relationship(
        "User", back_populates="sessions", foreign_keys=[booked_user_id]
    )
    payments = relationship(
        "Payment", back_populates="session", foreign_keys="Payment.session_id"
    )


class Payment(Base):
    __tablename__ = "payments"
    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    session_id = Column(Integer, ForeignKey("sessions.id"), nullable=False)
    payment_date = Column(DateTime, nullable=False)
    amount = Column(Integer, nullable=False)
    verified = Column(Boolean, default=False)
    user = relationship("User", back_populates="payments", foreign_keys=[user_id])
    session = relationship(
        "Session", back_populates="payments", foreign_keys=[session_id]
    )
