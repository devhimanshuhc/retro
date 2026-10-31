# 13. Research your own files

**Decision.** Users can attach files (PDF, text, Markdown, HTML, CSV, JSON) to a run, with or without web search.
Text is pulled out once on upload and the file itself isn't kept. Files are ranked and quoted exactly like web pages
and count as strong sources.

**Why.** Private documents are the main reason to run research on your own machine. Only the passages used reach the
model provider, never the whole file.

**Checked.** A files-only run on the Bitcoin paper passed review citing only that file (~37k tokens). Retrieval evals
were unchanged. A files-only run whose files don't answer the question fails at once instead of retrying.
