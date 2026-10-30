from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.models.messages import AgentMessage
from app.services import queues


@pytest.fixture
async def research_q():
    # Real Redis (docker compose), throwaway key prefix per test
    q = queues.open_queue(queues.RESEARCH, prefix=f"test-{uuid4().hex}")
    yield q
    await q.obliterate(force=True)
    await q.close()


async def test_enqueue_adds_job_with_defaults(research_q):
    job = await queues.enqueue(research_q, AgentMessage(workflow_run_id="r1"))
    assert job.id == "r1-research-0"
    stored = await research_q.getJob(job.id)
    assert stored.name == "research"
    assert stored.data == {"workflow_run_id": "r1", "revision": 0}
    assert stored.opts["attempts"] == 3
    assert stored.opts["backoff"] == {"type": "exponential", "delay": 2000}
    assert await research_q.getJobCounts("wait") == {"wait": 1}


async def test_same_run_step_revision_is_deduplicated(research_q):
    msg = AgentMessage(workflow_run_id="r1", revision=2)
    await queues.enqueue(research_q, msg)
    await queues.enqueue(research_q, msg)
    assert await research_q.getJobCounts("wait") == {"wait": 1}


async def test_new_revision_is_a_new_job(research_q):
    await queues.enqueue(research_q, AgentMessage(workflow_run_id="r1", revision=0))
    await queues.enqueue(research_q, AgentMessage(workflow_run_id="r1", revision=1))
    assert await research_q.getJobCounts("wait") == {"wait": 2}


def test_unknown_queue_name_is_rejected():
    with pytest.raises(ValueError):
        queues.open_queue("agent.reserch")


def test_message_carries_ids_only():
    with pytest.raises(ValidationError):
        AgentMessage(workflow_run_id="r1", report="# a big markdown report ...")
    with pytest.raises(ValidationError):
        AgentMessage(workflow_run_id="")
