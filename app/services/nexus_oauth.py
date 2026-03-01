"""
Nexus Mods OAuth 2.0 + PKCE authentication for desktop apps.

Spins up a temporary localhost HTTP server to capture the authorization
callback, exchanges the code for JWT tokens, and provides token refresh.
"""

import base64
import hashlib
import json
import os
import threading
import time
import uuid
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, urlparse, parse_qs
import urllib.request
import urllib.error

# ── Nexus OAuth endpoints ────────────────────────────────────────
NEXUS_AUTH_URL = "https://users.nexusmods.com/oauth/authorize"
NEXUS_TOKEN_URL = "https://users.nexusmods.com/oauth/token"
CLIENT_ID = "nexus_oauth_client"  # TODO: replace with registered Client ID
REDIRECT_URI = "http://127.0.0.1:9876/callback"
REDIRECT_PORT = 9876

# RSA public key for JWT verification (from Nexus docs)
NEXUS_PUBLIC_KEY = (
    "-----BEGIN PUBLIC KEY-----\n"
    "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQDhKHxCWOeUy38S3UOBOB11SNd/\n"
    "wyL9TVvzxePkEsZb4fEVGp0U5MEcDcJgXUo/fZOYTUFMX7ipvCC7sbsyKpJ0xZ/M\n"
    "l5zXMBcI03gu6p1TvG+eL0xEk6X8LD+t+GbzH9EY58bZ8kOLEx4lbAX3fNYhMhbh\n"
    "HJra9ZVW2QdgHoDV6wIDAQAB\n"
    "-----END PUBLIC KEY-----"
)


# ── PKCE helpers ─────────────────────────────────────────────────

def _generate_code_verifier() -> str:
    """Generate a cryptographically random code verifier (43+ chars)."""
    return base64.urlsafe_b64encode(os.urandom(43)).rstrip(b"=").decode("ascii")


def _generate_code_challenge(verifier: str) -> str:
    """SHA-256 hash of the verifier, base64url-encoded (no padding)."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


# ── JWT decode (minimal, no external dependency) ─────────────────

def _b64url_decode(s: str) -> bytes:
    """Decode base64url without padding."""
    s += "=" * (4 - len(s) % 4)
    return base64.urlsafe_b64decode(s)


def decode_jwt_payload(token: str) -> dict:
    """Decode the JWT payload without verification (user info extraction).

    We trust the token because it came directly from the Nexus token endpoint
    over HTTPS. Full RSA verification can be added later if needed.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return {}
    try:
        payload = _b64url_decode(parts[1])
        return json.loads(payload)
    except Exception:
        return {}


def extract_user_info(access_token: str) -> dict:
    """Extract user info from a Nexus OAuth JWT access token."""
    payload = decode_jwt_payload(access_token)
    user = payload.get("user", {})
    roles = user.get("membership_roles", [])
    return {
        "name": user.get("username", ""),
        "is_premium": "premium" in roles or "lifetimepremium" in roles,
        "is_supporter": "supporter" in roles,
        "profile_url": "",  # Not available in JWT; fetched separately if needed
    }


# ── Token exchange & refresh ─────────────────────────────────────

def exchange_code_for_tokens(code: str, code_verifier: str) -> dict:
    """Exchange an authorization code for access + refresh tokens.

    Returns:
        {"access_token", "refresh_token", "expires_in", "token_type"}
        or {"error": "..."} on failure.
    """
    body = urlencode({
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
        "scope": "",
    }).encode("utf-8")

    req = urllib.request.Request(
        NEXUS_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            data["expires_at"] = int(time.time()) + data.get("expires_in", 3600)
            return data
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode()
        except Exception:
            err_body = ""
        return {"error": f"Token exchange failed (HTTP {e.code}): {err_body}"}
    except Exception as e:
        return {"error": f"Token exchange failed: {e}"}


def refresh_access_token(refresh_token: str) -> dict:
    """Use a refresh token to obtain a new access token.

    Returns:
        {"access_token", "refresh_token", "expires_in", "token_type", "expires_at"}
        or {"error": "..."} on failure (e.g. token revoked).
    """
    body = urlencode({
        "grant_type": "refresh_token",
        "client_id": CLIENT_ID,
        "refresh_token": refresh_token,
    }).encode("utf-8")

    req = urllib.request.Request(
        NEXUS_TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            data["expires_at"] = int(time.time()) + data.get("expires_in", 3600)
            return data
    except urllib.error.HTTPError as e:
        code = e.code
        if 400 <= code < 500:
            return {"error": "Token revoked or expired. Please re-authorize."}
        return {"error": f"Token refresh failed (HTTP {code})"}
    except Exception as e:
        return {"error": f"Token refresh failed: {e}"}


# ── Localhost callback server ────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    """Handles the OAuth callback on localhost."""

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return

        params = parse_qs(parsed.query)
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]

        if error:
            self.server.oauth_error = error
        elif not code:
            self.server.oauth_error = "No authorization code received"
        elif state != self.server.expected_state:
            self.server.oauth_error = "State mismatch — possible CSRF attack"
        else:
            self.server.oauth_code = code

        # Send a user-friendly response page
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        if self.server.oauth_code:
            html = (
                "<html><body style='font-family:sans-serif;text-align:center;"
                "padding:60px;background:#1a1a2e;color:#e0e0ec;'>"
                "<h2>Authorization successful!</h2>"
                "<p>You can close this tab and return to FromSoft Mod Manager.</p>"
                "</body></html>"
            )
        else:
            html = (
                "<html><body style='font-family:sans-serif;text-align:center;"
                "padding:60px;background:#1a1a2e;color:#e0e0ec;'>"
                f"<h2>Authorization failed</h2>"
                f"<p>{self.server.oauth_error or 'Unknown error'}</p>"
                "</body></html>"
            )
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        """Suppress default HTTP server logging."""
        pass


class _OAuthHTTPServer(HTTPServer):
    """HTTPServer subclass to hold OAuth state."""

    def __init__(self, state: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.expected_state = state
        self.oauth_code = None
        self.oauth_error = None
        self.timeout = 0.5  # For handle_request() polling


# ── Main OAuth client ────────────────────────────────────────────

class NexusOAuthClient:
    """OAuth 2.0 PKCE client for Nexus Mods desktop authorization.

    Usage:
        client = NexusOAuthClient()
        client.start()          # opens browser + starts localhost server
        # poll periodically:
        tokens, err = client.poll()
        if tokens:  ...         # got tokens dict
        if err:     ...         # something went wrong
        client.stop()           # clean up
    """

    def __init__(self):
        self._tokens: dict | None = None
        self._error: str | None = None
        self._code_verifier: str = ""
        self._state: str = ""
        self._server: _OAuthHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._done = threading.Event()

    def start(self):
        """Generate PKCE params, start localhost server, and open browser."""
        self._tokens = None
        self._error = None
        self._done.clear()

        self._code_verifier = _generate_code_verifier()
        code_challenge = _generate_code_challenge(self._code_verifier)
        self._state = str(uuid.uuid4())

        # Start localhost callback server
        try:
            self._server = _OAuthHTTPServer(
                self._state,
                ("127.0.0.1", REDIRECT_PORT),
                _CallbackHandler,
            )
        except OSError as e:
            self._error = f"Could not start callback server on port {REDIRECT_PORT}: {e}"
            return

        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

        # Build and open authorize URL
        params = urlencode({
            "client_id": CLIENT_ID,
            "response_type": "code",
            "scope": "",
            "redirect_uri": REDIRECT_URI,
            "state": self._state,
            "code_challenge_method": "S256",
            "code_challenge": code_challenge,
        })
        webbrowser.open(f"{NEXUS_AUTH_URL}?{params}")

    def poll(self) -> tuple[dict | None, str | None]:
        """Non-blocking check for results.

        Returns (tokens_dict, error).
        tokens_dict keys: access_token, refresh_token, expires_at, user
        """
        return self._tokens, self._error

    def stop(self):
        """Shut down the callback server and clean up."""
        self._done.set()
        if self._server:
            try:
                self._server.shutdown()
            except Exception:
                pass
            self._server = None

    def _serve(self):
        """Run the callback server until we get a code/error or are stopped."""
        server = self._server
        if not server:
            return

        while not self._done.is_set():
            server.handle_request()

            if server.oauth_error:
                self._error = server.oauth_error
                self._done.set()
                break

            if server.oauth_code:
                # Exchange the code for tokens
                tokens = exchange_code_for_tokens(
                    server.oauth_code, self._code_verifier
                )
                if "error" in tokens:
                    self._error = tokens["error"]
                else:
                    # Attach user info extracted from JWT
                    tokens["user"] = extract_user_info(
                        tokens.get("access_token", "")
                    )
                    self._tokens = tokens
                self._done.set()
                break

        # Shut down the server
        try:
            server.server_close()
        except Exception:
            pass
