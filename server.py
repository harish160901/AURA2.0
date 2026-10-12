#!/usr/bin/env python3
"""
AURA 2.0 Web Server
===================
Provides:
  1. Dual-stack HTTP server (IPv4 + IPv6) serving the frontend UI.
  2. /api/token endpoint: Generates LiveKit access tokens & auto-dispatches the agent.
  3. /api/dispatch endpoint: Fallback manual dispatch for rooms.
  4. /api/system endpoint: Direct macOS system automation (open/close apps, folders, battery, volume).
  5. /api/upload endpoint: High-speed file and image attachment handling.
"""

import asyncio
import base64
import certifi
import json
import mimetypes
import os
import socket
import ssl
import subprocess
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import aiohttp
from dotenv import load_dotenv
from livekit.api import (
    AccessToken,
    CreateAgentDispatchRequest,
    LiveKitAPI,
    VideoGrants,
)

# Ensure certifi SSL certificates are trusted
os.environ["SSL_CERT_FILE"] = certifi.where()

BASE_DIR = Path(__file__).parent.resolve()
load_dotenv(BASE_DIR / ".env.local")

LIVEKIT_URL = os.environ.get("LIVEKIT_URL", "wss://aura-z0b0c205.livekit.cloud")
LIVEKIT_API_KEY = os.environ.get("LIVEKIT_API_KEY", "")
LIVEKIT_API_SECRET = os.environ.get("LIVEKIT_API_SECRET", "")
AGENT_NAME = "my-agent"
PORT = 3000

UPLOAD_DIR = BASE_DIR / "uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

HOME = Path.home()

# ── Application Aliases for macOS ───────────────────────────────────────────
APP_MAP = {
    "safari": "Safari",
    "maps": "Maps",
    "map": "Maps",
    "apple maps": "Maps",
    "finder": "Finder",
    "files": "Finder",
    "whatsapp": "WhatsApp",
    "zoom": "zoom.us",
    "keynote": "Keynote",
    "word": "Microsoft Word",
    "excel": "Microsoft Excel",
    "powerpoint": "Microsoft PowerPoint",
    "onenote": "Microsoft OneNote",
    "teams": "Microsoft Teams",
    "onedrive": "OneDrive",
    "notes": "Notes",
    "note": "Notes",
    "calendar": "Calendar",
    "calculator": "Calculator",
    "terminal": "Terminal",
    "settings": "System Settings",
    "system settings": "System Settings",
    "system preferences": "System Preferences",
    "mail": "Mail",
    "messages": "Messages",
    "facetime": "FaceTime",
    "photos": "Photos",
    "music": "Music",
    "chrome": "Google Chrome",
    "google chrome": "Google Chrome",
    "brave": "Brave Browser",
    "vscode": "Visual Studio Code",
    "code": "Visual Studio Code",
    "textedit": "TextEdit",
    "preview": "Preview",
    "activity monitor": "Activity Monitor",
    "reminders": "Reminders",
}

DIR_MAP = {
    "desktop": HOME / "Desktop",
    "documents": HOME / "Documents",
    "downloads": HOME / "Downloads",
    "pictures": HOME / "Pictures",
    "music": HOME / "Music",
    "movies": HOME / "Movies",
    "home": HOME,
    "aura": BASE_DIR,
    "applications": Path("/Applications"),
}


def resolve_app_name(key: str) -> str:
    cleaned = key.strip().lower()
    return APP_MAP.get(cleaned, key.strip())


def resolve_dir_path(key: str) -> Path:
    cleaned = key.strip().lower()
    if cleaned in DIR_MAP:
        return DIR_MAP[cleaned]
    p = Path(key.strip())
    if p.is_dir():
        return p
    hp = HOME / key.strip()
    if hp.is_dir():
        return hp
    return DIR_MAP["desktop"]


# ── System Control Functions ────────────────────────────────────────────────
def exec_open_app(app_key: str) -> dict:
    target = resolve_app_name(app_key)
    try:
        proc = subprocess.run(["open", "-a", target], capture_output=True, text=True, timeout=5)
        if proc.returncode == 0:
            return {"ok": True, "result": f"Opened {target}"}
        subprocess.Popen(["open", "-a", app_key.strip()])
        return {"ok": True, "result": f"Opening {app_key}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def exec_close_app(app_key: str) -> dict:
    target = resolve_app_name(app_key)
    try:
        script = f'tell application "{target}" to quit'
        subprocess.Popen(["osascript", "-e", script])
        return {"ok": True, "result": f"Closed {target}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def exec_open_dir(dir_key: str) -> dict:
    path = resolve_dir_path(dir_key)
    try:
        subprocess.Popen(["open", str(path)])
        return {"ok": True, "result": f"Opened folder {path.name}"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def exec_list_dir(dir_key: str) -> dict:
    path = resolve_dir_path(dir_key)
    try:
        if not path.exists():
            return {"ok": False, "error": f"Folder {path} does not exist"}
        items = [p.name for p in sorted(path.iterdir()) if not p.name.startswith(".")]
        return {"ok": True, "result": items, "path": str(path), "count": len(items)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def exec_set_volume(val: str) -> dict:
    try:
        vol = max(0, min(100, int(val)))
        subprocess.run(["osascript", "-e", f"set volume output volume {vol}"], check=True)
        return {"ok": True, "result": f"Volume set to {vol}%"}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def exec_get_battery() -> dict:
    try:
        res = subprocess.run(["pmset", "-g", "batt"], capture_output=True, text=True)
        return {"ok": True, "result": res.stdout.strip()}
    except Exception as e:
        return {"ok": False, "error": str(e)}


def handle_system_api(params: dict) -> dict:
    cmd = params.get("cmd", [""])[0].strip().lower()
    target = params.get("app", params.get("dir", params.get("val", [""])))[0].strip()

    if cmd == "open_app":
        return exec_open_app(target)
    elif cmd == "close_app":
        return exec_close_app(target)
    elif cmd == "open_dir":
        return exec_open_dir(target)
    elif cmd == "list_dir":
        return exec_list_dir(target)
    elif cmd == "set_volume":
        return exec_set_volume(target)
    elif cmd == "battery":
        return exec_get_battery()
    elif cmd == "list_apps":
        return {"ok": True, "result": list(APP_MAP.keys())}
    return {"ok": False, "error": f"Unknown system command '{cmd}'"}


# ── LiveKit Dispatch Helper ─────────────────────────────────────────────────
async def dispatch_agent_async(room_name: str):
    try:
        ssl_ctx = ssl.create_default_context(cafile=certifi.where())
        connector = aiohttp.TCPConnector(ssl=ssl_ctx)
        async with aiohttp.ClientSession(connector=connector) as session:
            async with LiveKitAPI(
                LIVEKIT_URL,
                LIVEKIT_API_KEY,
                LIVEKIT_API_SECRET,
                session=session,
            ) as lk:
                await lk.agent_dispatch.create_dispatch(
                    CreateAgentDispatchRequest(agent_name=AGENT_NAME, room=room_name)
                )
                print(f"[Server] Dispatched agent '{AGENT_NAME}' to room '{room_name}'")
    except Exception as exc:
        print(f"[Server] Dispatch error notice: {exc}")


def trigger_background_dispatch(room_name: str):
    def _run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(dispatch_agent_async(room_name))
        loop.close()

    t = threading.Thread(target=_run, daemon=True)
    t.start()


def generate_token_and_room(identity: str = "user") -> dict:
    room_name = f"aura-{uuid.uuid4().hex[:8]}"

    token = (
        AccessToken(LIVEKIT_API_KEY, LIVEKIT_API_SECRET)
        .with_identity(identity)
        .with_name("User")
        .with_grants(
            VideoGrants(
                room_join=True,
                room=room_name,
                can_publish=True,
                can_subscribe=True,
                can_publish_data=True,
            )
        )
        .to_jwt()
    )

    # Immediately queue the agent to join the newly created room
    trigger_background_dispatch(room_name)

    return {"token": token, "url": LIVEKIT_URL, "room": room_name}


# ── Threading Dual-Stack HTTP Server ─────────────────────────────────────────
class DualStackThreadingServer(ThreadingHTTPServer):
    address_family = socket.AF_INET6

    def server_bind(self):
        try:
            self.socket.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 0)
        except Exception:
            pass
        return super().server_bind()


class AuraRequestHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(204)
        self.send_cors_headers()
        self.end_headers()

    def do_HEAD(self):
        self.serve_file(BASE_DIR / "index.html", "text/html; charset=utf-8")

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path in ("/", "/index.html"):
            self.serve_file(BASE_DIR / "index.html", "text/html; charset=utf-8")
        elif path == "/livekit-client.umd.min.js":
            self.serve_file(BASE_DIR / "livekit-client.umd.min.js", "application/javascript")
        elif path == "/api/token":
            self.serve_json(generate_token_and_room())
        elif path == "/api/dispatch":
            params = parse_qs(parsed.query)
            room_name = params.get("room", ["aura-room"])[0]
            trigger_background_dispatch(room_name)
            self.serve_json({"ok": True, "room": room_name})
        elif path == "/api/system":
            params = parse_qs(parsed.query)
            self.serve_json(handle_system_api(params))
        elif path.startswith("/uploads/"):
            filename = Path(path[len("/uploads/"): ]).name
            target = UPLOAD_DIR / filename
            mime, _ = mimetypes.guess_type(str(target))
            self.serve_file(target, mime or "application/octet-stream")
        else:
            self.send_error(404, "File Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/upload":
            self.handle_upload()
        else:
            self.send_error(404)

    def handle_upload(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            payload = json.loads(body.decode("utf-8"))
            filename = payload.get("filename", f"upload_{uuid.uuid4().hex[:6]}.dat")
            safe_filename = f"{uuid.uuid4().hex[:6]}_{Path(filename).name}"
            dest = UPLOAD_DIR / safe_filename

            b64data = payload.get("data", "")
            if "," in b64data:
                b64data = b64data.split(",", 1)[1]
            raw_bytes = base64.b64decode(b64data)
            dest.write_bytes(raw_bytes)

            self.serve_json({
                "ok": True,
                "filename": filename,
                "saved_name": safe_filename,
                "url": f"/uploads/{safe_filename}",
                "size": len(raw_bytes),
                "type": payload.get("type", "application/octet-stream"),
            })
        except Exception as exc:
            self.serve_json({"ok": False, "error": str(exc)}, 500)

    def serve_file(self, file_path: Path, content_type: str):
        if not file_path.exists():
            self.send_error(404, "File Not Found")
            return
        data = file_path.read_bytes()
        self.send_response(200)
        self.send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(data)

    def serve_json(self, obj: dict, status: int = 200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "*")

    def log_message(self, fmt, *args):
        # Suppress noisy HTTP request logging
        pass
    

def ensure_agent_running():
    try:
        res = subprocess.run(["pgrep", "-f", "agent.py dev"], capture_output=True, text=True)
        if not res.stdout.strip():
            venv_python = BASE_DIR / "venv" / "bin" / "python3"
            python_bin = str(venv_python) if venv_python.exists() else "python3"
            print("[Server] Starting AI agent worker in background...")
            subprocess.Popen([python_bin, str(BASE_DIR / "agent.py"), "dev"], cwd=str(BASE_DIR))
        else:
            print("[Server] AI agent worker is active.")
    except Exception as e:
        print(f"[Server] Note on agent auto-start: {e}")


def main():
    ensure_agent_running()
    try:
        server = DualStackThreadingServer(("::", PORT), AuraRequestHandler)
    except Exception:
        server = ThreadingHTTPServer(("0.0.0.0", PORT), AuraRequestHandler)

    print(f"\n=======================================================")
    print(f"  ✦  AURA 2.0 Web Server Active")
    print(f"  ✦  Local Access: http://localhost:{PORT}")
    print(f"  ✦  Direct IPv4 : http://127.0.0.1:{PORT}")
    print(f"=======================================================\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down server.")
        server.server_close()


if __name__ == "__main__":
    main()
