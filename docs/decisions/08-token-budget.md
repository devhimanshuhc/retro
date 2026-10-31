# 8. A token budget per run

**Decision.** Each run has a token budget (500k by default). Before each step, the agent checks what the run has
used. Once over, no more rewrites run: the run ends with its latest draft and a warning, or fails if there is no
draft. The first report is always written, since research already paid for it. Starting runs is also capped per
hour.

**Why.** A review loop that never passes, or a search that keeps retrying, could otherwise spend without limit on
the user's own key.

**Checked.** Tests push a run over budget and confirm the step stops without calling the model. A step already
running can overshoot ([known limits](../KNOWN_LIMITS.md)).
