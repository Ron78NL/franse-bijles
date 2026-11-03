#!/usr/bin/env python3
"""Lokale Frans-bijles-server (kopie van de wiskundebijles, met Franse tutor-prompt en uploads)."""
import base64
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent
PUBLIC = (ROOT / "public").resolve()
SCHOOLWERK = ROOT / "schoolwerk"
PORT = int(os.environ.get("PORT", "3001"))
MODEL = "claude-sonnet-5-5"
API_URL = "https://api.anthropic.com/v1/messages"
PROMPT_FILE = ROOT / "system-prompt-fr.md"
MAX_BODY = 60 * 1024 * 1024  # Maximaal 60MB payload (PDF's worden base64 en dus ~33% groter)
ALLOWED_UPLOAD = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}

MIME = {
    ".html": "text/html; charset=utf-8",
    ".js": "text/javascript",
    ".css": "text/css",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".ico": "image/x-icon",
}


def load_env():
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        if k and k not in os.environ:
            os.environ[k] = v


def ssl_context():
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def build_system_prompt():
    return PROMPT_FILE.read_text(encoding="utf-8") if PROMPT_FILE.exists() else ""


def save_upload(name, data):
    """Bewaar een geüpload bestand in de map schoolwerk, zoals de wiskundebijles doet."""
    safe = re.sub(r"[^A-Za-z0-9._ -]", "_", Path(name).name).strip(" .")
    stem, ext = os.path.splitext(safe)
    if not stem or ext.lower() not in ALLOWED_UPLOAD:
        raise ValueError("Alleen foto's (jpg, png, webp) en pdf's zijn toegestaan.")
    SCHOOLWERK.mkdir(exist_ok=True)
    target = SCHOOLWERK / safe
    if target.exists():  # Nooit een bestaand bestand overschrijven
        target = SCHOOLWERK / f"{stem}_{int(time.time())}{ext}"
    target.write_bytes(data)
    return target.name


def call_claude(messages):
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    payload = json.dumps(
        {
            "model": MODEL,
            "max_tokens": 1000,
            "system": build_system_prompt(),
            "messages": messages,
        }
    ).encode("utf-8")

    req = urllib.request.Request(
        API_URL,
        data=payload,
        method="POST",
        headers={
            "content-type": "application/json",
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
        },
    )
    with urllib.request.urlopen(req, timeout=90, context=ssl_context()) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return "\n".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")


class Handler(BaseHTTPRequestHandler):
    server_version = "FransBijles/1.0"

    def log_message(self, fmt, *args):
        pass  # Geen clutter in de terminal

    def _json(self, status, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0"))
        if length <= 0 or length > MAX_BODY:
            raise ValueError("Bericht is leeg of overschrijdt de limiet.")
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def do_GET(self):
        # Beveiliging tegen path traversal
        path = unquote(urlparse(self.path).path)
        rel = "index.html" if path == "/" else path.lstrip("/")
        target = (PUBLIC / rel).resolve()

        if PUBLIC not in target.parents and target != PUBLIC:
            self.send_error(403, "Toegang geweigerd")
            return
        if not target.is_file():
            self.send_error(404, "Niet gevonden")
            return

        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        path = urlparse(self.path).path

        if path == "/api/upload":
            try:
                body = self._read_json()
                data = base64.b64decode(str(body.get("data", "")), validate=True)
                saved = save_upload(str(body.get("name", "")), data)
            except ValueError as e:
                return self._json(400, {"error": str(e)})
            except Exception:
                return self._json(400, {"error": "Het bestand kon niet worden opgeslagen."})
            return self._json(200, {"name": saved})

        if path != "/api/chat":
            self.send_error(404)
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return self._json(500, {"error": "Geen API-sleutel ingesteld in .env."})

        try:
            body = self._read_json()
            messages = body.get("messages")
            if not isinstance(messages, list) or not messages:
                return self._json(400, {"error": "Ongeldige berichtstructuur."})
        except Exception:
            return self._json(400, {"error": "Fout bij het verwerken van het verzoek."})

        try:
            text = call_claude(messages)
            self._json(200, {"text": text})
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            print(f"API-fout {e.code}: {detail}", file=sys.stderr)
            self._json(502, {"error": f"De tutor kon niet antwoorden ({e.code})."})
        except urllib.error.URLError as e:
            print(f"Netwerkfout: {e.reason}", file=sys.stderr)
            self._json(502, {"error": "Geen verbinding met de API."})
        except Exception as e:
            print(f"Interne fout: {e}", file=sys.stderr)
            self._json(502, {"error": "Er ging iets mis op de server."})


def main():
    load_env()
    # Gebonden aan localhost (127.0.0.1) voor lokale veiligheid
    httpd = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print(f"Frans-bijles draait op http://localhost:{PORT}  (stoppen: Ctrl+C)")
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("LET OP: zet je ANTHROPIC_API_KEY in het .env-bestand.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nGestopt.")


if __name__ == "__main__":
    main()
