# How well Retro works

Every number here was measured, and the raw results are saved in
[`apps/agents/evals/results/`](../apps/agents/evals/results/). Nothing below is an estimate.

## 1. Finding the right passages (research)

**What it tests:** given a question and a pile of saved pages, does research put the passage that answers it in
front of the writer?

- **Cases:** 14 questions over saved copies of real pages: papers (the Transformer, GPT-3, BERT, Llama 2, Chinchilla,  
ReAct, the MAST failure study, RAG), a company's annual results, the Bitcoin paper, encyclopedia articles. Every case also has pages on the same topic that don't answer it, so a wrong pick is possible.
- **Labels:** each case lists the evidence sentences that answer it, copied from the page.
- **Cost:** 0 tokens. It runs on every test pass, and a drop below the recorded floor fails the build.

| Metric | Result | Meaning |
|---|---|---|
| hit@6 | **0.857** | for 12 of 14 questions, an answering passage is among the 6 shown |
| recall@6 | **0.696** | share of all answering passages that make the top 6 |
| MRR | **0.702** | the first answering passage is usually first or second |

With the model added (`--llm`, 14 cases):

| Metric | Result | Meaning |
|---|---|---|
| answer accuracy | **0.857** | the expected facts appear in the answer (checked by code, not by a model) |
| faithfulness | **1.0** (0.988 on an earlier run) | share of claims supported by the passages, judged claim by claim |
| context sufficient | **0.857** | the passages shown were enough to answer |

**Ideas this measured and rejected:** dropping common words and word stemming both lowered the scores, so neither
shipped. Dropping reference-list passages raised them and shipped. The two misses (`actor-model` at rank 3 and
`bm25-params`) are keyword-ranking failures: the answer uses different words than the question (see
[Known limits](KNOWN_LIMITS.md)).

## 2. Whole reports against the facts (end to end)

**What it tests:** a real run, start to finish, on a question whose answers were checked by hand.

- **Case:** "Write a market report on Nvidia's Q2 fiscal 2027 earnings". It has 7 facts that must appear
(revenue, data-center revenue, segment revenue, EPS now and a year ago, net income, next-quarter outlook). Each was
checked against the company's own release filed with the SEC on 2026-08-26.
- **Scoring:** by code. A fact counts only if the report states it, and known wrong values are also searched for.

| Version | Runs | Facts found | 95% interval | Wrong claims | Tokens per run | Time |
|---|---|---|---|---|---|---|
| Before (ranked passages only) | 3 | **48%** | 28–68% | 2 | ~145k | ~2.5 min |
| After (short official documents read whole) | 2 | **86%** (6 of 7 each) | 60–96% | 1 | ~104k | ~3 min |

What the "after" runs still got wrong, from the saved results:

- One run missed the year-ago EPS ($1.01); the other missed segment revenue ($7.2B).
- One run claimed no segment results were published, which is false. The reviewer didn't catch it.

Two runs is a small sample; the interval is wide on purpose.

## 3. Your own files

A question answered only from an uploaded copy of the Bitcoin paper (no web search) passed review and cited only
that file. It used about 37k tokens.

## 4. Failures, retries and recovery

These are proven by automated tests that start real worker processes and a real queue (no model calls):

| Situation | What the test shows |
|---|---|
| A worker is killed in the middle of writing | another worker takes the job when its lock expires; the run finishes with exactly one report |
| The same worker is killed twice on one job | the job goes to dead letters and the run is marked failed, instead of hanging forever |
| The model provider answers "too many requests" | every worker of that agent pauses together, then retries |
| A step fails on every attempt | the job, its error and the model's last output are saved to dead letters; replay starts it again once |
| The same message is delivered twice | the step runs once |
| A run is canceled mid-step | the step's result is dropped |

A recorded demo of these on the live dashboard is still to do.

## Run them yourself

The commands are in [`AGENTS.md`](../AGENTS.md) under "Research evals" and "Report evals". The retrieval eval costs
nothing; a report eval run uses roughly 100k tokens of your own API key.
