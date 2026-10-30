"""One real agent process for the kill tests: `python -m tests.chaos_worker <agent> <prefix> <db> <lock_ms> <llm_delay_s>`.
The LLM is faked (pytest never calls Claude) and slowed so the test can kill the process mid-job."""
import asyncio
import importlib
import logging
import sys

from app.agents.base import Actor
from app.services import llm, sources, state
from tests.fakes import fake_fetch, fake_llm

agent, prefix, db_name, lock_ms, delay = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), float(sys.argv[5])
fake = fake_llm([])


async def slow(*a, **k):
    await asyncio.sleep(delay)
    return await fake(*a, **k)


llm.complete, sources.fetch = slow, fake_fetch
module = importlib.import_module(f"app.agents.{agent}")
queue = {"writer": "agent.write"}.get(agent, f"agent.{agent}")


async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout, format="%(name)s %(message)s")
    client = state.connect()
    try:
        await Actor(queue, module.handle, client[db_name], prefix=prefix, lock_ms=lock_ms).run(asyncio.Event())
    finally:
        await client.close()

asyncio.run(main())
