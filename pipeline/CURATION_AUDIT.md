# Curation Audit — issue #49

Audit of the hand-made curation decisions in `pipeline/curation.json` (1,635 merges,
934 deletes, 1,190 validated) against the base and taxonomy. Screens used: merges whose
final target is dead (silent deletions), culinarily wrong merge targets, meaning-drift
merge chains, cross-list contradictions, and the 60 highest-degree deletions.

Pair-EDGE auditing (wrong associations between two kept ingredients) is out of scope here —
that is what the #50 judgment set measures; `badPairs` is the fix mechanism (issue #46).

## Findings

### A. Wrong or dead merge targets — fixed (mechanical)

| Merge | Was | Fixed to | Why |
|---|---|---|---|
| 100% bran | → bran bud (not in base) | bran flake | dangling target |
| seafood cocktail sauce | → seafood sauce (not in base) | ketchup | closest live generic (ketchup+horseradish) |
| toffee piece | → english toffee bit (deleted) | caramel | dead target |
| tomatillo salsa | → salsa (deleted) | salsa verde | tomatillo salsa IS salsa verde |
| chicken carcass | → chicken bone (not in base) | chicken | stock ingredient |
| ground chuck | → chuck (not in base) | beef | ground chuck = ground beef |
| salad green, salad leaf | → green salad (deleted #51) | lettuce | raw greens, not a prepared dish |
| queso fresco | → cottage cheese | panela cheese | fresh Mexican cheese ≠ cottage cheese |
| queso blanco | → fromage blanc | panela cheese | false friend — firm Mexican cheese ≠ French spread |
| fromage frais | → cottage cheese | fromage blanc | fromage frais ≈ fromage blanc |
| carob chip | → chocolate | carob powder | carob ≠ chocolate; carob powder is deployed |
| prune juice | → plum | prune | prune is deployed and is the right parent |
| red wine vinaigrette | → vinegar | vinaigrette | vinaigrette is deployed |
| baby back rib | → beef rib → beef | rib | baby backs are PORK — wrong species |
| dry mustard | → dijon mustard → mustard | mustard powder | dry mustard = mustard powder exactly |
| chili bean paste | → bean paste → bean (deleted) | hot bean paste | doubanjiang — Sichuan essential, was silently dying |
| asafoetida powder | deleted | merged → hing | same spice (hing is deployed), deg-67 signal recovered |
| simple syrup | deleted | merged → sugar syrup | identical thing; one was deleted, the other kept |
| miracle whip | deleted | merged → mayonnaise | brand rule (2026-07-12): map brands to generic |
| chicken bouillon granule | deleted AND merged | merged entry removed | contradiction; deleted wins anyway |

### B. Judgment calls — owner arbitration (see Applied section for outcomes)

1. **Flavourful fats lost**: ghee (deleted, deg 83 — distinct nutty clarified butter) and
   bacon fat (merged → "fat", which #51 deleted, so it silently died — smoky, real).
2. **Inconsistent siblings**: salsa deleted but salsa verde kept; italian dressing deleted but
   ranch dressing and vinaigrette kept; candied cherry deleted but candied orange kept.
3. **Zest asymmetry**: lemon zest merged into lemon, but orange zest deliberately kept
   separate (probe-protected). One of the two treatments is wrong.
4. **Distinct classics buried by merges**: basil pesto (→ basil — pesto is a major condiment);
   creme de cassis (→ currant — kir!); pumpkin pie spice (→ gingerbread, a plainly wrong
   target); citron (→ lemon — cédrat is its own citrus).

### C. Benign / no action

- 51 names validated AND later deleted, 187 validated AND later merged — the later decision
  wins; `validated` is only a record. Stale but harmless.
- 147 merge chains (A→B→C): apply-time resolution makes intermediate hops harmless; all
  final targets were checked via screen A. Curious-but-fine examples: chocolate milk →
  milk chocolate → chocolate; 10 inch flour tortilla → corn tortilla → tortilla.
- Big intentional deletions confirmed as sound: water, salt/flour/sugar families, oils,
  baking chemistry (yeast, baking soda, gelatin), cooking spray, ice, food coloring,
  mixes and doughs, cool whip/whipped topping (no honest generic in base — stay deleted).
- ~35 merges that end on now-deleted generics (nut, berry, ice cream, waffle…) are
  consistent deletions, not bugs. mincemeat → meat (deleted) noted: culinarily wrong merge,
  but both outcomes are deletion; left as is.
- Chile powders (pasilla, new mexico, chipotle powder…) → chili follows the owner's own
  chili powder → chili decision. Consistent, left as is.

## Applied 2026-07-13 (owner sign-off via session Q&A)

Section A applied in full. Section B outcomes per owner arbitration:

1. **Fats**: ghee and bacon fat stay gone — original deletions stand.
2. **Siblings**: salsa restored; candied orange deleted (matching candied cherry);
   italian dressing stays deleted.
3. **Zests**: orange zest merged into orange — both zests now fold into their fruit.
   The #44 probe that pinned orange zest's suppression was rewritten to pin the merge.
4. **Classics**: basil pesto, pumpkin pie spice and citron restored as their own
   ingredients (with taxonomy overrides); creme de cassis stays merged into currant.

Net effect on the deployed list: +4 restored (salsa, basil pesto, pumpkin pie spice,
citron), −2 merged/deleted (orange zest, candied orange), +2 recovered as merges rather
than deletions (asafoetida→hing, simple syrup→sugar syrup, miracle whip→mayonnaise add
signal, not names). Validator and all ranking probes pass.
