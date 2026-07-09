import asyncio
import logging
from dataclasses import dataclass
from typing import List

from icmplib import async_multiping

from app.config import settings

logger = logging.getLogger("netmonitor.ping")


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


async def ping_batch(ip_list: List[str]) -> dict[str, PingOutcome]:
    """
    Faz ping em uma lista de IPs de forma concorrente, mas limitada
    (boas práticas: não disparar tudo de uma vez para não gerar rajada na rede).
    Cada IP recebe `PING_COUNT` pacotes ICMP.
    """
    results: dict[str, PingOutcome] = {}
    if not ip_list:
        return results

    try:
        hosts = await async_multiping(
            ip_list,
            count=settings.ping_count,
            interval=0.3,
            timeout=1.5,
            concurrent_tasks=settings.ping_concurrency,
            privileged=True,
        )
    except Exception as exc:
        logger.error("Erro geral no ping em lote: %s", exc)
        return results

    for host in hosts:
        results[host.address] = PingOutcome(
            ip=host.address,
            packets_sent=host.packets_sent,
            packets_received=host.packets_received,
            loss_pct=round(host.packet_loss * 100, 1),
            rtt_min_ms=host.min_rtt if host.is_alive else None,
            rtt_avg_ms=host.avg_rtt if host.is_alive else None,
            rtt_max_ms=host.max_rtt if host.is_alive else None,
            is_alive=host.is_alive,
        )
    return results
