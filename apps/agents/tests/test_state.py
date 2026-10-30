import asyncio

import pytest
from pydantic import ValidationError

from app.services import state


async def test_create_then_get_roundtrip(db):
    run = await state.create_run(db, "Write a report on Nvidia Q3")
    got = await state.get_run(db, run.id)
    assert got == run
    assert got.status == "submitted"
    assert got.revision == 0
    assert got.created_at.tzinfo is not None


async def test_get_missing_returns_none(db):
    assert await state.get_run(db, "nope") is None


async def test_update_sets_fields_and_bumps_updated_at(db):
    run = await state.create_run(db, "p")
    await asyncio.sleep(0.002)  # timestamps have ms resolution
    updated = await state.update_run(db, run.id, status="working", revision=1)
    assert updated.status == "working"
    assert updated.revision == 1
    assert updated.updated_at > run.updated_at
    assert updated.created_at == run.created_at
    assert await state.get_run(db, run.id) == updated


async def test_update_missing_run_returns_none(db):
    assert await state.update_run(db, "nope", status="working") is None


@pytest.mark.parametrize(
    "fields",
    [{"status": "bogus"}, {"status": None}, {"revision": None}, {"revision": -1}, {"prompt": "rewrite history"}, {"created_at": "2020-01-01"}],
)
async def test_update_rejects_invalid_or_unknown_fields_without_writing(db, fields):
    run = await state.create_run(db, "p")
    with pytest.raises(ValidationError):
        await state.update_run(db, run.id, **fields)
    assert await state.get_run(db, run.id) == run


async def test_create_rejects_empty_prompt(db):
    with pytest.raises(ValidationError):
        await state.create_run(db, "")
    assert await state.runs(db).count_documents({}) == 0


async def test_claim_marks_step_working_and_run_working(db):
    run = await state.create_run(db, "p")
    claimed = await state.claim_step(db, run.id, "research", 0)
    assert claimed.status == "working"
    assert claimed.steps["research"].status == "working"
    assert claimed.steps["research"].revision == 0


async def test_claim_skips_step_already_done_for_revision(db):
    run = await state.create_run(db, "p")
    await state.claim_step(db, run.id, "write", 0)
    await state.finish_step(db, run.id, "write", 0)
    assert await state.claim_step(db, run.id, "write", 0) is None
    assert await state.claim_step(db, run.id, "write", 1) is not None  # a new revision may run


async def test_claim_allows_retaking_a_working_step(db):
    # a crashed attempt leaves the step `working`; the retry must be able to claim it
    run = await state.create_run(db, "p")
    await state.claim_step(db, run.id, "research", 0)
    assert await state.claim_step(db, run.id, "research", 0) is not None


async def test_claim_skips_stale_revision_and_finished_or_missing_runs(db):
    run = await state.create_run(db, "p")
    await state.update_run(db, run.id, revision=2)
    assert await state.claim_step(db, run.id, "write", 1) is None  # older than the run
    await state.update_run(db, run.id, status="canceled")
    assert await state.claim_step(db, run.id, "write", 2) is None  # run is over
    assert await state.claim_step(db, "nope", "write", 0) is None


async def test_finish_marks_done_and_applies_run_updates_together(db):
    run = await state.create_run(db, "p")
    await state.claim_step(db, run.id, "critic", 0)
    done = await state.finish_step(db, run.id, "critic", 0, status="completed")
    assert done.steps["critic"].status == "done"
    assert done.steps["critic"].finished_at is not None
    assert done.status == "completed"


async def test_finish_without_claim_or_wrong_revision_does_nothing(db):
    run = await state.create_run(db, "p")
    assert await state.finish_step(db, run.id, "critic", 0, status="completed") is None
    await state.claim_step(db, run.id, "critic", 1)
    assert await state.finish_step(db, run.id, "critic", 0, status="completed") is None
    assert (await state.get_run(db, run.id)).status == "working"


async def test_finish_step_can_bump_run_revision(db):
    run = await state.create_run(db, "p")
    await state.claim_step(db, run.id, "critic", 0)
    done = await state.finish_step(db, run.id, "critic", 0, revision=1)
    assert done.revision == 1 and done.steps["critic"].revision == 0
