"""Vinted-Zugriff über das `vinted-scraper`-Paket.

Das Paket übernimmt den Session-Bootstrap inkl. DataDome-Token. Wir kapseln es
hier und liefern normalisierte, plattform-neutrale Dicts zurück, damit der Rest
des Codes nichts über Vinted-Interna wissen muss.
"""
import logging
import threading
from typing import Optional

from vinted_scraper import VintedScraper

from . import config

log = logging.getLogger("vinted")

_scraper: Optional[VintedScraper] = None
_lock = threading.Lock()


def _get_scraper() -> VintedScraper:
    """Lazy-Singleton. Erstellt den Scraper (und damit die Session) bei Bedarf."""
    global _scraper
    with _lock:
        if _scraper is None:
            log.info("Initialisiere Vinted-Session …")
            _scraper = VintedScraper(config.VINTED_BASE_URL)
        return _scraper


def reset_session() -> None:
    """Session verwerfen, damit sie beim nächsten Aufruf neu aufgebaut wird."""
    global _scraper
    with _lock:
        _scraper = None


def _to_params(query: str, filters: dict) -> dict:
    params: dict = {
        "search_text": query,
        "per_page": config.SEARCH_PER_PAGE,
        "order": "newest_first",  # neueste zuerst – wichtig fürs Monitoring
    }
    if filters.get("price_min") is not None:
        params["price_from"] = filters["price_min"]
    if filters.get("price_max") is not None:
        params["price_to"] = filters["price_max"]
    if filters.get("brand_ids"):
        params["brand_ids"] = filters["brand_ids"]
    if filters.get("catalog_ids"):
        params["catalog_ids"] = filters["catalog_ids"]
    if filters.get("size_ids"):
        params["size_ids"] = filters["size_ids"]
    return params


def _normalize(item) -> dict:
    price = item.price
    try:
        price = float(price) if price is not None else None
    except (TypeError, ValueError):
        price = None

    image_url = None
    if item.photos:
        image_url = getattr(item.photos[0], "url", None)

    seller = None
    if item.user:
        seller = getattr(item.user, "login", None)

    url = item.url
    if url and url.startswith("/"):
        url = config.VINTED_BASE_URL + url

    return {
        "platform": "vinted",
        "platform_item_id": str(item.id),
        "title": item.title,
        "price": price,
        "currency": item.currency or "EUR",
        "url": url,
        "image_url": image_url,
        "seller": seller,
        "brand": item.brand_title,
        "raw": item.json_data,  # vollständige Rohdaten für später
    }


def search(query: str, filters: Optional[dict] = None) -> list[dict]:
    """Sucht auf Vinted und gibt normalisierte Items zurück.

    Wendet zusätzlich client-seitige Preisfilter an (die API ist nicht immer strikt).
    """
    filters = filters or {}
    scraper = _get_scraper()
    items = scraper.search(_to_params(query, filters))
    results = [_normalize(it) for it in items]

    pmin, pmax = filters.get("price_min"), filters.get("price_max")
    if pmin is not None:
        results = [r for r in results if r["price"] is None or r["price"] >= pmin]
    if pmax is not None:
        results = [r for r in results if r["price"] is None or r["price"] <= pmax]

    return results
