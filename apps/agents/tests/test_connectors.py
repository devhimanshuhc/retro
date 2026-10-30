"""Google Docs export through Nango, against a fake Nango server (no network, no Google account)."""
import json

import httpx
import pytest

from app.models.run import Revision
from app.services import nango, state

DOC = "# Nvidia Q2\n\n## Revenue\nRevenue was **$96.2 billion** [1].\n\n## Sources\n1. [SEC](https://www.sec.gov/x)\n"


@pytest.fixture
def fake_nango(monkeypatch):
    """Serves Nango's API: records every request; connections are set per test."""
    seen, state_ = [], {"connections": []}

    def serve(req: httpx.Request):
        seen.append(req)
        if req.url.path == "/connect/sessions":
            return httpx.Response(201, json={"data": {"token": "tok-123", "expires_at": "x"}})
        if req.url.path == "/connection":
            return httpx.Response(200, json={"connections": state_["connections"]})
        if req.method == "GET" and req.url.path.startswith("/connection/"):
            return httpx.Response(200, json={"credentials": {"access_token": "google-token"}})
        if req.method == "DELETE" and req.url.path.startswith("/connection/"):
            state_["connections"] = [c for c in state_["connections"] if c["connection_id"] != req.url.path.split("/")[-1]]
            return httpx.Response(204)
        if req.url.host == "oauth2.googleapis.com":
            return httpx.Response(200)
        if req.url.path == "/drive/v3/about":
            return httpx.Response(200, json={"user": {"emailAddress": "me@gmail.com"}})
        if req.url.host == "www.googleapis.com" and req.url.path == "/upload/drive/v3/files":
            return httpx.Response(200, json={"id": "doc1", "webViewLink": "https://docs.google.com/document/d/doc1/edit"})
        return httpx.Response(404)

    monkeypatch.setattr(nango.config, "NANGO_SECRET_KEY", "secret")
    monkeypatch.setattr(nango, "_client", lambda: httpx.AsyncClient(base_url="http://nango", transport=httpx.MockTransport(serve),
                                                                    headers={"Authorization": "Bearer secret"}))
    monkeypatch.setattr(nango, "_google", lambda token: httpx.AsyncClient(transport=httpx.MockTransport(serve),
                                                                          headers={"Authorization": f"Bearer {token}"}))
    return seen, state_


def conn(cid, created, key="google-drive", errors=(), user="retro-owner"):
    return {"connection_id": cid, "provider_config_key": key, "created": created, "errors": list(errors),
            "tags": {"end_user_id": user}}


async def test_session_token_is_for_the_owner_and_only_google(fake_nango):
    seen, _ = fake_nango
    assert await nango.session_token() == "tok-123"
    body = json.loads(seen[0].content)
    assert body["tags"] == {"end_user_id": "retro-owner"} and body["allowed_integrations"] == ["google-drive"]
    # Google must show the account chooser and consent every time, so a reconnect can pick another account
    assert body["integrations_config_defaults"]["google-drive"]["authorization_params"]["prompt"] == "select_account consent"


async def test_connection_is_the_newest_healthy_google_one(fake_nango):
    _, st = fake_nango
    st["connections"] = [conn("old", "2026-01-01"), conn("new", "2026-02-01"), conn("broken", "2026-03-01", errors=[{"type": "auth"}]),
                         conn("slack", "2026-04-01", key="slack"), conn("someone-else", "2026-05-01", user="other")]
    assert await nango.connection_id() == "new"


async def test_doc_is_uploaded_to_drive_with_a_token_from_nango(fake_nango):
    seen, st = fake_nango
    st["connections"] = [conn("c1", "2026-01-01")]
    out = await nango.create_google_doc("Nvidia Q2", DOC)
    assert out == {"id": "doc1", "url": "https://docs.google.com/document/d/doc1/edit"}
    fetched, up = seen[-2], seen[-1]
    assert fetched.url.path == "/connection/c1" and fetched.url.params["provider_config_key"] == "google-drive"
    assert up.headers["authorization"] == "Bearer google-token"  # the token Nango handed out, used once
    assert up.url.params["uploadType"] == "multipart" and up.headers["content-type"].startswith("multipart/related")
    body = up.content.decode()
    assert '"mimeType": "application/vnd.google-apps.document"' in body and "<h1>Nvidia Q2</h1>" in body
    assert "<strong>$96.2 billion</strong>" in body


async def test_not_connected_and_not_configured(fake_nango, monkeypatch):
    with pytest.raises(nango.NotConnected):
        await nango.create_google_doc("t", DOC)
    monkeypatch.undo()  # back to the real _client, which refuses to run without a secret key
    monkeypatch.setattr(nango.config, "NANGO_SECRET_KEY", "")
    with pytest.raises(nango.NotConfigured):
        await nango.session_token()


async def test_export_endpoint(api, db, fake_nango):
    _, st = fake_nango
    run = await state.create_run(db, "p")
    assert (await api.post(f"/workflows/{run.id}/google-doc")).status_code == 409  # no report yet
    await state.update_run(db, run.id, revisions=[Revision(revision=0, report_md=DOC)])
    assert (await api.post(f"/workflows/{run.id}/google-doc")).status_code == 409  # not connected
    st["connections"] = [conn("c1", "2026-01-01")]
    r = await api.post(f"/workflows/{run.id}/google-doc")
    assert r.status_code == 200 and r.json()["url"].startswith("https://docs.google.com/")
    assert (await api.get("/connectors/google")).json() == {"configured": True, "connected": True}
    assert (await api.post("/workflows/nope/google-doc")).status_code == 404


async def test_disconnect_revokes_at_google_and_deletes_every_connection(api, fake_nango):
    seen, st = fake_nango
    st["connections"] = [conn("c1", "2026-01-01"), conn("c2", "2026-02-01"), conn("other", "2026-03-01", user="x")]
    assert (await api.delete("/connectors/google")).status_code == 204
    revoked = [r for r in seen if r.url.host == "oauth2.googleapis.com"]
    assert len(revoked) == 2 and all(b"token=google-token" in r.content for r in revoked)
    assert [c["connection_id"] for c in st["connections"]] == ["other"]  # someone else's connection is untouched
    [g] = (await api.get("/connectors")).json()
    assert (g["id"], g["configured"], g["connected"], g["account"]) == ("google", True, False, None)


async def test_connectors_list_shows_the_connected_account(api, fake_nango):
    _, st = fake_nango
    st["connections"] = [conn("c1", "2026-01-01")]
    [g] = (await api.get("/connectors")).json()
    assert (g["name"], g["connected"], g["account"]) == ("Google Docs", True, "me@gmail.com")
