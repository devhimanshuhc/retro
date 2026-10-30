<p align="center">
  <img src="docs/assets/banner.svg" alt="Retro" width="100%">
</p>

<h1 align="center">Retro</h1>

<p align="center">
  <a href="#install-one-command">Install</a> · <a href="#options-in-env">Options</a> · <a href="#optional-google-docs-export">Google Docs</a> · <a href="#develop">Develop</a>
</p>

<p align="center">
  <a href="#install-one-command"><img src="https://img.shields.io/badge/Install-one%20command-ece7dd?style=for-the-badge&labelColor=0d0d0c" alt="Install: one command"></a>
  <a href="#install-one-command"><img src="https://img.shields.io/badge/Runs-on%20your%20machine-3f8f5a?style=for-the-badge&labelColor=0d0d0c" alt="Runs on your machine"></a>
  <a href="https://docs.docker.com/get-docker/"><img src="https://img.shields.io/badge/Needs-Docker%20Desktop-2496ED?style=for-the-badge&logo=docker&logoColor=white&labelColor=0d0d0c" alt="Needs Docker Desktop"></a>
</p>

**Research agents you can leave running.** Ask a question; agents plan it, read real sources, write a cited report and
check it, and keep going when something breaks. Everything runs on your own machine.

<table>
<tr><td><b>Real sources, cited</b></td><td>Papers, filings and primary pages are read and quoted by code, so a citation always points at text that exists. Every number in the report must appear in the sources.</td></tr>
<tr><td><b>Checked before you see it</b></td><td>A reviewer scores each draft for accuracy, citations and completeness, and sends it back for a rewrite until it passes.</td></tr>
<tr><td><b>Keeps going when something breaks</b></td><td>A crashed step is picked up again from where the run left off, rate limits pause and resume, and anything that still fails lands on a dead-letters page you can replay.</td></tr>
<tr><td><b>Watch it work</b></td><td>Each step streams live: what is being searched, read, written and checked, with the token cost of every run.</td></tr>
<tr><td><b>Edit and export</b></td><td>Ask for changes to a finished report, keep every version in Artifacts, and open any report as a Google Doc.</td></tr>
</table>

---

## Install (one command)

You need [Docker Desktop](https://docs.docker.com/get-docker/) running and an API key from
[Anthropic](https://console.anthropic.com/) or [OpenAI](https://platform.openai.com/api-keys) (billed per token,
roughly 60-120k tokens a report).

```sh
curl -fsSL https://raw.githubusercontent.com/<owner>/retro/main/install.sh | sh
```

It installs into `~/retro`, starts everything and opens **http://localhost:3000**, where Retro asks for your API key
once. The key is checked with its provider, kept on this machine only and never shown again. Retro listens on this
machine only.

### Get started

1. **Install and start [Docker Desktop](https://docs.docker.com/get-docker/)**, and wait until it says it is running.
2. **Get an API key** (one is enough):
   - **Anthropic:** sign in at [console.anthropic.com](https://console.anthropic.com/), add credit under
     *Billing*, then open *[API keys](https://console.anthropic.com/settings/keys)* → *Create key*. It starts with
     `sk-ant-api`.
   - **OpenAI:** sign in at [platform.openai.com](https://platform.openai.com/), add credit under *Billing*, then
     open *[API keys](https://platform.openai.com/api-keys)* → *Create new secret key*. It starts with `sk-`
     (`sk-proj-` for project keys).

   Copy the key right away: both sites show it only once. A Claude or ChatGPT chat subscription (Pro, Max, Plus) is
   not an API key and can't be used here.
3. **Run the install command** above in a terminal (macOS or Linux; on Windows, inside WSL).
4. **Paste your key** in the browser tab that opens (or later under *Connectors*). Retro checks it with the
   provider, which costs no tokens, and saves it.
5. **Ask a question** and watch the agents work.

Without a key, the new-run page shows a *No model connected* message with the key form, and runs can't start. If
a key is removed, revoked or runs out of credit during a run, the run stops with *No working API key*: add or
replace the key under *Connectors*, then replay the run from its dead letter.

| | |
|---|---|
| Stop | `cd ~/retro && docker compose down` |
| Start again | `cd ~/retro && docker compose up -d` |
| Update | `cd ~/retro && docker compose pull && docker compose up -d` |
| Logs | `cd ~/retro && docker compose logs -f` |
| Remove Retro and its data | `cd ~/retro && docker compose down --volumes`, then delete the `~/retro` folder |

Prefer not to pipe a script into a shell? Clone the repository, then:

```sh
cd deploy && cp .env.example .env    # optional: put your key here instead of in the app
docker compose up -d --build         # builds the images from source
```

## Options (in `.env`)

- `RUN_TOKEN_BUDGET`: token cap per report (default 500k). `RUNS_PER_WINDOW` / `RUN_WINDOW_S`: run rate limit.
- `CONTACT_EMAIL`: a real address of yours, sent only to sites that require a contact (SEC filings).
- `*_MODEL` / `OPENAI_*_MODEL`: the model for each agent, per provider.
- Different ports: set `RETRO_WEB_PORT` / `RETRO_API_PORT` and build from source (the web app is built for its API port).

## Optional: Google Docs export

Retro can open reports as Google Docs in your Drive, through a self-hosted [Nango](https://github.com/NangoHQ/nango)
and your own Google OAuth client. Setup guide: coming soon.

## Develop

Two apps: `apps/agents` (Python API and agents) and `apps/web` (Next.js). See `AGENTS.md` for commands.

## Credits

Isometric figures drawn with the Anatomy kit (MIT, `apps/web/vendor/anatomy`). Archive photographs are public domain,
credited on the site.
