"""SQLite-Zugriff: Schema, Verbindung und CRUD-Helfer.

Eine neue Verbindung pro Operation (SQLite + WAL), damit Poller-Thread und
FastAPI-Requests sich nicht in die Quere kommen.
"""
import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Optional

from . import config


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


SCHEMA = """
CREATE TABLE IF NOT EXISTS searches (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    name          TEXT NOT NULL,
    query         TEXT NOT NULL,
    filters_json  TEXT NOT NULL DEFAULT '{}',   -- {price_min, price_max, brand, ...}
    platform      TEXT NOT NULL DEFAULT 'vinted',
    active        INTEGER NOT NULL DEFAULT 1,
    interval_sec  INTEGER NOT NULL DEFAULT 60,
    last_polled_at TEXT,
    last_status   TEXT,                          -- 'ok' | 'error: ...'
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS listings (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    platform         TEXT NOT NULL,
    platform_item_id TEXT NOT NULL,
    search_id        INTEGER REFERENCES searches(id) ON DELETE SET NULL,
    title            TEXT,
    price            REAL,
    currency         TEXT,
    url              TEXT,
    image_url        TEXT,
    seller           TEXT,
    brand            TEXT,
    first_seen       TEXT NOT NULL,
    last_seen        TEXT NOT NULL,
    status           TEXT NOT NULL DEFAULT 'neu', -- neu|gesehen|angefragt|gekauft|ignoriert
    raw_json         TEXT,
    UNIQUE(platform, platform_item_id)
);
CREATE INDEX IF NOT EXISTS idx_listings_status ON listings(status);
CREATE INDEX IF NOT EXISTS idx_listings_search ON listings(search_id);

CREATE TABLE IF NOT EXISTS message_templates (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    name  TEXT NOT NULL,
    body  TEXT NOT NULL                          -- Platzhalter: {title} {price} {currency} {seller} {url} {brand}
);

CREATE TABLE IF NOT EXISTS inquiries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id    INTEGER REFERENCES listings(id) ON DELETE CASCADE,
    template_id   INTEGER REFERENCES message_templates(id) ON DELETE SET NULL,
    message_text  TEXT,
    marked_sent_at TEXT,
    status        TEXT NOT NULL DEFAULT 'angefragt', -- angefragt|antwort|verhandlung|gekauft|abgelehnt
    notes         TEXT,
    created_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS purchases (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    listing_id   INTEGER REFERENCES listings(id) ON DELETE SET NULL,
    order_number TEXT,                            -- eindeutige Bestell-/Verkaufsnummer
    item_name    TEXT NOT NULL,
    product      TEXT,                            -- z.B. 'Cartier Santos' / 'Cartier Tank'
    bought_price REAL,
    bought_date  TEXT,
    platform     TEXT,
    sold_price   REAL,
    sold_date    TEXT,
    sold_channel TEXT,                            -- wo verkauft
    notes        TEXT
);
"""

DEFAULT_TEMPLATES = [
    (
        "Verfügbarkeit + Preis",
        "Hallo {seller}, ist \"{title}\" noch verfügbar? "
        "Würdest du es für {price} {currency} abgeben? Danke dir!",
    ),
    (
        "Detailfotos anfragen",
        "Hi {seller}, schönes Stück! Kannst du mir bitte noch Detailfotos schicken: "
        "Zifferblatt aus der Nähe, Gehäuseboden, Krone/Seriennummer und ggf. Papiere/Box? Danke!",
    ),
    (
        "Zustand + Echtheit",
        "Hallo {seller}, zu \"{title}\": Sind Papiere/Box dabei und gibt es eine Seriennummer? "
        "Funktioniert das Werk einwandfrei und gibt es Kratzer/Macken? Danke!",
    ),
    (
        "Schnellkauf-Angebot",
        "Hi {seller}, ich hätte starkes Interesse an \"{title}\" und kann sofort zahlen. "
        "Wäre {price} {currency} okay oder hast du einen Wunschpreis? Danke!",
    ),
]

# Vorangelegte Suchen für den Start (Cartier Santos + Tank), aktiv.
# price_min filtert Billigkram (T-Shirts, Parfüm, Fake-Zubehör) raus.
DEFAULT_SEARCHES = [
    ("Cartier Santos", "cartier santos", {"brand": "Cartier", "price_min": 200}),
    ("Cartier Tank", "cartier tank", {"brand": "Cartier", "price_min": 200}),
]


def init_db() -> None:
    conn = get_conn()
    try:
        conn.executescript(SCHEMA)
        # Standard-Vorlagen anlegen, falls noch keine existieren
        if conn.execute("SELECT COUNT(*) AS n FROM message_templates").fetchone()["n"] == 0:
            conn.executemany(
                "INSERT INTO message_templates(name, body) VALUES(?, ?)",
                DEFAULT_TEMPLATES,
            )
        # Start-Suchen anlegen, falls noch keine existieren
        if conn.execute("SELECT COUNT(*) AS n FROM searches").fetchone()["n"] == 0:
            for name, query, filters in DEFAULT_SEARCHES:
                conn.execute(
                    "INSERT INTO searches(name, query, filters_json, platform, active, "
                    "interval_sec, created_at) VALUES(?,?,?, 'vinted', 1, ?, ?)",
                    (name, query, json.dumps(filters), config.DEFAULT_INTERVAL_SEC, now_iso()),
                )
        conn.commit()
    finally:
        conn.close()


# ---------- Helfer ----------

def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    # JSON-Felder auspacken
    if "filters_json" in d and d["filters_json"]:
        try:
            d["filters"] = json.loads(d["filters_json"])
        except json.JSONDecodeError:
            d["filters"] = {}
    return d


def rows_to_dicts(rows) -> list[dict]:
    return [_row_to_dict(r) for r in rows]


# ---------- searches ----------

def list_searches(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute("SELECT * FROM searches ORDER BY id").fetchall()
    return rows_to_dicts(rows)


def get_search(conn: sqlite3.Connection, search_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM searches WHERE id=?", (search_id,)).fetchone()
    return _row_to_dict(row) if row else None


def create_search(conn, name, query, filters: dict, interval_sec: int) -> int:
    cur = conn.execute(
        "INSERT INTO searches(name, query, filters_json, platform, active, interval_sec, created_at) "
        "VALUES(?,?,?,?,1,?,?)",
        (name, query, json.dumps(filters), "vinted", interval_sec, now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def update_search(conn, search_id: int, fields: dict) -> None:
    allowed = {"name", "query", "filters_json", "active", "interval_sec",
               "last_polled_at", "last_status"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(search_id)
    conn.execute(f"UPDATE searches SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()


def delete_search(conn, search_id: int) -> None:
    conn.execute("DELETE FROM searches WHERE id=?", (search_id,))
    conn.commit()


# ---------- listings ----------

def upsert_listing(conn, item: dict, search_id: int) -> tuple[int, bool]:
    """Fügt ein Listing ein oder aktualisiert last_seen.

    Rückgabe: (listing_id, is_new).
    """
    ts = now_iso()
    existing = conn.execute(
        "SELECT id FROM listings WHERE platform=? AND platform_item_id=?",
        (item["platform"], item["platform_item_id"]),
    ).fetchone()
    if existing:
        conn.execute(
            "UPDATE listings SET last_seen=?, price=?, title=?, image_url=? WHERE id=?",
            (ts, item.get("price"), item.get("title"), item.get("image_url"), existing["id"]),
        )
        conn.commit()
        return existing["id"], False

    cur = conn.execute(
        "INSERT INTO listings(platform, platform_item_id, search_id, title, price, currency, "
        "url, image_url, seller, brand, first_seen, last_seen, status, raw_json) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'neu', ?)",
        (
            item["platform"], item["platform_item_id"], search_id,
            item.get("title"), item.get("price"), item.get("currency"),
            item.get("url"), item.get("image_url"), item.get("seller"),
            item.get("brand"), ts, ts, json.dumps(item.get("raw"), ensure_ascii=False),
        ),
    )
    conn.commit()
    return cur.lastrowid, True


def list_listings(conn, status: Optional[str] = None, search_id: Optional[int] = None,
                  limit: int = 200) -> list[dict]:
    sql = "SELECT * FROM listings"
    where, vals = [], []
    if status:
        where.append("status=?")
        vals.append(status)
    if search_id:
        where.append("search_id=?")
        vals.append(search_id)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY datetime(first_seen) DESC LIMIT ?"
    vals.append(limit)
    result = rows_to_dicts(conn.execute(sql, vals).fetchall())
    for r in result:
        r.pop("raw_json", None)  # Rohdaten sind fürs Dashboard unnötig und groß
    return result


def get_listing(conn, listing_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM listings WHERE id=?", (listing_id,)).fetchone()
    return _row_to_dict(row) if row else None


def set_listing_status(conn, listing_id: int, status: str) -> None:
    conn.execute("UPDATE listings SET status=? WHERE id=?", (status, listing_id))
    conn.commit()


# ---------- templates ----------

def list_templates(conn) -> list[dict]:
    return rows_to_dicts(conn.execute("SELECT * FROM message_templates ORDER BY id").fetchall())


def get_template(conn, template_id: int) -> Optional[dict]:
    row = conn.execute("SELECT * FROM message_templates WHERE id=?", (template_id,)).fetchone()
    return dict(row) if row else None


def create_template(conn, name: str, body: str) -> int:
    cur = conn.execute("INSERT INTO message_templates(name, body) VALUES(?,?)", (name, body))
    conn.commit()
    return cur.lastrowid


def update_template(conn, template_id: int, name: str, body: str) -> None:
    conn.execute("UPDATE message_templates SET name=?, body=? WHERE id=?", (name, body, template_id))
    conn.commit()


def delete_template(conn, template_id: int) -> None:
    conn.execute("DELETE FROM message_templates WHERE id=?", (template_id,))
    conn.commit()


# ---------- inquiries ----------

def create_inquiry(conn, listing_id: int, template_id: Optional[int], message_text: str) -> int:
    cur = conn.execute(
        "INSERT INTO inquiries(listing_id, template_id, message_text, marked_sent_at, status, created_at) "
        "VALUES(?,?,?,?, 'angefragt', ?)",
        (listing_id, template_id, message_text, now_iso(), now_iso()),
    )
    conn.commit()
    return cur.lastrowid


def list_inquiries(conn) -> list[dict]:
    sql = (
        "SELECT i.*, l.title AS listing_title, l.url AS listing_url, l.seller AS listing_seller, "
        "l.price AS listing_price, l.currency AS listing_currency "
        "FROM inquiries i LEFT JOIN listings l ON l.id = i.listing_id "
        "ORDER BY datetime(i.created_at) DESC"
    )
    return [dict(r) for r in conn.execute(sql).fetchall()]


def update_inquiry(conn, inquiry_id: int, fields: dict) -> None:
    allowed = {"status", "notes", "message_text"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(inquiry_id)
    conn.execute(f"UPDATE inquiries SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()


# ---------- purchases ----------

def create_purchase(conn, data: dict) -> int:
    cur = conn.execute(
        "INSERT INTO purchases(listing_id, order_number, item_name, product, bought_price, "
        "bought_date, platform, sold_price, sold_date, sold_channel, notes) "
        "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
        (
            data.get("listing_id"), data.get("order_number"), data.get("item_name"),
            data.get("product"), data.get("bought_price"), data.get("bought_date"),
            data.get("platform"), data.get("sold_price"), data.get("sold_date"),
            data.get("sold_channel"), data.get("notes"),
        ),
    )
    conn.commit()
    return cur.lastrowid


def list_purchases(conn) -> list[dict]:
    rows = [dict(r) for r in conn.execute("SELECT * FROM purchases ORDER BY id DESC").fetchall()]
    for r in rows:
        if r.get("sold_price") is not None and r.get("bought_price") is not None:
            r["margin"] = round(r["sold_price"] - r["bought_price"], 2)
        else:
            r["margin"] = None
    return rows


def get_stats(conn) -> dict:
    """Kennzahlen fürs Dashboard: Gewinn (gesamt + aktueller Monat), Umsatz,
    investiertes/gebundenes Kapital, Bestand und Monatsaufschlüsselung."""
    rows = [dict(r) for r in conn.execute(
        "SELECT bought_price, sold_price, sold_date FROM purchases").fetchall()]

    sold = [r for r in rows if r["sold_price"] is not None]
    open_items = [r for r in rows if r["sold_price"] is None]

    total_invested = sum(r["bought_price"] or 0 for r in rows)
    total_revenue = sum(r["sold_price"] or 0 for r in sold)
    total_profit = sum((r["sold_price"] or 0) - (r["bought_price"] or 0) for r in sold)
    open_capital = sum(r["bought_price"] or 0 for r in open_items)

    monthly: dict[str, dict] = {}
    for r in sold:
        sd = r["sold_date"] or ""
        month = sd[:7] if len(sd) >= 7 else "ohne Datum"
        m = monthly.setdefault(month, {"month": month, "profit": 0.0, "revenue": 0.0, "count": 0})
        m["profit"] += (r["sold_price"] or 0) - (r["bought_price"] or 0)
        m["revenue"] += r["sold_price"] or 0
        m["count"] += 1
    monthly_list = sorted(monthly.values(), key=lambda x: x["month"], reverse=True)
    for m in monthly_list:
        m["profit"] = round(m["profit"], 2)
        m["revenue"] = round(m["revenue"], 2)

    cur_month = datetime.now(timezone.utc).strftime("%Y-%m")
    current_month_profit = round(monthly.get(cur_month, {}).get("profit", 0.0), 2)

    avg_margin = round(total_profit / len(sold), 2) if sold else 0.0

    return {
        "total_invested": round(total_invested, 2),
        "total_revenue": round(total_revenue, 2),
        "total_profit": round(total_profit, 2),
        "open_capital": round(open_capital, 2),
        "open_count": len(open_items),
        "sold_count": len(sold),
        "avg_margin": avg_margin,
        "current_month": cur_month,
        "current_month_profit": current_month_profit,
        "monthly": monthly_list,
    }


def update_purchase(conn, purchase_id: int, fields: dict) -> None:
    allowed = {"order_number", "item_name", "product", "bought_price", "bought_date",
               "platform", "sold_price", "sold_date", "sold_channel", "notes"}
    sets, vals = [], []
    for k, v in fields.items():
        if k in allowed:
            sets.append(f"{k}=?")
            vals.append(v)
    if not sets:
        return
    vals.append(purchase_id)
    conn.execute(f"UPDATE purchases SET {', '.join(sets)} WHERE id=?", vals)
    conn.commit()
