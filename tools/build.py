#!/usr/bin/env python3
"""Pressed-coin (elongated coin) and souvenir-medal machines from OpenStreetMap, one file per country.

Usage:  python3 tools/build.py OUT_DIR [--old-index old/index.json] [--only HU,AT]

One worldwide Overpass query; the country of each machine comes from the Natural Earth 1:10m country
borders (public domain; NE_FILE=path uses a local copy).

Output:
  OUT_DIR/index.json   – list of countries with machine counts, checksum and last-change date
  OUT_DIR/<CC>.json    – the machines of one country (ISO 3166-1 alpha-2 code)

Data: © OpenStreetMap contributors, ODbL 1.0 (https://www.openstreetmap.org/copyright).
"""
import hashlib
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
]
UA = "pennypressmap-data/1.0 (+https://github.com/meszarosatilla-hue/pennypressmappublic)"

# Everything that can mean "a machine that presses a coin" or "a machine that mints a souvenir medal".
VENDING_QUERY = "elongated|pressed|penny|coin_press|souvenir_coin|souvenir_medal|medal|commemorative_coin|tourist_coin|token_press"
PRESSED = re.compile(r"elongated|(?<![a-z])pressed|penny|coin_press|token_press")  # not "compressed_air"
MEDAL = re.compile(r"souvenir_coin|souvenir_medal|medal|commemorative_coin|tourist_coin")
# Machines tagged only in free text (name / description / model), in several languages:
# "érmepréselő", "pénzérme-nyomó", "préselt érme", "Münzpresse", "penny press" → pressed;
# "emlékérme", "érem minta", "Medaille", "médaille" → medal.
TEXT_QUERY = ("rmeprés|rmepres|rme-prés|rmenyom|rme-nyom|préselt|preselt|emlékérm|emlekerm|érem minta|"
              "münzpress|münzpräg|pressed coin|pressed penny|penny press|elongated|souvenir coin|souvenir medal|medaille|médaille")
TEXT_PRESSED = re.compile(r"rmeprés|rmepres|rme-prés|rmenyom|rme-nyom|préselt|preselt|münzpress|pressed|penny|elongated", re.I)
TEXT_MEDAL = re.compile(r"emlékérm|emlekerm|érem|medaille|médaille|medal|souvenir coin|münzpräg", re.I)

# Tags that are of no use in the app.
DROP = re.compile(r"^(source(:.*)?|created_by|fixme|FIXME|note:.*|import(:.*)?|attribution|is_in.*|tiger:.*|osak:.*)$")

# Languages of the app: country names are also stored in these.
LANGS = ["en", "hu", "de", "fr", "es", "it", "pt", "nl", "pl", "cs", "sk", "ro"]


def overpass(query, attempts=6):
    data = urllib.parse.urlencode({"data": query}).encode()
    last = None
    for i in range(attempts):
        url = ENDPOINTS[i % len(ENDPOINTS)]
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=400) as r:
                body = r.read()
            j = json.loads(body)
            remark = j.get("remark", "")
            if "runtime error" in remark or "Query timed out" in remark or "out of memory" in remark:
                raise RuntimeError(remark)
            return j
        except Exception as e:  # noqa: BLE001 – retry on anything (timeouts, 429, 504, bad JSON)
            last = e
            wait = 10 * (i + 1)
            print("  ! %s: %s – újra %d mp múlva" % (url, str(e)[:160], wait), flush=True)
            time.sleep(wait)
    raise RuntimeError("Overpass failed: %s" % last)


NE_URL = "https://raw.githubusercontent.com/nvkelso/natural-earth-vector/master/geojson/ne_10m_admin_0_countries.geojson"


def load_borders(path=None):
    """Country polygons (Natural Earth 1:10m, public domain): [(code, name, names, bbox, rings)]."""
    if path and os.path.exists(path):
        gj = json.load(open(path, encoding="utf-8"))
    else:
        req = urllib.request.Request(NE_URL, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=300) as r:
            gj = json.loads(r.read())
    out = []
    for f in gj["features"]:
        pr = f["properties"]
        code = pr.get("ISO_A2_EH") or pr.get("ISO_A2")
        if not code or len(code) != 2 or not code.isalpha():
            continue
        g = f["geometry"]
        polys = g["coordinates"] if g["type"] == "MultiPolygon" else [g["coordinates"]]
        rings = []
        for poly in polys:
            for i, ring in enumerate(poly):
                xs = [pt[0] for pt in ring]
                ys = [pt[1] for pt in ring]
                rings.append((i == 0, (min(xs), min(ys), max(xs), max(ys)), ring))
        if not rings:
            continue
        xs = [r[1][0] for r in rings] + [r[1][2] for r in rings]
        ys = [r[1][1] for r in rings] + [r[1][3] for r in rings]
        names = {l: pr["NAME_" + l.upper()] for l in LANGS if pr.get("NAME_" + l.upper())}
        out.append((code.upper(), pr.get("NAME_EN") or pr.get("NAME") or code, names, (min(xs), min(ys), max(xs), max(ys)), rings))
    return out


def _in_ring(x, y, ring):
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _seg_d2(x, y, a, b):
    ax, ay, bx, by = a[0], a[1], b[0], b[1]
    dx, dy = bx - ax, by - ay
    L = dx * dx + dy * dy
    t = 0.0 if L == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L))
    px, py = ax + t * dx - x, ay + t * dy - y
    return px * px + py * py


def country_of(borders, lat, lon):
    x, y = lon, lat
    for code, _n, _ns, bb, rings in borders:
        if not (bb[0] <= x <= bb[2] and bb[1] <= y <= bb[3]):
            continue
        # Outer rings add, holes (lakes, enclaves) remove.
        inside = False
        for outer, rb, ring in rings:
            if rb[0] <= x <= rb[2] and rb[1] <= y <= rb[3] and _in_ring(x, y, ring):
                inside = outer
        if inside:
            return code
    # Piers, ships, small islands: the nearest country border within ~30 km.
    best, bestd = None, 0.3 ** 2
    for code, _n, _ns, bb, rings in borders:
        if not (bb[0] - 0.3 <= x <= bb[2] + 0.3 and bb[1] - 0.3 <= y <= bb[3] + 0.3):
            continue
        for _o, rb, ring in rings:
            if not (rb[0] - 0.3 <= x <= rb[2] + 0.3 and rb[1] - 0.3 <= y <= rb[3] + 0.3):
                continue
            for i in range(1, len(ring)):
                d = _seg_d2(x, y, ring[i - 1], ring[i])
                if d < bestd:
                    best, bestd = code, d
    return best


def kind(tags):
    v = tags.get("vending", "").lower()
    if PRESSED.search(v):
        return "pressed"
    if MEDAL.search(v):
        return "medal"
    text = " ".join(tags.get(k, "") for k in ("name", "description", "model", "note"))
    if v and v not in ("coin", "souvenir", "souvenirs"):
        return None  # a vending machine for something else that merely mentions coins
    if TEXT_PRESSED.search(text):
        return "pressed"
    # vending=coin in Hungary, Austria …: the machine mints a souvenir medal ("emlékérme")
    if v == "coin" or TEXT_MEDAL.search(text):
        return "medal" if v == "coin" or tags.get("amenity") == "vending_machine" else None
    return None


def machines_world():
    q = ('[out:json][timeout:900];('
         'nwr["vending"~"%s",i];'
         'nwr["amenity"="vending_machine"]["vending"="coin"];'
         'nwr["amenity"="vending_machine"]["description"~"%s",i];'
         'nwr["amenity"="vending_machine"]["name"~"%s",i];'
         'nwr["amenity"="vending_machine"]["model"~"%s",i];'
         ');out tags center meta;') % (VENDING_QUERY, TEXT_QUERY, TEXT_QUERY, TEXT_QUERY)
    items = []
    for el in overpass(q)["elements"]:
        t = el.get("tags", {})
        k = kind(t)
        if not k:
            continue
        if "lat" in el:
            lat, lon = el["lat"], el["lon"]
        elif "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:
            continue
        tags = {key: val for key, val in sorted(t.items()) if not DROP.match(key)}
        items.append({
            "id": el["type"][0] + str(el["id"]),
            "lat": round(lat, 7),
            "lon": round(lon, 7),
            "kind": k,
            "edited": (el.get("timestamp") or "")[:10],
            "tags": tags,
        })
    items.sort(key=lambda x: x["id"])
    return items


def main():
    args = [a for a in sys.argv[1:]]
    out = args[0]
    old_index = None
    only = None
    if "--old-index" in args:
        p = args[args.index("--old-index") + 1]
        if os.path.exists(p):
            try:
                old_index = {c["code"]: c for c in json.load(open(p, encoding="utf-8"))["countries"]}
            except Exception as e:  # noqa: BLE001
                print("régi index nem olvasható:", e)
    if "--only" in args:
        only = set(args[args.index("--only") + 1].split(","))
    os.makedirs(out, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    borders = load_borders(os.environ.get("NE_FILE"))
    print("országhatárok:", len(borders), flush=True)
    # A country can have several parts (France + Clipperton …): the name comes from the largest one.
    names = {}
    for code, name, cnames, bb, _r in sorted(borders, key=lambda c: (c[3][2] - c[3][0]) * (c[3][3] - c[3][1])):
        names[code] = (name, cnames)
    world = machines_world()
    print("automaták a világon:", len(world), flush=True)
    by = {}
    lost = 0
    for it in world:
        code = it.pop("cc", None) or country_of(borders, it["lat"], it["lon"])
        if not code:
            lost += 1
            continue
        by.setdefault(code, []).append(it)
    print("ország nélkül (nyílt tengeren):", lost, flush=True)

    index = []
    total = 0
    failed = []
    for code in sorted(by):
        if only and code not in only:
            continue
        items = by[code]
        name, cnames = names.get(code, (code, {}))
        doc = {"code": code, "name": name, "items": items}
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        sha = hashlib.sha1(body).hexdigest()
        updated = now
        if old_index and code in old_index and old_index[code].get("sha1") == sha:
            updated = old_index[code].get("updated", now)
        doc["updated"] = updated
        doc["license"] = "ODbL-1.0"
        doc["attribution"] = "© OpenStreetMap contributors"
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        open(os.path.join(out, code + ".json"), "wb").write(body)
        lats = [i["lat"] for i in items]
        lons = [i["lon"] for i in items]
        index.append({
            "code": code,
            "name": name,
            "names": cnames,
            "count": len(items),
            "pressed": sum(1 for i in items if i["kind"] == "pressed"),
            "medal": sum(1 for i in items if i["kind"] == "medal"),
            "bytes": len(body),
            "sha1": sha,
            "updated": updated,
            "bbox": [min(lats), min(lons), max(lats), max(lons)],
        })
        total += len(items)
        print("%s %-30s %5d" % (code, name[:30], len(items)), flush=True)

    index.sort(key=lambda c: c["code"])
    idx = {
        "version": 1,
        "generated": now,
        "source": "OpenStreetMap",
        "license": "ODbL-1.0",
        "attribution": "© OpenStreetMap contributors",
        "total": total,
        "countries": index,
    }
    json.dump(idx, open(os.path.join(out, "index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("összesen: %d automata, %d ország; sikertelen: %s" % (total, len(index), ",".join(failed) or "-"))
    open(os.path.join(out, "failed.txt"), "w").write("\n".join(failed))
    # Almost nothing found = Overpass trouble: better keep the old release than publish an empty one.
    if old_index and total < 0.5 * sum(c["count"] for c in old_index.values()):
        print("::error::Gyanúsan kevés automata (%d) – a régi kiadás marad." % total)
        sys.exit(1)


if __name__ == "__main__":
    main()
