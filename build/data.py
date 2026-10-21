"""Single source of truth for BCH Taxi prices, tours and content.

Edit prices here, then run `python3 build/build.py` to regenerate every page.
"""

PHONE = "+353870330046"
PHONE_DISPLAY = "+353 87 033 0046"
EMAIL = "bachintaxi@gmail.com"
WHATSAPP = "https://wa.me/353870330046"

# Leave empty until the site has a live domain (e.g. "https://www.bchtaxi.ie").
# When set, the build adds canonical URLs and writes sitemap.xml.
SITE_URL = "https://web-production-95242.up.railway.app"

# Rates used by the price calculator and multi-day tours.
MULTI_DAY_RATE = 649   # per vehicle, per day
EXTRA_HOUR_RATE = 50   # per hour, whole booking
MAX_PASSENGERS = 8

# name, county/region, price, favourite, duration, approx drive from Dublin,
# short description, highlights, longer intro
TOURS = [
    dict(slug="giants-causeway", name="Giant's Causeway", region="Co. Antrim · Northern Ireland", area="North",
         price=600, fav=True, duration="12–13 hrs", drive="about 2 hrs 45 mins",
         desc="Head north across the border to 40,000 basalt columns on the Antrim coast, with Game of Thrones locations and a whiskey stop along the way.",
         highlights=["Giant's Causeway (UNESCO site)", "The Dark Hedges", "Carrick-a-Rede rope bridge (optional)",
                     "Bushmills Distillery", "Dunluce Castle", "Belfast sights & Titanic Quarter (optional)"],
         intro="The Causeway Coast is one of the great road trips of these islands. We head north on the motorway, cross into Northern Ireland and follow the coast past cliff-top castle ruins, the beech-tree tunnel of the Dark Hedges and the rope bridge at Carrick-a-Rede before reaching the hexagonal columns of the Giant's Causeway itself. It's a long day, so we build in plenty of breaks, and Belfast can be added on the way home."),
    dict(slug="ring-of-kerry", name="Ring of Kerry", region="Co. Kerry", area="South-West",
         price=460, fav=True, duration="11–12 hrs", drive="about 3 hrs 30 mins to Killarney",
         desc="The classic 179 km loop around the Iveragh Peninsula: lakes, mountain passes, harbour villages and the coast where Star Wars was filmed.",
         highlights=["Killarney National Park & Muckross House", "Ladies View & Moll's Gap", "Kenmare",
                     "Sneem, Waterville & Cahersiveen", "Skellig Ring", "Valentia Island detour (optional)"],
         intro="The Ring of Kerry packs lakes, mountains, beaches and colourful villages into a single loop. Starting from Killarney, we stop at the famous viewpoints of Ladies View and Moll's Gap, pass through Kenmare and Sneem, and follow the Atlantic coast around to Waterville. If time allows we add the quieter Skellig Ring, with views out to the Skellig islands."),
    dict(slug="cliffs-of-moher", name="Cliffs of Moher", region="Co. Clare", area="West",
         price=430, fav=True, duration="10–11 hrs", drive="about 3 hrs",
         desc="Stand 214 m above the Atlantic on Ireland's most famous cliffs, then drive through the Burren and stop in Doolin for some trad music.",
         highlights=["O'Brien's Tower viewpoint", "Cliffs visitor centre", "Doolin village", "The Burren drive", "Wild Atlantic Way coastline"],
         intro="Ireland's most visited natural wonder rises straight out of the Atlantic for 14 km along the Clare coast. We drive across the country, give you time on the cliff paths and at O'Brien's Tower, then take the scenic route home through the limestone landscape of the Burren, with a stop in the music village of Doolin."),
    dict(slug="glendalough-wicklow", name="Glendalough & Wicklow", region="Co. Wicklow", area="East",
         price=280, fav=False, duration="Half or full day", drive="about 1 hr 15 mins",
         desc="The closest escape from Dublin: a 6th-century monastic site in a glacial valley, mountain roads and Ireland's tallest waterfall.",
         highlights=["Glendalough monastic site & round tower", "Upper & Lower Lakes", "Sally Gap & Military Road",
                     "Powerscourt Waterfall", "Lough Tay ('Guinness Lake')", "Avoca woollen mill"],
         intro="The 'Garden of Ireland' is right on Dublin's doorstep. We climb into the Wicklow Mountains over the Sally Gap, stop above the dark waters of Lough Tay, and drop into Glendalough, where St Kevin's monastic city sits between two lakes. It works as a relaxed half day or a fuller day with Powerscourt and Avoca added."),
    dict(slug="the-burren", name="The Burren", region="Co. Clare", area="West",
         price=380, fav=False, duration="Full day", drive="about 2 hrs 45 mins",
         desc="A strange, beautiful limestone landscape packed with ancient tombs, caves and stone forts, and with rare flowers in the cracks.",
         highlights=["Poulnabrone Dolmen", "Aillwee Cave", "Burren National Park trails", "Caherconnell Stone Fort",
                     "Corcomroe Abbey", "Doolin & Kilfenora"],
         intro="The Burren looks like nowhere else in Ireland: grey limestone pavement stretching to the sea, with Arctic, Alpine and Mediterranean flowers growing side by side. We visit the Poulnabrone portal tomb, go underground at Aillwee Cave and finish at the coast, and it pairs easily with a stop at the Cliffs of Moher."),
    dict(slug="killarney-national-park", name="Killarney National Park", region="Co. Kerry", area="South-West",
         price=330, fav=False, duration="Half or full day", drive="about 3 hrs 30 mins",
         desc="Oak woods, three lakes and Ireland's only native red deer, plus castles, waterfalls and the lively town of Killarney.",
         highlights=["Muckross House & gardens", "Ross Castle", "Torc Waterfall", "Lakes of Killarney",
                     "Gap of Dunloe viewpoints", "Killarney town"],
         intro="Ireland's first national park wraps around the Lakes of Killarney. We visit Muckross House and its gardens, walk to Torc Waterfall, stop at Ross Castle on the lake shore and finish in Killarney town. It's ideal if you're staying in Kerry or want a gentler day than the full Ring."),
    dict(slug="slieve-league", name="Slieve League", region="Co. Donegal", area="North-West",
         price=560, fav=False, duration="12 hrs", drive="about 4 hrs",
         desc="Sea cliffs nearly three times the height of Moher, in wild Donegal and far from the crowds.",
         highlights=["Slieve League cliffs (601 m)", "Bunglas viewing point", "Glencolmcille folk village",
                     "Killybegs harbour", "Assaranca Waterfall & Maghera Caves", "Donegal Castle"],
         intro="For travellers who want drama without the crowds, Slieve League's cliffs drop 601 m into the Atlantic. We drive up to the Bunglas viewpoint, continue to the folk village at Glencolmcille and the waterfall at Assaranca, and stop in Donegal town on the way back."),
    dict(slug="achill-island", name="Achill Island", region="Co. Mayo", area="West",
         price=430, fav=False, duration="Full day", drive="about 3 hrs 45 mins",
         desc="Ireland's largest island: blue-flag beaches, towering cliffs, a deserted Famine village and the Atlantic Drive.",
         highlights=["Keem Bay", "Atlantic Drive", "Slievemore Deserted Village", "Croaghaun Cliffs", "Westport", "Croagh Patrick views"],
         intro="Achill is joined to the mainland by a short bridge but feels a world away. We follow the Atlantic Drive, drop down to the horseshoe beach at Keem Bay, walk among the stone cottages of the deserted village at Slievemore and stop in the Georgian town of Westport."),
    dict(slug="skellig-michael", name="Skellig Michael", region="Co. Kerry", area="South-West",
         price=600, fav=False, duration="10–11 hrs", drive="about 4 hrs 30 mins to Portmagee",
         desc="A cliff-top monastery 12 km out in the Atlantic, famous as Luke Skywalker's island hideaway. Landings run May to September, weather permitting.",
         highlights=["Skellig Michael boat trip (seasonal)", "Skellig Ring drive", "Portmagee harbour", "Valentia Island",
                     "Star Wars filming locations", "Cahergal stone fort"],
         intro="Skellig Michael's early Christian monastery clings to a rock far out in the Atlantic. Boats leave from Portmagee between May and September when the sea allows. Landing trips are limited and book up fast, so the boat is reserved separately with a licensed operator. On days the boats can't sail, we take in the Skellig Ring and Valentia Island instead."),
    dict(slug="rock-of-cashel", name="Rock of Cashel", region="Co. Tipperary", area="South",
         price=330, fav=False, duration="Half or full day", drive="about 1 hr 45 mins",
         desc="The hilltop seat of the Kings of Munster, with a medieval cathedral, a round tower and one of Ireland's best Norman castles nearby.",
         highlights=["Rock of Cashel cathedral & round tower", "Cormac's Chapel", "Hore Abbey", "Cahir Castle",
                     "Mitchelstown Cave (optional)", "Glen of Aherlow"],
         intro="The Rock of Cashel rises out of the Tipperary plains crowned by a ruined cathedral, a round tower and the Romanesque Cormac's Chapel. We pair it with Hore Abbey just below and the remarkably intact Cahir Castle, making an easy-paced day of Irish history within two hours of Dublin."),
    dict(slug="dingle-peninsula", name="Dingle Peninsula", region="Co. Kerry", area="South-West",
         price=460, fav=False, duration="Full day", drive="about 4 hrs 15 mins",
         desc="Slea Head Drive to the western edge of Europe, with beehive huts, the Blasket Islands and a colourful harbour town.",
         highlights=["Slea Head Drive", "Dingle town", "Beehive huts", "Blasket Islands viewpoint", "Conor Pass", "Gallarus Oratory & Inch Beach"],
         intro="Dingle is Kerry at its most Irish-speaking and most dramatic. We loop around Slea Head with views of the Blasket Islands, stop at the ancient beehive huts and the boat-shaped Gallarus Oratory, cross the Conor Pass, and leave time to wander the pubs and shops of Dingle town."),
    dict(slug="connemara-galway", name="Connemara & Galway", region="Co. Galway", area="West",
         price=400, fav=False, duration="Full day", drive="about 2 hrs 15 mins to Galway",
         desc="Galway's buzzing streets, then the mountains and lakes of Connemara, Kylemore Abbey and Ireland's only fjord.",
         highlights=["Galway city & Latin Quarter", "Connemara National Park", "Kylemore Abbey & gardens", "Sky Road", "Clifden", "Killary Fjord"],
         intro="West of Galway city the land opens into the bogs, lakes and mountains of Connemara. We stop at Kylemore Abbey and its walled garden, drive the Sky Road above Clifden and follow Killary Fjord, with time in Galway's Latin Quarter on the way in or out."),
]

AREAS = ["East", "South", "West", "South-West", "North-West", "North"]

# Sample multi-day routes, priced at MULTI_DAY_RATE per day.
MULTI_DAY = [
    dict(slug="west-coast-explorer", name="West Coast Explorer", days=3,
         summary="Galway, Connemara, the Burren and the Cliffs of Moher at a relaxed pace.",
         plan=["Dublin → Galway city, then Connemara, Kylemore Abbey and the Sky Road. Overnight in Galway or Clifden.",
               "Down the coast to the Burren, Poulnabrone Dolmen and Doolin. Overnight in Doolin or Lahinch.",
               "Morning at the Cliffs of Moher before the crowds, then home to Dublin."]),
    dict(slug="kerry-and-the-south-west", name="Kerry & the South-West", days=4,
         summary="The Rock of Cashel, Killarney, the Ring of Kerry and the Dingle Peninsula.",
         plan=["Dublin → Rock of Cashel and Cahir Castle → Killarney. Overnight in Killarney.",
               "The full Ring of Kerry loop with the Skellig Ring. Overnight in Killarney.",
               "Slea Head Drive around the Dingle Peninsula. Overnight in Dingle.",
               "Killarney National Park in the morning, then home to Dublin."]),
    dict(slug="causeway-coast-and-donegal", name="Causeway Coast & Donegal", days=3,
         summary="Belfast, the Giant's Causeway, Derry and the cliffs of Slieve League.",
         plan=["Dublin → Belfast and the Titanic Quarter → the Causeway Coast. Overnight near Bushmills or Portrush.",
               "Giant's Causeway, Carrick-a-Rede and Dunluce → Derry's city walls. Overnight in Derry or Donegal.",
               "Slieve League cliffs and Donegal town, then home to Dublin."]),
    dict(slug="wild-atlantic-way-grand-tour", name="Wild Atlantic Way Grand Tour", days=7,
         summary="A week down Ireland's west coast from Donegal to Kerry.",
         plan=["Dublin → Donegal town and Slieve League. Overnight in Donegal.",
               "Donegal → Sligo → Westport. Overnight in Westport.",
               "Achill Island and the Atlantic Drive. Overnight in Westport.",
               "Connemara, Kylemore Abbey and Clifden → Galway. Overnight in Galway.",
               "The Burren and the Cliffs of Moher → Kerry. Overnight in Killarney.",
               "The Ring of Kerry. Overnight in Killarney.",
               "Rock of Cashel on the way home to Dublin."]),
]

# Fixed airport fares: area, distance, to airport, from airport
AIRPORT_FARES = [
    ("Dublin 13", "10 km", 25, 30),
    ("Dublin City Centre", "12–15 km", 35, 40),
    ("Lucan", "20–25 km", 45, 50),
    ("Tallaght", "25–30 km", 50, 55),
    ("Dun Laoghaire", "25 km", 55, 60),
    ("Rathcoole", "32 km", 60, 65),
    ("Bray", "35 km", 65, 70),
]
LONG_TRANSFERS = [("Galway", 300), ("Cork", 350)]
