# Research: actor-model multi-agent systems

Collected 2026-10-25. Each entry says **what we take from it** for this scheduler.

## Must-read (directly shapes our design)

| Source | Type | What we take |
|---|---|---|
| [How we built our multi-agent research system](https://www.anthropic.com/engineering/multi-agent-research-system) — Anthropic, 2025 | Eng blog | Orchestrator-worker is the proven shape. Resume from where the error happened instead of restarting. Agents hand off **artifacts stored outside the conversation** (our Mongo pointers). Full tracing is required because runs are non-deterministic. Rainbow deploys so running jobs aren't broken by new code. Judge outputs with a rubric (factual accuracy, citation accuracy, completeness, source quality). Multi-agent costs ~15× the tokens of chat. They call subagents *synchronously* and name that as a bottleneck; our async queues are the answer to it. |
| [Building effective agents](https://www.anthropic.com/engineering/building-effective-agents) — Anthropic | Eng blog | Our flow is two named patterns: **orchestrator-workers** (router → research) and **evaluator-optimizer** (writer ↔ critic). Evaluator-optimizer only works with clear evaluation criteria, so the critic needs explicit checks, not "is this good?". |
| [Why Do Multi-Agent LLM Systems Fail? (MAST)](https://arxiv.org/abs/2503.13657) — Cemri, Pan, … Zaharia, Gonzalez, Stoica (Berkeley), 2025 | Paper | 14 failure modes from 1600+ traces. Most failures are **system design**, not model weakness. See the mapping below. |
| [Don't Build Multi-Agents](https://cognition.ai/blog/dont-build-multi-agents) — Cognition, 2025 (+ follow-up [Multi-Agents: What's Actually Working](https://cognition.com/blog/multi-agents-working)) | Eng blog (counterpoint) | Agents fail when they get a summary instead of the full context. So every actor loads the **full run context** from Mongo (original prompt, plan, prior outputs), not just the queue message. Keep decisions single-threaded: one actor owns each step. |
| [Your Agent Needs a Supervisor, Not a Retry Loop](https://tianpan.co/blog/2026-07-02-your-agent-needs-a-supervisor-not-a-retry-loop) — 2026 | Blog | The Erlang "let it crash" idea for agents: a retry must start from **clean, durable inputs**, not carry the failed attempt's output. And retrying the same thing only helps when the failure is transient (429, timeout). Logic failures go to the DLQ. |
| [BullMQ: retrying failing jobs](https://docs.bullmq.io/guide/retrying-failing-jobs) · [DLQ pattern](https://oneuptime.com/blog/post/2026-01-21-bullmq-dead-letter-queue/view) · [Railway retry/DLQ guide](https://docs.railway.com/guides/bullmq-jobs-retry-dlq) | Docs | Exponential backoff = `2^(attempts-1) × delay`. BullMQ has **no built-in DLQ**; build it on the `failed` event. Jobs must be idempotent. |

## MAST failure modes → how this scheduler prevents them

| MAST failure mode (share of failures) | Our guard |
|---|---|
| FM-1.3 Step repetition (17.1%) | Idempotent workers + deterministic `job_id` per step/revision |
| FM-1.5 Unaware of termination (9.8%) | Hard `MAX_REVISIONS` cap; run status is set only by the critic or the DLQ |
| FM-1.1 Disobey task spec (11.0%) | Router writes a structured plan (pydantic); later agents read it from Mongo |
| FM-1.4 Loss of history (3.3%) / FM-2.1 Conversation reset (2.3%) | All state in Mongo, actors are stateless, each step loads the full run doc |
| FM-2.6 Reasoning-action mismatch (14.0%) / FM-2.3 Task derailment (7.2%) | Structured outputs validated by pydantic before saving; bad output → retry, then DLQ |
| FM-2.2 Fail to ask for clarification (11.7%) | Out of scope for v1 (no human loop); could add an A2A-style `input-required` status |
| FM-3.1 Premature termination (7.8%), FM-3.2/3.3 Missing or wrong verification (13.5%) | Critic runs deterministic checks first (sections present, citations exist), then an LLM rubric; pass needs both |

## Papers

**Actor-model / distributed agent runtimes**
- [AgentScope: A Flexible yet Robust Multi-Agent Platform](https://arxiv.org/abs/2402.14034) (Alibaba, 2024). Message exchange as the only communication, an **actor-based distribution framework** (same code runs locally or distributed), and built-in fault tolerance for LLM errors. The closest academic match to this project.
- [MetaGPT](https://arxiv.org/abs/2308.00352) (ICLR 2024). A shared **publish-subscribe message pool**: agents subscribe only to the messages relevant to their role. Structured intermediate outputs (documents, not chat) greatly raise success rates, which supports our pydantic-validated step outputs.
- [Multi-Agent Collaboration Mechanisms: A Survey of LLMs](https://arxiv.org/abs/2501.06322) (2025). A survey of how agents coordinate: centralized vs decentralized, and their effect on robustness.

**Fault tolerance and reliability**
- [On the Resilience of LLM-Based Multi-Agent Collaboration with Faulty Agents](https://arxiv.org/abs/2408.00989). Hierarchical structures lose the least performance (-9.2%) when an agent is faulty, and **adding a review agent** improves resilience. This supports our router + critic shape.
- [MAS-FIRE: Fault Injection and Reliability Evaluation for LLM-Based MAS](https://arxiv.org/abs/2602.19843) (2026). 15 fault types, intra-agent and inter-agent, injected by rewriting prompts, responses or message routing. A template for our chaos demo (step 19).
- [Rethinking the Reliability of MAS: A Byzantine Fault Tolerance Perspective](https://arxiv.org/abs/2511.10400). Confidence-weighted consensus among agents. Beyond v1; only matters with redundant agents voting.

**Scheduling agent workloads (serving layer, mostly beyond v1)**
- [HexAGenT: workflow- and heterogeneity-aware scheduling](https://arxiv.org/abs/2605.16637) (2026). Schedules for an end-to-end **workflow SLO**, not per-request latency.
- [Decoupling Readiness from Release for Tail-Aware Scheduling of Agentic LLM Workflows](https://arxiv.org/abs/2609.10964) (2026). Decides which ready step runs next, prioritizing workflows at risk of a slow tail. Idea for later: BullMQ job `priority` based on how long a run has been going.
- [Maestro: workload-aware cross-cluster scheduling for LLM MAS](https://arxiv.org/abs/2606.12950) (2026) and [TOPAS: workflow-aware prefix-state scheduling](https://arxiv.org/abs/2608.25523) (2026). GPU-level scheduling with prefix caching. Relevant only if self-hosting models.

## Production frameworks worth studying (not dependencies)

| Framework | Why look at it |
|---|---|
| [AutoGen v0.4 core](https://microsoft.github.io/autogen/0.4.0/user-guide/core-user-guide/index.html) ([announcement](https://www.microsoft.com/en-us/research/?p=1116288)) | Microsoft rebuilt AutoGen on the **actor model**: async messages, event-driven agents, delivery separated from handling. Now in maintenance. |
| [Microsoft Agent Framework](https://learn.microsoft.com/agent-framework/overview/agent-framework-overview) (1.0 GA Apr 2026) | AutoGen's successor. Graph workflows with **checkpointing at step boundaries** and resume after restarts, which our Mongo run doc mirrors. |
| [Dapr Agents](https://dapr.io/ai/) ([InfoQ](https://infoq.com/news/2025/03/dapr-agents), [durable workflows](https://www.diagrid.io/blog/durable-agentic-workflows-with-dapr)) | Agents as **virtual actors** (Orleans-style) on a durable workflow engine; every reasoning step checkpointed. The production-grade version of this idea. |
| [Temporal for AI agents](https://temporal.io/blog/durable-execution-meets-ai-why-temporal-is-the-perfect-foundation-for-ai) | Durable execution: a crash after the LLM call but before the tool call resumes exactly there. Good to compare against queue-based retries in the README. |
| [Ray actors for agents](https://infoq.com/presentations/scale-llm-agents-production-ray) | A supervisor actor dispatching to worker actors, with in-memory actors instead of Redis queues. A contrast point. |

## Standards

- [A2A (Agent2Agent) protocol](https://www.agentpatterns.ai/standards/a2a-protocol/) (Google, Apr 2025). Task lifecycle `submitted → working → input-required → completed | failed | canceled` for long-running async work. **We use these names for run status.**
- [OpenTelemetry GenAI semantic conventions](https://www.dash0.com/knowledge/opentelemetry-genai-semantic-conventions-explained). Standard span names for model calls, tool calls and agent runs. Trace context can travel inside the job data, so one trace covers the whole run across workers. Model and tool attributes are stable; agent attributes are still settling (2026).

## What changed in our plan because of this research
1. Run status uses A2A task states.
2. Every actor loads the full run context from Mongo (Cognition, MAST FM-1.4).
3. On a 429, pause the whole queue for the `retry-after` time with `queue.rateLimit(ms)` (bullmq-python has no declarative worker limiter), then retry.
4. Retries start from clean durable inputs, never from the failed attempt's output (supervisor "restart clean").
5. The critic does deterministic checks plus a rubric (Anthropic eval criteria), so MAST's verification failures are covered.
6. Optional tracing step using OTel GenAI conventions, with `workflow_run_id` on every span.
