from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Float
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from .database import Base

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True)
    handle = Column(String, unique=True, index=True, nullable=False)
    platform = Column(String, default="local")
    created_at = Column(DateTime, server_default=func.now())

class TikTokAccount(Base):
    __tablename__ = "tiktok_accounts"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    tiktok_id = Column(String, index=True)
    account = relationship("Account", backref="tiktok")

class Post(Base):
    __tablename__ = "posts"
    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)
    caption = Column(Text, default="")
    image_path = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    account = relationship("Account", backref="posts")

class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    detector = Column(String, nullable=False)  # 'email','phone','address','gps'
    value = Column(Text, nullable=False)
    extra = Column(Text, nullable=True)
    post = relationship("Post", backref="detections")

class RiskScore(Base):
    __tablename__ = "risk_scores"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    score = Column(Float, nullable=False)
    band = Column(String, nullable=False)  # LOW/MEDIUM/HIGH
    why = Column(Text, nullable=False)     # serialized reasons
    post = relationship("Post", backref="risk_score")

class Recommendation(Base):
    __tablename__ = "recommendations"
    id = Column(Integer, primary_key=True)
    post_id = Column(Integer, ForeignKey("posts.id"), nullable=False, index=True)
    text = Column(Text, nullable=False)
    post = relationship("Post", backref="recommendations")
