# 1. Agents talk only through queues

**Decision.** The four agents (planner, researcher, writer, reviewer) are separate processes. They never call each
other. Each one reads a message from its own queue, does its step, and sends a message to the next agent's queue.
A message carries only the run's id and revision; plans, findings and drafts live in one stored record per run.

**Why.** If one agent crashes, the others keep working and its unfinished job waits in its queue for another copy of
it. Any agent can be scaled by starting more copies. Because every agent loads the whole run record, none of them
works from a shortened summary passed along by the previous one, a failure common in agent chains ("Don't Build
Multi-Agents", the MAST failure study; see [research](../research.md)).

**Checked.** Tests run the four agents as real processes and push runs through them end to end, including duplicate
deliveries and a worker killed mid-step ([evals §4](../EVALS.md#4-failures-retries-and-recovery)).
