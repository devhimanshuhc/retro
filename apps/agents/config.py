import os

# Values come from the environment: `uv run --env-file .env ...` locally, compose `env_file` in Docker.
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6380")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.environ.get("MONGO_DB", "scheduler")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # or paste one in the web app (Connectors), which wins
# Or run the agents on OpenAI instead: a key here or pasted in the web app (the provider whose key was saved last is used)
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
# 1 = with no API key, run on this machine's own Claude login. Personal development only: Anthropic doesn't allow
# offering claude.ai login to other users, and it doesn't work inside Docker.
USE_CLAUDE_LOGIN = os.environ.get("USE_CLAUDE_LOGIN", "0") == "1"

ROUTER_MODEL = os.environ.get("ROUTER_MODEL", "claude-haiku-4-5-20251001")  # reads every message: small and cheap
SUPERVISOR_MODEL = os.environ.get("SUPERVISOR_MODEL", "claude-haiku-4-5-20251001")
RESEARCH_MODEL = os.environ.get("RESEARCH_MODEL", "claude-haiku-4-5-20251001")
WRITER_MODEL = os.environ.get("WRITER_MODEL", "claude-sonnet-5-5")
CRITIC_MODEL = os.environ.get("CRITIC_MODEL", "claude-haiku-4-5-20251001")
# The same agents on OpenAI (Responses API)
OPENAI_ROUTER_MODEL = os.environ.get("OPENAI_ROUTER_MODEL", "gpt-6-luna")
OPENAI_SUPERVISOR_MODEL = os.environ.get("OPENAI_SUPERVISOR_MODEL", "gpt-6-luna")
OPENAI_RESEARCH_MODEL = os.environ.get("OPENAI_RESEARCH_MODEL", "gpt-6-luna")
OPENAI_WRITER_MODEL = os.environ.get("OPENAI_WRITER_MODEL", "gpt-6.1-sol")
OPENAI_CRITIC_MODEL = os.environ.get("OPENAI_CRITIC_MODEL", "gpt-6-luna")

# User-Agent for checking sources. SEC EDGAR (sec.gov) blocks browser-like agents and requires
# "<name> <contact email>", e.g. "Retro you@example.com"; set it to verify SEC filings.
FETCH_USER_AGENT = os.environ.get("FETCH_USER_AGENT") or ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36")

# Contact address for services that ask automated clients to identify themselves (SEC EDGAR requires
# "<name> <email>"). Sent only to those services, never to other sites. Empty = SEC filings can't be fetched.
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "")

# How long an agent's whole queue pauses on a 429 when the provider doesn't say when the limit resets
RATE_LIMIT_PAUSE_MS = int(os.environ.get("RATE_LIMIT_PAUSE_MS", "30000"))

MAX_REVISIONS = int(os.environ.get("MAX_REVISIONS", "3"))

# Re-read pages that refuse a plain fetch (403/429) or render in JavaScript with headless Chromium (public pages
# only, no logins). Needs `uv run playwright install chromium`; 0 turns it off.
BROWSER_FALLBACK = os.environ.get("BROWSER_FALLBACK", "1") == "1"

# Spending cap per run (input + output tokens, all agents). Checked before each step: an over-budget run stops
# with its latest draft (completed + warning), or fails if it has none. A typical run uses 200-250k.
RUN_TOKEN_BUDGET = int(os.environ.get("RUN_TOKEN_BUDGET", "500000"))

# POST /workflows: at most RUNS_PER_WINDOW new runs per client per RUN_WINDOW_S seconds (429 + Retry-After after)
RUNS_PER_WINDOW = int(os.environ.get("RUNS_PER_WINDOW", "10"))  # reports started (counted when the router starts research) and edits
MESSAGES_PER_WINDOW = int(os.environ.get("MESSAGES_PER_WINDOW", "60"))  # every message; the router reads each one cheaply
RUN_WINDOW_S = int(os.environ.get("RUN_WINDOW_S", "3600"))

# Google Docs export. Retro's own Google app (OAuth client, "Desktop app" type) when set; else users paste theirs in
# Connectors. Not a secret for a Desktop-app client (Google documents it as non-confidential).
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
API_URL = os.environ.get("API_URL", "http://localhost:8000").rstrip("/")  # how the browser reaches the API (OAuth return)

# Browser origins allowed to call the API (the Next.js app in apps/web)
WEB_ORIGINS = os.environ.get("WEB_ORIGINS", "http://localhost:3000").split(",")
