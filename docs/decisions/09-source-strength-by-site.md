# 9. The site decides how strong a source is

**Decision.** Whether a source counts as a paper, an official document, news or other is decided by its website
(government and investor-relations sites are official, journals and preprint servers are papers, aggregators never
count as official), not by the model's guess. Research also adds papers from an open research index, and searches
once more for official sources when under half of what it found is papers or official documents.

**Why.** The model labelled aggregator pages as official sources. A report about earnings should rest on the
company's own release, not a site repackaging it.

**Checked.** The reviewer's "sources" score is counted from these labels, not judged. Retrieval evals were unchanged
by the change.
