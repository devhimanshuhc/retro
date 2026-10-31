# 14. Google sign-in built into Retro

**Decision.** Retro signs in to Google itself (OAuth with PKCE), asking only for permission to see the files it
creates (`drive.file`). This replaced a separate self-hosted connector service.

**Why.** The connector service added three containers, ran slowly under emulation on Apple Silicon Macs, and still
needed a Google app from every user. Installed users had no way to set it up and saw an error. Built in, the setup
is a guided page in the app, and with a Retro-owned Google app it becomes a single Connect click.

**Checked.** Tests against a simulated Google cover sign-in, a sign-in link used twice, a missing Drive permission,
revoked access, export and disconnect. On a fresh install, Google Docs shows a Set up button, never an error. A real
Google sign-in end to end is still to verify.
