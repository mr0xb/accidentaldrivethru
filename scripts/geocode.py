#!/usr/bin/env python3
"""Geocode incidents and fetch the county/city outlines the map is drawn on.

Nominatim asks for at most one request a second and a real user agent, so this
caches every hit back into data/incidents.json and only looks up what is new.
Entries pinned to a street address are exact; entries pinned to a neighborhood
are approximate, and the map draws them hollow to say so.
"""
import json, pathlib, sys, time, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "incidents.json"
GEO  = ROOT / "data" / "geo.json"
UA   = "accidentaldrivethru.com incident map (+https://accidentaldrivethru.com)"
API  = "https://nominatim.openstreetmap.org/search?"

# Greater Columbus. "830 Bethel Rd" exists in other Ohio towns too, so every
# lookup is boxed and every result is re-checked against these bounds.
WEST, EAST, SOUTH, NORTH = -83.45, -82.55, 39.70, 40.35

def in_columbus(lat, lon):
    return SOUTH <= lat <= NORTH and WEST <= lon <= EAST

def get(params):
    url = API + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())
    
def query_for(inc):
    """Most specific location we can name, and how much to trust it."""
    if inc.get("address") and any(ch.isdigit() for ch in inc["address"]):
        return f'{inc["address"]}, Columbus, OH', "address"
    if inc.get("address"):
        return f'{inc["address"]}, Columbus, OH', "street"
    if inc.get("area") and inc["area"] not in ("Columbus", "Central Ohio"):
        return f'{inc["area"]}, Columbus, OH', "area"
    # No address and no neighborhood: a named business may still be findable.
    generic = ("wall", "garage", "business", "buildings", "restaurant", "bar", "home")
    name = (inc.get("name") or "").lower()
    if name and not any(g in name for g in generic):
        return f'{inc["name"]}, Columbus, OH', "name"
    return None, None

def simplify(points, tolerance):
    """Douglas-Peucker, so a 1100-point county outline ships as a few hundred."""
    if len(points) < 3:
        return points
    def dist(p, a, b):
        (x, y), (x1, y1), (x2, y2) = p, a, b
        dx, dy = x2 - x1, y2 - y1
        if dx == 0 and dy == 0:
            return ((x-x1)**2 + (y-y1)**2) ** 0.5
        t = max(0, min(1, ((x-x1)*dx + (y-y1)*dy) / (dx*dx + dy*dy)))
        return ((x - (x1+t*dx))**2 + (y - (y1+t*dy))**2) ** 0.5
    first, last = points[0], points[-1]
    worst, idx = 0, 0
    for i in range(1, len(points) - 1):
        d = dist(points[i], first, last)
        if d > worst:
            worst, idx = d, i
    if worst <= tolerance:
        return [first, last]
    return simplify(points[:idx+1], tolerance)[:-1] + simplify(points[idx:], tolerance)

def outline(name, tolerance):
    hits = get({"q": name, "format": "json", "polygon_geojson": 1, "limit": 1})
    if not hits or "geojson" not in hits[0]:
        return []
    g = hits[0]["geojson"]
    rings = g["coordinates"] if g["type"] == "Polygon" else max(g["coordinates"], key=lambda p: len(p[0]))
    ring = [(float(x), float(y)) for x, y in rings[0]]
    small = simplify(ring, tolerance)
    return [[round(x, 4), round(y, 4)] for x, y in small]

def main():
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    looked_up = 0

    for inc in incidents:
        if inc.get("lat") is not None or inc.get("geo") == "none":
            continue
        q, precision = query_for(inc)
        if not q:
            inc["geo"] = "none"
            continue
        try:
            hits = get({"q": q, "format": "json", "limit": 1, "countrycodes": "us",
                        "viewbox": f"{WEST},{NORTH},{EAST},{SOUTH}", "bounded": 1})
        except Exception as e:
            print(f"lookup failed for {q}: {e}", file=sys.stderr)
            continue
        looked_up += 1
        if hits and in_columbus(float(hits[0]["lat"]), float(hits[0]["lon"])):
            inc["lat"] = round(float(hits[0]["lat"]), 5)
            inc["lon"] = round(float(hits[0]["lon"]), 5)
            inc["geo"] = precision
            print(f'  {precision:8} {inc["name"][:34]:34} -> {inc["lat"]}, {inc["lon"]}')
        else:
            inc["geo"] = "none"
            print(f'  {"miss":8} {inc["name"][:34]}')
        time.sleep(1.1)

    DATA.write_text(json.dumps(incidents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if not GEO.exists():
        print("fetching outlines")
        geo = {
            "county": outline("Franklin County, Ohio", 0.004),
            "city":   outline("Columbus, Ohio", 0.003),
        }
        time.sleep(1.1)
        GEO.write_text(json.dumps(geo, separators=(",", ":")) + "\n", encoding="utf-8")
        print(f'  county: {len(geo["county"])} points, city: {len(geo["city"])} points')

    placed = sum(1 for i in incidents if i.get("lat"))
    print(f"{looked_up} looked up, {placed}/{len(incidents)} incidents placed")
    return 0

if __name__ == "__main__":
    sys.exit(main())
