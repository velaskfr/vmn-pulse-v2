import enum
from datetime import datetime

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    Boolean,
    ForeignKey,
    Enum,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class DeviceStatus(str, enum.Enum):
    online = "online"
    warning = "warning"
    offline = "offline"
    unknown = "unknown"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(80), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="admin")  # admin | viewer
    created_at = Column(DateTime, default=datetime.utcnow)


class PingHourly(Base):
    """Agregados por hora, usados após a limpeza do histórico detalhado."""

    __tablename__ = "ping_hourly"
    __table_args__ = (UniqueConstraint("device_id", "hour", name="uq_ping_hourly"),)

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    hour = Column(DateTime, nullable=False, index=True)
    total = Column(Integer, default=0)
    ok = Column(Integer, default=0)
    rtt_avg_ms = Column(Float, nullable=True)
    rtt_min_ms = Column(Float, nullable=True)
    rtt_max_ms = Column(Float, nullable=True)
    loss_avg_pct = Column(Float, nullable=True)


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False)
    ip = Column(String(64), nullable=False, index=True)
    mac = Column(String(64), nullable=True)
    location = Column(String(120), nullable=True)

    is_active = Column(Boolean, default=True)  # monitoramento ligado/pausado

    # limites específicos do equipamento (opcional, senão usa os globais)
    latency_warn_ms = Column(Integer, nullable=True)
    loss_warn_pct = Column(Integer, nullable=True)

    # estado atual (cache para não recalcular toda hora)
    current_status = Column(Enum(DeviceStatus), default=DeviceStatus.unknown)
    last_seen_at = Column(DateTime, nullable=True)  # última vez que respondeu
    last_state_change_at = Column(DateTime, nullable=True)  # última mudança de status
    consecutive_fail_cycles = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)

    ping_results = relationship(
        "PingResult", back_populates="device", cascade="all, delete-orphan"
    )
    alert_events = relationship(
        "AlertEvent", back_populates="device", cascade="all, delete-orphan"
    )


class PingResult(Base):
    __tablename__ = "ping_results"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    packets_sent = Column(Integer, default=0)
    packets_received = Column(Integer, default=0)
    loss_pct = Column(Float, default=100.0)

    rtt_min_ms = Column(Float, nullable=True)
    rtt_avg_ms = Column(Float, nullable=True)
    rtt_max_ms = Column(Float, nullable=True)

    status = Column(Enum(DeviceStatus), default=DeviceStatus.unknown)

    device = relationship("Device", back_populates="ping_results")


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

    from_status = Column(Enum(DeviceStatus), nullable=True)
    to_status = Column(Enum(DeviceStatus), nullable=False)
    message = Column(Text, nullable=True)
    discord_sent = Column(Boolean, default=False)

    device = relationship("Device", back_populates="alert_events")


class SpeedTestResult(Base):
    __tablename__ = "speedtest_results"

    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    ping_ms = Column(Float, nullable=True)
    download_mbps = Column(Float, nullable=True)
    upload_mbps = Column(Float, nullable=True)
    server_name = Column(String(200), nullable=True)
    isp = Column(String(120), nullable=True)
    wan_ip = Column(String(64), nullable=True)  # IP publico de saida do teste
    status = Column(String(20), default="ok")  # ok | slow | error
    error_message = Column(Text, nullable=True)
