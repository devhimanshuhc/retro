from fastapi import APIRouter, Depends, Query
from pymongo.asynchronous.database import AsyncDatabase

from app.deps import get_db
from app.models.api import ArtifactSummary
from app.services import state

router = APIRouter(prefix="/artifacts", tags=["artifacts"])


@router.get("", response_model=list[ArtifactSummary])
async def list_artifacts(limit: int = Query(100, ge=1, le=500), db: AsyncDatabase = Depends(get_db)):
    """Finished reports, newest change first. Open one with GET /workflows/{run_id}."""
    return await state.list_artifacts(db, limit)
