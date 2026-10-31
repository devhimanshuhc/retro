from bullmq import Job, Queue

import config
from app.models.messages import AgentMessage

ROUTER = "agent.router"
SUPERVISOR = "agent.supervisor"
RESEARCH = "agent.research"
WRITE = "agent.write"
CRITIC = "agent.critic"
DLQ = "agent.dlq"
AGENT_QUEUES = (ROUTER, SUPERVISOR, RESEARCH, WRITE, CRITIC)
ALL_QUEUES = (*AGENT_QUEUES, DLQ)

DEFAULT_JOB_OPTS = {
    "attempts": 3,
    "backoff": {"type": "exponential", "delay": 2000},  # retries after 2s, then 4s
    # Finished jobs are kept for a while so re-enqueueing the same job id stays a no-op.
    # Kept forever they would fill Redis, which is set to noeviction. Past this window the
    # step status in Mongo is the duplicate guard.
    "removeOnComplete": {"age": 24 * 3600},
    "removeOnFail": {"age": 7 * 24 * 3600},
}


def open_queue(name: str, url: str = config.REDIS_URL, prefix: str = "bull") -> Queue:
    if name not in ALL_QUEUES:
        raise ValueError(f"unknown queue {name!r}; expected one of {ALL_QUEUES}")
    return Queue(name, {"connection": url, "prefix": prefix})


def step_of(queue: Queue) -> str:
    return queue.name.removeprefix("agent.")


def job_id(run_id: str, step: str, revision: int) -> str:
    # '-' not ':' because Node BullMQ rejects ':' in custom ids
    return f"{run_id}-{step}-{revision}"


async def enqueue(queue: Queue, message: AgentMessage) -> Job:
    """Send a message to an actor's mailbox. The same run/step/revision enqueued twice gives one job."""
    step = step_of(queue)
    jid = job_id(message.workflow_run_id, step, message.revision)
    return await queue.add(step, message.model_dump(), {**DEFAULT_JOB_OPTS, "jobId": jid})
