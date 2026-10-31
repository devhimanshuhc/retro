# 7. Failed jobs go to dead letters, with replay

**Decision.** Each job gets 3 attempts with growing waits. On the last failure, or an error a retry can't fix (a bad
key, a malformed message), Retro saves a dead letter with the error, the stack trace and the model's last output,
and marks the run failed. The Dead letters page shows it and can replay it once.

**Why.** A run must never hang in "working" forever. A worker killed twice on the same job is failed by the queue
itself without running Retro's code, so Retro also listens for that event; without it such runs hung.

**Checked.** End-to-end tests with real workers: fail → dead letter → replay → step done, and a second replay is
refused. API keys are removed from saved errors.
