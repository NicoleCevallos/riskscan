from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, Text, JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from ..database import Base

class TikTokUser(Base):
    __tablename__ = "tiktok_users"
    id = Column(Integer, primary_key=True)
    open_id = Column(String, unique=True, index=True, nullable=False)
    access_token = Column(Text, nullable=False)
    refresh_token = Column(Text, nullable=True)
    expires_at = Column(DateTime, nullable=True)

    display_name = Column(String, nullable=True)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    videos = relationship("TikTokVideo", back_populates="user", cascade="all, delete-orphan")

class TikTokVideo(Base):
    __tablename__ = "tiktok_videos"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("tiktok_users.id"), index=True, nullable=False)
    video_id = Column(String, index=True, nullable=False)
    caption = Column(Text, nullable=True)
    cover_image_url = Column(Text, nullable=True)
    create_time_utc = Column(DateTime, nullable=True)
    share_url = Column(Text, nullable=True)

    scanned_at = Column(DateTime, nullable=True)
    score = Column(Integer, default=0)
    band = Column(String, default="low")
    factors = Column(JSON, default={})
    detections = Column(JSON, default=[])
    recs = Column(JSON, default=[])

    user = relationship("TikTokUser", back_populates="videos")
    __table_args__ = (UniqueConstraint("video_id", name="uq_tiktok_video_id"),)
