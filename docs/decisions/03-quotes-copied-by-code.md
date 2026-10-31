# 3. Quotes are copied by code, never written by the model

**Decision.** The model never writes a quote or a URL. Code fetches the pages, splits them into passages and numbers
them. The model only picks passage numbers. The quote shown under each citation is that passage, copied from the
page by code, and the sources list is built by code from the same records.

**Why.** A model asked to cite sources can invent a URL or put words in a source's mouth. When the quote is copied
from a page Retro actually read, every citation points at text that exists.

**Checked.** Tests assert that each saved quote equals the fetched page text, not the model's output, and that
passage numbers the model invents are dropped.
