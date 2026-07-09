from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class DeviceCreate(BaseModel):
    name: str = Field(..., max_length=120)
    ip: str = Field(..., max_length=64)
    mac: Optional[str] = Field(None, max_length=64)
    location: Optional[str] = Field(None, max_length=120)
    latency_warn_ms: Optional[int] = None
    loss_warn_pct: Optional[int] = None


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    mac: Optional[str] = None
    location: Optional[str] = None
    is_active: Optional[bool] = None
    latency_warn_ms: Optional[int] = None
    loss_warn_pct: Optional[int] = None


class DeviceOut(BaseModel):
    id: int
    name: str
    ip: str
    mac: Optional[str]
    location: Optional[str]
    is_active: bool
    current_status: str
    last_seen_at: Optional[datetime]
    last_state_change_at: Optional[datetime]

    class Config:
        from_attributes = True


class DeviceStatsOut(DeviceOut):
    """Linha da tabela principal, com estatísticas da última hora."""

    last_rtt_ms: Optional[float] = None
    last_loss_pct: Optional[float] = None
    avg_rtt_1h_ms: Optional[float] = None
    min_rtt_1h_ms: Optional[float] = None
    max_rtt_1h_ms: Optional[float] = None
    avg_loss_1h_pct: Optional[float] = None
    offline_since_seconds: Optional[int] = None
    availability_24h_pct: Optional[float] = None


class PingResultOut(BaseModel):
    timestamp: datetime
    packets_sent: int
    packets_received: int
    loss_pct: float
    rtt_min_ms: Optional[float]
    rtt_avg_ms: Optional[float]
    rtt_max_ms: Optional[float]
    status: str

    class Config:
        from_attributes = True


class AlertEventOut(BaseModel):
    timestamp: datetime
    from_status: Optional[str]
    to_status: str
    message: Optional[str]

    class Config:
        from_attributes = True


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str = "admin"


class MeResponse(BaseModel):
    username: str
    role: str


class UserCreate(BaseModel):
    username: str = Field(..., max_length=80)
    password: str = Field(..., min_length=4)
    role: str = "viewer"


class UserPasswordReset(BaseModel):
    password: str = Field(..., min_length=4)


class UserOut(BaseModel):
    id: int
    username: str
    role: str

    class Config:
        from_attributes = True


class CorrelationCluster(BaseModel):
    window_start: datetime
    device_count: int
    devices: list[dict]


class LocationSummary(BaseModel):
    location: str
    events: int
    devices_affected: int


class AvailabilityPoint(BaseModel):
    period_start: datetime
    availability_pct: float
    avg_rtt_ms: Optional[float]
