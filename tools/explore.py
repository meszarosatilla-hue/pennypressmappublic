#!/usr/bin/env python3
"""One-off: which other OpenStreetMap taggings could be pressed-coin machines in a country (default HU)."""
import collections, json, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from build import overpass  # noqa: E402

cc = sys.argv[1] if len(sys.argv) > 1 else "HU"
area = '[out:json][timeout:600];area["ISO3166-1"="%s"]["admin_level"="2"]->.a;' % cc

j = overpass(area + 'nwr(area.a)["vending"];out tags;')
c = collections.Counter(el["tags"].get("vending") for el in j["elements"])
print("== vending values (%d objects)" % len(j["elements"]))
for v, n in c.most_common(80):
    print("  %5d %s" % (n, v))

WORDS = "érme|ermepr|préselt|emlékérem|emlékérme|emlekerme|pénzpréselő|souvenir.?coin|penny|elongated|münzpr|prägeautomat|medail|medal"
for key in ["name", "description", "note", "brand", "operator", "model", "shop", "souvenir"]:
    j = overpass(area + 'nwr(area.a)["%s"~"%s",i];out tags center;' % (key, WORDS))
    print("== %s ~ words: %d" % (key, len(j["elements"])))
    for el in j["elements"][:60]:
        t = el["tags"]
        print("  %s%s %s" % (el["type"][0], el["id"], json.dumps({k: t[k] for k in list(t)[:14]}, ensure_ascii=False)))

j = overpass(area + 'nwr(area.a)[~"elongated|penny|pressed_coin|souvenir_coin|coin_press"~"."];out tags center;')
print("== keys with elongated/penny: %d" % len(j["elements"]))
for el in j["elements"][:60]:
    print("  %s%s %s" % (el["type"][0], el["id"], json.dumps(el["tags"], ensure_ascii=False)[:400]))
