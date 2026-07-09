import asyncio
import logging
from datetime import datetime

from app.config import settings
from app.database import SessionLocal
from app.discord_alert import send_discord_alert
from app.models import Device, PingResult, AlertEvent, DeviceStatus
from app.ping_service import ping_batch, PingOutcome

logger = logging.getLogger("netmonitor.scheduler")


def _classify(outcome: PingOutcome, latency_warn_ms: int, loss_warn_pct: int) -> DeviceStatus:
    if not outcome.is_alive or outcome.loss_pct >= 100:
        return DeviceStatus.offline
    if outcome.loss_pct >= loss_warn_pct or (
        outcome.rtt_avg_ms is not None and outcome.rtt_avg_ms >= latency_warn_ms
    ):
        return DeviceStatus.warning
    return DeviceStatus.online


async def _run_cycle():
    db = SessionLocal()
    try:
        devices = db.query(Device).filter(Device.is_active.is_(True)).all()
        if not devices:
            return

        ip_list = [d.ip for d in devices]
        outcomes = await ping_batch(ip_list)
        now = datetime.utcnow()

        for device in devices:
            outcome = outcomes.get(device.ip)
            if outcome is None:
                # não deveria acontecer, mas por segurança tratamos como offline
                outcome = PingOutcome(device.ip, settings.ping_count, 0, 100.0, None, None, None, False)

            latency_warn = device.latency_warn_ms or settings.latency_warn_ms
            loss_warn = device.loss_warn_pct or settings.loss_warn_pct
            raw_status = _classify(outcome, latency_warn, loss_warn)

            ping_row = PingResult(
                device_id=device.id,
                timestamp=now,
                packets_sent=outcome.packets_sent,
                packets_received=outcome.packets_received,
                loss_pct=outcome.loss_pct,
                rtt_min_ms=outcome.rtt_min_ms,
                rtt_avg_ms=outcome.rtt_avg_ms,
                rtt_max_ms=outcome.rtt_max_ms,
                status=raw_status,
            )
            db.add(ping_row)

            if outcome.is_alive:
                device.last_seen_at = now

            previous_status = device.current_status

            if raw_status == DeviceStatus.offline:
                device.consecutive_fail_cycles = (device.consecutive_fail_cycles or 0) + 1
            else:
                device.consecutive_fail_cycles = 0

            # Histerese: só confirma "offline" depois de N ciclos ruins seguidos,
            # para não alarmar por causa de uma perda pontual de pacote.
            if raw_status == DeviceStatus.offline and device.consecutive_fail_cycles < settings.offline_confirm_cycles:
                effective_status = DeviceStatus.warning if previous_status == DeviceStatus.online else previous_status
                if previous_status in (None, DeviceStatus.unknown):
                    effective_status = DeviceStatus.warning
            else:
                effective_status = raw_status

            if effective_status != previous_status:
                device.current_status = effective_status
                device.last_state_change_at = now

                event = AlertEvent(
                    device_id=device.id,
                    timestamp=now,
                    from_status=previous_status,
                    to_status=effective_status,
                    message=f"Perda: {outcome.loss_pct}% | RTT médio: {outcome.rtt_avg_ms}",
                )
                db.add(event)

                asyncio.create_task(
                    send_discord_alert(
                        device_name=device.name,
                        ip=device.ip,
                        location=device.location,
                        from_status=previous_status.value if previous_status else None,
                        to_status=effective_status.value,
                        extra=f"Perda: {outcome.loss_pct}%"
                        + (f" | RTT médio: {round(outcome.rtt_avg_ms, 1)} ms" if outcome.rtt_avg_ms else ""),
                    )
                )

        db.commit()
    except Exception:
        logger.exception("Erro no ciclo de monitoramento")
        db.rollback()
    finally:
        db.close()


async def scheduler_loop():
    logger.info("Scheduler de ping iniciado (intervalo: %ss)", settings.ping_interval_seconds)
    while True:
        start = asyncio.get_event_loop().time()
        try:
            await _run_cycle()
        except Exception:
            logger.exception("Falha inesperada no loop do scheduler")

        elapsed = asyncio.get_event_loop().time() - start
        sleep_for = max(settings.ping_interval_seconds - elapsed, 5)
        await asyncio.sleep(sleep_for)
