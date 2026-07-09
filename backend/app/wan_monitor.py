import asyncio
import logging
from datetime import datetime

import speedtest

from app.config import settings
from app.database import SessionLocal
from app.discord_alert import send_discord_alert
from app.models import SpeedTestResult

logger = logging.getLogger("netmonitor.speedtest")

_last_status: str | None = None


def _run_speedtest_blocking() -> dict:
    st = speedtest.Speedtest(secure=True)
    st.get_best_server()
    st.download()
    st.upload()
    r = st.results.dict()
    return {
        "ping_ms": round(r.get("ping") or 0, 1),
        "download_mbps": round((r.get("download") or 0) / 1_000_000, 1),
        "upload_mbps": round((r.get("upload") or 0) / 1_000_000, 1),
        "server_name": f"{r['server'].get('sponsor', '')} - {r['server'].get('name', '')}".strip(" -"),
        "isp": (r.get("client") or {}).get("isp"),
    }


def _classify(data: dict) -> tuple[str, str]:
    problems = []
    if data["download_mbps"] < settings.speedtest_min_download_mbps:
        problems.append(f"download {data['download_mbps']} Mbps (mín {settings.speedtest_min_download_mbps})")
    if data["upload_mbps"] < settings.speedtest_min_upload_mbps:
        problems.append(f"upload {data['upload_mbps']} Mbps (mín {settings.speedtest_min_upload_mbps})")
    if data["ping_ms"] > settings.speedtest_max_ping_ms:
        problems.append(f"latência {data['ping_ms']} ms (máx {settings.speedtest_max_ping_ms})")
    if problems:
        return "slow", "; ".join(problems)
    return "ok", ""


async def run_wan_test():
    """Executa um speedtest, grava o resultado e alerta em mudanças de estado."""
    global _last_status
    db = SessionLocal()
    try:
        try:
            data = await asyncio.to_thread(_run_speedtest_blocking)
            status, detail = _classify(data)
            row = SpeedTestResult(
                timestamp=datetime.utcnow(),
                ping_ms=data["ping_ms"],
                download_mbps=data["download_mbps"],
                upload_mbps=data["upload_mbps"],
                server_name=data["server_name"],
                isp=data["isp"],
                status=status,
            )
        except Exception as exc:
            logger.warning("Speedtest falhou: %s", exc)
            status, detail = "error", str(exc)[:300]
            row = SpeedTestResult(timestamp=datetime.utcnow(), status="error", error_message=detail)

        db.add(row)
        db.commit()

        if _last_status is not None and status != _last_status:
            emoji_status = {"ok": "online", "slow": "warning", "error": "offline"}
            extra = detail
            if status == "ok":
                extra = (
                    f"Download: {row.download_mbps} Mbps | Upload: {row.upload_mbps} Mbps | "
                    f"Ping: {row.ping_ms} ms"
                )
            asyncio.create_task(
                send_discord_alert(
                    device_name="Internet (Speedtest)",
                    ip=row.isp or "WAN",
                    location=row.server_name,
                    from_status=emoji_status.get(_last_status),
                    to_status=emoji_status.get(status, "unknown"),
                    extra=extra,
                )
            )
        _last_status = status
        logger.info(
            "Speedtest: %s | down=%s up=%s ping=%s",
            status, row.download_mbps, row.upload_mbps, row.ping_ms,
        )
    except Exception:
        logger.exception("Erro ao gravar resultado do speedtest")
        db.rollback()
    finally:
        db.close()


async def wan_loop():
    if not settings.speedtest_enabled:
        logger.info("Speedtest desativado (SPEEDTEST_ENABLED=false)")
        return
    interval = max(settings.speedtest_interval_minutes, 5) * 60
    logger.info("Monitor de internet iniciado (speedtest a cada %s min)", interval // 60)
    await asyncio.sleep(20)  # deixa o app subir e o primeiro ciclo de ping rodar
    while True:
        await run_wan_test()
        await asyncio.sleep(interval)
