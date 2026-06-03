"""Zentrale Pfade und Defaults."""
import os
from pathlib import Path

APP_NAME = "Mr. Johns Sniper"

# Projekt-Wurzel (eine Ebene über backend/)
ROOT = Path(__file__).resolve().parent.parent
# Datenverzeichnis: lokal "data/", auf Hosting per DATA_DIR auf ein persistentes
# Disk umlenkbar (in render.yaml gesetzt — kein vom Nutzer einzugebendes Secret).
DATA_DIR = Path(os.environ.get("DATA_DIR", ROOT / "data"))
FRONTEND_DIR = ROOT / "frontend"
DB_PATH = DATA_DIR / "marktmonitor.db"

# Vinted
VINTED_BASE_URL = "https://www.vinted.de"

# Benachrichtigungen
# Auf True setzen, um Windows-Toasts bei neuen Inseraten zu erhalten.
NOTIFICATIONS_ENABLED = False

# Polling
DEFAULT_INTERVAL_SEC = 60          # höfliches Standard-Intervall pro Suche
MIN_INTERVAL_SEC = 30              # untere Grenze gegen Rate-Limit/Sperre
POLLER_TICK_SEC = 5               # wie oft der Loop prüft, welche Suche fällig ist
SEARCH_PER_PAGE = 40               # Items pro Suchabfrage

# Backoff bei Fehlern/Blocks (Sekunden)
ERROR_BACKOFF_SEC = 120

DATA_DIR.mkdir(parents=True, exist_ok=True)
