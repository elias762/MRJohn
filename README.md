# 🎯 Mr. Johns Sniper

Lokaler Markt-Monitor für Schmuck & Uhren auf **Vinted**. Überwacht definierte Suchen
(aktuell **Cartier Santos** & **Cartier Tank**), zeigt neue Inserate mit **Foto + Details**,
ermöglicht **blitzschnelles Anfragen** (vorformulierte Nachricht → Zwischenablage → Inserat
öffnet sich) und trackt **Ein-/Verkäufe inkl. Order-Nummer und Marge**.

## Setup (Windows)

```powershell
cd C:\Users\Dell\Desktop\Repo\John-bday
python -m pip install -r requirements.txt
python -m uvicorn backend.main:app --port 8000
```

Dann im Browser öffnen: **http://localhost:8000**

> Beim ersten Start werden die DB (`data/marktmonitor.db`), die zwei Cartier-Suchen und
> vier Nachrichten-Vorlagen automatisch angelegt. Der Poller startet sofort.

## Deploy auf Render (ohne Secrets/Env-Variablen)

Die App braucht **keine** versteckten Variablen oder API-Keys. Den Port gibt Render
per `$PORT` automatisch vor.

1. [render.com](https://render.com) → mit GitHub einloggen
2. **New** → **Blueprint** → Repo `elias762/MRJohn` wählen
3. Render erkennt `render.yaml` → **Apply** → fertig

> **Diese App ist eigentlich ein Dauer-Monitor — Serverless (z. B. Vercel) passt nicht**
> (kein Hintergrund-Thread, read-only Dateisystem). Render läuft als persistenter Server.

### Grenzen des Free-Tiers (ehrlich)

- **Flüchtige Daten:** Free-Services haben kein persistentes Disk → SQLite-Daten gehen
  bei Redeploy/Neustart verloren.
- **Schlafmodus:** Free-Services schlafen nach ~15 Min ohne Zugriff ein → der Poller
  pausiert bis zum nächsten Aufruf, also **keine echte 24/7-Überwachung**.

**Beides lösbar mit Render Starter (~7 $/Monat):** in `render.yaml` `plan: starter` setzen
und den `envVars`+`disk`-Block einkommentieren → persistente DB **und** kein Einschlafen.

### Weitere Hinweise

- Vinted/DataDome blocken Rechenzentrums-IPs oft stärker als Privat-IPs; der Poller läuft
  dann ggf. in Backoff. Für zuverlässiges Polling ist **lokaler Betrieb** am robustesten.
- Windows-Toasts (`winotify`) werden auf Linux-Hosts automatisch übersprungen.

## Bedienung

- **Inserate** — Karten mit Bild, Preis, Verkäufer. Buttons:
  - **⚡ Anfragen** → Vorlage wählen/bearbeiten → *Kopieren & Inserat öffnen*. Die Nachricht
    liegt in der Zwischenablage; im geöffneten Vinted-Tab nur noch einfügen (Strg+V) & senden.
  - **Gesehen / Gekauft / Ignorieren** → Status setzen.
  - Klick aufs Bild oder „Inserat ↗" öffnet das Angebot.
- **Suchen** — neue Modelle/Begriffe anlegen, Preis-Range & Intervall, aktiv/pausiert.
- **Anfragen** — wen habe ich angefragt; Status (angefragt → antwort → verhandlung → gekauft/abgelehnt) + Notizen.
- **Ein-/Verkäufe** — Order-Nr., Einkaufspreis/-datum, später Verkaufspreis/-datum/-kanal → **Marge** automatisch.
- **Vorlagen** — Nachrichten-Vorlagen mit Platzhaltern `{title} {price} {currency} {seller} {url} {brand}`.

## Benachrichtigungen

Windows-Desktop-Toasts bei neuen Treffern sind **aktuell deaktiviert**.
Zum Aktivieren in `backend/config.py`:

```python
NOTIFICATIONS_ENABLED = True
```

und den Server neu starten.

## Konfiguration (`backend/config.py`)

| Einstellung | Default | Bedeutung |
|---|---|---|
| `NOTIFICATIONS_ENABLED` | `False` | Windows-Toasts an/aus |
| `DEFAULT_INTERVAL_SEC` | `60` | Standard-Poll-Intervall pro Suche |
| `MIN_INTERVAL_SEC` | `30` | Untergrenze (gegen Rate-Limit/Sperre) |
| `SEARCH_PER_PAGE` | `40` | Items pro Abfrage |
| `ERROR_BACKOFF_SEC` | `120` | Pause nach Vinted-Fehler/Block |

## Architektur

```
backend/
  main.py      FastAPI: API + statisches Dashboard, startet Poller
  poller.py    Hintergrund-Thread: aktive Suchen pollen, neue Inserate erkennen
  vinted.py    Wrapper um vinted-scraper (Session/DataDome automatisch)
  db.py        SQLite: Schema + CRUD (searches, listings, inquiries, purchases, templates)
  notify.py    Windows-Toast (winotify)
  templates.py Nachrichten-Vorlagen rendern
  config.py    Pfade & Defaults
frontend/      index.html / app.js / style.css  (kein Build-Step)
data/          SQLite-Datei (gitignored)
```

## Hinweise

- Anfragen sind **halbautomatisch** (du klickst senden) — ToS-konform, kein Spam.
- Vinted-Endpoints sind intern und können sich ändern; bei Fehlern baut der Client die
  Session neu auf und der Poller macht eine kurze Pause (Backoff).
- Polling ≥ 30 s halten, um nicht geblockt zu werden.

## Nächste Schritte (geplant)

- **Kleinanzeigen** als zweite Plattform (Anti-Bot → Browser-Automatisierung/Extension).
- Preis-Historie & „guter Deal"-Heuristik (Preis < Median der Suche).
- Optional **Supabase**-Anbindung für Cloud-Sync der Ein-/Verkäufe (mehrere Geräte).
- Optional Telegram-Push als mobiler Kanal.
