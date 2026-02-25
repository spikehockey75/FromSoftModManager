"""
Nexus Mods SSO authentication.
Opens browser for SSO flow, captures API key via local callback server.
"""

import json
import socket
import threading
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

NEXUS_SSO_URL = "https://app.nexusmods.com/oauth/authorize"
NEXUS_TOKEN_URL = "https://users.nexusmods.com/oauth/token"
NEXUS_SSO_CONNECT = "wss://sso.nexusmods.com"

# Nexus SSO uses a WebSocket-based flow. We'll use the API key approach:
# The user can also manually paste their API key.
# For the SSO-style flow without WebSocket deps, we use the NXM handler approach:
# Open nexusmods.com/users/myaccount and guide user to copy their personal API key.


class _CallbackHandler(BaseHTTPRequestHandler):
    """Simple HTTP handler to capture OAuth callback."""
    api_key = None

    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        key = params.get("api_key", [None])[0]
        if key:
            _CallbackHandler.api_key = key
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:sans-serif;background:#1a1a2e;color:#e0e0ec;
                display:flex;align-items:center;justify-content:center;height:100vh;margin:0'>
                <div style='text-align:center'>
                <h2 style='color:#e94560'>API Key Received!</h2>
                <p>You can close this tab and return to the app.</p>
                </div></body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"No API key received.")

    def log_message(self, format, *args):
        pass  # suppress server logs


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0))
        return s.getsockname()[1]


class NexusSSOAuth:
    """
    Nexus Mods authentication helper.
    Opens the Nexus API key page in a browser — user copies their personal key
    and pastes it into the app, OR we intercept a redirect if using callback.
    """

    def __init__(self):
        self._server = None
        self._port = None
        self._api_key = None
        self._done = threading.Event()

    def start_callback_server(self) -> int:
        """Start local HTTP server to receive callback. Returns port."""
        self._port = _find_free_port()
        _CallbackHandler.api_key = None

        self._server = HTTPServer(("127.0.0.1", self._port), _CallbackHandler)

        def _serve():
            while not self._done.is_set():
                self._server.handle_request()

        t = threading.Thread(target=_serve, daemon=True)
        t.start()
        return self._port

    def open_nexus_api_page(self):
        """Open the Nexus personal API key page in the default browser."""
        webbrowser.open("https://www.nexusmods.com/users/myaccount?tab=api+access")

    def poll_for_key(self) -> str | None:
        """Check if callback server received an API key."""
        return _CallbackHandler.api_key

    def stop(self):
        self._done.set()
        if self._server:
            try:
                self._server.server_close()
            except Exception:
                pass
