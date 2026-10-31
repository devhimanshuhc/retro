# 4. Keyword ranking instead of embeddings

**Decision.** Passages are ranked against each question with BM25 keyword scoring, in code, at zero tokens. There is
no vector database and no embedding model.

**Why.** It is free, fast, needs no extra service, and its mistakes are easy to explain. Each idea to improve it was
measured on the retrieval eval before shipping: dropping common words and stemming lowered the scores and were
rejected; skipping reference-list passages raised them and shipped.

**Checked.** hit@6 0.857, recall@6 0.696, MRR 0.702 on 14 cases ([evals](../EVALS.md)). The cost is real: questions
worded differently from their answer get missed ([known limits](../KNOWN_LIMITS.md)), which led to
[decision 10](10-read-official-documents-whole.md).
