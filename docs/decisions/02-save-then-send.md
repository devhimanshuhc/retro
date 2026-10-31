# 2. Save, then send

**Decision.** An agent saves its output, marks its step done and records the next message in one write, and only
then sends that message. If the agent dies after saving but before sending, the redelivered job sees the step is done
and sends the recorded message again.

**Why.** Sending first lets the next agent start before the output exists, so it reads an empty record. Saving and
sending in two unrelated steps can lose the message, leaving the run stuck.

**Checked.** Tests crash a step between saving and sending and confirm the run still finishes, with no duplicate
report.
