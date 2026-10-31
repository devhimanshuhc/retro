"""Google Docs export with Retro's own Google sign-in: OAuth 2.0 with PKCE, redirected back to this machine's API.
One Google account per install. Its refresh token is kept in Mongo `settings` like the model keys; access tokens are
fetched per export and never stored. Scope `drive.file` only: Retro can see just the docs it creates.

The OAuth client (the "Google app") is Retro's own when GOOGLE_CLIENT_ID is set at build or in .env, so users only
click Connect; otherwise the user registers one in Google Cloud and pastes it in Connectors (a setup guide shows how).
"""
import base64
import hashlib
import json
import re
import secrets
import uuid
from urllib.parse import urlencode

import httpx
import markdown
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

import config
from app.models.run import now

SCOPE = "openid email https://www.googleapis.com/auth/drive.file"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
CLIENT_ID = re.compile(r"^[\w-]+\.apps\.googleusercontent\.com$")
CLIENT, ACCOUNT = "google_client", "google"  # settings ids: the pasted Google app, the connected account
STATE_TTL_S = 600  # a sign-in must finish within 10 minutes


class NotConfigured(Exception):
    """No Google app (OAuth client) yet: neither GOOGLE_CLIENT_ID nor one pasted in Connectors."""


class NotConnected(Exception):
    """No Google account connected, or Google no longer accepts its token."""


def _http() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60)


def _settings(db: AsyncDatabase):
    return db["settings"]


def redirect_uri() -> str:
    return f"{config.API_URL}/connectors/google/callback"


async def client(db: AsyncDatabase) -> tuple[str, str] | None:
    """(client_id, client_secret) of the Google app: one pasted in the app wins over the env's."""
    doc = await _settings(db).find_one({"_id": CLIENT})
    if doc:
        return doc["client_id"], doc.get("client_secret", "")
    return (config.GOOGLE_CLIENT_ID, config.GOOGLE_CLIENT_SECRET) if config.GOOGLE_CLIENT_ID else None


async def save_client(db: AsyncDatabase, client_id: str, client_secret: str) -> None:
    """Use this Google app. The connected account's token belongs to the old app, so it is dropped."""
    if not CLIENT_ID.match(client_id) or len(client_id) > 200:
        raise ValueError("That isn't a Google client ID: it ends in .apps.googleusercontent.com")
    if not 10 <= len(client_secret) <= 200:
        raise ValueError("That isn't a Google client secret: copy it from the client's page (it often starts with GOCSPX-)")
    await disconnect(db)
    # shortcut: stored as plain text on the local Mongo, like the model keys; encrypt if Retro is ever hosted
    await _settings(db).replace_one({"_id": CLIENT}, {"client_id": client_id, "client_secret": client_secret,
                                                      "updated_at": now()}, upsert=True)


async def account(db: AsyncDatabase) -> dict | None:
    return await _settings(db).find_one({"_id": ACCOUNT})


def _challenge(verifier: str) -> str:
    return base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()


async def start(db: AsyncDatabase, redis: Redis, prefix: str, return_to: str) -> str:
    """Google's sign-in URL. The state and PKCE verifier wait in Redis for the callback."""
    if (app := await client(db)) is None:
        raise NotConfigured("Set up Google Docs first: Connectors → Google Docs → Set up")
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(64)
    await redis.set(f"{prefix}:google:oauth:{state}", json.dumps({"verifier": verifier, "return_to": return_to}),
                    ex=STATE_TTL_S)
    return AUTH_URL + "?" + urlencode({
        "client_id": app[0], "redirect_uri": redirect_uri(), "response_type": "code", "scope": SCOPE, "state": state,
        "code_challenge": _challenge(verifier), "code_challenge_method": "S256",
        "access_type": "offline",  # a refresh token, so exports work without signing in again
        "prompt": "select_account consent",  # pick the account every time; consent so Google returns a refresh token
    })


def _email(id_token: str | None) -> str | None:
    """The account's email from the ID token. It came straight from Google's token endpoint over TLS, so the
    signature isn't checked again."""
    try:
        payload = id_token.split(".")[1]
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))).get("email")
    except (AttributeError, IndexError, ValueError):
        return None


async def finish(db: AsyncDatabase, redis: Redis, prefix: str, state: str, code: str) -> str:
    """Trade the callback's code for tokens and save the account. Returns where the browser goes next."""
    pending = await redis.getdel(f"{prefix}:google:oauth:{state}")
    if pending is None:
        raise NotConnected("This sign-in expired or was already used; connect again")
    pending = json.loads(pending)
    if (app := await client(db)) is None:
        raise NotConfigured("The Google app was removed during sign-in; set it up again")
    async with _http() as h:
        r = await h.post(TOKEN_URL, data={"grant_type": "authorization_code", "code": code, "client_id": app[0],
                                          "client_secret": app[1], "redirect_uri": redirect_uri(),
                                          "code_verifier": pending["verifier"]})
    tok = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    if r.status_code >= 400:
        hint = " (check the client secret in Connectors)" if tok.get("error") in ("invalid_client", "unauthorized_client") else ""
        raise NotConnected(f"Google refused the sign-in: {tok.get('error_description') or tok.get('error') or r.status_code}{hint}")
    if "drive.file" not in tok.get("scope", ""):
        raise NotConnected("Retro needs permission to create Google Docs: tick that box when Google asks")
    if not tok.get("refresh_token"):
        raise NotConnected("Google didn't grant lasting access; connect again")
    old = await account(db)
    await _settings(db).replace_one({"_id": ACCOUNT}, {"refresh_token": tok["refresh_token"],
                                                       "email": _email(tok.get("id_token")), "updated_at": now()},
                                    upsert=True)
    if old and old["refresh_token"] != tok["refresh_token"]:
        await _revoke(old["refresh_token"])
    return pending["return_to"]


async def _revoke(token: str) -> None:
    try:
        async with _http() as h:
            await h.post(REVOKE_URL, data={"token": token})
    except httpx.HTTPError:
        pass  # best effort: the user can also remove Retro at myaccount.google.com/permissions


async def disconnect(db: AsyncDatabase) -> None:
    """Revoke Retro's access at Google and forget the account. Docs already created stay in the user's Drive."""
    if old := await account(db):
        await _revoke(old["refresh_token"])
        await _settings(db).delete_one({"_id": ACCOUNT})


async def access_token(db: AsyncDatabase) -> str:
    """A fresh access token for one export. shortcut: refreshes on every export; cache it until expiry if exports
    ever get frequent."""
    if (acct := await account(db)) is None:
        raise NotConnected("Connect your Google account first")
    if (app := await client(db)) is None:
        raise NotConfigured("Set up Google Docs first: Connectors → Google Docs → Set up")
    async with _http() as h:
        r = await h.post(TOKEN_URL, data={"grant_type": "refresh_token", "refresh_token": acct["refresh_token"],
                                          "client_id": app[0], "client_secret": app[1]})
    if r.status_code in (400, 401):  # invalid_grant: revoked, expired, or the Google app is still in Testing mode
        await _settings(db).delete_one({"_id": ACCOUNT})
        raise NotConnected("Google no longer accepts Retro's access (revoked or expired); connect your account again")
    r.raise_for_status()
    return r.json()["access_token"]


def report_html(report_md: str) -> str:
    """The report as HTML for Google's Docs import (headings, lists, links and tables survive the conversion)."""
    return "<html><body>" + markdown.markdown(report_md, extensions=["tables"]) + "</body></html>"


async def create_google_doc(db: AsyncDatabase, title: str, report_md: str) -> dict:
    """Upload the report to the user's Drive as a Google Doc (HTML, converted by Drive). Returns {id, url}."""
    token = await access_token(db)
    boundary = f"retro-{uuid.uuid4().hex}"
    meta = json.dumps({"name": title, "mimeType": "application/vnd.google-apps.document"})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n{report_html(report_md)}\r\n--{boundary}--").encode()
    async with _http() as g:
        r = await g.post("https://www.googleapis.com/upload/drive/v3/files",
                         params={"uploadType": "multipart", "fields": "id,webViewLink"}, content=body,
                         headers={"Authorization": f"Bearer {token}",
                                  "Content-Type": f"multipart/related; boundary={boundary}"})
    if r.status_code == 403 and "accessNotConfigured" in r.text:
        raise NotConnected("Turn on the Google Drive API for your Google app (Connectors → Google Docs → Set up, step 2)")
    if r.status_code in (401, 403):
        raise NotConnected(f"Google refused the upload ({r.status_code}); connect your account again")
    r.raise_for_status()
    doc = r.json()
    return {"id": doc["id"], "url": doc.get("webViewLink") or f"https://docs.google.com/document/d/{doc['id']}/edit"}
