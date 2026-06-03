"""Einstiegspunkt im Wurzelverzeichnis.

Manche Hosting-Plattformen suchen die FastAPI-App nur an Standard-Orten
(root main.py / app.py), nicht in Unterordnern. Wir reichen die App hier
einfach aus backend/main.py durch — so wird `app` automatisch gefunden.

Lokal/Hosting weiterhin auch direkt nutzbar:  uvicorn main:app  bzw.  uvicorn backend.main:app
"""
import os

from backend.main import app  # re-export für Auto-Detection

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)
