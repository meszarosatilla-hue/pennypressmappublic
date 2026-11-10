#!/usr/bin/env python3
"""One-off: which other OpenStreetMap taggings could be pressed-coin machines in a country (default HU)."""
import collections, json, re, sys
sys.path.insert(0, __file__.rsplit("/", 1)[0])
from build import overpass  # noqa: E402

cc = sys.argv[1] if len(sys.argv) > 1 else "HU"
area = '[out:json][timeout:300];area["ISO3166-1"="%s"]["admin_level"="2"]->.a;' % cc
WORDS = re.compile(r"érme|erme|préselt|presel|emlékérem|emlékérme|pénzpréselő|souvenir|penny|elongated|münz|präg|medail|medal|coin", re.I)

# All vending machines (cheap: tag-indexed)
j = overpass(area + 'nwr(area.a)["amenity"="vending_machine"];out tags center;')
print("== vending machines: %d" % len(j["elements"]))
c = collections.Counter(el["tags"].get("vending", "<none>") for el in j["elements"])
for v, n in c.most_common(100):
    print("  %5d %s" % (n, v))
print("== vending machines with coin-ish words anywhere, but not vending=elongated_coin")
for el in j["elements"]:
    t = el["tags"]
    if t.get("vending") == "elongated_coin":
        continue
    if WORDS.search(" ".join("%s=%s" % kv for kv in t.items())):
        print("  %s%s %s" % (el["type"][0], el["id"], json.dumps(t, ensure_ascii=False)[:500]))
print("== vending machines without vending tag (sample)")
for el in [e for e in j["elements"] if "vending" not in e["tags"]][:80]:
    print("  %s%s %s" % (el["type"][0], el["id"], json.dumps(el["tags"], ensure_ascii=False)[:300]))

# Souvenir shops / attractions with coin words
j = overpass(area + 'nwr(area.a)["shop"="souvenir"];out tags center;')
print("== souvenir shops: %d" % len(j["elements"]))
for el in j["elements"]:
    t = el["tags"]
    if WORDS.search(" ".join("%s=%s" % kv for kv in t.items() if not kv[0].startswith("payment"))):
        print("  %s%s %s" % (el["type"][0], el["id"], json.dumps(t, ensure_ascii=False)[:400]))
