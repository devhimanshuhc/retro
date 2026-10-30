"""Dev helper until the API exists (step 17): create a run, send it to the supervisor, wait for the end.

    uv run --env-file .env python -m scripts.submit "Write a report on Nvidia Q3 earnings"
"""
import asyncio
import sys
import time

import config
from app.models.messages import AgentMessage
from app.models.run import TERMINAL
from app.services import queues, state


async def main(prompt: str, timeout_s: float = 600) -> int:
    client = state.connect()
    db = client[config.MONGO_DB]
    q = queues.open_queue(queues.SUPERVISOR)
    try:
        run = await state.create_run(db, prompt)
        await queues.enqueue(q, AgentMessage(workflow_run_id=run.id))
        print(f"submitted {run.id}")
        deadline = time.monotonic() + timeout_s
        while time.monotonic() < deadline:
            run = await state.get_run(db, run.id)
            if run.status in TERMINAL:
                print(f"{run.status}: " + ", ".join(f"{k}={v.status}@rev{v.revision}" for k, v in run.steps.items()))
                for r in run.revisions:
                    c = r.critique
                    print(f"rev {r.revision}: {'passed' if c and c.passed else 'failed'}"
                          + (f" scores={c.scores.model_dump()}" if c and c.scores else "")
                          + (f" errors={c.errors}" if c and c.errors else ""))
                print("usage:", {k: v.model_dump() for k, v in run.usage.items()}, "warnings:", run.warnings)
                if run.revisions:
                    print("\n" + run.revisions[-1].report_md)
                return 0 if run.status == "completed" else 1
            await asyncio.sleep(0.2)
        print(f"timed out after {timeout_s}s, status={run.status}. Are the agent workers running?")
        return 1
    finally:
        await q.close()
        await client.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit('usage: python -m scripts.submit "<prompt>"')
    sys.exit(asyncio.run(main(sys.argv[1])))
