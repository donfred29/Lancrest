from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Enum as SAEnum, Text
from sqlalchemy.orm import relationship
import enum

from .database import Base


class UserRole(str, enum.Enum):
    user = "user"
    admin = "admin"


class AccountStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"


class TransactionType(str, enum.Enum):
    deposit = "deposit"
    withdrawal = "withdrawal"
    transfer_in = "transfer_in"
    transfer_out = "transfer_out"
    bill_pay = "bill_pay"
    admin_credit = "admin_credit"
    admin_debit = "admin_debit"
    card_charge = "card_charge"


class TransactionStatus(str, enum.Enum):
    completed = "completed"
    pending = "pending"
    failed = "failed"


class CardStatus(str, enum.Enum):
    active = "active"
    frozen = "frozen"
    pending = "pending"
    declined = "declined"


class CardType(str, enum.Enum):
    virtual = "virtual"
    physical = "physical"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    username = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(SAEnum(UserRole), default=UserRole.user, nullable=False)
    phone = Column(String, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="user", uselist=False)
    cards = relationship("Card", back_populates="user")


class Account(Base):
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    account_number = Column(String, unique=True, nullable=False)
    balance = Column(Float, default=0.0, nullable=False)
    status = Column(SAEnum(AccountStatus), default=AccountStatus.active)
    branch = Column(String, default="Lancrest Main Branch")
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="account")
    transactions = relationship(
        "Transaction",
        back_populates="account",
        foreign_keys="Transaction.account_id",
        order_by="desc(Transaction.created_at)",
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    type = Column(SAEnum(TransactionType), nullable=False)
    amount = Column(Float, nullable=False)
    description = Column(String, default="")
    status = Column(SAEnum(TransactionStatus), default=TransactionStatus.completed)
    related_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="transactions", foreign_keys=[account_id])


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    card_type = Column(SAEnum(CardType), nullable=False)
    card_number = Column(String, default="")          # masked or full for demo
    cvv = Column(String, default="")
    expiry = Column(String, default="")
    status = Column(SAEnum(CardStatus), default=CardStatus.pending)
    daily_limit = Column(Float, default=1000.0)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="cards")
