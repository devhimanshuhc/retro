"""Google Docs export with Retro's own Google sign-in, against a fake Google (no network, no Google account)."""
import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from app.models.run import Revision
from app.services import google, state

DOC = "# Nvidia Q2\n\n## Revenue\nRevenue was **$96.2 billion** [1].\n\n## Sources\n1. [SEC](https://www.sec.gov/x)\n"
CLIENT = {"client_id": "123-abc.apps.googleusercontent.com", "client_secret": "GOCSPX-shh"}


def id_token(email: str) -> str:
    part = base64.urlsafe_b64encode(json.dumps({"email": email}).encode()).rstrip(b"=").decode()
    return f"h.{part}.sig"


@pytest.fixture
def fake_google(monkeypatch):
    """Serves Google's token, revoke and Drive upload endpoints; records every request."""
    seen, g = [], {"scope": "openid email https://www.googleapis.com/auth/drive.file", "refresh": "ok"}

    def serve(req: httpx.Request):
        seen.append(req)
        form = parse_qs(req.content.decode()) if req.method == "POST" else {}
        if req.url.path == "/token" and form["grant_type"] == ["authorization_code"]:
            return httpx.Response(200, json={"access_token": "a1", "refresh_token": f"r-{form['code'][0]}",
                                             "scope": g["scope"], "id_token": id_token("me@gmail.com")})
        if req.url.path == "/token":
            if g["refresh"] != "ok":
                return httpx.Response(400, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"access_token": "fresh-token", "expires_in": 3599})
        if req.url.path == "/revoke":
            return httpx.Response(200)
        if req.url.path == "/upload/drive/v3/files":
            return httpx.Response(200, json={"id": "doc1", "webViewLink": "https://docs.google.com/document/d/doc1/edit"})
        return httpx.Response(404)

    monkeypatch.setattr(google, "_http", lambda: httpx.AsyncClient(transport=httpx.MockTransport(serve)))
    monkeypatch.setattr(google.config, "GOOGLE_CLIENT_ID", "")
    return seen, g


async def sign_in(api, return_to="/connectors", code="c1"):
    url = (await api.post("/connectors/google/session", json={"return_to": return_to})).json()["url"]
    st = parse_qs(urlparse(url).query)["state"][0]
    return await api.get(f"/connectors/google/callback?state={st}&code={code}"), url, st


async def test_without_a_google_app_it_shows_setup_not_an_error(api, fake_google):
    [g] = (await api.get("/connectors")).json()
    assert (g["configured"], g["connected"]) == (False, False)
    assert g["redirect_uri"] == "http://localhost:8000/connectors/google/callback"
    r = await api.post("/connectors/google/session", json={})
    assert r.status_code == 409 and "Set up" in r.json()["detail"]


async def test_client_is_checked_and_its_secret_never_returned(api, fake_google):
    r = await api.put("/connectors/google/client", json={"client_id": "nope", "client_secret": "x"})
    assert r.status_code == 400 and "googleusercontent" in r.json()["detail"]
    r = await api.put("/connectors/google/client", json=CLIENT)
    assert r.status_code == 200 and r.json()["configured"] is True and "GOCSPX" not in r.text


async def test_sign_in_uses_pkce_and_comes_back_connected(api, db, fake_google):
    seen, _ = fake_google
    await api.put("/connectors/google/client", json=CLIENT)
    r, url, st = await sign_in(api, "/runs/abc")
    q = parse_qs(urlparse(url).query)
    assert q["client_id"] == [CLIENT["client_id"]] and q["code_challenge_method"] == ["S256"]
    assert "drive.file" in q["scope"][0] and q["access_type"] == ["offline"]
    assert q["redirect_uri"] == ["http://localhost:8000/connectors/google/callback"]
    assert r.status_code == 303 and r.headers["location"] == "http://localhost:3000/runs/abc?google=connected"
    token_req = parse_qs(seen[-1].content.decode())
    assert token_req["code_verifier"][0] and token_req["client_secret"] == ["GOCSPX-shh"]
    [g] = (await api.get("/connectors")).json()
    assert (g["connected"], g["account"]) == (True, "me@gmail.com")
    again = await api.get(f"/connectors/google/callback?state={st}&code=c1")  # a state works once
    assert "google_error" in again.headers["location"]


async def test_sign_in_without_drive_permission_or_canceled_is_explained(api, fake_google):
    _, g = fake_google
    await api.put("/connectors/google/client", json=CLIENT)
    g["scope"] = "openid email"
    r, _, _ = await sign_in(api)
    assert "google_error=" in r.headers["location"] and "permission" in r.headers["location"]
    r = await api.get("/connectors/google/callback?error=access_denied&state=x")
    assert "canceled" in r.headers["location"]
    [c] = (await api.get("/connectors")).json()
    assert c["connected"] is False


async def test_export_refreshes_a_token_and_uploads_a_doc(api, db, fake_google):
    seen, _ = fake_google
    await api.put("/connectors/google/client", json=CLIENT)
    run = await state.create_run(db, "p")
    assert (await api.post(f"/workflows/{run.id}/google-doc")).status_code == 409  # no report yet
    await state.update_run(db, run.id, revisions=[Revision(revision=0, report_md=DOC)])
    r = await api.post(f"/workflows/{run.id}/google-doc")
    assert r.status_code == 409 and "Connect" in r.json()["detail"]  # not connected
    await sign_in(api)
    r = await api.post(f"/workflows/{run.id}/google-doc")
    assert r.status_code == 200 and r.json()["url"].startswith("https://docs.google.com/")
    up = seen[-1]
    assert up.headers["authorization"] == "Bearer fresh-token" and up.url.params["uploadType"] == "multipart"
    body = up.content.decode()
    assert '"mimeType": "application/vnd.google-apps.document"' in body and "<strong>$96.2 billion</strong>" in body
    assert (await api.post("/workflows/nope/google-doc")).status_code == 404


async def test_revoked_access_disconnects_with_a_clear_message(api, db, fake_google):
    _, g = fake_google
    await api.put("/connectors/google/client", json=CLIENT)
    await sign_in(api)
    run = await state.create_run(db, "p")
    await state.update_run(db, run.id, revisions=[Revision(revision=0, report_md=DOC)])
    g["refresh"] = "revoked"
    r = await api.post(f"/workflows/{run.id}/google-doc")
    assert r.status_code == 409 and "connect your account again" in r.json()["detail"]
    assert (await api.get("/connectors/google")).json() == {"configured": True, "connected": False}


async def test_disconnect_and_new_app_revoke_the_old_token(api, fake_google):
    seen, _ = fake_google
    await api.put("/connectors/google/client", json=CLIENT)
    await sign_in(api, code="first")
    assert (await api.delete("/connectors/google")).status_code == 204
    assert parse_qs(seen[-1].content.decode())["token"] == ["r-first"]
    await sign_in(api, code="second")
    await api.put("/connectors/google/client", json={**CLIENT, "client_id": "456-x.apps.googleusercontent.com"})
    assert parse_qs(seen[-1].content.decode())["token"] == ["r-second"]  # the old app's token is revoked
    [c] = (await api.get("/connectors")).json()
    assert (c["configured"], c["connected"]) == (True, False)


async def test_retros_own_google_app_needs_no_setup(api, fake_google, monkeypatch):
    monkeypatch.setattr(google.config, "GOOGLE_CLIENT_ID", "999-retro.apps.googleusercontent.com")
    [c] = (await api.get("/connectors")).json()
    assert c["configured"] is True
    r, url, _ = await sign_in(api)
    assert "999-retro" in url and r.headers["location"].endswith("google=connected")
