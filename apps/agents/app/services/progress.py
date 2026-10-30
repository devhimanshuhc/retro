"""Sub-step progress from inside a handler ("searching: <query>", "read 7 of 9 pages"), without handlers knowing
about queues or Redis. The Actor sets the sink for each job; with none set (tests, scripts) reporting is a no-op."""
from collections.abc import Awaitable, Callable
from contextvars import ContextVar

Sink = Callable[[str, str, dict], Awaitable[None]]
sink: ContextVar[Sink | None] = ContextVar("progress_sink", default=None)


async def report(phase: str, detail: str, **data) -> None:
    """phase: short machine label (searching, fetching, ...); detail: one human-readable line."""
    if (f := sink.get()) is not None:
        await f(phase, detail, data)
