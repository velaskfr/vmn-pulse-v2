from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import SpeedTestResult
from app.security import get_current_user, require_admin
from app.wan_monitor import run_wan_test

router = APIRouter(prefix="/api/wan", tags=["wan"], dependencies=[Depends(get_current_user)])


def _serialize(r: SpeedTestResult) -> dict:
    return {
        "timestamp": r.timestamp.isoformat(),
        "ping_ms": r.ping_ms,
        "download_mbps": r.download_mbps,
        "upload_mbps": r.upload_mbps,
        "server_name": r.server_name,
        "isp": r.isp,
        "status": r.status,
        "error_message": r.error_message,
    }


@router.get("/latest")
def latest(db: Session = Depends(get_db)):
    row = db.query(SpeedTestResult).order_by(SpeedTestResult.timestamp.desc()).first()
    return {
        "result": _serialize(row) if row else None,
        "thresholds": {
            "min_download_mbps": settings.speedtest_min_download_mbps,
            "min_upload_mbps": settings.speedtest_min_upload_mbps,
            "max_ping_ms": settings.speedtest_max_ping_ms,
            "interval_minutes": settings.speedtest_interval_minutes,
            "enabled": settings.speedtest_enabled,
        },
    }


@router.get("/history")
def history(hours: int = 24, db: Session = Depends(get_db)):
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(SpeedTestResult)
        .filter(SpeedTestResult.timestamp >= since)
        .order_by(SpeedTestResult.timestamp)
        .all()
    )
    return [_serialize(r) for r in rows]


@router.post("/run", dependencies=[Depends(require_admin)])
async def run_now():
    """Dispara um speedtest manual imediatamente (admin)."""
    await run_wan_test()
    return {"status": "executado"}
