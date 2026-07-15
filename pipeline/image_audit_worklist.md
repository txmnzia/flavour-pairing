# Ingredient image audit — replacement worklist (issue #48)

All 806 deployed tiles were scored 1–5 for accuracy + appeal. Full scores: `pipeline/image_audit.csv`.
171 tiles scored ≤2 and are queued for replacement, resolved three ways:

- **39 article-swaps** — override added in `image_overrides.json` pointing at a better Wikipedia article; re-fetch via the `fetch-images.yml` workflow, then review on `ingredient-images-assets`.
- **99 skipped** — no good free-licensed photo of the correct form exists; `{"skip": true}` reverts them to the emoji tile (an existing tile must be deleted by hand).
- **33 manual** — the subject is correct but the cutout is mangled; an article swap can't fix that. Needs a hand-picked image via `web/public/images.html` (upload / URL).

## Manual-source needed (hand-pick an image)

- **acorn squash** — ghost blocks on correct acorn squash
- **bamboo shoot** — dark/halo on correct shoot
- **black eyed pea** — single tiny pea
- **black pepper** — article gives leaves; needs peppercorns
- **brown sugar** — halo + mixed sugars; needs clean brown sugar
- **chestnut** — article gives a leaf; needs chestnuts
- **chia seed** — faint ghost; needs seed pile
- **chickpea** — single blob; needs chickpea pile
- **cotija cheese** — ghost halos
- **daikon radish** — motion-blur
- **date** — poor cutout; existing override Date palm
- **fava bean** — sparse/ghost; needs broad beans
- **frog's leg** — messy; needs clean frog legs
- **garlic** — HIGH PRIORITY: whole plant; needs bulbs/cloves
- **greek yogurt** — blob-in-liquid; needs bowl of greek yogurt
- **hash brown** — faint ghost
- **huckleberry** — dark ghost; needs berry cluster
- **marshmallow** — grey ghost blobs
- **napa cabbage** — ghost halo
- **papaya** — floral ghost artifact overlaid
- **parsnip** — seed umbel; needs the root
- **peppercorn** — article gives leaves; needs peppercorns
- **quinoa** — plant head; needs the grain
- **raspberry** — mis-cut; needs raspberries
- **rosemary** — blurry flowers; needs herb sprig
- **sausage** — unclear cut; needs sausages
- **smoked tofu** — white tofu; needs brown smoked tofu
- **spearmint** — aloe-like; needs mint leaves
- **star anise** — HIGH PRIORITY: leaves; needs star pods
- **suckling pig** — ghosty; needs roast pig
- **tamarind paste** — dark scattered; needs paste/pods
- **taro root** — murky; needs the corm
- **vanilla** — flower; needs the pods/beans

## Article-swaps queued (verify lead image on the assets branch)

- achiote → *Annatto*
- asian chili sauce → *Sriracha*
- beer → *Lager*
- benedictine → *Bénédictine*
- black bread → *Pumpernickel*
- buckwheat groat → *Kasha*
- calamari → *Fried squid*
- cannellini bean → *Cannellini bean*
- cantaloupe → *Muskmelon*
- caramel → *Caramel candy*
- cereal → *Breakfast cereal*
- cherry flavored liqueur → *Cherry Heering*
- chili garlic sauce → *Sambal oelek*
- chili paste → *Gochujang*
- chili sauce → *Sambal*
- conch → *Lobatus gigas*
- corn → *Sweet corn*
- crawfish → *Crayfish as food*
- curacao → *Curaçao (liqueur)*
- curd → *Cheese curd*
- duck stock → *Stock (food)*
- grape → *Table grape*
- green chili → *Anaheim pepper*
- green mango → *Mango*
- ground meat → *Ground beef*
- ham hock → *Pork knuckle*
- hazelnut flavored liqueur → *Frangelico*
- liquor → *Distilled beverage*
- liver → *Liver (food)*
- lobster → *Lobster as food*
- peri peri → *Bird's eye chili*
- pudding → *Chocolate pudding*
- quark → *Quark (dairy product)*
- ramp → *Allium tricoccum*
- spicy sausage → *Chorizo*
- spring green → *Spring greens*
- sugar → *Sucrose*
- sweet pea → *Pea*
- szechuan hot bean sauce → *Doubanjiang*
