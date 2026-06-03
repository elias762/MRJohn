"""Nachrichten-Vorlagen rendern: Platzhalter durch Listing-Daten ersetzen."""


def render(body: str, listing: dict) -> str:
    price = listing.get("price")
    values = {
        "title": listing.get("title") or "",
        "price": (f"{price:.0f}" if price is not None else ""),
        "currency": listing.get("currency") or "",
        "seller": listing.get("seller") or "",
        "url": listing.get("url") or "",
        "brand": listing.get("brand") or "",
    }
    try:
        return body.format(**values)
    except (KeyError, IndexError, ValueError):
        # Unbekannte Platzhalter im Text nicht crashen lassen
        out = body
        for k, v in values.items():
            out = out.replace("{" + k + "}", str(v))
        return out
