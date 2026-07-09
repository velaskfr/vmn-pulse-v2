from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, PingResult, AlertEvent, DeviceStatus
from app.schemas import DeviceStatsOut, PingResultOut, AlertEventOut, AvailabilityPoint
from app.security import get_current_user

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"], dependencies=[Depends(get_current_user)])


@router.get("/status", response_model=list[DeviceStatsOut])
def get_status(db: Session = Depends(get_db)):
    now = datetime.utcnow()
    one_hour_ago = now - timedelta(hours=1)
    one_day_ago = now - timedelta(hours=24)

    devices = db.query(Device).order_by(Device.name).all()
    result = []

    for device in devices:
        last_ping = (
            db.query(PingResult)
            .filter(PingResult.device_id == device.id)
            .order_by(PingResult.timestamp.desc())
            .first()
        )

        stats_1h = (
            db.query(
                func.avg(PingResult.rtt_avg_ms).label("avg_rtt"),
                func.min(PingResult.rtt_min_ms).label("min_rtt"),
                func.max(PingResult.rtt_max_ms).label("max_rtt"),
                func.avg(PingResult.loss_pct).label("avg_loss"),
            )
            .filter(PingResult.device_id == device.id, PingResult.timestamp >= one_hour_ago)
            .first()
        )

        total_24h = (
            db.query(func.count(PingResult.id))
            .filter(PingResult.device_id == device.id, PingResult.timestamp >= one_day_ago)
            .scalar()
        )
        ok_24h = (
            db.query(func.count(PingResult.id))
            .filter(
                PingResult.device_id == device.id,
                PingResult.timestamp >= one_day_ago,
                PingResult.status != DeviceStatus.offline,
            )
            .scalar()
        )
        availability = round((ok_24h / total_24h) * 100, 2) if total_24h else None

        offline_seconds = None
        if device.current_status == DeviceStatus.offline and device.last_state_change_at:
            offline_seconds = int((now - device.last_state_change_at).total_seconds())

        result.append(
            DeviceStatsOut(
                id=device.id,
                name=device.name,
                ip=device.ip,
                mac=device.mac,
                location=device.location,
                is_active=device.is_active,
                current_status=device.current_status.value if device.current_status else "unknown",
                last_seen_at=device.last_seen_at,
                last_state_change_at=device.last_state_change_at,
                last_rtt_ms=last_ping.rtt_avg_ms if last_ping else None,
                last_loss_pct=last_ping.loss_pct if last_ping else None,
                avg_rtt_1h_ms=round(stats_1h.avg_rtt, 1) if stats_1h and stats_1h.avg_rtt else None,
                min_rtt_1h_ms=round(stats_1h.min_rtt, 1) if stats_1h and stats_1h.min_rtt else None,
                max_rtt_1h_ms=round(stats_1h.max_rtt, 1) if stats_1h and stats_1h.max_rtt else None,
                avg_loss_1h_pct=round(stats_1h.avg_loss, 1) if stats_1h and stats_1h.avg_loss is not None else None,
                offline_since_seconds=offline_seconds,
                availability_24h_pct=availability,
            )
        )

    return result


@router.get("/devices/{device_id}/history", response_model=list[PingResultOut])
def get_history(device_id: int, limit: int = 100, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    rows = (
        db.query(PingResult)
        .filter(PingResult.device_id == device_id)
        .order_by(PingResult.timestamp.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.get("/devices/{device_id}/alerts", response_model=list[AlertEventOut])
def get_alerts(device_id: int, limit: int = 50, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    rows = (
        db.query(AlertEvent)
        .filter(AlertEvent.device_id == device_id)
        .order_by(AlertEvent.timestamp.desc())
        .limit(limit)
        .all()
    )
    return rows


@router.get("/devices/{device_id}/availability", response_model=list[AvailabilityPoint])
def get_availability(device_id: int, days: int = 7, db: Session = Depends(get_db)):
    """Disponibilidade agrupada por hora, para montar o gráfico da página de detalhe."""
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    since = datetime.utcnow() - timedelta(days=days)

    # Agregamos por hora em Python (simples e portátil entre bancos).
    all_rows = (
        db.query(PingResult.timestamp, PingResult.status, PingResult.rtt_avg_ms)
        .filter(PingResult.device_id == device_id, PingResult.timestamp >= since)
        .order_by(PingResult.timestamp)
        .all()
    )

    buckets: dict[datetime, dict] = {}
    for ts, status, rtt in all_rows:
        key = ts.replace(minute=0, second=0, microsecond=0)
        b = buckets.setdefault(key, {"total": 0, "ok": 0, "rtt_sum": 0.0, "rtt_n": 0})
        b["total"] += 1
        if status != DeviceStatus.offline:
            b["ok"] += 1
        if rtt is not None:
            b["rtt_sum"] += rtt
            b["rtt_n"] += 1

    points = []
    for key in sorted(buckets.keys()):
        b = buckets[key]
        points.append(
            AvailabilityPoint(
                period_start=key,
                availability_pct=round((b["ok"] / b["total"]) * 100, 2) if b["total"] else 0,
                avg_rtt_ms=round(b["rtt_sum"] / b["rtt_n"], 1) if b["rtt_n"] else None,
            )
        )
    return points
