import asyncio
import csv
import io
from collections import defaultdict
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse, PlainTextResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Device, PingResult, PingHourly, AlertEvent, DeviceStatus
from app.schemas import DeviceStatsOut, PingResultOut, AlertEventOut, AvailabilityPoint
from app.security import get_current_user

router = APIRouter(prefix="/api/monitoring", tags=["monitoring"], dependencies=[Depends(get_current_user)])


def build_status_rows(db: Session) -> list[DeviceStatsOut]:
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

        status_value = device.current_status.value if device.current_status else "unknown"
        if not device.is_active:
            status_value = "maintenance"

        result.append(
            DeviceStatsOut(
                id=device.id,
                name=device.name,
                ip=device.ip,
                mac=device.mac,
                location=device.location,
                is_active=device.is_active,
                current_status=status_value,
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


@router.get("/status", response_model=list[DeviceStatsOut])
def get_status(db: Session = Depends(get_db)):
    return build_status_rows(db)


@router.get("/export/status.csv")
def export_status_csv(db: Session = Depends(get_db)):
    rows = build_status_rows(db)
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow([
        "Nome", "IP", "MAC", "Localizacao", "Status", "RTT ultimo (ms)",
        "Media 1h (ms)", "Min 1h (ms)", "Max 1h (ms)", "Perda 1h (%)",
        "Disponibilidade 24h (%)", "Ultima mudanca de status", "Tempo offline (s)",
    ])
    for r in rows:
        writer.writerow([
            r.name, r.ip, r.mac or "", r.location or "", r.current_status,
            r.last_rtt_ms or "", r.avg_rtt_1h_ms or "", r.min_rtt_1h_ms or "",
            r.max_rtt_1h_ms or "", r.avg_loss_1h_pct if r.avg_loss_1h_pct is not None else "",
            r.availability_24h_pct if r.availability_24h_pct is not None else "",
            r.last_state_change_at.isoformat() if r.last_state_change_at else "",
            r.offline_since_seconds or "",
        ])
    buf.seek(0)
    filename = f"vmn-pulse-status-{datetime.utcnow().strftime('%Y%m%d-%H%M')}.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.get("/devices/{device_id}/history.csv")
def export_history_csv(device_id: int, hours: int = 24, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(PingResult)
        .filter(PingResult.device_id == device_id, PingResult.timestamp >= since)
        .order_by(PingResult.timestamp)
        .all()
    )
    buf = io.StringIO()
    writer = csv.writer(buf, delimiter=";")
    writer.writerow(["Data/hora (UTC)", "Status", "Enviados", "Recebidos", "Perda (%)",
                     "RTT min (ms)", "RTT medio (ms)", "RTT max (ms)"])
    for r in rows:
        writer.writerow([
            r.timestamp.isoformat(), r.status.value, r.packets_sent, r.packets_received,
            r.loss_pct, r.rtt_min_ms or "", r.rtt_avg_ms or "", r.rtt_max_ms or "",
        ])
    buf.seek(0)
    safe_name = "".join(c for c in device.name if c.isalnum() or c in "-_ ").strip().replace(" ", "-")
    filename = f"vmn-pulse-{safe_name}-{hours}h.csv"
    return StreamingResponse(
        iter([buf.getvalue().encode("utf-8-sig")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


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


@router.post("/devices/{device_id}/traceroute", response_class=PlainTextResponse)
async def run_traceroute(device_id: int, db: Session = Depends(get_db)):
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    try:
        proc = await asyncio.create_subprocess_exec(
            "traceroute", "-n", "-w", "2", "-q", "1", "-m", "20", device.ip,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=45)
        return stdout.decode(errors="replace")
    except asyncio.TimeoutError:
        try:
            proc.kill()
        except Exception:
            pass
        raise HTTPException(status_code=504, detail="Traceroute excedeu o tempo limite (45s)")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="traceroute não está instalado no container")


@router.get("/devices/{device_id}/availability", response_model=list[AvailabilityPoint])
def get_availability(device_id: int, days: int = 7, db: Session = Depends(get_db)):
    """Disponibilidade por hora: mescla histórico detalhado + agregados antigos."""
    device = db.query(Device).get(device_id)
    if not device:
        raise HTTPException(status_code=404, detail="Equipamento não encontrado")

    since = datetime.utcnow() - timedelta(days=days)

    buckets: dict[datetime, dict] = {}

    # 1) agregados por hora (dados antigos, já compactados pela retenção)
    hourly = (
        db.query(PingHourly)
        .filter(PingHourly.device_id == device_id, PingHourly.hour >= since)
        .all()
    )
    for h in hourly:
        buckets[h.hour] = {
            "total": h.total,
            "ok": h.ok,
            "rtt_sum": (h.rtt_avg_ms or 0) * h.total,
            "rtt_n": h.total if h.rtt_avg_ms is not None else 0,
        }

    # 2) histórico detalhado (dados recentes)
    all_rows = (
        db.query(PingResult.timestamp, PingResult.status, PingResult.rtt_avg_ms)
        .filter(PingResult.device_id == device_id, PingResult.timestamp >= since)
        .order_by(PingResult.timestamp)
        .all()
    )
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


@router.get("/correlation")
def get_correlation(hours: int = 24, window_minutes: int = 5, db: Session = Depends(get_db)):
    """
    Agrupa eventos de queda/lentidão em janelas de tempo para identificar
    quedas simultâneas (mesmo switch/AP/uplink afetando vários equipamentos).
    """
    since = datetime.utcnow() - timedelta(hours=hours)
    window = max(window_minutes, 1) * 60

    events = (
        db.query(AlertEvent, Device)
        .join(Device, AlertEvent.device_id == Device.id)
        .filter(
            AlertEvent.timestamp >= since,
            AlertEvent.to_status.in_([DeviceStatus.offline, DeviceStatus.warning]),
        )
        .order_by(AlertEvent.timestamp)
        .all()
    )

    clusters: dict[int, dict] = {}
    location_stats: dict[str, dict] = defaultdict(lambda: {"events": 0, "devices": set()})

    for event, device in events:
        bucket = int(event.timestamp.timestamp() // window)
        c = clusters.setdefault(bucket, {"window_start": datetime.utcfromtimestamp(bucket * window), "devices": {}})
        c["devices"][device.id] = {
            "name": device.name,
            "ip": device.ip,
            "location": device.location or "(sem local)",
            "to_status": event.to_status.value,
            "time": event.timestamp.isoformat(),
        }
        loc = device.location or "(sem local)"
        location_stats[loc]["events"] += 1
        location_stats[loc]["devices"].add(device.id)

    simultaneous = [
        {
            "window_start": c["window_start"].isoformat(),
            "device_count": len(c["devices"]),
            "devices": list(c["devices"].values()),
        }
        for c in clusters.values()
        if len(c["devices"]) >= 2
    ]
    simultaneous.sort(key=lambda x: x["window_start"], reverse=True)

    by_location = [
        {"location": loc, "events": s["events"], "devices_affected": len(s["devices"])}
        for loc, s in location_stats.items()
    ]
    by_location.sort(key=lambda x: x["events"], reverse=True)

    return {
        "hours": hours,
        "window_minutes": window_minutes,
        "total_events": len(events),
        "simultaneous_clusters": simultaneous,
        "by_location": by_location,
    }
