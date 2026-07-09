import logging

import httpx

from app.config import settings

logger = logging.getLogger("netmonitor.discord")

STATUS_EMOJI = {
    "online": "🟢",
    "warning": "🟡",
    "offline": "🔴",
    "unknown": "⚪",
}


async def send_discord_alert(device_name: str, ip: str, location: str | None,
                              from_status: str | None, to_status: str, extra: str = ""):
    if not settings.discord_webhook_url:
        return

    emoji = STATUS_EMOJI.get(to_status, "⚪")
    loc = f" ({location})" if location else ""
    from_txt = f"{from_status} → " if from_status else ""

    content = (
        f"{emoji} **{device_name}**{loc} — IP `{ip}`\n"
        f"Status: {from_txt}**{to_status.upper()}**"
    )
    if extra:
        content += f"\n{extra}"

    payload = {"content": content}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(settings.discord_webhook_url, json=payload)
            resp.raise_for_status()
    except Exception as exc:  # não deixamos falha de alerta derrubar o monitor
        logger.warning("Falha ao enviar alerta ao Discord: %s", exc)
