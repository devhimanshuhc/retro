"""The user's own files (Mongo `documents`): text is pulled out once on upload, then research reads it like a fetched
page. The file itself isn't kept, only its text."""
import asyncio
from contextvars import ContextVar
from pathlib import PurePath
from uuid import uuid4

from pymongo.asynchronous.database import AsyncDatabase

from app.models.run import now
from app.services import sources

MAX_BYTES = 20_000_000
MAX_CHARS = 2_000_000  # ~500k tokens of text; only the best passages ever reach the model
MAX_PAGES = 400
TYPES = {".pdf": "pdf", ".html": "html", ".htm": "html",
         ".txt": "text", ".md": "text", ".markdown": "text", ".csv": "text", ".json": "text"}
SCHEME = "doc://"  # a file's Source.url: doc://<id>

# the Actor's db for this job, so research can read files without handlers taking a db argument
store: ContextVar[AsyncDatabase | None] = ContextVar("documents_store", default=None)


def collection(db: AsyncDatabase):
    return db["documents"]


def extract(name: str, body: bytes) -> str:
    """The file's text, or ValueError with why it can't be used."""
    kind = TYPES.get(PurePath(name).suffix.lower())
    if kind is None:
        raise ValueError("Use a PDF, text, Markdown, HTML, CSV or JSON file")
    try:
        if kind == "pdf":
            text = sources.page_text(body, "application/pdf", pages=MAX_PAGES)
        elif kind == "html":
            text = sources.page_text(body, "text/html")
        else:
            text = body.decode("utf-8", errors="replace")
    except Exception as e:  # corrupt or encrypted PDF
        raise ValueError(f"Couldn't read this file ({type(e).__name__})") from e
    text = text.strip()
    if len(text) < 80:
        raise ValueError("No readable text in this file (a scanned PDF needs OCR first)")
    return text[:MAX_CHARS]


async def save(db: AsyncDatabase, name: str, body: bytes) -> dict:
    text = await asyncio.to_thread(extract, name, body)  # big PDFs take seconds: keep the event loop free
    doc = {"_id": uuid4().hex, "name": name[:200], "size": len(body), "chars": len(text), "text": text,
           "created_at": now()}
    await collection(db).insert_one(doc)
    return doc


async def list_all(db: AsyncDatabase) -> list[dict]:
    return await collection(db).find({}, {"text": 0}).sort("created_at", -1).to_list(500)


async def load(db: AsyncDatabase, ids: list[str]) -> list[dict]:
    """The files with these ids that still exist, text included, in the given order."""
    if not ids:
        return []
    found = {d["_id"]: d for d in await collection(db).find({"_id": {"$in": ids}}).to_list(len(ids))}
    return [found[i] for i in ids if i in found]


async def missing(db: AsyncDatabase, ids: list[str]) -> list[str]:
    if not ids:
        return []
    have = {d["_id"] for d in await collection(db).find({"_id": {"$in": ids}}, {"_id": 1}).to_list(len(ids))}
    return [i for i in ids if i not in have]


async def remove(db: AsyncDatabase, doc_id: str) -> bool:
    return (await collection(db).delete_one({"_id": doc_id})).deleted_count == 1
