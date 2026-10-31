from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pymongo.asynchronous.database import AsyncDatabase
from redis.asyncio import Redis

import config
from app.deps import get_db, get_prefix, get_redis
from app.models.api import Connector, ConnectorStatus, ConnectSession, DocCreated, GoogleClientSet, GoogleSessionCreate
from app.services import google, state

router = APIRouter(tags=["connectors"])
# shortcut: the API has no auth yet, so anyone who can reach it could export to the connected Drive; add auth before
# exposing the API beyond localhost


def _upstream(e: Exception) -> HTTPException:
    if isinstance(e, google.NotConfigured):
        return HTTPException(409, str(e))
    if isinstance(e, google.NotConnected):
        return HTTPException(409, str(e))
    if isinstance(e, httpx.HTTPStatusError):
        return HTTPException(502, f"Google Docs export failed (HTTP {e.response.status_code}); try again")
    return HTTPException(502, "Couldn't reach Google; check this computer's internet connection and try again")


async def _google(db: AsyncDatabase) -> Connector:
    acct = await google.account(db)
    return Connector(id="google", name="Google Docs", configured=await google.client(db) is not None,
                     connected=acct is not None, account=acct.get("email") if acct else None,
                     redirect_uri=google.redirect_uri(),
                     description="Open any report as a Google Doc in your Drive. Retro can only see the docs it creates.")


@router.get("/connectors", response_model=list[Connector])
async def list_connectors(db: AsyncDatabase = Depends(get_db)):
    """Every connector with its status; the Connectors page lists these. Never fails on a missing setup."""
    return [await _google(db)]


@router.get("/connectors/google", response_model=ConnectorStatus)
async def google_status(db: AsyncDatabase = Depends(get_db)):
    g = await _google(db)
    return ConnectorStatus(configured=g.configured, connected=g.connected)


@router.put("/connectors/google/client", response_model=Connector)
async def set_google_client(body: GoogleClientSet, db: AsyncDatabase = Depends(get_db)):
    """Use the user's own Google app (OAuth client). Replacing it disconnects the account, whose token was the old app's."""
    try:
        await google.save_client(db, body.client_id.strip(), body.client_secret.get_secret_value().strip())
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return await _google(db)


@router.post("/connectors/google/session", response_model=ConnectSession)
async def google_session(body: GoogleSessionCreate, db: AsyncDatabase = Depends(get_db),
                         redis: Redis = Depends(get_redis), prefix: str = Depends(get_prefix)):
    """Google's sign-in URL for the browser to open. Google sends it back to /connectors/google/callback."""
    try:
        return ConnectSession(url=await google.start(db, redis, prefix, body.return_to))
    except google.NotConfigured as e:
        raise _upstream(e) from e


@router.get("/connectors/google/callback", include_in_schema=False)
async def google_callback(state: str = "", code: str = "", error: str = "", db: AsyncDatabase = Depends(get_db),
                          redis: Redis = Depends(get_redis), prefix: str = Depends(get_prefix)):
    """Where Google returns after sign-in; sends the browser back to the page it came from with the outcome."""
    web = config.WEB_ORIGINS[0].rstrip("/")
    if error or not (state and code):
        msg = "Sign-in was canceled" if error == "access_denied" else f"Google sign-in failed: {error or 'no code returned'}"
        return RedirectResponse(f"{web}/connectors?google_error={quote(msg)}", 303)
    try:
        back = await google.finish(db, redis, prefix, state, code)
    except (google.NotConfigured, google.NotConnected) as e:
        return RedirectResponse(f"{web}/connectors?google_error={quote(str(e))}", 303)
    except httpx.HTTPError:
        return RedirectResponse(f"{web}/connectors?google_error={quote('Could not reach Google; try again')}", 303)
    return RedirectResponse(f"{web}{back}{'&' if '?' in back else '?'}google=connected", 303)


@router.delete("/connectors/google", status_code=204)
async def disconnect_google(db: AsyncDatabase = Depends(get_db)):
    """Revoke Retro's Google access and forget the account; the next connect asks which account to use."""
    await google.disconnect(db)
    return Response(status_code=204)


@router.post("/workflows/{run_id}/google-doc", response_model=DocCreated)
async def export_google_doc(run_id: str, db: AsyncDatabase = Depends(get_db)):
    """Create a Google Doc in the connected account from the run's latest report."""
    run = await state.get_run(db, run_id)
    if run is None:
        raise HTTPException(404, "workflow run not found")
    rev = next((r for r in reversed(run.revisions) if r.critique and r.critique.passed), None) or (run.revisions or [None])[-1]
    if rev is None:
        raise HTTPException(409, "this run has no report yet")
    title = next((line[2:].strip() for line in rev.report_md.splitlines() if line.startswith("# ")), run.request[:80])
    try:
        return DocCreated(**await google.create_google_doc(db, title, rev.report_md))
    except (google.NotConfigured, google.NotConnected, httpx.HTTPError) as e:
        raise _upstream(e) from e
