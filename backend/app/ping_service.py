import asyncio
import logging
import time
from dataclasses import dataclass
from typing import List

from icmplib import async_ping

from app.config import settings

logger = logging.getLogger("netmonitor.ping")

TCP_TIMEOUT_S = 3.0


@dataclass
class PingOutcome:
    ip: str
    packets_sent: int
    packets_received: int
    loss_pct: float
    rtt_min_ms: float | None
    rtt_avg_ms: float | None
    rtt_max_ms: float | None
    is_alive: bool


def _failed(target: str) -> PingOutcome:
    return PingOutcome(target, settings.ping_count, 0, 100.0, None, None, None, False)


async def _ping_one(target: str, sem: asyncio.Semaphore) -> PingOutcome:
    """ICMP isolado: falha (DNS, socket, etc.) de um host nunca afeta os outros."""
    async with sem:
        try:
            host = await async_ping(
                target,
                count=settings.ping_count,
                interval=0.3,
                timeout=1.5,
                privileged=True,
            )
        except Exception as exc:
            logger.warning("Ping falhou para %s: %s", target, exc)
            return _failed(target)

    return PingOutcome(
        ip=target,
        packets_sent=host.packets_sent,
        packets_received=host.packets_received,
        loss_pct=round(host.packet_loss * 100, 1),
        rtt_min_ms=host.min_rtt if host.is_alive else None,
        rtt_avg_ms=host.avg_rtt if host.is_alive else None,
        rtt_max_ms=host.max_rtt if host.is_alive else None,
        is_alive=host.is_alive,
    )


async def ping_batch(targets: List[str]) -> dict[str, PingOutcome]:
    """Pinga IPs ou hostnames (ICMP) com concorrência limitada, indexado pelo valor cadastrado."""
    if not targets:
        return {}
    sem = asyncio.Semaphore(settings.ping_concurrency)
    unique = list(dict.fromkeys(targets))
    outcomes = await asyncio.gather(*(_ping_one(t, sem) for t in unique))
    return dict(zip(unique, outcomes))


async def _tcp_one(target: str, port: int, sem: asyncio.Semaphore) -> PingOutcome:
    """
    Mede o tempo de conexão TCP (handshake) `ping_count` vezes. O hostname é
    resolvido a cada tentativa, então mudanças de IP (CDN/AWS) são acompanhadas.
    """
    rtts: list[float] = []
    async with sem:
        for i in range(settings.ping_count):
            start = time.perf_counter()
            try:
                _, writer = await asyncio.wait_for(
                    asyncio.open_connection(target, port), timeout=TCP_TIMEOUT_S
                )
                rtts.append((time.perf_counter() - start) * 1000)
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
            except Exception as exc:
                logger.debug("TCP %s:%s falhou: %s", target, port, exc)
            if i < settings.ping_count - 1:
                await asyncio.sleep(0.3)

    sent = settings.ping_count
    received = len(rtts)
    return PingOutcome(
        ip=target,
        packets_sent=sent,
        packets_received=received,
        loss_pct=round((sent - received) / sent * 100, 1),
        rtt_min_ms=round(min(rtts), 3) if rtts else None,
        rtt_avg_ms=round(sum(rtts) / len(rtts), 3) if rtts else None,
        rtt_max_ms=round(max(rtts), 3) if rtts else None,
        is_alive=received > 0,
    )


async def tcp_batch(targets: List[tuple[str, int]]) -> dict[tuple[str, int], PingOutcome]:
    if not targets:
        return {}
    sem = asyncio.Semaphore(settings.ping_concurrency)
    unique = list(dict.fromkeys(targets))
    outcomes = await asyncio.gather(*(_tcp_one(h, p, sem) for h, p in unique))
    return dict(zip(unique, outcomes))
