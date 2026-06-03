"""Windows-Desktop-Benachrichtigungen (Toast) via winotify.

Klick auf den Toast öffnet das Inserat im Browser. Fällt auf der Konsole
zurück, falls winotify nicht verfügbar ist (z.B. Nicht-Windows).
"""
import logging

from . import config

log = logging.getLogger("notify")

try:
    from winotify import Notification, audio
    _AVAILABLE = True
except Exception:  # pragma: no cover - nur auf Nicht-Windows
    _AVAILABLE = False


def notify_new_listing(listing: dict) -> None:
    if not config.NOTIFICATIONS_ENABLED:
        return  # Benachrichtigungen sind global deaktiviert (config.NOTIFICATIONS_ENABLED)

    title = listing.get("title") or "Neues Inserat"
    price = listing.get("price")
    currency = listing.get("currency") or ""
    seller = listing.get("seller") or "?"
    url = listing.get("url") or config.VINTED_BASE_URL

    price_str = f"{price:.0f} {currency}".strip() if price is not None else "Preis n/a"
    msg = f"{price_str} · {seller}"

    if not _AVAILABLE:
        log.info("[TOAST] %s — %s — %s", title, msg, url)
        return

    try:
        toast = Notification(
            app_id=config.APP_NAME,
            title=f"🎯 {title}",
            msg=msg,
            duration="short",
        )
        toast.set_audio(audio.Default, loop=False)
        # Klick auf die ganze Notification + expliziter Button öffnen das Inserat
        toast.add_actions(label="Inserat öffnen", launch=url)
        toast.launch = url
        toast.show()
    except Exception as e:  # robust: Benachrichtigungsfehler dürfen den Poller nie crashen
        log.warning("Toast fehlgeschlagen: %s", e)
        log.info("[TOAST-FALLBACK] %s — %s — %s", title, msg, url)
