# Set up Retro for development

To **use** Retro, run the one-command install in the [README](../README.md). This page is for working on Retro's code.

Paste this into your coding agent with the repository open:

```text
Read AGENTS.md and .claude/CLAUDE.md, then set up Retro for development on this machine:
1. Check for Docker (running), Python 3.12 with uv, and Node 25 with npm. Install what's missing and say what you
   installed.
2. From the repository root, start the local services (the "Start Redis + Mongo" command in AGENTS.md) and wait until
   they are healthy. Note that Redis is on host port 6380.
3. In apps/agents: copy .env.example to .env if it doesn't exist, install dependencies, and run the backend tests.
   All must pass before you continue.
4. In apps/web: copy .env.example to .env.local if it doesn't exist, install dependencies, then run lint, tests and
   build.
5. Start the API dev server, the four agent workers (supervisor, research, writer, critic) and the web dev server,
   each in the background, using the commands in AGENTS.md. Check that GET http://localhost:8000/workers lists four
   workers and that http://localhost:3000 loads.
6. Tell me to open http://localhost:3000/connectors and paste an Anthropic or OpenAI API key.
Never print, log or commit API keys. Read .env files only with a parser, never by sourcing them.
```

The same steps by hand are in [`AGENTS.md`](../AGENTS.md) under "Commands".
