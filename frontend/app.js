// Mr. Johns Sniper — Frontend-Logik (kein Build-Step, reines Vanilla JS)

const api = {
  async get(path) { const r = await fetch(path); if (!r.ok) throw new Error(await r.text()); return r.json(); },
  async send(method, path, body) {
    const r = await fetch(path, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
    });
    if (!r.ok) throw new Error(await r.text());
    return r.json();
  },
  post(p, b) { return this.send("POST", p, b); },
  put(p, b) { return this.send("PUT", p, b); },
  del(p) { return this.send("DELETE", p); },
};

let templatesCache = [];
let listingsCache = [];
let searchesCache = [];
let inquiriesCache = [];
let currentInquireListing = null;
let currentPurchaseListing = null;

// Browser-Popup-Meldungen (Snackbar). Auf true setzen, um sie wieder zu aktivieren.
const SHOW_TOASTS = false;

function toast(msg) {
  if (!SHOW_TOASTS) return;  // Benachrichtigungen im Browser deaktiviert
  const el = document.getElementById("toast");
  el.textContent = msg;
  el.classList.add("show");
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove("show"), 2600);
}

function fmtPrice(p, c) { return p == null ? "—" : `${Number(p).toFixed(0)} ${c || ""}`.trim(); }
function fmtTime(iso) {
  if (!iso) return "—";
  const d = new Date(iso), now = new Date();
  const mins = Math.round((now - d) / 60000);
  if (mins < 1) return "gerade eben";
  if (mins < 60) return `vor ${mins} Min`;
  if (mins < 1440) return `vor ${Math.round(mins / 60)} Std`;
  return d.toLocaleDateString("de-DE");
}

// ---------- Ansicht: Mobile / Desktop ----------
const VIEW_KEY = "mjs_view_mode";
const mqMobile = window.matchMedia("(max-width: 768px)");

function applyViewMode(mode) {
  document.body.classList.toggle("view-mobile", mode === "mobile");
  document.body.classList.toggle("view-desktop", mode === "desktop");
  document.querySelectorAll("#view-toggle .vt-btn").forEach((b) =>
    b.classList.toggle("active", b.dataset.mode === mode));
}
function effectiveMode() {
  return localStorage.getItem(VIEW_KEY) || (mqMobile.matches ? "mobile" : "desktop");
}
document.querySelectorAll("#view-toggle .vt-btn").forEach((b) => {
  b.addEventListener("click", () => {
    localStorage.setItem(VIEW_KEY, b.dataset.mode);
    applyViewMode(b.dataset.mode);
  });
});
// Bei Größenänderung automatisch wechseln, solange nicht manuell gepinnt
mqMobile.addEventListener("change", (e) => {
  if (!localStorage.getItem(VIEW_KEY)) applyViewMode(e.matches ? "mobile" : "desktop");
});
applyViewMode(effectiveMode());

// ---------- Live-Status im Header ----------
async function updateStatus() {
  let s;
  try { s = await api.get("/api/status"); } catch (e) { return; }
  const badge = document.getElementById("new-badge");
  if (s.new_count > 0) { badge.textContent = s.new_count; badge.hidden = false; }
  else { badge.hidden = true; }
  const el = document.getElementById("poll-status");
  if (!s.ok) {
    el.innerHTML = `<span class="dot err"></span>Vinted blockt – Backoff`;
    el.title = "Fehler bei: " + s.errors.join(", ");
  } else {
    el.innerHTML = `<span class="dot ok"></span>${s.active_searches} aktiv · ${fmtTime(s.last_polled_at)} · ${s.new_count} neu`;
    el.title = "";
  }
}

// ---------- Tabs ----------
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
    document.querySelectorAll(".panel").forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById("tab-" + tab.dataset.tab).classList.add("active");
    refreshTab(tab.dataset.tab);
  });
});

function refreshTab(name) {
  if (name === "overview") loadOverview();
  else if (name === "listings") loadListings();
  else if (name === "searches") loadSearches();
  else if (name === "inquiries") loadInquiries();
  else if (name === "purchases") loadPurchases();
  else if (name === "templates") loadTemplates();
}

// ---------- Übersicht / Dashboard ----------
const eur = (n) => (n == null ? "—" : Number(n).toLocaleString("de-DE", { style: "currency", currency: "EUR", maximumFractionDigits: 0 }));
const MONTHS = ["Jan", "Feb", "März", "Apr", "Mai", "Juni", "Juli", "Aug", "Sept", "Okt", "Nov", "Dez"];
function formatMonth(ym) {
  const m = /^(\d{4})-(\d{2})$/.exec(ym);
  return m ? `${MONTHS[+m[2] - 1]} ${m[1]}` : ym;
}

async function loadOverview() {
  const s = await api.get("/api/stats");
  const kpis = [
    { label: "Gewinn diesen Monat", value: eur(s.current_month_profit), cls: s.current_month_profit >= 0 ? "pos" : "neg" },
    { label: "Gesamtgewinn", value: eur(s.total_profit), cls: s.total_profit >= 0 ? "pos" : "neg", sub: `Ø ${eur(s.avg_margin)} / Verkauf` },
    { label: "Umsatz gesamt", value: eur(s.total_revenue), sub: `${s.sold_count} Verkäufe` },
    { label: "Im Bestand", value: `${s.open_count}`, sub: `${eur(s.open_capital)} gebunden` },
  ];
  document.getElementById("kpis").innerHTML = kpis.map((k) => `
    <div class="kpi-card">
      <div class="kpi-label">${k.label}</div>
      <div class="kpi-value ${k.cls || ""}">${k.value}</div>
      ${k.sub ? `<div class="kpi-sub">${k.sub}</div>` : ""}
    </div>`).join("");

  const tb = document.querySelector("#monthly-table tbody");
  if (!s.monthly.length) {
    tb.innerHTML = `<tr><td colspan="4" class="muted">Noch keine Verkäufe erfasst. Trage im Tab „Ein-/Verkäufe" einen Verkaufspreis ein.</td></tr>`;
    return;
  }
  tb.innerHTML = s.monthly.map((m) => `
    <tr>
      <td>${formatMonth(m.month)}</td>
      <td>${m.count}</td>
      <td>${eur(m.revenue)}</td>
      <td><strong class="${m.profit >= 0 ? "pos" : "neg"}">${eur(m.profit)}</strong></td>
    </tr>`).join("");
}

// ---------- Inserate ----------
async function loadListings() {
  const status = document.getElementById("filter-status").value;
  const searchId = document.getElementById("filter-search").value;
  let path = "/api/listings?";
  if (status) path += "status=" + encodeURIComponent(status) + "&";
  if (searchId) path += "search_id=" + encodeURIComponent(searchId);
  listingsCache = await api.get(path);
  renderListings();
  updateStatus();
}

function renderListings() {
  const wrap = document.getElementById("listings");
  // Bei "Alle Status" ignorierte Inserate ausblenden (über das Dropdown „Ignoriert" bleiben sie sichtbar)
  const statusFilter = document.getElementById("filter-status").value;
  const items = statusFilter ? listingsCache : listingsCache.filter((l) => l.status !== "ignoriert");
  if (!items.length) {
    wrap.innerHTML = '<p class="muted">Keine Inserate in dieser Ansicht. „Jetzt pollen" klicken oder Filter ändern.</p>';
    return;
  }
  const dealThresholds = computeDealThresholds(items);
  wrap.innerHTML = "";
  for (const l of items) {
    const card = document.createElement("div");
    card.className = "card" + (l.status === "neu" ? " neu" : "");
    const img = l.image_url
      ? `<img class="thumb" src="${l.image_url}" loading="lazy" onclick="window.open('${l.url}','_blank')" />`
      : `<div class="thumb"></div>`;
    const statusBadge = l.status === "neu"
      ? '<span class="badge">Neu</span>'
      : `<span class="badge status-badge">${l.status}</span>`;
    const thr = dealThresholds[l.search_id];
    const isDeal = l.price != null && thr != null && l.price <= thr;
    const dealBadge = isDeal ? '<span class="badge deal">💰 Deal</span>' : "";
    card.innerHTML = `
      ${img}
      <div class="body">
        <div class="badges">${statusBadge}${dealBadge}</div>
        <div class="title">${escapeHtml(l.title || "(ohne Titel)")}</div>
        <div class="price">${fmtPrice(l.price, l.currency)}</div>
        <div class="meta"><span>${escapeHtml(l.seller || "?")}</span><span>${fmtTime(l.first_seen)}</span></div>
        <div class="meta"><span>${escapeHtml(l.brand || "")}</span><a href="${l.url}" target="_blank">Inserat ↗</a></div>
        <div class="actions">
          <button class="btn primary small" onclick="openInquire(${l.id})">⚡ Anfragen</button>
          <button class="btn small" onclick="setStatus(${l.id}, 'gesehen')">Gesehen</button>
          <button class="btn small" onclick="openPurchase(${l.id})">Gekauft</button>
          <button class="btn small ghost" onclick="setStatus(${l.id}, 'ignoriert')">Ignorieren</button>
        </div>
      </div>`;
    wrap.appendChild(card);
  }
}

// Schwellen pro Suche: deutlich (>25%) unter dem Median = "Deal" (nur ab 5 Vergleichswerten)
function computeDealThresholds(items) {
  const groups = {};
  for (const l of items) {
    if (l.price == null || l.search_id == null) continue;
    (groups[l.search_id] ||= []).push(l.price);
  }
  const thr = {};
  for (const sid in groups) {
    const prices = groups[sid];
    if (prices.length < 5) continue;
    const sorted = [...prices].sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
    thr[sid] = median * 0.75;
  }
  return thr;
}

async function setStatus(id, status) {
  await api.post(`/api/listings/${id}/status`, { status });
  toast(`Status: ${status}`);
  loadListings();
}

// ---------- Kauf-Dialog (Gekauft -> echten EK erfassen) ----------
const purchaseDialog = document.getElementById("purchase-dialog");
function todayStr() { return new Date().toISOString().slice(0, 10); }

function openPurchase(listingId) {
  const l = listingsCache.find((x) => x.id === listingId);
  if (!l) return;
  currentPurchaseListing = l;
  document.getElementById("purchase-listing-title").textContent = l.title || "";
  document.getElementById("pd-name").value = l.title || "";
  document.getElementById("pd-product").value = l.brand || "";
  document.getElementById("pd-bought").value = l.price != null ? l.price : "";
  document.getElementById("pd-bdate").value = todayStr();
  document.getElementById("pd-order").value = "";
  purchaseDialog.showModal();
}

document.getElementById("pd-cancel").addEventListener("click", () => purchaseDialog.close());
document.getElementById("pd-save").addEventListener("click", async () => {
  const l = currentPurchaseListing;
  if (!l) return;
  const body = {
    listing_id: l.id,
    item_name: document.getElementById("pd-name").value || l.title || "Artikel",
    product: document.getElementById("pd-product").value || null,
    bought_price: numOrNullEl("pd-bought"),
    bought_date: document.getElementById("pd-bdate").value || null,
    order_number: document.getElementById("pd-order").value || null,
    platform: "vinted",
  };
  await api.post("/api/purchases", body);
  await api.post(`/api/listings/${l.id}/status`, { status: "gekauft" });
  purchaseDialog.close();
  toast("Als gekauft gespeichert");
  loadListings();
});
function numOrNullEl(id) { const v = document.getElementById(id).value; return v === "" ? null : Number(v); }

// ---------- Anfrage-Dialog (schnelles Senden) ----------
const dialog = document.getElementById("inquire-dialog");

async function openInquire(listingId) {
  currentInquireListing = listingsCache.find((l) => l.id === listingId);
  if (!currentInquireListing) return;
  if (!templatesCache.length) templatesCache = await api.get("/api/templates");

  const sel = document.getElementById("inquire-template");
  sel.innerHTML = templatesCache.map((t) => `<option value="${t.id}">${escapeHtml(t.name)}</option>`).join("");
  document.getElementById("inquire-listing-title").textContent = currentInquireListing.title || "";
  await renderInquirePreview();
  dialog.showModal();
}

async function renderInquirePreview() {
  const tplId = Number(document.getElementById("inquire-template").value);
  const tpl = templatesCache.find((t) => t.id === tplId);
  document.getElementById("inquire-text").value = tpl ? renderTemplate(tpl.body, currentInquireListing) : "";
}

function renderTemplate(body, l) {
  const map = {
    title: l.title || "", price: l.price != null ? Number(l.price).toFixed(0) : "",
    currency: l.currency || "", seller: l.seller || "", url: l.url || "", brand: l.brand || "",
  };
  return body.replace(/\{(\w+)\}/g, (m, k) => (k in map ? map[k] : m));
}

document.getElementById("inquire-template").addEventListener("change", renderInquirePreview);
document.getElementById("inquire-cancel").addEventListener("click", () => dialog.close());
document.getElementById("inquire-send").addEventListener("click", async () => {
  const text = document.getElementById("inquire-text").value;
  const tplId = Number(document.getElementById("inquire-template").value);
  const res = await api.post(`/api/listings/${currentInquireListing.id}/inquire`, {
    template_id: tplId, message_text: text,
  });
  try { await navigator.clipboard.writeText(res.message_text); } catch (e) {}
  if (res.url) window.open(res.url, "_blank");
  dialog.close();
  toast("Nachricht kopiert — Inserat geöffnet. Einfügen & senden!");
  loadListings();
});

// ---------- Suchen ----------
async function loadSearches() {
  const searches = await api.get("/api/searches");
  searchesCache = searches;
  // Filter-Dropdown der Inserate befüllen
  const fs = document.getElementById("filter-search");
  const cur = fs.value;
  fs.innerHTML = '<option value="">Alle Suchen</option>' +
    searches.map((s) => `<option value="${s.id}">${escapeHtml(s.name)}</option>`).join("");
  fs.value = cur;

  const tb = document.querySelector("#searches-table tbody");
  tb.innerHTML = "";
  for (const s of searches) {
    const f = s.filters || {};
    const priceStr = [f.price_min, f.price_max].some((x) => x != null)
      ? `${f.price_min ?? ""}–${f.price_max ?? ""}` : "—";
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><input type="checkbox" ${s.active ? "checked" : ""} onchange="toggleSearch(${s.id}, this.checked)" /></td>
      <td>${escapeHtml(s.name)}</td>
      <td>${escapeHtml(s.query)}</td>
      <td>${priceStr}</td>
      <td>${s.interval_sec}s</td>
      <td>${fmtTime(s.last_polled_at)}</td>
      <td>${statusDot(s.last_status)}</td>
      <td>
        <button class="btn small" onclick="editSearch(${s.id})">Bearb.</button>
        <button class="btn small ghost" onclick="deleteSearch(${s.id})">Löschen</button>
      </td>`;
    tb.appendChild(tr);
  }
}

function statusDot(status) {
  if (!status) return '<span class="muted">—</span>';
  if (status === "ok") return '<span class="dot ok"></span>ok';
  return `<span class="dot err"></span><span class="muted" title="${escapeHtml(status)}">Fehler</span>`;
}

async function toggleSearch(id, active) { await api.put(`/api/searches/${id}`, { active }); toast(active ? "Suche aktiv" : "Suche pausiert"); }
async function deleteSearch(id) { if (!confirm("Suche löschen?")) return; await api.del(`/api/searches/${id}`); loadSearches(); }

function editSearch(id) {
  const s = searchesCache.find((x) => x.id === id);
  if (!s) return;
  const f = s.filters || {};
  document.getElementById("search-id").value = s.id;
  document.getElementById("search-name").value = s.name;
  document.getElementById("search-query").value = s.query;
  document.getElementById("search-pmin").value = f.price_min ?? "";
  document.getElementById("search-pmax").value = f.price_max ?? "";
  document.getElementById("search-interval").value = s.interval_sec;
  document.getElementById("form-search").scrollIntoView({ behavior: "smooth", block: "center" });
}

document.getElementById("form-search").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("search-id").value;
  // Bestehende Filter übernehmen (z.B. brand), nur die Preisfelder aus dem Formular setzen
  const existing = id ? searchesCache.find((x) => x.id === Number(id)) : null;
  const filters = existing && existing.filters ? { ...existing.filters } : {};
  const pmin = document.getElementById("search-pmin").value;
  const pmax = document.getElementById("search-pmax").value;
  if (pmin !== "") filters.price_min = Number(pmin); else delete filters.price_min;
  if (pmax !== "") filters.price_max = Number(pmax); else delete filters.price_max;
  const body = {
    name: document.getElementById("search-name").value,
    query: document.getElementById("search-query").value,
    filters,
    interval_sec: Number(document.getElementById("search-interval").value) || 60,
  };
  if (id) await api.put(`/api/searches/${id}`, body);
  else await api.post("/api/searches", body);
  resetSearchForm();
  loadSearches();
  toast("Suche gespeichert");
});
document.getElementById("search-reset").addEventListener("click", resetSearchForm);
function resetSearchForm() {
  document.getElementById("form-search").reset();
  document.getElementById("search-id").value = "";
  document.getElementById("search-interval").value = 60;
}

// ---------- Anfragen ----------
async function loadInquiries() {
  const rows = await api.get("/api/inquiries");
  inquiriesCache = rows;
  const tb = document.querySelector("#inquiries-table tbody");
  tb.innerHTML = "";
  const statuses = ["angefragt", "antwort", "verhandlung", "gekauft", "abgelehnt"];
  for (const r of rows) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${r.listing_url ? `<a href="${r.listing_url}" target="_blank">${escapeHtml(r.listing_title || "Inserat")}</a>` : escapeHtml(r.listing_title || "—")}</td>
      <td>${escapeHtml(r.listing_seller || "—")}</td>
      <td>${fmtPrice(r.listing_price, r.listing_currency)}</td>
      <td class="muted">${escapeHtml((r.message_text || "").slice(0, 80))}</td>
      <td><select onchange="updateInquiry(${r.id}, 'status', this.value)">
        ${statuses.map((s) => `<option value="${s}" ${r.status === s ? "selected" : ""}>${s}</option>`).join("")}
      </select></td>
      <td><input value="${escapeAttr(r.notes || "")}" onchange="updateInquiry(${r.id}, 'notes', this.value)" /></td>
      <td><button class="btn small" onclick="copyInquiry(${r.id})">Kopieren</button></td>`;
    tb.appendChild(tr);
  }
}
async function updateInquiry(id, field, value) { await api.put(`/api/inquiries/${id}`, { [field]: value }); toast("Anfrage aktualisiert"); }
function copyInquiry(id) {
  const r = inquiriesCache.find((x) => x.id === id);
  if (r) copyText(r.message_text || "");
}
async function copyText(t) { try { await navigator.clipboard.writeText(t); toast("Kopiert"); } catch (e) {} }

// ---------- Ein-/Verkäufe ----------
async function loadPurchases() {
  const rows = await api.get("/api/purchases");
  const tb = document.querySelector("#purchases-table tbody");
  tb.innerHTML = "";
  for (const p of rows) {
    const tr = document.createElement("tr");
    const margin = p.margin == null ? "—" : `<strong style="color:${p.margin >= 0 ? "var(--green)" : "var(--red)"}">${p.margin.toFixed(2)} €</strong>`;
    tr.innerHTML = `
      <td><input value="${escapeAttr(p.order_number || "")}" onchange="updatePurchase(${p.id}, 'order_number', this.value)" /></td>
      <td>${escapeHtml(p.item_name || "")}</td>
      <td>${escapeHtml(p.product || "")}</td>
      <td>${p.bought_price ?? "—"}</td>
      <td>${escapeHtml(p.bought_date || "—")}</td>
      <td><input type="number" step="0.01" value="${p.sold_price ?? ""}" placeholder="Verkauf €" onchange="updatePurchase(${p.id}, 'sold_price', this.value === '' ? null : Number(this.value))" /></td>
      <td><input type="date" value="${escapeAttr(p.sold_date || "")}" onchange="updatePurchase(${p.id}, 'sold_date', this.value)" /></td>
      <td><input value="${escapeAttr(p.sold_channel || "")}" placeholder="Kanal" onchange="updatePurchase(${p.id}, 'sold_channel', this.value)" /></td>
      <td>${margin}</td>
      <td><input value="${escapeAttr(p.notes || "")}" onchange="updatePurchase(${p.id}, 'notes', this.value)" /></td>`;
    tb.appendChild(tr);
  }
}
async function updatePurchase(id, field, value) { await api.put(`/api/purchases/${id}`, { [field]: value }); loadPurchases(); }

document.getElementById("form-purchase").addEventListener("submit", async (e) => {
  e.preventDefault();
  const body = {
    order_number: val("p-order"), item_name: val("p-name"), product: val("p-product"),
    bought_price: numOrNull("p-bought"), bought_date: val("p-bdate"), platform: val("p-platform"),
  };
  await api.post("/api/purchases", body);
  document.getElementById("form-purchase").reset();
  loadPurchases();
  toast("Einkauf erfasst");
});

// ---------- Vorlagen ----------
async function loadTemplates() {
  templatesCache = await api.get("/api/templates");
  const wrap = document.getElementById("templates-list");
  wrap.innerHTML = "";
  for (const t of templatesCache) {
    const div = document.createElement("div");
    div.className = "card";
    div.innerHTML = `<div class="body">
      <div class="title">${escapeHtml(t.name)}</div>
      <div class="muted" style="white-space:pre-wrap">${escapeHtml(t.body)}</div>
      <div class="actions">
        <button class="btn small" onclick="editTemplate(${t.id})">Bearbeiten</button>
        <button class="btn small ghost" onclick="deleteTemplate(${t.id})">Löschen</button>
      </div>
    </div>`;
    wrap.appendChild(div);
  }
}
async function deleteTemplate(id) {
  const t = templatesCache.find((x) => x.id === id);
  if (!confirm(`Vorlage „${t ? t.name : ""}" wirklich löschen?`)) return;
  await api.del(`/api/templates/${id}`);
  // Falls genau diese Vorlage gerade im Formular bearbeitet wird: zurücksetzen
  if (document.getElementById("tpl-id").value === String(id)) {
    document.getElementById("form-template").reset();
    document.getElementById("tpl-id").value = "";
  }
  loadTemplates();
  toast("Vorlage gelöscht");
}
function editTemplate(id) {
  const t = templatesCache.find((x) => x.id === id);
  if (!t) return;
  document.getElementById("tpl-id").value = t.id;
  document.getElementById("tpl-name").value = t.name;
  document.getElementById("tpl-body").value = t.body;
  document.getElementById("form-template").scrollIntoView({ behavior: "smooth", block: "center" });
}
document.getElementById("form-template").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = document.getElementById("tpl-id").value;
  const body = { name: val("tpl-name"), body: val("tpl-body") };
  if (id) await api.put(`/api/templates/${id}`, body);
  else await api.post("/api/templates", body);
  document.getElementById("form-template").reset();
  document.getElementById("tpl-id").value = "";
  loadTemplates();
  toast("Vorlage gespeichert");
});
document.getElementById("tpl-reset").addEventListener("click", () => {
  document.getElementById("form-template").reset();
  document.getElementById("tpl-id").value = "";
});

// ---------- Poll-Now + Auto-Refresh ----------
document.getElementById("btn-poll-now").addEventListener("click", async () => {
  const btn = document.getElementById("btn-poll-now");
  btn.disabled = true; btn.textContent = "Polle…";
  try {
    const res = await api.post("/api/poll-now");
    const total = Object.values(res).reduce((a, r) => a + (r.new || 0), 0);
    toast(`Gepollt — ${total} neue Inserate`);
    loadListings();
    updateStatus();
  } catch (e) { toast("Poll-Fehler: " + e.message); }
  finally { btn.disabled = false; btn.textContent = "Jetzt pollen"; }
});

document.getElementById("filter-status").addEventListener("change", loadListings);
document.getElementById("filter-search").addEventListener("change", loadListings);

// Inserate-Auto-Refresh (nur auf dem Tab)
setInterval(() => {
  const onListings = document.getElementById("tab-listings").classList.contains("active");
  const auto = document.getElementById("auto-refresh").checked;
  if (onListings && auto) loadListings();
}, 15000);

// Header-Status immer aktuell halten (unabhängig vom Tab)
setInterval(updateStatus, 15000);

// ---------- Helfer ----------
function val(id) { return document.getElementById(id).value || null; }
function numOrNull(id) { const v = document.getElementById(id).value; return v === "" ? null : Number(v); }
function escapeHtml(s) { return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])); }
function escapeAttr(s) { return escapeHtml(s); }

// ---------- Init ----------
(async function init() {
  try {
    const meta = await api.get("/api/meta");
    document.title = meta.app_name;
  } catch (e) {}
  await loadSearches();   // füllt auch den Such-Filter + Cache
  await loadTemplates();  // cache für Anfrage-Dialog
  await loadListings();   // cache für Kauf-/Anfrage-Dialog
  await loadOverview();   // Dashboard ist der Start-Tab
  updateStatus();         // Header-Status initial
})();
