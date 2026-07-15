# Ingredient image audit — replacement worklist (issue #48)

All 806 deployed tiles were scored 1–5 for accuracy + appeal (full scores: `pipeline/image_audit.csv`).
171 tiles scored ≤2. Direct Wikipedia access is blocked by the environment's egress policy, so the
re-fetch runs in the `fetch-images.yml` workflow. Resolution of the 171:

- **4 pinned files** — `image_overrides.json` names an exact free-licensed Commons file
  (WebSearch-sourced) for the flagship commons.
- **113 scan** — `{"title": ..., "scan": true}`: the fetcher now inspects *all* images in the
  article and picks the most relevant culinary-form one (new `scan` mode in `fetch_images.py`), instead
  of blindly taking the article's lead image. A scan that finds nothing usable falls back to the emoji.
- **54 skip** — no clean free photo of the correct form, or scanning would re-grab a wrong
  image (live animal, wrong variety/colour, jam-smear, generic bottle wall, brand logo, pure abstraction).

After the workflow runs, review the picks on `ingredient-images-assets` before merging — scan choices are
unverified until fetched.

## Pinned to a specific Commons file

- **black pepper** → `Black Peppercorns.jpg`
- **garlic** → `Garlic bulbs and cloves.jpg`
- **peppercorn** → `Black Peppercorns.jpg`
- **star anise** → `Star anise.jpg`

## Scan (article inspected for its best culinary image)

- achiote → *Annatto*
- acorn squash → *Acorn squash*
- ajwain → *Ajwain*
- alligator meat → *Alligator meat*
- allspice → *Allspice*
- almond flour → *Almond meal*
- amarula cream liqueur → *Amarula*
- asian chili sauce → *Sriracha*
- bamboo shoot → *Bamboo shoot*
- barberry → *Berberis*
- beer → *Lager*
- benedictine → *Bénédictine*
- bitter melon → *Momordica charantia*
- black bread → *Pumpernickel*
- black eyed pea → *Black-eyed pea*
- brown sugar → *Brown sugar*
- buckwheat groat → *Kasha*
- burdock root → *Arctium*
- buttercup squash → *Cucurbita maxima*
- calamari → *Fried squid*
- candlenut → *Aleurites moluccanus*
- cannellini bean → *Cannellini bean*
- cantaloupe → *Muskmelon*
- caramel → *Caramel candy*
- carob powder → *Carob*
- cashew → *Cashew*
- cashew nut → *Cashew*
- cassava → *Cassava*
- celery seed → *Celery*
- cereal → *Breakfast cereal*
- cherry flavored liqueur → *Cherry Heering*
- chestnut → *Chestnut*
- chestnut flour → *Chestnut*
- chia seed → *Chia seed*
- chickpea → *Chickpea*
- chihuahua cheese → *Queso Chihuahua*
- chili garlic sauce → *Sambal oelek*
- chili paste → *Gochujang*
- chili sauce → *Sambal*
- chuck roast → *Chuck steak*
- conch → *Lobatus gigas*
- corn → *Sweet corn*
- cotija cheese → *Cotija cheese*
- crawfish → *Crayfish as food*
- curacao → *Curaçao (liqueur)*
- curd → *Cheese curd*
- daikon radish → *Daikon*
- date → *Date palm*
- duck stock → *Stock (food)*
- fava bean → *Broad bean*
- filet mignon → *Filet mignon*
- frog's leg → *Frog legs*
- galangal → *Galangal*
- ginkgo nut → *Ginkgo biloba*
- grape → *Table grape*
- greek yogurt → *Strained yogurt*
- green chili → *Anaheim pepper*
- green mango → *Mango*
- green peppercorn → *Black pepper*
- ground meat → *Ground beef*
- ham hock → *Pork knuckle*
- hash brown → *Hash browns*
- hazelnut flavored liqueur → *Frangelico*
- hijiki seaweed → *Hijiki*
- hubbard squash → *Cucurbita maxima*
- huckleberry → *Huckleberry*
- kaffir lime leaf → *Kaffir lime*
- kasseri cheese → *Kasseri*
- kelp → *Kelp*
- khoya → *Khoa*
- liquor → *Distilled beverage*
- liver → *Liver (food)*
- lobster → *Lobster as food*
- marshmallow → *Marshmallow*
- masa harina → *Masa*
- napa cabbage → *Napa cabbage*
- nigella seed → *Nigella sativa*
- onion seed → *Nigella sativa*
- papaya → *Papaya*
- parsnip → *Parsnip*
- passion fruit → *Passiflora edulis*
- peri peri → *Bird's eye chili*
- potato flake → *Instant mashed potatoes*
- psyllium → *Psyllium*
- pudding → *Chocolate pudding*
- quark → *Quark (dairy product)*
- quinoa → *Quinoa*
- ramp → *Allium tricoccum*
- raspberry → *Raspberry*
- rosemary → *Rosemary*
- safflower oil → *Safflower*
- salsify → *Salsify*
- saskatoon berry → *Amelanchier alnifolia*
- sausage → *Sausage*
- smoked tofu → *Tofu*
- sorghum → *Sorghum*
- spearmint → *Spearmint*
- spicy sausage → *Chorizo*
- spring green → *Spring greens*
- suckling pig → *Suckling pig*
- sugar → *Sucrose*
- sweet pea → *Pea*
- szechuan hot bean sauce → *Doubanjiang*
- tamarind paste → *Tamarind*
- taro root → *Taro*
- teff → *Teff*
- vanilla → *Vanilla*
- vinaigrette → *Vinaigrette*
- wakame seaweed → *Wakame*
- wasabi → *Wasabi*
- white pepper → *Black pepper*
- winter melon → *Wax gourd*
- yellow pear tomato → *Pear tomato*

## Kept as skip (emoji fallback)

adobo sauce, ancho chili, apricot jam, brine, brown rice syrup, browning sauce, cajun seasoning, char siu sauce, crabapple, daikon sprout, dandelion green, demi glace, dried lily bud, duck fat, fat, fig jam, fruit jam, garlic oil, golden beet, green chili paste, green tomato, ground elk, jam, konnyaku, lumpia skin, maggi seasoning, malt vinegar, onion paste, orange extract, orange flower water, peach jam, pheasant, pickle juice, pineapple syrup, pomegranate molasses, pomegranate syrup, ponzu sauce, poultry, rabbit, red wine vinegar, rice krispies, rice vinegar, rice wine, sherry wine, sloe gin, squirrel, tabasco sauce, turnip green, veal, vegemite, verjuice, vinegar, white vinegar, yacon syrup
