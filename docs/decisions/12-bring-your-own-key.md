# 12. Users bring their own API key

**Decision.** Retro runs on the user's own Anthropic or OpenAI API key, pasted in the app. The key is checked with
the provider (at no cost) before it's saved, never shown again, and removed from any saved error. There is no
sign-in with a Claude or ChatGPT chat subscription.

**Why.** Anthropic's terms don't allow third-party products to offer sign-in with a claude.ai account. A key also
makes cost visible: each run shows its token use.

**Checked.** Tests confirm a key is never returned by the API or echoed in an error message, and that runs can't
start without one. The OpenAI path is tested against a simulated server only ([known limits](../KNOWN_LIMITS.md)).
