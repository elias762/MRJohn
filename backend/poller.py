"""Hintergrund-Poller: fragt aktive Suchen in Intervallen ab, erkennt neue
Inserate, speichert sie und löst Windows-Toasts aus.

Läuft in einem eigenen Thread (Vinted-Calls sind synchron/blocking), getrennt
vom FastAPI-Event-Loop.
"""
import logging
import threading
import time
from datetime import datetime, timezone

from . import config, db, notify, vinted

log = logging.getLogger("poller")

_thread: threading.Thread | None = None
_stop = threading.Event()


def _due(search: dict) -> bool:
    """Ist die Suche jetzt fällig?"""
    if not search.get("active"):
        return False
    last = search.get("last_polled_at")
    if not last:
        return True
    try:
        last_dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    elapsed = (datetime.now(timezone.utc) - last_dt).total_seconds()
    return elapsed >= max(search.get("interval_sec") or config.DEFAULT_INTERVAL_SEC,
                          config.MIN_INTERVAL_SEC)


def poll_search(search: dict, notify_new: bool = True) -> dict:
    """Pollt eine einzelne Suche. Gibt {new: int, total: int} zurück."""
    conn = db.get_conn()
    new_count = 0
    total = 0
    try:
        items = vinted.search(search["query"], search.get("filters") or {})
        total = len(items)
        # älteste zuerst verarbeiten, damit Toast-Reihenfolge chronologisch ist
        for item in reversed(items):
            listing_id, is_new = db.upsert_listing(conn, item, search["id"])
            if is_new:
                new_count += 1
                if notify_new:
                    full = db.get_listing(conn, listing_id)
                    notify.notify_new_listing(full)
        db.update_search(conn, search["id"], {
            "last_polled_at": db.now_iso(),
            "last_status": "ok",
        })
        log.info("Suche '%s': %d Treffer, %d neu", search["name"], total, new_count)
    except Exception as e:
        log.warning("Suche '%s' fehlgeschlagen: %s", search.get("name"), e)
        db.update_search(conn, search["id"], {
            "last_polled_at": db.now_iso(),
            "last_status": f"error: {e}",
        })
        vinted.reset_session()  # Session evtl. abgelaufen/geblockt -> neu aufbauen
        raise
    finally:
        conn.close()
    return {"new": new_count, "total": total}


def poll_all_now(notify_new: bool = False) -> dict:
    """Pollt sofort ALLE aktiven Suchen (für den 'Jetzt pollen'-Button)."""
    conn = db.get_conn()
    try:
        searches = [s for s in db.list_searches(conn) if s.get("active")]
    finally:
        conn.close()
    summary = {}
    for s in searches:
        try:
            summary[s["name"]] = poll_search(s, notify_new=notify_new)
        except Exception as e:
            summary[s["name"]] = {"error": str(e)}
    return summary


def _loop() -> None:
    log.info("Poller gestartet.")
    error_until = 0.0
    while not _stop.is_set():
        now = time.time()
        if now < error_until:
            _stop.wait(config.POLLER_TICK_SEC)
            continue
        try:
            conn = db.get_conn()
            try:
                searches = db.list_searches(conn)
            finally:
                conn.close()
            for s in searches:
                if _stop.is_set():
                    break
                if _due(s):
                    try:
                        poll_search(s, notify_new=True)
                    except Exception:
                        # Backoff für alle Suchen, wenn Vinted blockt/Fehler wirft
                        error_until = time.time() + config.ERROR_BACKOFF_SEC
                        log.info("Backoff %ds nach Fehler.", config.ERROR_BACKOFF_SEC)
                        break
        except Exception as e:
            log.exception("Poller-Loop-Fehler: %s", e)
        _stop.wait(config.POLLER_TICK_SEC)
    log.info("Poller gestoppt.")


def start() -> None:
    global _thread
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_loop, name="poller", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
