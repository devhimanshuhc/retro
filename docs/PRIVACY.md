# Your data

Retro runs on your computer. This page lists everything that leaves it, and everything it keeps.

## What leaves your computer, and where it goes

| Goes to | What | When |
|---|---|---|
| **Your model provider** (Anthropic or OpenAI, whichever key you use) | your question, the plan, the passages chosen from sources and your files, the drafts and the review | every run |
| **Your model provider's web search** | search queries the agents write from your question | runs that search the web |
| **Websites** | ordinary page requests to the pages being read | runs that search the web |
| **An open index of research papers** ([OpenAlex](https://openalex.org)) | the research questions from the plan | runs that search the web |
| **SEC (sec.gov) only** | the contact email you set in `CONTACT_EMAIL`, which SEC requires from automated readers | when a filing is read and the email is set |
| **Google** | the report you export, and your sign-in | only when you click "Open in Google Docs" |

**Your own files** stay on your computer. Only the passages picked for the report go to the model provider, never
the whole file. Turn off "Also search the web" and nothing about your question goes to websites or the paper index.

Retro sends no analytics and no usage data to anyone, including us.

## Google

Retro asks Google only for permission to see the files it creates (`drive.file`). It can't see, list or change any
other file in your Drive. Your Google sign-in token stays in Retro's local database and is used only to create docs
you ask for. Disconnecting in Connectors revokes it at Google. You can also remove Retro at
[myaccount.google.com/permissions](https://myaccount.google.com/permissions).

## What Retro keeps, and where

Everything is kept in Docker volumes on your computer:

- runs: your questions, plans, sources with their quotes, every draft and review, timelines;
- the text pulled out of files you upload (not the files themselves);
- your API keys and Google sign-in.

**Keys are stored unencrypted** in that local database. Anyone who can use your computer's Docker can read them.
The web app never receives a key back once saved, and keys are removed from error reports before they are saved.

## Who can reach it

Retro listens only on your own computer (`127.0.0.1`), not on your network. There is no login, so anyone using your
computer can open it.

## Deleting everything

```sh
cd ~/retro && docker compose down --volumes
```

This removes all runs, files, keys and the Google sign-in. Then delete the `~/retro` folder. Docs already created
in your Google Drive stay there.
