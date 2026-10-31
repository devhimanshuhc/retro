# 5. The reviewer checks numbers in code

**Decision.** Before the model reviews a draft, code checks it: the required sections exist, every citation number
is in range, every sentence with a number or date carries a citation, and every number in the report appears in the
sources. A draft that fails goes back to the writer with the exact errors, and the model review is skipped.

**Why.** In testing, the model's review alone passed reports with deliberately planted wrong numbers, scoring them
about 0.85. A string check can't be talked into accepting a number that isn't in the sources.

**Checked.** Tests plant wrong numbers and uncited figures and confirm the draft is sent back. This doesn't catch a
missing fact, or a false claim that something wasn't reported ([known limits](../KNOWN_LIMITS.md)).
