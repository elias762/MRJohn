"""Mr. Johns Sniper — FastAPI-Backend.

Liefert die JSON-API und das statische Dashboard aus und startet den Hintergrund-Poller.
Start:  uvicorn backend.main:app   (aus dem Projektordner)
"""
import logging
import webbrowser
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config, db, poller, templates

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    poller.start()
    log.info("%s läuft — Dashboard: http://localhost:8000", config.APP_NAME)
    yield
    poller.stop()


app = FastAPI(title=config.APP_NAME, lifespan=lifespan)


# ---------- Request-Modelle ----------

class SearchIn(BaseModel):
    name: str
    query: str
    filters: dict = {}
    interval_sec: int = config.DEFAULT_INTERVAL_SEC


class SearchPatch(BaseModel):
    name: Optional[str] = None
    query: Optional[str] = None
    filters: Optional[dict] = None
    active: Optional[bool] = None
    interval_sec: Optional[int] = None


class StatusIn(BaseModel):
    status: str


class InquireIn(BaseModel):
    template_id: Optional[int] = None
    message_text: Optional[str] = None  # falls schon im Frontend gerendert/bearbeitet


class TemplateIn(BaseModel):
    name: str
    body: str


class InquiryPatch(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    message_text: Optional[str] = None


class PurchaseIn(BaseModel):
    listing_id: Optional[int] = None
    order_number: Optional[str] = None
    item_name: str
    product: Optional[str] = None
    bought_price: Optional[float] = None
    bought_date: Optional[str] = None
    platform: Optional[str] = None
    sold_price: Optional[float] = None
    sold_date: Optional[str] = None
    sold_channel: Optional[str] = None
    notes: Optional[str] = None


class PurchasePatch(BaseModel):
    order_number: Optional[str] = None
    item_name: Optional[str] = None
    product: Optional[str] = None
    bought_price: Optional[float] = None
    bought_date: Optional[str] = None
    platform: Optional[str] = None
    sold_price: Optional[float] = None
    sold_date: Optional[str] = None
    sold_channel: Optional[str] = None
    notes: Optional[str] = None


# ---------- Meta ----------

@app.get("/api/meta")
def meta():
    return {"app_name": config.APP_NAME}


# ---------- Searches ----------

@app.get("/api/searches")
def get_searches():
    conn = db.get_conn()
    try:
        return db.list_searches(conn)
    finally:
        conn.close()


@app.post("/api/searches")
def post_search(body: SearchIn):
    conn = db.get_conn()
    try:
        sid = db.create_search(conn, body.name, body.query, body.filters,
                               max(body.interval_sec, config.MIN_INTERVAL_SEC))
        return db.get_search(conn, sid)
    finally:
        conn.close()


@app.put("/api/searches/{search_id}")
def put_search(search_id: int, body: SearchPatch):
    conn = db.get_conn()
    try:
        if not db.get_search(conn, search_id):
            raise HTTPException(404, "Suche nicht gefunden")
        fields = {}
        if body.name is not None:
            fields["name"] = body.name
        if body.query is not None:
            fields["query"] = body.query
        if body.filters is not None:
            import json
            fields["filters_json"] = json.dumps(body.filters)
        if body.active is not None:
            fields["active"] = 1 if body.active else 0
        if body.interval_sec is not None:
            fields["interval_sec"] = max(body.interval_sec, config.MIN_INTERVAL_SEC)
        db.update_search(conn, search_id, fields)
        return db.get_search(conn, search_id)
    finally:
        conn.close()


@app.delete("/api/searches/{search_id}")
def del_search(search_id: int):
    conn = db.get_conn()
    try:
        db.delete_search(conn, search_id)
        return {"ok": True}
    finally:
        conn.close()


# ---------- Listings ----------

@app.get("/api/listings")
def get_listings(status: Optional[str] = None, search_id: Optional[int] = None):
    conn = db.get_conn()
    try:
        return db.list_listings(conn, status=status, search_id=search_id)
    finally:
        conn.close()


@app.post("/api/listings/{listing_id}/status")
def post_listing_status(listing_id: int, body: StatusIn):
    conn = db.get_conn()
    try:
        if not db.get_listing(conn, listing_id):
            raise HTTPException(404, "Listing nicht gefunden")
        db.set_listing_status(conn, listing_id, body.status)
        return db.get_listing(conn, listing_id)
    finally:
        conn.close()


@app.post("/api/listings/{listing_id}/inquire")
def post_inquire(listing_id: int, body: InquireIn):
    """Rendert eine Vorlage, legt eine Anfrage an und setzt das Listing auf 'angefragt'.

    Liefert message_text + url zurück, damit das Frontend in die Zwischenablage kopiert
    und das Inserat öffnet.
    """
    conn = db.get_conn()
    try:
        listing = db.get_listing(conn, listing_id)
        if not listing:
            raise HTTPException(404, "Listing nicht gefunden")

        message_text = body.message_text
        template_id = body.template_id
        if not message_text:
            tpl = db.get_template(conn, template_id) if template_id else None
            if not tpl:
                tpls = db.list_templates(conn)
                tpl = tpls[0] if tpls else None
            if tpl:
                template_id = tpl["id"]
                message_text = templates.render(tpl["body"], listing)
            else:
                message_text = ""

        inquiry_id = db.create_inquiry(conn, listing_id, template_id, message_text)
        db.set_listing_status(conn, listing_id, "angefragt")
        return {
            "inquiry_id": inquiry_id,
            "message_text": message_text,
            "url": listing.get("url"),
        }
    finally:
        conn.close()


# ---------- Templates ----------

@app.get("/api/templates")
def get_templates():
    conn = db.get_conn()
    try:
        return db.list_templates(conn)
    finally:
        conn.close()


@app.post("/api/templates")
def post_template(body: TemplateIn):
    conn = db.get_conn()
    try:
        tid = db.create_template(conn, body.name, body.body)
        return db.get_template(conn, tid)
    finally:
        conn.close()


@app.put("/api/templates/{template_id}")
def put_template(template_id: int, body: TemplateIn):
    conn = db.get_conn()
    try:
        if not db.get_template(conn, template_id):
            raise HTTPException(404, "Vorlage nicht gefunden")
        db.update_template(conn, template_id, body.name, body.body)
        return db.get_template(conn, template_id)
    finally:
        conn.close()


@app.delete("/api/templates/{template_id}")
def del_template(template_id: int):
    conn = db.get_conn()
    try:
        db.delete_template(conn, template_id)
        return {"ok": True}
    finally:
        conn.close()


# ---------- Inquiries ----------

@app.get("/api/inquiries")
def get_inquiries():
    conn = db.get_conn()
    try:
        return db.list_inquiries(conn)
    finally:
        conn.close()


@app.put("/api/inquiries/{inquiry_id}")
def put_inquiry(inquiry_id: int, body: InquiryPatch):
    conn = db.get_conn()
    try:
        db.update_inquiry(conn, inquiry_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


# ---------- Purchases ----------

@app.get("/api/status")
def status_overview():
    """Schlanker Live-Status für die Header-Anzeige (ein kleiner Call, oft gepollt)."""
    conn = db.get_conn()
    try:
        searches = db.list_searches(conn)
        active = [s for s in searches if s.get("active")]
        polled = [s["last_polled_at"] for s in searches if s.get("last_polled_at")]
        errors = [s["name"] for s in searches if (s.get("last_status") or "").startswith("error")]
        new_count = len(db.list_listings(conn, status="neu"))
        return {
            "new_count": new_count,
            "active_searches": len(active),
            "total_searches": len(searches),
            "last_polled_at": max(polled) if polled else None,
            "ok": len(errors) == 0,
            "errors": errors,
        }
    finally:
        conn.close()


@app.get("/api/stats")
def stats():
    conn = db.get_conn()
    try:
        return db.get_stats(conn)
    finally:
        conn.close()


@app.get("/api/purchases")
def get_purchases():
    conn = db.get_conn()
    try:
        return db.list_purchases(conn)
    finally:
        conn.close()


@app.post("/api/purchases")
def post_purchase(body: PurchaseIn):
    conn = db.get_conn()
    try:
        pid = db.create_purchase(conn, body.model_dump())
        return {"id": pid}
    finally:
        conn.close()


@app.put("/api/purchases/{purchase_id}")
def put_purchase(purchase_id: int, body: PurchasePatch):
    conn = db.get_conn()
    try:
        db.update_purchase(conn, purchase_id, body.model_dump(exclude_none=True))
        return {"ok": True}
    finally:
        conn.close()


# ---------- Poll now ----------

@app.post("/api/poll-now")
def poll_now():
    return poller.poll_all_now(notify_new=False)


# ---------- Static Frontend ----------
# Muss nach den /api-Routen kommen, damit "/" das Dashboard liefert.

@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")


app.mount("/", StaticFiles(directory=config.FRONTEND_DIR), name="static")
