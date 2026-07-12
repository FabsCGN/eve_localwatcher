"""EVE Online SSO v2 — OAuth2 with PKCE (native/desktop, no client secret).

Flow: build authorize URL with a PKCE challenge → open the browser → catch the
redirect on a tiny local HTTP server → exchange the code for tokens → decode the
JWT for the character id. Refresh tokens are stored in the config.

Requested scopes: fleet-read (friendly filter) and location-read (the kill
radar follows your current system); corp/alliance come from the character's
public affiliation, so no further scopes are needed.
"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlencode, urlparse

import requests

AUTHORIZE = "https://login.eveonline.com/v2/oauth/authorize/"
TOKEN = "https://login.eveonline.com/v2/oauth/token"
CALLBACK_PORT = 8765
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
LOCATION_SCOPE = "esi-location.read_location.v1"
DEFAULT_SCOPES = ["esi-fleets.read_fleet.v1", LOCATION_SCOPE]

_DONE_HTML = (
    "<html><body style='font-family:sans-serif;background:#111;"
    "color:#eee;text-align:center;padding-top:60px'>"
    "<h2>Flint Local Watcher</h2><p>Login abgeschlossen — "
    "du kannst dieses Fenster schließen.</p></body></html>"
).encode("utf-8")


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def generate_pkce() -> Tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


def authorize_url(client_id: str, scopes: List[str], challenge: str,
                  state: str) -> str:
    q = urlencode({
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "client_id": client_id,
        "scope": " ".join(scopes),
        "code_challenge": challenge,
        "code_challenge_method": "S256",
        "state": state,
    })
    return f"{AUTHORIZE}?{q}"


def decode_token(access_token: str) -> Dict:
    """Decode the JWT payload (no signature check — we just received it over TLS)."""
    payload = access_token.split(".")[1]
    payload += "=" * (-len(payload) % 4)
    data = json.loads(base64.urlsafe_b64decode(payload))
    sub = data.get("sub", "")            # "CHARACTER:EVE:123456789"
    char_id = int(sub.split(":")[-1]) if sub.startswith("CHARACTER") else None
    return {"character_id": char_id, "name": data.get("name"),
            "scopes": data.get("scp"), "exp": data.get("exp")}


def _exchange(client_id: str, code: str, verifier: str) -> Dict:
    r = requests.post(TOKEN, data={
        "grant_type": "authorization_code", "code": code,
        "client_id": client_id, "code_verifier": verifier},
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Host": "login.eveonline.com"}, timeout=20)
    r.raise_for_status()
    return r.json()


def refresh(client_id: str, refresh_token: str) -> Dict:
    """Exchange a refresh token for a fresh access token."""
    r = requests.post(TOKEN, data={
        "grant_type": "refresh_token", "refresh_token": refresh_token,
        "client_id": client_id},
        headers={"Content-Type": "application/x-www-form-urlencoded",
                 "Host": "login.eveonline.com"}, timeout=20)
    r.raise_for_status()
    return r.json()


def access_from_refresh(client_id: str, refresh_token: str):
    """Get a fresh access token from a stored refresh token.

    Returns (access_token|None, refresh_token) — EVE may rotate the refresh
    token, so the caller should persist the returned one.
    """
    try:
        data = refresh(client_id, refresh_token)
        return data.get("access_token"), data.get("refresh_token") or refresh_token
    except Exception:
        return None, refresh_token


def _make_handler(result: Dict, expect_state: str):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            qs = parse_qs(urlparse(self.path).query)
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(_DONE_HTML)
            if "code" in qs and qs.get("state", [""])[0] == expect_state:
                result["code"] = qs["code"][0]
            elif "error" in qs:
                result["error"] = qs["error"][0]
            else:
                result["error"] = "state mismatch"

        def log_message(self, *_):  # silence the default stderr logging
            pass
    return Handler


def login(client_id: str, scopes: Optional[List[str]] = None,
          timeout: int = 180) -> Tuple[Dict, Dict]:
    """Run the interactive PKCE login. Returns (tokens, character_info).

    Opens the browser and waits up to ``timeout`` seconds for the callback.
    """
    scopes = scopes or DEFAULT_SCOPES
    verifier, challenge = generate_pkce()
    state = secrets.token_urlsafe(16)
    result: Dict = {}

    server = HTTPServer(("localhost", CALLBACK_PORT), _make_handler(result, state))
    server.timeout = 1
    done = threading.Event()

    def serve():
        while not done.is_set() and "code" not in result and "error" not in result:
            server.handle_request()
    t = threading.Thread(target=serve, daemon=True)
    t.start()

    webbrowser.open(authorize_url(client_id, scopes, challenge, state))
    t.join(timeout)
    done.set()
    try:
        server.server_close()
    except Exception:
        pass

    if "error" in result:
        raise RuntimeError(f"SSO-Login fehlgeschlagen: {result['error']}")
    if "code" not in result:
        raise TimeoutError("Kein Login innerhalb des Zeitlimits.")

    tokens = _exchange(client_id, result["code"], verifier)
    return tokens, decode_token(tokens["access_token"])
