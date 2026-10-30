from fastapi import APIRouter, Depends, HTTPException
from pymongo.asynchronous.database import AsyncDatabase

from app.deps import get_db, get_prefix
from app.models.dead_letter import DeadLetter
from app.services import dlq

router = APIRouter(prefix="/dead-letters", tags=["dead letters"])


@router.get("", response_model=list[DeadLetter], response_model_by_alias=False)
async def list_dead_letters(workflow_run_id: str | None = None, db: AsyncDatabase = Depends(get_db)):
    return await dlq.list_dead_letters(db, workflow_run_id)


@router.get("/{dl_id}", response_model=DeadLetter, response_model_by_alias=False)
async def get_dead_letter(dl_id: str, db: AsyncDatabase = Depends(get_db)):
    if dl := await dlq.get_dead_letter(db, dl_id):
        return dl
    raise HTTPException(404, "dead letter not found")


@router.post("/{dl_id}/replay", status_code=202, response_model=DeadLetter, response_model_by_alias=False)
async def replay(dl_id: str, db: AsyncDatabase = Depends(get_db), prefix: str = Depends(get_prefix)):
    try:
        dl = await dlq.replay(db, dl_id, prefix=prefix)
    except dlq.NotReplayable as e:
        raise HTTPException(409, str(e)) from e
    if dl is None:
        raise HTTPException(404, "dead letter not found")
    return dl
