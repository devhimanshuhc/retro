import asyncio
import logging
import os
import signal
import socket
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from uuid import uuid4

from bullmq import Queue, UnrecoverableError, Worker
from pydantic import ValidationError
from pymongo.asynchronous.database import AsyncDatabase

import config
from app.models.api import WorkerInfo
from app.models.events import Event
from app.models.messages import AgentMessage
from app.models.run import TERMINAL, NextHop, Usage, WorkflowRun, now
from app.services import api_keys, dlq, events, llm, progress, queues, state, workers


@dataclass
class Outcome:
    """What a handler decided. With no next_queue, the pipeline ends at this step."""

    next_queue: str | None = None
    next_revision: int | None = None  # defaults to the incoming message's revision
    run_updates: dict = field(default_factory=dict)  # written together with marking the step done
    usage: Usage | None = None  # tokens this step used; added to run.usage[step]


def worker_url(redis_url: str) -> str:
    # redis-py 8 defaults socket_timeout to 5s, but BullMQ blocks for 5-10s waiting for jobs: the read times out,
    # BullMQ takes it for a dropped connection and silently sleeps 15s, so new jobs wait up to ~20s for pickup.
    return f"{redis_url}{'&' if '?' in redis_url else '?'}socket_timeout=30"


Handler = Callable[[WorkflowRun, AgentMessage], Awaitable[Outcome]]


class Actor:
    """One agent: consumes its own queue, runs the handler, sends the next message. Holds no state of its own."""

    def __init__(self, queue_name: str, handler: Handler, db: AsyncDatabase,
                 redis_url: str = config.REDIS_URL, prefix: str = "bull", lock_ms: int = 30_000):
        self.queue_name = queue_name
        self.step = queue_name.removeprefix("agent.")
        self.handler = handler
        self.db = db
        self.redis_url = redis_url
        self.prefix = prefix
        self.lock_ms = lock_ms  # a killed worker's job is taken back once its lock expires (BullMQ stalled check)
        self._bg: set[asyncio.Task] = set()
        self.log = logging.getLogger(queue_name)
        self._out: dict[str, Queue] = {}
        host, t = socket.gethostname(), now()
        self.id = f"{self.step}-{host}-{os.getpid()}-{uuid4().hex[:4]}"
        self.info = WorkerInfo(id=self.id, agent=self.step, host=host, pid=os.getpid(), started_at=t, since=t, last_seen=t)

    def _queue(self, name: str) -> Queue:
        if name not in self._out:
            self._out[name] = queues.open_queue(name, self.redis_url, self.prefix)
        return self._out[name]

    @property
    def _redis(self):
        return self._queue(self.queue_name).client  # reuses the Redis connection of this agent's own queue

    async def _emit(self, type_: str, run_id: str, agent: bool = True, **data) -> None:
        await events.emit(self.db, self._redis,
                          Event(type=type_, workflow_run_id=run_id, agent=self.step if agent else None, data=data))

    async def _presence(self, **changes) -> None:
        """Update and publish this worker's heartbeat (what it's doing now). Best effort."""
        t = now()
        if "state" in changes:
            changes["since"] = t
        self.info = self.info.model_copy(update={**changes, "last_seen": t})
        try:
            await workers.beat(self._redis, self.prefix, self.info)
        except Exception as e:
            self.log.warning("heartbeat failed: %r", e)

    async def _heartbeat(self, stop: asyncio.Event) -> None:
        while not stop.is_set():
            await self._presence()
            try:
                await asyncio.wait_for(stop.wait(), workers.HEARTBEAT_S)
            except TimeoutError:
                pass

    async def process(self, data: dict) -> str:
        try:
            msg = AgentMessage.model_validate(data)
        except ValidationError as e:
            raise UnrecoverableError(f"bad message: {e}") from e  # retrying can't fix a malformed message

        run = await state.claim_step(self.db, msg.workflow_run_id, self.step, msg.revision)
        if run is None:
            await self._resend(msg)
            self.log.info("skip run=%s rev=%s (duplicate, stale, or run finished)", msg.workflow_run_id, msg.revision)
            return "skipped"

        self.log.info("start run=%s rev=%s", run.id, msg.revision)
        await self._emit("step.started", run.id, revision=msg.revision)
        await self._presence(state="busy", run_id=run.id, revision=msg.revision, activity="started")

        async def on_progress(phase: str, detail: str, data: dict) -> None:
            await self._emit("step.progress", run.id, revision=msg.revision, phase=phase, detail=detail, **data)
            await self._presence(activity=detail)

        creds = llm.credentials.set(await api_keys.credentials(self.db))  # per job: a new key needs no restart
        sink = progress.sink.set(on_progress)
        try:
            used = run.tokens_used()
            # the budget stops extra rewrites, never the first report: research already paid for it
            first_report = (self.step == "write" and not run.revisions) or (
                self.step == "critic" and len(run.revisions) == 1 and run.revisions[0].critique is None)
            over = used >= config.RUN_TOKEN_BUDGET and not first_report
            outcome = self._over_budget(run, used) if over else await self.handler(run, msg)
        except llm.RateLimited as e:
            # Pause every worker of this agent together, not just this one; the raise makes BullMQ retry the job.
            ms = e.retry_after_ms or config.RATE_LIMIT_PAUSE_MS
            await self._queue(self.queue_name).rateLimit(ms)
            self.log.warning("rate limited run=%s: pausing %s for %sms", run.id, self.queue_name, ms)
            await self._emit("rate_limited", run.id, pause_ms=ms)
            raise
        finally:
            progress.sink.reset(sink)
            llm.credentials.reset(creds)
        hop = None
        if outcome.next_queue:
            hop = NextHop(queue=outcome.next_queue,
                          revision=msg.revision if outcome.next_revision is None else outcome.next_revision)
        updates = dict(outcome.run_updates)
        if outcome.usage:
            prev = run.usage.get(self.step, Usage())
            updates["usage"] = {**run.usage, self.step: Usage(input_tokens=prev.input_tokens + outcome.usage.input_tokens,
                                                               output_tokens=prev.output_tokens + outcome.usage.output_tokens)}
        # Outbox: save outputs + done + next hop in one write, then send. Sending first could let the next
        # actor read the run before our outputs exist; a crash after this write is healed by _resend.
        if await state.finish_step(self.db, run.id, self.step, msg.revision, next_hop=hop, **updates) is None:
            self.log.info("lost run=%s rev=%s to a concurrent duplicate", run.id, msg.revision)
            return "skipped"
        if hop:
            await self._send(run.id, hop)
        self.log.info("done run=%s rev=%s -> %s", run.id, msg.revision, hop.queue if hop else "end")
        await self._emit("step.done", run.id, revision=msg.revision, next=hop.queue if hop else None)
        if updates.get("status") in TERMINAL:
            await self._emit("run.status", run.id, agent=False, status=updates["status"])
        return "done"

    def _over_budget(self, run: WorkflowRun, used: int) -> Outcome:
        """The run spent its token budget: stop here instead of calling the LLM. Keep the latest draft if there is one."""
        draft = next((r for r in reversed(run.revisions) if r.report_md), None)
        note = (f"token budget reached: {used:,} of {config.RUN_TOKEN_BUDGET:,} tokens used; stopped before {self.step}"
                + (f", the report is draft {draft.revision + 1}" if draft else ", no report was written"))
        self.log.warning("run=%s over budget (%s tokens), stopping before %s", run.id, used, self.step)
        return Outcome(run_updates={"status": "completed" if draft else "failed", "warnings": [*run.warnings, note]})

    async def _send(self, run_id: str, hop: NextHop) -> None:
        await queues.enqueue(self._queue(hop.queue), AgentMessage(workflow_run_id=run_id, revision=hop.revision))

    async def _resend(self, msg: AgentMessage) -> None:
        """A redelivered job for a step already done: re-send its recorded next hop, in case the crash
        happened between saving and sending. The deduped enqueue makes this a no-op otherwise."""
        run = await state.get_run(self.db, msg.workflow_run_id)
        st = run.steps.get(self.step) if run else None
        if st and st.status == "done" and st.revision == msg.revision and st.next:
            await self._send(run.id, st.next)

    async def _job(self, job, token=None) -> str:
        """BullMQ processor: run the job; on its last failed attempt, dead-letter it before BullMQ marks it failed."""
        done = False
        try:
            result = await self.process(job.data)
            done = result == "done"
            return result
        except Exception as e:  # BullMQ records it but logs nothing
            attempt = job.attemptsMade + 1
            self.log.warning("failed job=%s attempt=%s: %r", job.id, attempt, e)
            final = isinstance(e, UnrecoverableError) or attempt >= job.opts.get("attempts", 1)
            if isinstance(run_id := (job.data or {}).get("workflow_run_id"), str):
                await self._emit("step.failed", run_id, revision=job.data.get("revision"), attempt=attempt, final=final,
                                 error=dlq.redact(f"{type(e).__name__}: {e}")[:500])
            if final:
                await self._dead_letter(job, e, llm.last_output.get())
            raise
        finally:
            await self._presence(state="idle", run_id=None, revision=None, activity=None,
                                 jobs_done=self.info.jobs_done + done)

    async def _dead_letter(self, job, err: BaseException, raw_output: str | None = None) -> None:
        try:
            dl = await dlq.dead_letter(self.db, self._queue(queues.DLQ), self.queue_name, job, err, raw_output)
            self.log.error("dead-lettered job=%s as %s", job.id, dl.id)
            if dl.workflow_run_id:
                await self._emit("dead_lettered", dl.workflow_run_id, dead_letter_id=dl.id)
                await self._emit("run.status", dl.workflow_run_id, agent=False, status="failed")
        except Exception:  # never mask the job's own error
            self.log.exception("could not dead-letter job=%s", job.id)

    def _on_failed(self, job, err) -> None:
        # A job whose worker died more than maxStalledCount times is failed by BullMQ without calling _job.
        if getattr(job, "deferredFailure", None):
            task = asyncio.ensure_future(self._dead_letter(job, err))
            self._bg.add(task)
            task.add_done_callback(self._bg.discard)

    async def run(self, stop: asyncio.Event) -> None:

        # A limiter must be set or the worker ignores queue.rateLimit(); this one is high enough never to bind itself.
        # shortcut: bullmq-python ignores the limit's TTL and re-polls every drainDelay (5s), so pickup after a pause
        # can lag up to 5s; fine for minute-scale LLM limits, revisit if pauses get short.
        worker = Worker(self.queue_name, self._job, {"connection": worker_url(self.redis_url), "prefix": self.prefix,
                                                     "limiter": {"max": 1_000_000, "duration": 1000},
                                                     "lockDuration": self.lock_ms, "stalledInterval": self.lock_ms})
        worker.on("failed", self._on_failed)
        heartbeat = asyncio.create_task(self._heartbeat(stop))
        try:
            await stop.wait()
        finally:
            await worker.close()  # waits for the job in progress to finish
            await asyncio.gather(*self._bg, heartbeat)
            try:
                await workers.leave(self._redis, self.prefix, self.id)
            except Exception as e:
                self.log.warning("could not remove heartbeat: %r", e)
            for q in self._out.values():
                await q.close()


def main(queue_name: str, handler: Handler) -> None:
    """Entry point for `python -m app.agents.<name>`: one process, one actor, stops cleanly on SIGINT/SIGTERM."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(message)s")

    async def _run():
        client = state.connect()
        stop = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop.set)
        logging.getLogger(queue_name).info("listening")
        try:
            await Actor(queue_name, handler, client[config.MONGO_DB]).run(stop)
        finally:
            await client.close()

    asyncio.run(_run())
