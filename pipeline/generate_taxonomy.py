#!/usr/bin/env python3
"""
Generate web/public/taxonomy.json — category + base-ingredient mapping for every
name in web/public/pairings.json (issue #41).

Output format (compact keys to keep the shipped file small):
    { "hash brown": {"c": "starch", "b": "potato"},
      "cinnamon":   {"c": "spice"} }

- "c" — one of CATEGORIES below
- "b" — optional culinary parent (preparation/derivative of another ingredient),
        used by the client for same-base variant suppression (issue #44)

Deterministic rules + hand-curated overrides. Re-run after ingredient renames:
    python pipeline/generate_taxonomy.py
Rules only ever ADD coverage; hand overrides (OVERRIDES / BASE_OVERRIDES) always win.
"""
import json
import os
import re

PAIRINGS = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'pairings.json')
OUTPUT   = os.path.join(os.path.dirname(__file__), '..', 'web', 'public', 'taxonomy.json')

CATEGORIES = [
    'meat', 'seafood', 'dairy', 'egg', 'vegetable', 'fruit', 'herb', 'spice',
    'starch', 'legume-nut', 'fat', 'condiment', 'sweet', 'beverage', 'alcohol',
    'other',
]

# ── Keyword vocabulary per category ──────────────────────────────────────────
# Matched against whole tokens (singularised). Order between categories is
# resolved by RULE_PRIORITY when a name hits several categories.

KEYWORDS = {
    'meat': """
        beef pork veal lamb mutton chicken turkey duck goose quail pheasant
        venison bison elk rabbit boar ham bacon pancetta prosciutto salami
        chorizo pepperoni sausage bratwurst kielbasa bologna hotdog frankfurter
        meatball meat steak brisket ribeye sirloin tenderloin chuck oxtail
        tripe liver giblet gizzard foie pastrami jerky spam liverwurst
        mortadella capicola guanciale speck poultry hen squab partridge
        drumstick drumette wiener charcuterie burger frog escargot snail
        buffalo deer squirrel bresaola soppressata pate mignon rib marrow
        sweetbread meatloaf pig goat kangaroo ostrich emu pheasant grouse
        guinea capon poussin cornish chateaubriand porterhouse t-bone
        shank hock trotter cheek tongue kidney heart neck rump loin
    """,
    'seafood': """
        fish salmon tuna cod halibut trout sardine anchovy herring mackerel
        tilapia flounder catfish snapper mahi bass swordfish sole haddock
        pollock perch pike eel monkfish grouper turbot branzino barramundi
        shrimp prawn lobster crab crawfish crayfish langoustine scampi clam
        oyster mussel scallop squid calamari octopus abalone caviar roe uni
        seafood surimi whitefish bluefish amberjack wahoo escolar smelt
        shark skate cuttlefish conch periwinkle whelk krill
        char carp hake kingfish butterfish walleye shad bream sturgeon
        rockfish cockle bonito tarama fillet mullet pompano orange-roughy
        john-dory dover kipper lox
    """,
    'dairy': """
        milk cream cheese butter yogurt yoghurt kefir buttermilk mascarpone
        ricotta mozzarella parmesan cheddar gouda brie feta gruyere camembert
        roquefort gorgonzola emmental asiago fontina pecorino manchego colby
        provolone velveeta paneer halloumi burrata stracciatella quark curd
        whey custard creme dairy gelato
    """,
    'egg': """egg yolk albumen meringue""",
    'vegetable': """
        onion garlic shallot leek scallion chive tomato potato carrot celery
        pepper cucumber zucchini courgette eggplant aubergine broccoli
        cauliflower cabbage spinach kale lettuce arugula endive radicchio
        watercress chard collard mushroom truffle asparagus artichoke fennel
        beet beetroot radish daikon turnip parsnip rutabaga kohlrabi jicama
        yam squash pumpkin okra corn maize pea sprout celeriac
        tomatillo salsify sunchoke cardoon nopales seaweed kelp nori wakame
        kombu bamboo taro cassava yuca plantain vegetable greens rapini
        broccolini pimento caper olive avocado horseradish wasabi shishito
        chayote fiddlehead ramp escarole frisee mizuna tatsoi bok choy
        pak choi choy edamame heart palm zucchini pickle sauerkraut kimchi
        gherkin cornichon giardiniera artichokes chili chile jalapeno
        jalapeño habanero serrano poblano anaheim chipotle pepperoncini
        rhubarb swede gourd morel gai-lan burdock mesclun salad kudzu
        konnyaku nori cress chicory broccoflower romanesco
    """,
    'fruit': """
        apple pear banana orange lemon lime grapefruit tangerine mandarin
        clementine pomelo kumquat yuzu citrus peach nectarine apricot plum
        prune cherry grape raisin currant sultana fig date strawberry
        blueberry raspberry blackberry cranberry gooseberry elderberry
        boysenberry huckleberry mulberry berry melon watermelon cantaloupe
        honeydew pineapple mango papaya guava lychee longan rambutan
        jackfruit passion persimmon pomegranate quince kiwi coconut
        starfruit dragonfruit tamarind fruit zest applesauce craisin
        maraschino calamansi bergamot lingonberry crabapple pawpaw
        barberry cloudberry loganberry acai goji physalis feijoa
        soursop cherimoya sapote plantain
    """,
    'herb': """
        basil oregano thyme rosemary parsley cilantro coriander mint sage
        dill tarragon marjoram chervil sorrel lovage lemongrass bay chamomile
        lavender verbena shiso epazote herb herbes borage hyssop savory
        fenugreek curry-leaf makrut kaffir peppermint spearmint angelica
        purslane mitsuba rose violet hibiscus dandelion chrysanthemum
        pandan wintergreen
    """,
    'spice': """
        cinnamon nutmeg clove allspice cardamom ginger turmeric cumin caraway
        paprika cayenne saffron sumac zaatar harissa achiote annatto ajwain
        asafoetida anise star-anise peppercorn vanilla salt seasoning spice
        masala curry five-spice chili-powder garam adobo dukkah baharat
        berbere shichimi togarashi furikake mace juniper grains-of-paradise
        galangal wattleseed amchur hing gumbo-file quatre-epices
        panch-phoron peri-peri dashida file
    """,
    'starch': """
        rice pasta spaghetti fettuccine linguine penne rigatoni fusilli
        rotini farfalle orzo macaroni lasagna ravioli tortellini gnocchi
        noodle ramen udon soba vermicelli couscous polenta grits oat barley
        quinoa millet buckwheat bulgur farro spelt rye wheat flour bread
        toast crouton cracker tortilla pita naan lavash matzo bagel muffin
        croissant pretzel waffle pancake crepe biscuit roll bun baguette
        brioche focaccia ciabatta sourdough dough crust pastry phyllo filo
        panko breadcrumb cornmeal semolina tapioca sago arrowroot starch
        cereal granola oatmeal hash-brown tater dumpling wonton gyoza
        potato-chip crostini rusk crispbread grain amaranth teff freekeh
        wrapper shell cone challah cornbread crumpet scone tostada tamale
        pierogi pastina perciatelli kasha sorghum masa pappadam sev
        lumpia panettone breadstick wheatberry wheatberries bran couscous
        pierogies grissini melba zwieback injera arepa pupusa
    """,
    'legume-nut': """
        bean lentil chickpea garbanzo soy soybean tofu tempeh miso edamame
        almond walnut pecan cashew pistachio hazelnut macadamia chestnut
        peanut groundnut pine-nut nut tahini hummus natto seitan
        pea-protein legume mung adzuki cannellini pinto fava lima navy
        kidney black-eyed sesame sunflower-seed pepita flaxseed chia hemp
        dal okara psyllium
    """,
    'fat': """
        oil lard tallow suet schmaltz ghee shortening margarine drippings
        crisco
    """,
    'condiment': """
        sauce ketchup catsup mustard mayonnaise mayo aioli vinegar relish
        chutney salsa pesto tapenade dressing marinade glaze gravy stock
        broth bouillon dashi demi-glace gochujang sriracha tabasco
        worcestershire hoisin teriyaki ponzu mirin fish-sauce soy-sauce
        sambal tzatziki guacamole extract paste puree concentrate rub
        brine bitters shrub liquid-smoke msg nutritional-yeast bouquet
        marmite vegemite condiment gremolata verjuice roux mole crema
        vinaigrette soup ketjap tamari umeboshi tapenade chimichurri
        za'atar essence
    """,
    'sweet': """
        sugar honey molasses treacle syrup agave stevia saccharin sweetener
        chocolate cocoa cacao caramel toffee butterscotch fudge marshmallow
        candy nougat praline marzipan jam jelly marmalade preserves compote
        curd-lemon dulce gumdrop licorice sprinkles frosting icing fondant
        cake cooky cookie brownie pie tart cobbler pudding custard-dessert
        ice-cream sorbet sherbet gelatin jello wafer graham ladyfinger
        macaroon meringue-dessert oreo twinkie snickers candy-bar
        piloncillo jaggery turbinado demerara muscovado ganache dragee
        molasses biscotti amaretti shortbread shortcake cheesecake
        gingerbread truvia ovaltine koshi-an dessert
    """,
    'beverage': """
        water juice soda cola lemonade coffee espresso tea matcha
        beverage drink nectar smoothie punch eggnog horchata kombucha
        seltzer tonic ginger-ale ginger-beer club-soda kool-aid gatorade
        milk-plant soymilk
    """,
    'alcohol': """
        wine beer ale lager stout porter pilsner cider champagne prosecco
        whiskey whisky bourbon scotch rum vodka tequila mezcal gin brandy
        cognac liqueur schnapps vermouth sake sherry port marsala kahlua
        amaretto cointreau curacao campari aperol absinthe pastis ouzo
        grappa limoncello frangelico chartreuse drambuie galliano midori
        lillet benedictine armagnac cachaca kirsch pisco aquavit anisette
        herbsaint pimms goldschlager liquor bitter chambord sambuca strega
    """,
}

# When a name matches several categories, the earlier category in this list wins
# unless a suffix rule (below) already decided.
RULE_PRIORITY = [
    'seafood', 'meat', 'egg', 'herb', 'spice', 'legume-nut', 'fat',
    'alcohol', 'beverage', 'sweet', 'condiment', 'starch', 'dairy',
    'fruit', 'vegetable',
]

# ── Suffix rules: the last word decides the category and often the base ──────
# (base = the name minus the suffix, when that remainder is itself an ingredient)
SUFFIX_CAT = {
    'oil': 'fat', 'butter': None, 'milk': None,
    'juice': 'beverage', 'nectar': 'beverage', 'soda': 'beverage',
    'tea': 'beverage', 'coffee': 'beverage', 'wine': 'alcohol',
    'beer': 'alcohol', 'liqueur': 'alcohol', 'brandy': 'alcohol',
    'vodka': 'alcohol', 'rum': 'alcohol', 'whiskey': 'alcohol',
    'sauce': 'condiment', 'paste': 'condiment', 'puree': 'condiment',
    'stock': 'condiment', 'broth': 'condiment', 'bouillon': 'condiment',
    'vinegar': 'condiment', 'dressing': 'condiment', 'extract': 'condiment',
    'concentrate': 'condiment', 'marinade': 'condiment', 'relish': 'condiment',
    'chutney': 'condiment', 'glaze': 'condiment', 'rub': 'spice',
    'seasoning': 'spice', 'powder': 'spice', 'salt': 'spice',
    'syrup': 'sweet', 'jam': 'sweet', 'jelly': 'sweet', 'honey': 'sweet',
    'preserves': 'sweet', 'marmalade': 'sweet', 'sugar': 'sweet',
    'flour': 'starch', 'bread': 'starch', 'noodle': 'starch',
    'pasta': 'starch', 'rice': 'starch', 'cracker': 'starch',
    'chip': 'starch', 'crumb': 'starch', 'crust': 'starch',
    'cereal': 'starch', 'meal': 'starch', 'starch': 'starch',
    'cheese': 'dairy', 'cream': None, 'yogurt': 'dairy',
    'zest': 'fruit', 'peel': 'fruit', 'rind': 'fruit',
    'seed': 'spice', 'leaf': 'herb', 'flake': None,
    'fat': 'fat', 'lard': 'fat', 'drippings': 'fat',
}

# Suffixes that imply the remainder is the culinary parent ("apple juice" → apple)
DERIVATIVE_SUFFIXES = {
    'zest', 'peel', 'rind', 'juice', 'nectar', 'fat', 'stock', 'broth',
    'bouillon', 'bone', 'skin', 'carcass', 'breast', 'thigh', 'wing', 'leg',
    'drumstick', 'liver', 'powder', 'paste', 'puree', 'extract', 'concentrate',
    'flour', 'starch', 'oil', 'butter', 'milk', 'cream', 'sauce', 'syrup',
    'seed', 'leaf', 'flake', 'chip', 'crumb', 'jam', 'jelly', 'preserves',
    'marmalade', 'vinegar', 'wine', 'liqueur', 'brandy', 'salt', 'sugar',
    'tea', 'soup', 'gravy', 'roe', 'meal', 'chunk', 'slice', 'wedge', 'half',
    'ring', 'stick', 'floret', 'sprig', 'stem', 'stalk', 'top', 'green',
}

# ── Hand overrides — always win ──────────────────────────────────────────────
OVERRIDES = {
    # cat only
    'egg': 'egg', 'quail egg': 'egg', 'duck egg': 'egg', 'egg white': 'egg',
    'egg yolk': 'egg', 'egg substitute': 'egg',
    'salt': 'spice', 'pepper': 'spice', 'black pepper': 'spice',
    'white pepper': 'spice', 'chili powder': 'spice',
    'bell pepper': 'vegetable', 'red pepper': 'vegetable',
    'green pepper': 'vegetable', 'yellow pepper': 'vegetable',
    'sweet pepper': 'vegetable', 'banana pepper': 'vegetable',
    'water': 'beverage', 'ice': 'beverage', 'espresso': 'beverage',
    'peanut butter': 'legume-nut', 'almond butter': 'legume-nut',
    'cashew butter': 'legume-nut', 'sunflower butter': 'legume-nut',
    'tahini': 'legume-nut', 'nutella': 'sweet',
    'coconut milk': 'condiment', 'coconut cream': 'condiment',
    'almond milk': 'beverage', 'soy milk': 'beverage', 'oat milk': 'beverage',
    'rice milk': 'beverage', 'buttermilk': 'dairy',
    'cream cheese': 'dairy', 'sour cream': 'dairy', 'heavy cream': 'dairy',
    'whipped cream': 'dairy', 'half and half': 'dairy',
    'ice cream': 'sweet', 'whipped topping': 'sweet',
    'cream of tartar': 'other', 'baking powder': 'other',
    'baking soda': 'other', 'yeast': 'other', 'gelatin': 'other',
    'xanthan gum': 'other', 'pectin': 'other', 'food coloring': 'other',
    'corn': 'vegetable', 'sweet corn': 'vegetable', 'corn on the cob': 'vegetable',
    'popcorn': 'starch', 'hash brown': 'starch',
    'french fry': 'starch', 'potato chip': 'starch', 'tater tot': 'starch',
    'mashed potato': 'starch',
    'butter': 'dairy', 'ghee': 'fat', 'margarine': 'fat',
    'honey': 'sweet', 'maple syrup': 'sweet',
    'wheat germ': 'starch', 'bran': 'starch',
    'olive': 'vegetable', 'olive oil': 'fat',
    'coconut': 'fruit', 'coconut oil': 'fat', 'coconut water': 'beverage',
    'chocolate': 'sweet', 'white chocolate': 'sweet', 'cocoa': 'sweet',
    'vanilla': 'spice', 'vanilla extract': 'spice', 'vanilla bean': 'spice',
    # Cooking alcohols: consumed as seasoning, not as drinks, in the recipe
    # corpus — classified condiment so they aren't globally damped as alcohol
    # (drinking wine, beer and spirits stay in 'alcohol').
    'mirin': 'condiment', 'cooking wine': 'condiment', 'sake': 'condiment',
    'rice wine': 'condiment', 'cooking sherry': 'condiment',
    'dry sherry': 'condiment', 'cream sherry': 'condiment',
    'sweet sherry': 'condiment', 'sherry wine': 'condiment',
    'marsala': 'condiment', 'sweet marsala wine': 'condiment',
    'madeira wine': 'condiment', 'port wine': 'condiment',
    'tawny port': 'condiment',
    'lemon grass': 'herb', 'ginger': 'spice', 'fresh ginger': 'spice',
    'galangal': 'spice', 'candlenut': 'legume-nut',
    'mushroom soup': 'condiment', 'chicken soup': 'condiment',
    'tomato soup': 'condiment', 'onion soup mix': 'condiment',
    'english muffin': 'starch',
    'alum': 'other', 'ascorbic acid': 'other', 'rennet': 'other',
    'certo': 'other', 'charcoal': 'other', 'liquid smoke': 'condiment',
    'maca': 'other', 'fat': 'fat', 'khoya': 'dairy', 'fromage blanc': 'dairy',
    'crema': 'dairy', 'montrachet': 'dairy', 'taleggio': 'dairy',
    'kefalotiri': 'dairy', 'caciocavallo': 'dairy',
    'angostura bitter': 'alcohol', 'eau de vie': 'alcohol',
    'grand marnier': 'alcohol', 'licor 43': 'alcohol',
    'tia maria': 'alcohol', 'triple sec': 'alcohol', 'rom': 'alcohol',
    'vin santo': 'alcohol', 'peppermint schnapps': 'alcohol',
    'kewra essence': 'condiment', 'rose water': 'condiment',
    'dried lily bud': 'vegetable', 'cactus piece': 'vegetable',
    'dried kasha': 'starch', 'grit': 'starch', 'roux': 'condiment',
    'green salad': 'vegetable', 'spring green': 'vegetable',
    'dandelion green': 'vegetable', 'dandelion flower': 'herb',
    'dried hibiscus flower': 'herb', 'blood orange': 'fruit',
    'candied orange': 'fruit', 'orange': 'fruit',
    "frog's leg": 'meat', 'pigs tail': 'meat', 'suckling pig': 'meat',
    'filet mignon': 'meat', 'pimiento': 'vegetable', 'quatre epices': 'spice',
    'hearts of palm': 'vegetable', 'heart of palm': 'vegetable',
    'creme fraiche': 'dairy',
    # ingredient audit (#51) — miscategorisations surfaced by the #52 swimlanes
    'scotch bonnet pepper': 'vegetable', 'bitter melon': 'vegetable',
    'root beer': 'beverage', 'ginger beer': 'beverage', 'ginger ale': 'beverage',
    'baileys irish cream': 'alcohol',
    'oyster mushroom': 'vegetable', 'chestnut mushroom': 'vegetable',
    'artichoke heart': 'vegetable', 'mustard green': 'vegetable',
    'cherry pepper': 'vegetable', 'lemon pepper': 'spice',
    'corn flake': 'starch', 'spaghetti squash': 'vegetable',
    'malted milk': 'sweet',  # renamed from ovaltine; a drink/baking powder, not dairy
    # curation audit (#49) — restored ingredients the token rules misfile
    'basil pesto': 'condiment', 'pesto sauce': 'condiment',
    'citron': 'fruit', 'pumpkin pie spice': 'spice',
    'sugar pumpkin': 'vegetable', 'black pudding': 'meat',
    'rice cake': 'starch', 'pastry cream': 'sweet',
}

BASE_OVERRIDES = {
    # derivative → culinary parent that token rules can't infer
    'hash brown': 'potato', 'tater tot': 'potato', 'french fry': 'potato',
    'potato chip': 'potato', 'mashed potato': 'potato', 'gnocchi': 'potato',
    'schmaltz': 'chicken', 'lard': 'pork', 'bacon fat': 'bacon',
    'suet': 'beef', 'tallow': 'beef',
    'guacamole': 'avocado', 'ketchup': 'tomato', 'catsup': 'tomato',
    'marinara sauce': 'tomato', 'tomato sauce': 'tomato', 'salsa': 'tomato',
    'hummus': 'chickpea', 'tahini': 'sesame seed',
    'applesauce': 'apple', 'apple sauce': 'apple', 'cider': 'apple',
    'apple cider': 'apple', 'raisin': 'grape', 'sultana': 'grape',
    'prune': 'plum', 'craisin': 'cranberry', 'sauerkraut': 'cabbage',
    'kimchi': 'cabbage', 'cabbage kimchi': 'cabbage', 'coleslaw': 'cabbage',
    'pickle': 'cucumber', 'gherkin': 'cucumber', 'cornichon': 'cucumber',
    'dill pickle': 'cucumber', 'pesto': 'basil', 'polenta': 'corn',
    'cornmeal': 'corn', 'grits': 'corn', 'popcorn': 'corn',
    'masa': 'corn', 'hominy': 'corn', 'oatmeal': 'oat', 'panko': 'bread',
    'breadcrumb': 'bread', 'crouton': 'bread', 'toast': 'bread',
    'buttermilk': 'milk', 'creme fraiche': 'cream', 'ghee': 'butter',
    'yuzu': None, 'mayonnaise': None, 'wasabi': None,
    'sesame oil': 'sesame seed', 'toasted sesame oil': 'sesame seed',
    'tofu': 'soybean', 'tempeh': 'soybean', 'miso': 'soybean',
    'soy sauce': 'soybean', 'edamame': 'soybean', 'natto': 'soybean',
    'mole': None, 'worcestershire sauce': None,
}

STOPWORDS = {
    'fresh', 'freshly', 'dried', 'dry', 'frozen', 'canned', 'cooked', 'raw',
    'ground', 'whole', 'large', 'small', 'baby', 'mini', 'jumbo', 'medium',
    'sweet', 'sour', 'hot', 'cold', 'warm', 'mild', 'spicy', 'smoked',
    'roasted', 'toasted', 'grilled', 'fried', 'boiled', 'baked', 'pickled',
    'candied', 'crystallized', 'salted', 'unsalted', 'sweetened',
    'unsweetened', 'seedless', 'boneless', 'skinless', 'organic', 'wild',
    'minced', 'chopped', 'sliced', 'diced', 'shredded', 'grated', 'crushed',
    'peeled', 'pitted', 'halved', 'melted', 'softened', 'packed', 'crumbled',
    'cubed', 'julienned', 'snipped', 'trimmed', 'drained', 'thawed', 'beaten',
    'sifted', 'divided', 'prepared', 'condensed', 'evaporated', 'granulated',
    'instant', 'quick', 'light', 'dark', 'red', 'green', 'yellow', 'white',
    'black', 'purple', 'golden', 'brown', 'pink', 'blue', 'orange',
    'style', 'mix', 'blend', 'piece', 'chunk', 'strip', 'and', 'of', 'the',
    'with', 'in', 'a', 'low', 'free', 'reduced', 'nonfat', 'lowfat',
    'italian', 'french', 'mexican', 'greek', 'spanish', 'asian', 'chinese',
    'japanese', 'thai', 'indian', 'english', 'german', 'cuban', 'korean',
}

_kw_to_cat = {}
for cat, words in KEYWORDS.items():
    for w in words.split():
        _kw_to_cat.setdefault(w.replace('-', ' '), []).append(cat)


def singular(w):
    if len(w) < 4:
        return w
    if w.endswith('ies'):
        return w[:-3] + 'y'
    if w.endswith('oes'):
        return w[:-2]
    # don't mangle words that only look plural (asparagus, couscous, molasses…)
    if w.endswith(('ss', 'us', 'is', 'sses')):
        return w
    if w.endswith('s'):
        return w[:-1]
    return w


def tokens(name):
    return [singular(t) for t in re.split(r'[\s\-/]+', name.lower()) if t]


def classify(name):
    if name in OVERRIDES:
        return OVERRIDES[name]
    if name.startswith('creme de ') or name.startswith('creme d'):
        return 'alcohol'   # creme de menthe/cacao/cassis — liqueurs, not dairy
    toks = tokens(name)
    # 1. suffix rule on the last meaningful token
    for t in reversed(toks):
        if t in STOPWORDS:
            continue
        cat = SUFFIX_CAT.get(t)
        if cat:
            return cat
        break
    # 2. keyword votes, resolved by priority. Match raw and singularised forms;
    #    only apply stopword filtering when the name has other tokens to vote.
    hits = set()
    raw_toks = [t for t in re.split(r'[\s\-/]+', name.lower()) if t]
    for raw, t in zip(raw_toks, toks):
        if t in STOPWORDS and len(toks) > 1:
            continue
        for form in (raw, t):
            for cat in _kw_to_cat.get(form, []):
                hits.add(cat)
    # two-word keyword phrases ("bok choy", "star anise")
    lower = ' '.join(toks)
    for phrase, cats in _kw_to_cat.items():
        if ' ' in phrase and phrase in lower:
            hits.update(cats)
    if hits:
        for cat in RULE_PRIORITY:
            if cat in hits:
                return cat
    return None


def find_base(name, all_names, cats):
    if name in BASE_OVERRIDES:
        return BASE_OVERRIDES[name]
    toks = tokens(name)
    if len(toks) < 2:
        return None
    # 1. derivative suffix: "apple juice" → "apple" (if that's an ingredient)
    if toks[-1] in DERIVATIVE_SUFFIXES:
        rest = ' '.join(toks[:-1])
        if rest in all_names and rest != name:
            return rest
    # 2. modifier variant: after stripping preparation/colour/size modifiers the
    #    name is identical to another ingredient ("smoked salmon" → "salmon",
    #    "green onion" → "onion"). Deliberately NOT plain containment — that
    #    would link siblings ("lima bean" → "bean" → suppressing black bean
    #    next to green bean), which is the category penalty's job (issue #43).
    tset = frozenset(toks) - STOPWORDS
    if not tset:
        return None
    best = None
    for other in all_names:
        if other == name:
            continue
        otoks = frozenset(tokens(other)) - STOPWORDS
        if otoks == tset and len(other) < len(name):
            if best is None or len(other) < len(best):
                best = other
    return best


def main():
    with open(PAIRINGS, encoding='utf-8') as f:
        names = json.load(f)['i']
    all_names = set(names)

    # pass 1: raw base per name; pass 2: resolve chains through the full map
    raw_base = {n: find_base(n, all_names, None) for n in names}
    result = {}
    for name in names:
        base = raw_base.get(name)
        seen = {name}
        while base and raw_base.get(base) and base not in seen:
            seen.add(base)
            base = raw_base[base]
        cat = classify(name)
        if cat is None and base:
            cat = classify(base)   # inherit from parent
        entry = {'c': cat or 'other'}
        if base:
            entry['b'] = base
        result[name] = entry

    with open(OUTPUT, 'w', encoding='utf-8') as f:
        json.dump(result, f, ensure_ascii=False, separators=(',', ':'))

    from collections import Counter
    dist = Counter(v['c'] for v in result.values())
    n_base = sum(1 for v in result.values() if 'b' in v)
    print(f"{len(result)} ingredients classified → {OUTPUT}")
    for cat, n in dist.most_common():
        print(f"  {cat:<12} {n}")
    print(f"  base assigned: {n_base}")


if __name__ == '__main__':
    main()
