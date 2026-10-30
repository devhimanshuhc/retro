import httpx
from fastapi import APIRouter, Depends, HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from app.deps import get_db
from app.models.api import Connector, ConnectorStatus, ConnectSession, DocCreated
from app.services import nango, state

router = APIRouter(tags=["connectors"])
# shortcut: the API has no auth yet, so anyone who can reach it could export to the connected Drive; add auth before
# exposing the API beyond localhost


def _upstream(e: Exception) -> HTTPException:
    if isinstance(e, nango.NotConfigured):
        return HTTPException(503, str(e))
    if isinstance(e, nango.NotConnected):
        return HTTPException(409, str(e))
    status = f" (HTTP {e.response.status_code})" if isinstance(e, httpx.HTTPStatusError) else ""
    return HTTPException(502, f"Google Docs export failed{status}; try again")


@router.get("/connectors", response_model=list[Connector])
async def list_connectors():
    """Every connector with its status; the Connectors page lists these."""
    google = Connector(id="google", name="Google Docs", configured=False, connected=False,
                       description="Open any report as a Google Doc in your Drive. Retro can only see the docs it creates.")
    try:
        email = await nango.account_email()
        google = google.model_copy(update={"configured": True, "connected": email is not None or
                                           await nango.connection_id() is not None, "account": email})
    except nango.NotConfigured:
        pass
    except httpx.HTTPError as e:
        raise _upstream(e) from e
    return [google]


@router.delete("/connectors/google", status_code=204)
async def disconnect_google():
    """Revoke Retro's Google access and forget the connection; the next connect asks which account to use."""
    try:
        await nango.disconnect()
    except (nango.NotConfigured, httpx.HTTPError) as e:
        raise _upstream(e) from e


@router.get("/connectors/google", response_model=ConnectorStatus)
async def google_status():
    try:
        return ConnectorStatus(configured=True, connected=await nango.connection_id() is not None)
    except nango.NotConfigured:
        return ConnectorStatus(configured=False, connected=False)
    except httpx.HTTPError as e:
        raise _upstream(e) from e


@router.post("/connectors/google/session", response_model=ConnectSession)
async def google_session():
    """A token for the browser to open Nango's Connect UI and sign in to Google."""
    try:
        return ConnectSession(token=await nango.session_token())
    except (nango.NotConfigured, httpx.HTTPError) as e:
        raise _upstream(e) from e


@router.post("/workflows/{run_id}/google-doc", response_model=DocCreated)
async def export_google_doc(run_id: str, db: AsyncDatabase = Depends(get_db)):
    """Create a Google Doc in the connected account from the run's latest report."""
    run = await state.get_run(db, run_id)
    if run is None:
        raise HTTPException(404, "workflow run not found")
    rev = next((r for r in reversed(run.revisions) if r.critique and r.critique.passed), None) or (run.revisions or [None])[-1]
    if rev is None:
        raise HTTPException(409, "this run has no report yet")
    title = next((line[2:].strip() for line in rev.report_md.splitlines() if line.startswith("# ")), run.prompt[:80])
    try:
        return DocCreated(**await nango.create_google_doc(title, rev.report_md))
    except (nango.NotConfigured, nango.NotConnected, httpx.HTTPError) as e:
        raise _upstream(e) from e
