import pytest
from bullmq import UnrecoverableError

from app.agents import research, writer
from app.models.messages import AgentMessage
from app.services import documents, llm, sources, state
from tests.fakes import fake_fetch, fake_llm
from tests.test_api import cleanup_queues  # noqa: F401  (fixture)
from tests.test_handlers import run_at

NOTES = ("Our internal review found that churn fell to 3.1% in the third quarter after the pricing change. "
         "Revenue per customer rose to $412, the highest the company has recorded since the product launched.")


def test_extract_reads_text_and_rejects_what_it_cant_use():
    assert documents.extract("notes.md", NOTES.encode()) == NOTES
    assert "churn" in documents.extract("page.html", f"<html><script>x()</script><p>{NOTES}</p></html>".encode())
    with pytest.raises(ValueError, match="Use a PDF"):
        documents.extract("photo.png", b"\x89PNG")
    with pytest.raises(ValueError, match="No readable text"):
        documents.extract("empty.txt", b"  hi  ")
    with pytest.raises(ValueError, match="Couldn't read"):
        documents.extract("broken.pdf", b"%PDF-not really")


async def test_upload_list_delete_and_attach_to_a_run(api, db, cleanup_queues):  # noqa: F811
    r = await api.post("/documents", files={"file": ("notes.md", NOTES.encode(), "text/markdown")})
    assert r.status_code == 201
    doc = r.json()
    assert doc["name"] == "notes.md" and doc["chars"] == len(NOTES) and "text" not in doc
    assert [d["id"] for d in (await api.get("/documents")).json()] == [doc["id"]]

    r = await api.post("/workflows", json={"prompt": "Churn?", "document_ids": [doc["id"]], "web": False})
    assert r.status_code == 202
    run = await state.get_run(db, r.json()["workflow_run_id"])
    assert run.document_ids == [doc["id"]] and run.web is False

    assert (await api.delete(f"/documents/{doc['id']}")).status_code == 204
    assert (await api.delete(f"/documents/{doc['id']}")).status_code == 404
    r = await api.post("/workflows", json={"prompt": "Churn?", "document_ids": [doc["id"]]})
    assert r.status_code == 400 and "no longer exist" in r.json()["detail"]


async def test_upload_and_run_rejections(api):
    r = await api.post("/documents", files={"file": ("x.exe", b"MZ" * 100, "application/octet-stream")})
    assert r.status_code == 400
    r = await api.post("/workflows", json={"prompt": "p", "web": False})
    assert r.status_code == 400 and "Attach a file" in r.json()["detail"]


@pytest.fixture
async def files_only(db, monkeypatch):
    calls = []
    monkeypatch.setattr(llm, "complete", fake_llm(calls))
    monkeypatch.setattr(sources, "fetch", fake_fetch)
    doc = await documents.save(db, "review.md", NOTES.encode())
    token = documents.store.set(db)
    yield calls, doc
    documents.store.reset(token)


async def test_research_reads_files_only_without_searching(files_only, monkeypatch):
    calls, doc = files_only
    monkeypatch.setattr(research, "write_findings", None)  # replaced below; keeps the test about what research reads
    seen = {}

    async def write(brief, objectives, passages, blocks):
        seen["blocks"] = blocks
        c, p = passages["d.1"]
        from app.models.run import Finding, Source
        return [Finding(objective_id="o1", summary="Churn fell to 3.1%.",
                        sources=[Source(url=c.url, title=c.title, kind=c.kind, quote=p)])], llm.Completion("", {}, {"input_tokens": 1, "output_tokens": 1})
    monkeypatch.setattr(research, "write_findings", write)
    out = await research.handle(run_at("research", document_ids=[doc["_id"]], web=False), AgentMessage(workflow_run_id="r"))
    assert not calls  # no web search, no OpenAlex search through the model
    [src] = out.run_updates["findings"][0].sources
    assert (src.url, src.kind, src.title) == (f"doc://{doc['_id']}", "file", "review.md")
    assert "churn fell to 3.1%" in src.quote.lower() and any("review.md" in b for b in seen["blocks"])


async def test_files_only_research_with_nothing_relevant_fails_without_retry(db, files_only):
    _, doc = files_only
    await documents.collection(db).update_one({"_id": doc["_id"]}, {"$set": {"text": "zzz " * 50}})
    with pytest.raises(UnrecoverableError, match="don't answer"):
        await research.handle(run_at("research", document_ids=[doc["_id"]], web=False), AgentMessage(workflow_run_id="r"))


def test_writer_lists_files_without_a_link():
    from app.models.run import Finding, Source
    run = run_at("write", findings=[Finding(objective_id="o1", summary="s", sources=[
        Source(url="doc://abc", title="review.md", kind="file", quote=NOTES[:100])])])
    assert "review.md" in writer.build_prompt(run, 0)
