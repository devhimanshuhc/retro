# 10. Short official documents are read whole

**Decision.** Official documents and papers that fit in about 30,000 characters are given to the model in full, in
order, instead of only their best-ranked passages. Longer ones are ranked as usual.

**Why.** Keyword ranking missed facts in tables and facts worded differently from the question ("outlook" when the
question said "guidance"), and those documents hold exactly the facts a report most needs.

**Checked.** On the end-to-end earnings report test, facts found went from 48% to 86%, and tokens per run went down
(about 145k to 104k) ([evals](../EVALS.md)).
