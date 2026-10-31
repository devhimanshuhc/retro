# Known limits

What Retro doesn't do well yet, so you know before you rely on it.

## Research and reports

- **Keyword matching misses other wording.** Passages are found by the words they share with the question. If a
  source says "outlook" and you asked about "guidance", the passage can be missed. Short official documents are read
  whole to soften this; long ones are not. 2 of the 14 retrieval test cases fail this way ([evals](EVALS.md)).
- **A report can still miss or misstate a fact.** In the end-to-end test, each run missed 1 of 7 facts, and one run
  wrongly said no segment results were published. Numbers are checked against the sources by code, but a missing
  fact or a wrong "not reported" claim isn't.
- **Some sites can't be read.** Sites that block automated visitors, even a real browser, are skipped and listed as
  dropped sources. Paywalled articles are read only as far as the public part.
- **Source strength varies by topic.** Some questions only find news coverage. The reviewer's "sources" score shows
  this (for example 0.33 means a third of the cited sources are papers or official documents).
- **Asking for a change reuses the same sources.** A follow-up edit rewrites the report from what was already found;
  it doesn't research again.
- **The token cap is checked between steps.** A step that's already running can go over the per-run budget.

## Providers and files

- **OpenAI support is untested with a real key.** It is tested against a simulated server only. All quality numbers
  were measured with Anthropic models.
- **Your own files:** PDF, text, Markdown, HTML, CSV and JSON. Word documents and scanned PDFs (they need OCR) aren't
  read.
- **No sign-in through a chat subscription.** Claude or ChatGPT plans (Pro, Max, Plus) can't be used, only API keys.

## Google Docs

- **One-time setup in Google Cloud** (about 5 minutes, guided in the app) until Retro ships its own Google app.
- If the sign-in screen in Google Cloud is left in Testing mode, Google signs Retro out every 7 days.

## Running it

- **No login.** Retro listens only on your own computer, but anyone using that computer can open it.
- **Keys are stored unencrypted** in Retro's local database (see [privacy](PRIVACY.md)).
- **Windows needs WSL.** The installer is a Unix shell script.
- **The first download is about 5 GB**, mostly the browser used for pages that need one.
- **Changing the API port** (8000) needs a build from source.
- A citation written just before a colon, like `[2]:`, shows as plain text instead of a link.
