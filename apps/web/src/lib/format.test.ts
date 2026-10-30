import assert from "node:assert/strict";
import { test } from "node:test";

import { duration, linkCitations, numberedSources } from "./format.ts";
import type { Source } from "./types.ts";

const src = (url: string): Source => ({ url, title: url, kind: "news", quote: "q".repeat(20) });

test("sources are numbered in first-seen order, deduped by URL", () => {
  const out = numberedSources([
    { objective_id: "o1", summary: "s", sources: [src("a"), src("b")] },
    { objective_id: "o2", summary: "s", sources: [src("b"), src("c")] },
  ]);
  assert.deepEqual(out.map((s) => s.url), ["a", "b", "c"]);
});

test("citations become links and the sources list is dropped", () => {
  const md = "# T\n\nRevenue rose [1][2]. See [docs](https://x).\n\n## Sources\n1. [A](https://a)\n";
  assert.equal(linkCitations(md), "# T\n\nRevenue rose [1](#source-1)[2](#source-2). See [docs](https://x).\n\n");
});

test("duration reads as seconds, then minutes", () => {
  assert.equal(duration("2026-10-29T10:00:00Z", "2026-10-29T10:00:42Z"), "42s");
  assert.equal(duration("2026-10-29T10:00:00Z", "2026-10-29T10:02:05Z"), "2m 05s");
});

test("report title, usage line and short warnings", async () => {
  const { reportTitle, usageLine, parseWarning } = await import("./format.ts");
  assert.equal(reportTitle("intro\n# State of SSBs\n## A"), "State of SSBs");
  assert.equal(reportTitle("no heading"), null);
  assert.equal(
    usageLine({ critic: { input_tokens: 6000, output_tokens: 900 }, supervisor: { input_tokens: 10000, output_tokens: 200 } }),
    "17,100 tokens · supervisor 10.2k · critic 6.9k",
  );
  assert.equal(usageLine({}), null);
  assert.deepEqual(parseWarning("dropped source https://www.axios.com/2026/x: HTTP 403"), { what: "Source dropped", where: "axios.com", why: "HTTP 403" });
  assert.deepEqual(parseWarning("weak sources: source_quality 0.67"), { what: "Weak sources", why: "source quality 0.67" });
  assert.deepEqual(parseWarning("MAX_REVISIONS (3) reached"), { what: "Note", why: "MAX_REVISIONS (3) reached" });
});
