# Ingredient Audit — issue #51

Audited set: the **deployed** ingredient list (base 3,517 − curation = **1,038** as of 2026-07-12),
derived by running `apply_curation_json.py` on a copy. Degrees/strengths below come from the
deployed pairing table. Names already curated out (e.g. *green chilies*, *cream of chicken soup*)
are not re-listed here.

Legend: **merge A→B** = A's pairings absorbed by B (curation.json `merged`); **delete** =
removed from deployed list (curation.json `deleted`); **recat** = category fix in
`generate_taxonomy.py` OVERRIDES (affects swimlane placement only, not the ingredient list).

---

## 1. Clear-cut fixes (no judgment call needed)

### 1a. Duplicates, synonyms, typos — merge (17)

| From | To | Why |
|---|---|---|
| rom | rum | typo import artifact |
| chili pepper | chili | same thing, both huge (deg 235/239) |
| pimiento | pimento | spelling |
| habanero | habanero pepper | same thing |
| soya milk | soymilk | spelling |
| deer | venison | same meat |
| escargot | snail | same thing (FR translation covers *escargot*) |
| calamari | squid | same animal |
| swede | rutabaga | same vegetable |
| sultana | raisin | sultana = golden raisin (your "too niche" example) |
| sticky rice | glutinous rice | same thing |
| mochi rice | glutinous rice | same thing |
| cashew nut | cashew | same thing |
| white cheese | cheese | vague variant |
| light cheese | cheese | vague variant (deg 1) |
| cloud ear mushroom | wood ear mushroom | same fungus |
| haricot bean | navy bean | same bean |
| dry onion | onion | preparation, not an ingredient |
| yellow pear tomato | cherry tomato | its taxonomy base (*red pear tomato*) isn't even deployed |

### 1b. Non-food / additives — delete (8)

`charcoal` · `alum` · `ascorbic acid` · `certo` (brand pectin) · `xanthan gum` · `rennet` ·
`psyllium` · `maca`

This is the entire deployed `other` category plus two stragglers — none contributes flavour
pairing value. (`msg` is NOT in this list: it is a real flavour ingredient; see §2b.)

### 1c. Miscategorisations — recat (17)

These became painfully visible with the #52 swimlanes (wrong lane placement):

| Ingredient | Is | Should be |
|---|---|---|
| scotch bonnet pepper | alcohol | vegetable |
| bitter melon | alcohol | vegetable |
| root beer | alcohol | beverage |
| ginger beer | alcohol | beverage |
| ginger ale | spice | beverage |
| baileys irish cream | dairy | alcohol |
| oyster mushroom | seafood | vegetable |
| chestnut mushroom | legume-nut | vegetable |
| artichoke heart | meat | vegetable |
| mustard green | condiment | vegetable |
| cherry pepper | fruit | vegetable |
| lemon pepper | fruit | spice |
| corn flake | vegetable | starch |
| spaghetti squash | starch | vegetable |
| sugar pumpkin | sweet | vegetable |
| black pudding | sweet | meat |
| rice cake | sweet | starch |
| pastry cream | starch | sweet |

---

## 2. Rules needing your arbitration

### 2a. Variant granularity — "how many chilis?"

Deployed chili/pepper family (≈20): chili, red chile, green chili, jalapeno, chipotle chile,
ancho chili, serrano pepper, habanero pepper, scotch bonnet pepper, bird chile, thai pepper,
cubanelle pepper, piquillo pepper, pepperoncini pepper, banana pepper, aleppo pepper,
sansho pepper, cherry pepper, cayenne pepper (spice).

**Proposed rule (moderate):** keep a variety when it has a *distinct culinary identity you'd
seek out* (chipotle = smoky, ancho = raisiny, habanero = fruity-hot, aleppo = Middle-Eastern,
sansho = Japanese); merge colour/vagueness variants into the parent; merge true synonyms.

Moderate merge list: red chile→chili, green chili→chili, bird chile→thai pepper,
cherry pepper→pimento, cubanelle pepper→bell pepper, banana pepper→pepperoncini pepper.

Same rule applied to the other proliferating families:
- **beans**: pink bean→pinto bean, anasazi bean→pinto bean, romano bean→green bean,
  wax bean→green bean, flageolet bean→cannellini bean *(flag: flageolet is classic French —
  keep if you cook it)*, chili bean→delete (ambiguous American canned product)
- **mushrooms**: white mushroom→button mushroom, black mushroom→shiitake mushroom
- **squash**: hubbard/buttercup/delicata→winter squash, pattypan→summer squash
- **rice**: red rice→rice (black rice kept: distinct nutty identity)
- **scallops**: sea scallop→scallop (bay scallop kept: genuinely different, sweeter)
- **cheeses**: left alone — nearly every deployed cheese is flavour-distinct; the long tail
  (kefalotiri, mizithra, asadero…) is niche but not wrong. Revisit only if lanes feel cluttered.

*Aggressive alternative:* single "chili" + jalapeno/chipotle only; single "bean" + chickpea/lentil.
Loses real information (a Thai curry wants bird's eye, not ancho) — not recommended.

### 2b. Hyper-processed & brands — where's the line?

**Proposed rule:** an ingredient earns its place if it contributes a **distinct flavour you would
shop for**, regardless of processing level. Fish sauce, miso, worcestershire, tahini, gochujang
are processed and essential — they stay. Delete when it is:

- **(a) a brand with a generic equivalent**: velveeta cheese, rice krispies, karo syrup,
  hershey's syrup, truvia, ovaltine, pickapeppa sauce, dashida, maggi seasoning
  *(flag: maggi is iconic in several cuisines — your call)*, guinness stout→merge to beer.
  Kept: baileys, campari, grand marnier, angostura (a brand IS the flavour in cocktails); nutella
  (distinct enough); marmite/vegemite (distinct flavour).
- **(b) a prepared end-product, not a building block**: meatloaf, meatball, pound cake,
  sponge cake, cheesecake, brownie, shortcake, macaroon, tamale, dumpling, pierogies, tostada,
  waffle, pancake, crepe, fish cake, coleslaw, green salad, soup, refried bean.
  Kept after owner review: spam (a genuine ingredient in Okinawan/Hawaiian cooking —
  spam musubi, spam sushi).
  Kept deliberately: gingerbread, ladyfinger, amaretti, biscotti, crouton, english muffin
  (recipe *components* with distinct flavour — tiramisu, tuna melt…), and all sauces/condiments
  (tzatziki, guacamole, tapenade are pairing-relevant).

### 2c. Too-generic terms — delete or keep?

**Pure category words with no shopping identity — propose delete (15):**
meat, poultry, seafood, nut, seed, berry, fat, liquor, liqueur, soup, root vegetable,
spring green, ground meat, smoked meat, candied fruit.

**Culinary generics people actually cook with — propose keep:**
fish, cheese, wine, bean, stock, broth, pepper, sausage, curry, melon, squash, gravy, masala.
("fish" is how recipes talk about white fish generally; "cheese" and "wine" are top-40
ingredients. Deleting them would throw away real pairing signal.)

### 2d. Flavourless staples (pasta, rice, bread) — your idea from the issue

Your idea — *"recommend them only in a specific category for carbs"* — **is effectively what
the #52 swimlanes now do**: pasta/rice/bread/noodle appear only inside the "Starches" lane and
no longer dilute the rest. Deleting them would also break genuine signal (tomato→pasta is a
golden-pair consistency probe).

Options:
1. **Keep as-is** — the lane already isolates them (recommended).
2. Additionally damp starch scores globally (like alcohol's 0.6) so the Starches lane sorts
   lower. Would need one probe updated intentionally.
3. Delete the plain staples — not recommended (breaks real pairings).

---

## 3. Niche long tail (degree ≤ 3, 56 names) — handled by the rules above

Deletes fall out of §1b/§2b/§2c (certo, rennet, ovaltine, black pudding is a recat…).
Of the rest, propose deleting the obscure-with-no-signal: butterfish, rockfish fillet, hake fillet,
walleye, kingfish, sea bream (merge→sea bass?), saskatoon berry, barberry, pawpaw, mulberry,
crabapple, sunflower sprout, tatsoi, cardoon, sev, sago, teff, kewra essence, panch phoron,
methi leaf (→merge fenugreek leaf), winter melon, gourd, angelica, chamomile flower,
dandelion flower, dried hibiscus flower, herbsaint, licor 43, goldschlager, porter (→merge beer),
st. germain elderflower liqueur (→merge elderflower liqueur), jasmine tea (→merge tea),
cucumber juice, cherry syrup, pigs tail, suckling pig (→merge pork), hubbard squash (§2a),
crumpet & scone (kept: real British bakery staples — arbitration-light), jackfruit (kept:
rising ingredient), spelt & amaranth kept (real grains), prickly pear (kept: distinct),
elderberry (kept: distinct), lotus seed (kept: dim sum staple)… full list applied per your
§2 answers.

---

## Estimated outcome

Applying §1 + moderate §2 answers ≈ **−95 to −110 names** → roughly **930 deployed
ingredients**, every lane populated by things you'd actually shop for.

## Applied 2026-07-12 (owner sign-off via session Q&A)

- §1 applied in full: 19 merges, 8 non-food deletes, 18 recats (incl. *pastry cream*).
- §2a applied at **moderate with owner tolerance**: *flageolet bean*, *red rice* and
  *black mushroom* kept as distinct ingredients ("black mushroom doesn't mean shiitake").
- §2b + §2c applied as proposed; **maggi seasoning kept** per owner.
- §2d: no change — the #52 Starches lane is the implementation of the "carbs category" idea.
- §3 tail applied as written.

Net: 42 merges + 81 deletes in `pipeline/curation.json` → deployed list **1,038 → 915**
(spam restored after owner review 2026-07-12: used as a real ingredient in Okinawan/Hawaiian
cooking).
`validate_pairings.py` and all 27 ranking probes pass unchanged.

## Not in scope here

- Pair-level correctness (bad edges) — that's issue #49.
- The eval pool (#50/#53) references some names that would be merged/deleted; the metrics
  scripts resolve names through curation the same way the app does, but the annotation set
  should be re-pooled after a big curation wave.
