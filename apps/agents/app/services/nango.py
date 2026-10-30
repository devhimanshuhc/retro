"""Connectors through a self-hosted Nango (docker compose --profile nango): Nango runs the OAuth flow, stores and
refreshes the user's tokens; Retro asks it for a current access token per export and keeps none. Retro's only
long-lived secret is Nango's secret key. First connector: Google Docs, via the Drive API with the narrow `drive.file` scope
(Retro can see only the files it creates)."""
import json
import uuid

import httpx
import markdown

import config


class NotConfigured(Exception):
    """NANGO_SECRET_KEY isn't set: the connector can't be used."""


class NotConnected(Exception):
    """The user hasn't connected their Google account yet."""


def _client() -> httpx.AsyncClient:
    if not config.NANGO_SECRET_KEY:
        raise NotConfigured("set NANGO_SECRET_KEY in apps/agents/.env (Nango dashboard → Environment settings)")
    return httpx.AsyncClient(base_url=config.NANGO_HOST, timeout=60,
                             headers={"Authorization": f"Bearer {config.NANGO_SECRET_KEY}"})


async def session_token() -> str:
    """A short-lived token the browser uses to open Nango's Connect UI for the Google integration."""
    async with _client() as c:
        # prompt=select_account consent: Google always shows the account chooser and the consent screen, so after
        # a disconnect the user picks an account again instead of being signed back in silently
        r = await c.post("/connect/sessions", json={
            "tags": {"end_user_id": config.CONNECTOR_USER}, "allowed_integrations": [config.NANGO_GOOGLE_KEY],
            "integrations_config_defaults": {config.NANGO_GOOGLE_KEY: {
                "authorization_params": {"prompt": "select_account consent"}}}})
        r.raise_for_status()
        return r.json()["data"]["token"]


async def connection_ids() -> list[str]:
    """All of the user's Google connections, newest first."""
    async with _client() as c:
        # matched on the tag in code: Nango's endUserId filter only sees the legacy end_user field, not session tags
        r = await c.get("/connection")
        r.raise_for_status()
        mine = [x for x in r.json().get("connections", []) if x.get("provider_config_key") == config.NANGO_GOOGLE_KEY
                and (x.get("tags") or {}).get("end_user_id") == config.CONNECTOR_USER]
    return [x["connection_id"] for x in sorted(mine, key=lambda x: x["created"], reverse=True)]


async def account_email() -> str | None:
    """The connected Google account's email (what the Connectors page shows), or None."""
    if (conn := await connection_id()) is None:
        return None
    async with _google(await google_token(conn)) as g:
        r = await g.get("https://www.googleapis.com/drive/v3/about", params={"fields": "user(emailAddress)"})
    return r.json()["user"]["emailAddress"] if r.status_code == 200 else None


async def disconnect() -> int:
    """Revoke Retro's access at Google, then delete the connections in Nango. Returns how many were removed.
    Revoking matters: without it Google remembers the grant and a reconnect skips the account and consent screens."""
    ids = await connection_ids()
    for conn in ids:
        try:
            token = await google_token(conn)
            async with _google(token) as g:
                await g.post("https://oauth2.googleapis.com/revoke", data={"token": token})
        except (NotConnected, httpx.HTTPError):
            pass  # already invalid at Google: deleting it in Nango is all that's left
        async with _client() as c:
            r = await c.delete(f"/connection/{conn}", params={"provider_config_key": config.NANGO_GOOGLE_KEY})
            if r.status_code not in (200, 204, 404):
                r.raise_for_status()
    return len(ids)


async def connection_id() -> str | None:
    """The user's newest Google connection, if they have connected one."""
    async with _client() as c:
        # matched on the tag in code: Nango's endUserId filter only sees the legacy end_user field, not session tags
        r = await c.get("/connection")
        r.raise_for_status()
        mine = [x for x in r.json().get("connections", []) if x.get("provider_config_key") == config.NANGO_GOOGLE_KEY
                and (x.get("tags") or {}).get("end_user_id") == config.CONNECTOR_USER and not x.get("errors")]
    return max(mine, key=lambda x: x["created"])["connection_id"] if mine else None


def report_html(report_md: str) -> str:
    """The report as HTML for Google's Docs import (headings, lists, links and tables survive the conversion)."""
    return "<html><body>" + markdown.markdown(report_md, extensions=["tables"]) + "</body></html>"


def _google(token: str) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=60, headers={"Authorization": f"Bearer {token}"})


async def google_token(conn: str) -> str:
    """A current Google access token for the connection; Nango refreshes it when it has expired. Used for one
    request and never stored: Nango's proxy can't carry a file upload (it drops non-JSON bodies)."""
    async with _client() as c:
        r = await c.get(f"/connection/{conn}", params={"provider_config_key": config.NANGO_GOOGLE_KEY})
        if r.status_code in (400, 404):
            raise NotConnected("the Google connection is gone; connect your account again")
        r.raise_for_status()
        token = (r.json().get("credentials") or {}).get("access_token")
    if not token:
        raise NotConnected("the Google connection has no valid token; connect your account again")
    return token


async def create_google_doc(title: str, report_md: str) -> dict:
    """Upload the report to the user's Drive as a Google Doc (HTML, converted by Drive). Returns {id, url}."""
    if (conn := await connection_id()) is None:
        raise NotConnected("connect your Google account first")
    boundary = f"retro-{uuid.uuid4().hex}"
    meta = json.dumps({"name": title, "mimeType": "application/vnd.google-apps.document"})
    body = (f"--{boundary}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n"
            f"--{boundary}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n{report_html(report_md)}\r\n--{boundary}--").encode()
    async with _google(await google_token(conn)) as g:
        r = await g.post("https://www.googleapis.com/upload/drive/v3/files",
                         params={"uploadType": "multipart", "fields": "id,webViewLink"},
                         content=body, headers={"Content-Type": f"multipart/related; boundary={boundary}"})
        if r.status_code in (401, 403):
            raise NotConnected(f"Google refused the upload ({r.status_code}); connect your account again")
        r.raise_for_status()
        doc = r.json()
    return {"id": doc["id"], "url": doc.get("webViewLink") or f"https://docs.google.com/document/d/{doc['id']}/edit"}
