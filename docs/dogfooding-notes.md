# Dogfooding Notes

Informal notes from real-world use. Not a formal document — don't over-format this.
Record what surprises you: wrong grades, missed recalls, broken UI, slow scans.
Anything that would make you not trust the app is worth a line here.

---

## Scan observations

| Date | Barcode | Product | Expected grade | Actual grade | Notes |
|------|---------|---------|---------------|--------------|-------|
|      |         |         |               |              |       |

---

## UI / rendering issues

<!--
Examples: ingredient list truncated, allergen banner wrong color,
report card overflows on small screen, compare mode layout broken on iOS.
-->

---

## Missing ingredients / false negatives

<!--
Ingredient was on the label but not flagged / not found in DB.
Include: raw label text, what it should have resolved to, what the report said.
-->

---

## Incorrect flags / false positives

<!--
Ingredient was flagged but shouldn't have been, or grade is harsher than warranted.
Include: canonical name, concern tag applied, why it's wrong.
-->

---

## Performance notes

<!--
Slow scans (>10s), spinner stuck, camera lag, backend timeouts.
Note whether it was Phase 1, Phase 2, or DB lookup that was slow.
-->

---

## Recall attachment quality

<!--
Recalls shown that don't match the product (false positive match via FTS).
Recalls missing that you know should be there.
Risk level (serious/high) correctly set?
-->
