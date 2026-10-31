# 11. A smaller model for research and review

**Decision.** Planning, research and review run on a smaller, cheaper model; only the writer uses a larger one. The
reviewer runs with extended thinking off.

**Why.** Research mostly picks passages and summarises them, and review fills in a fixed scorecard. Neither gained
from the larger model, and thinking was about 90% of the reviewer's output tokens.

**Checked.** Moving research to the smaller model kept answer accuracy at 0.857 and faithfulness at 1.0 vs 0.988.
Turning thinking off cut the reviewer's output tokens about 30×. Each agent's model can be changed in settings.
