"""js/fares.js: the instant airport fare matched from the From/To addresses.
Runs the pure JS functions in Node (skipped if Node isn't installed)."""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
NODE = shutil.which("node")
FARES = {"airport": [{"area": "Dublin 13", "to": 25, "from": 30},
                     {"area": "Dublin City Centre", "to": 35, "from": 40},
                     {"area": "Lucan", "to": 45, "from": 50},
                     {"area": "Bray", "to": 65, "from": 70}],
         "long": [{"area": "Galway", "price": 300}]}
AIRPORT = {"label": "Dublin Airport, Terminal 1", "lat": 53.4273, "lon": -6.244}


def match(frm, to):
    js = ("const F=require(%s);process.stdout.write(JSON.stringify(F.matchFare(%s,%s,%s)))"
          % (json.dumps(str(ROOT / "js" / "fares.js")), json.dumps(frm), json.dumps(to), json.dumps(FARES)))
    return json.loads(subprocess.run([NODE, "-e", js], capture_output=True, text=True, check=True).stdout)


pytestmark = pytest.mark.skipif(not NODE, reason="node not installed")


def test_to_and_from_airport_by_town():
    lucan = {"label": "12 Main Street, Lucan, County Dublin", "city": "Lucan", "type": "house"}
    assert match(lucan, AIRPORT) == {"area": "Lucan", "dir": "to", "price": 45}
    assert match(AIRPORT, lucan) == {"area": "Lucan", "dir": "from", "price": 50}


def test_eircode_routing_keys():
    d13 = {"label": "5 Grange Road, Baldoyle, D13 R2X8", "city": "Dublin", "postcode": "D13 R2X8", "type": "house"}
    assert match(d13, AIRPORT)["area"] == "Dublin 13"
    d02 = {"label": "Merrion Square, Dublin, D02 XY45", "city": "Dublin", "postcode": "D02 XY45", "type": "street"}
    assert match(d02, AIRPORT)["area"] == "Dublin City Centre"


def test_long_transfer_and_typed_text():
    assert match(AIRPORT, {"label": "Eyre Square, Galway"}) == {"area": "Galway", "dir": "from", "price": 300}


def test_no_fixed_fare():
    assert match({"label": "Kells, County Meath", "city": "Kells"}, AIRPORT) is None   # unknown area
    assert match({"label": "Lucan"}, {"label": "Bray"}) is None                       # not an airport trip
    street = {"label": "Bray Road, Foxrock", "name": "Bray Road", "type": "street", "city": "Dublin"}
    assert match(street, AIRPORT) is None                                             # a street name is not a town


def test_airport_by_coordinates_and_google_flag():
    near = {"label": "Swords Road", "lat": 53.428, "lon": -6.245}
    assert match(near, {"label": "Bray"})["dir"] == "from"
    santry = {"label": "Dublin Airport Business Park, Santry, Dublin 9", "lat": 53.4036, "lon": -6.242,
              "is_airport": "false", "sublocality": "Santry", "locality": "Dublin 9"}
    assert match({"label": "Bray"}, santry) is None                      # Google says not the airport
    assert match({"label": "Bray"}, {"label": "Dublin Airport Business Park"}) is None
    t1 = {"label": "Dublin Airport, Collinstown", "is_airport": "true", "lat": 53.4265, "lon": -6.2499}
    assert match({"label": "Bray"}, t1)["dir"] == "to"


def test_google_components():
    # Google details: Eircode routing key and locality / sublocality
    d13 = {"label": "Grange Road, Baldoyle, Dublin 13, D13 R2X8", "postcode": "D13 R2X8",
           "locality": "Dublin 13", "sublocality": "Baldoyle", "lat": 53.399, "lon": -6.127}
    assert match(d13, AIRPORT) == {"area": "Dublin 13", "dir": "to", "price": 25}
    lucan = {"label": "Main Street, Lucan, Co. Dublin, K78 X2Y4", "postcode": "K78 X2Y4", "locality": "Lucan"}
    assert match(lucan, AIRPORT)["price"] == 45
