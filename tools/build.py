#!/usr/bin/env python3
"""Pressed-coin (elongated coin) and souvenir-medal machines from OpenStreetMap, one file per country.

Usage:  python3 tools/build.py OUT_DIR [--old-index old/index.json] [--only HU,AT]

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
PRESSED = re.compile(r"elongated|pressed|penny|coin_press|token_press")
MEDAL = re.compile(r"souvenir_coin|souvenir_medal|medal|commemorative_coin|tourist_coin")

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


def countries():
    q = '[out:json][timeout:300];area["ISO3166-1"~"^[A-Z]{2}$"]["admin_level"="2"];out tags;'
    res = {}
    for el in overpass(q)["elements"]:
        t = el.get("tags", {})
        code = t.get("ISO3166-1")
        if not code or code in res:
            continue
        names = {l: t["name:" + l] for l in LANGS if t.get("name:" + l)}
        res[code] = {"name": t.get("name:en") or t.get("name") or code, "names": names}
    return res


def kind(vending):
    v = vending.lower()
    if PRESSED.search(v):
        return "pressed"
    if MEDAL.search(v):
        return "medal"
    return None


def machines(code):
    q = (
        '[out:json][timeout:300];area["ISO3166-1"="%s"]["admin_level"="2"]->.a;'
        'nwr(area.a)["vending"~"%s",i];out tags center meta;' % (code, VENDING_QUERY)
    )
    items = []
    for el in overpass(q)["elements"]:
        t = el.get("tags", {})
        k = kind(t.get("vending", ""))
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

    cs = countries()
    print("országok:", len(cs), flush=True)
    index = []
    total = 0
    failed = []
    for code in sorted(cs):
        if only and code not in only:
            continue
        try:
            items = machines(code)
        except Exception as e:  # noqa: BLE001
            print("%s HIBA: %s" % (code, e), flush=True)
            failed.append(code)
            # Keep the previous file for this country (the workflow re-uses the old asset).
            if old_index and code in old_index:
                index.append(old_index[code])
                total += old_index[code]["count"]
            continue
        time.sleep(1.5)
        if not items:
            continue
        doc = {
            "code": code,
            "name": cs[code]["name"],
            "items": items,
        }
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
        entry = {
            "code": code,
            "name": cs[code]["name"],
            "names": cs[code]["names"],
            "count": len(items),
            "pressed": sum(1 for i in items if i["kind"] == "pressed"),
            "medal": sum(1 for i in items if i["kind"] == "medal"),
            "bytes": len(body),
            "sha1": sha,
            "updated": updated,
            "bbox": [min(lats), min(lons), max(lats), max(lons)],
        }
        index.append(entry)
        total += len(items)
        print("%s %-30s %5d" % (code, cs[code]["name"][:30], len(items)), flush=True)

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
    # Too many failures = Overpass trouble: better keep the old release than publish a half one.
    if len(failed) > 20:
        sys.exit(1)


if __name__ == "__main__":
    main()
