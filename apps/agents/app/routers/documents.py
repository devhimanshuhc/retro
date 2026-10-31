from fastapi import APIRouter, Depends, HTTPException, Response, UploadFile
from pymongo.asynchronous.database import AsyncDatabase

from app.deps import get_db
from app.models.api import DocumentInfo
from app.services import documents

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("", status_code=201, response_model=DocumentInfo, response_model_by_alias=False)
async def upload_document(file: UploadFile, db: AsyncDatabase = Depends(get_db)):
    """Upload a file for runs to research. 400 when it has no readable text, 413 when over 20 MB."""
    body = await file.read(documents.MAX_BYTES + 1)
    if len(body) > documents.MAX_BYTES:
        raise HTTPException(413, f"Files can be up to {documents.MAX_BYTES // 1_000_000} MB")
    try:
        return await documents.save(db, file.filename or "file.txt", body)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("", response_model=list[DocumentInfo], response_model_by_alias=False)
async def list_documents(db: AsyncDatabase = Depends(get_db)):
    return await documents.list_all(db)


@router.delete("/{doc_id}", status_code=204)
async def delete_document(doc_id: str, db: AsyncDatabase = Depends(get_db)):
    """Reports that already cite the file keep their quotes."""
    if not await documents.remove(db, doc_id):
        raise HTTPException(404, "file not found")
    return Response(status_code=204)
