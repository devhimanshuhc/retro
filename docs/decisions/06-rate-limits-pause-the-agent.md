# 6. Rate limits pause the whole agent

**Decision.** When the model provider answers "too many requests", the agent pauses its entire queue until the time
the provider gives (or a default), so every copy of that agent waits together. Then the job retries.

**Why.** If only the worker that got the answer backed off, the other copies would keep hitting the limit and the
retries would pile up.

**Checked.** A test sends a fake rate-limit answer to two real workers and confirms both pause and the job then
succeeds. The test fails if the pause is removed.
