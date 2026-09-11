#!/usr/bin/env python3
"""Walk 614NOW's car-crashing-into-building archive and pull every incident.

The RSS feed only exposes the ten most recent posts, so the daily job alone can
never see history. This walks the category's archive pages, reads each article
once (cached on disk), and pulls what the prose actually states: the crash date,
the time of day, a street address, the vehicle. Anything it guesses is flagged
review:true — the extractor is reading English, not a database.
"""
import html, json, pathlib, re, sys, time, urllib.request
from datetime import datetime, timedelta

ROOT  = pathlib.Path(__file__).resolve().parent.parent
DATA  = ROOT / "data" / "incidents.json"
CACHE = ROOT / "data" / ".cache"
BASE  = "https://614now.com/category/hot-topics/car-crashing-into-building/page/{}/"
UA    = "accidentaldrivethru.com archive reader (+https://accidentaldrivethru.com)"

MONTHS = ("January February March April May June July August September October "
          "November December").split()

AREAS = ["Clintonville", "German Village", "Franklinton", "Grandview", "Hilliard",
         "Westerville", "Dublin", "Bexley", "Whitehall", "Reynoldsburg", "Gahanna",
         "Upper Arlington", "Short North", "Olde Towne East", "Linden", "Hilltop",
         "Westgate", "Merion Village", "Victorian Village", "Weinland Park",
         "Polaris", "Northland", "Marble Cliff", "Grove City", "Pickerington",
         "Powell", "Worthington", "Canal Winchester", "Groveport", "New Albany",
         "Blacklick", "Obetz", "Italian Village", "Arena District", "Brewery District",
         "Downtown", "Easton", "Dublin", "Delaware", "Galloway", "Lewis Center"]

KINDS = [("restaurant", r"restaurant|pizza|diner|bbq|taco|café|cafe|coffee|bakery|deli|eatery|grill"),
         ("bar",        r"\bbar\b|brewery|\bpub\b|wine|beer|tavern|nightclub|lounge"),
         ("medical",    r"pharmacy|clinic|mammogram|dental|dentist|hospital|medical|urgent care|physical therapy"),
         ("bank",       r"\bbank\b|credit union"),
         ("home",       r"\bhome\b|\bhouse\b|garage|apartment|porch|residence|duplex|condo"),
         ("school",     r"school|library|daycare|university|campus"),
         ("nonprofit",  r"nonprofit|church|arts hub|community center|food pantry"),
         ("retail",     r"store|shop\b|storefront|salon|boutique|market|grocery|barber|laundromat|vape|smoke shop|gas station|carryout")]

CAUSES = [("drunk",      r"\bOVI\b|\bDUI\b|drunk|impaired|intoxicat"),
          ("hit & run",  r"fled|hit[- ]and[- ]run|took off|ran from|stolen"),
          ("medical",    r"medical emergency|suffered a|seizure|passed out|health episode"),
          ("pedal error",r"gas pedal|mistook the|accelerator|wrong pedal"),
          ("parking",    r"trying to park|attempting to park|parking spot|pulled forward"),
          ("reverse",    r"in reverse|backed into|backing"),
          ("delivery",   r"delivery driver|DoorDash|Uber Eats|food delivery"),
          ("police chase", r"pursuit|chase|fleeing police")]

ADDRESS = re.compile(
    r"\b(\d{2,5}\s+(?:[NSEW]\.?\s+)?[A-Z][A-Za-z.’']*"
    r"(?:\s+[A-Z][A-Za-z.’']*){0,3}\s+"
    r"(?:Rd|Road|St|Street|Ave|Avenue|Blvd|Boulevard|Dr|Drive|Ln|Lane|Pkwy|Parkway|Way|Hwy|Highway|Pike|Court|Ct)\.?)\b")
CLOCK = re.compile(r"\b(1[0-2]|[1-9])(?::([0-5]\d))?\s*(a\.m\.|p\.m\.|am|pm|AM|PM)")
VEHICLE = re.compile(
    r"\b(Buick|Ford|Chevrolet|Chevy|Honda|Toyota|Nissan|Jeep|Dodge|Ram|GMC|Kia|Hyundai|"
    r"Subaru|Mazda|Lexus|Cadillac|Chrysler|Volkswagen|BMW|Mercedes|Audi|Tesla|Lincoln|"
    r"Mitsubishi|Acura|Infiniti|Volvo)\b(?:\s+([A-Z][A-Za-z0-9-]+))?")

SKIP = re.compile(r"\b(roundup|year in review|explain|why do|list of|best of|petition|"
                  r"almost crashes|near miss|nearly crashes)\b", re.I)

# 614NOW drops sponsor blocks inside the article body. Left in, the sponsor's
# city ("City of Dublin") gets read as the crash location.
AD = re.compile(r'<article class="custom-614[^"]*".*?</article>', re.S)
NOISE = re.compile(r"BROUGHT TO YOU BY|gtag\(.*?\);", re.S)


def fetch(url, cache_name=None):
    if cache_name:
        cached = CACHE / cache_name
        if cached.exists():
            return cached.read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode("utf-8", "replace")
    if cache_name:
        CACHE.mkdir(parents=True, exist_ok=True)
        (CACHE / cache_name).write_text(text, encoding="utf-8")
    time.sleep(1.0)
    return text


def article_links():
    """Every article URL in the category, oldest page last."""
    seen, page = [], 1
    while page < 30:
        try:
            listing = fetch(BASE.format(page))
        except Exception as e:
            print(f"  page {page}: {e}")
            break
        found = re.findall(r'href="(https://614now\.com/20\d{2}/[a-z0-9-]+/[a-z0-9/-]+)"', listing)
        fresh = [u for u in dict.fromkeys(found) if u not in seen]
        if not fresh:
            break
        seen.extend(fresh)
        print(f"  page {page}: {len(fresh)} links")
        page += 1
    return seen


def plain_text(page):
    m = re.search(r'class="[^"]*entry-content[^"]*"[^>]*>(.*?)<footer', page, re.S)
    body = m.group(1) if m else page
    body = AD.sub(" ", body)
    body = re.sub(r"<script.*?</script>|<style.*?</style>", " ", body, flags=re.S)
    text = html.unescape(re.sub(r"<[^>]+>", " ", body))
    text = re.sub(r"\s+", " ", NOISE.sub(" ", text)).strip()
    # The related-posts rail sits above the footer and mentions other suburbs.
    return re.split(r"Related Posts|More from 614|You might also like", text)[0].strip()


def crash_date(text, published):
    """Prefer a date the article states outright; fall back to the publish date."""
    m = re.search(r"\bOn ((?:%s)\s+\d{1,2})" % "|".join(MONTHS), text)
    if m:
        for year in (published.year, published.year - 1):
            try:
                guess = datetime.strptime(f"{m.group(1)} {year}", "%B %d %Y")
            except ValueError:
                continue
            if guess <= published + timedelta(days=2):
                return guess.date(), True
    if re.search(r"\byesterday\b", text[:400], re.I):
        return (published - timedelta(days=1)).date(), True
    return published.date(), False


def first_match(pairs, text):
    for label, pattern in pairs:
        if re.search(pattern, text, re.I):
            return label
    return None


def parse(url, page):
    text = plain_text(page)
    title = html.unescape(re.search(r"<title>(.*?)</title>", page, re.S).group(1))
    title = re.sub(r"\s*[-|]\s*614NOW.*$", "", title).strip()
    title = re.sub(r"^(Another|Videos?|Watch|Photos?|Update|Look Inside)\s*:?\s+", "", title).strip()
    title = title[:1].upper() + title[1:]   # the strip can leave a lowercase lede
    if SKIP.search(title):
        return None

    pub = re.search(r'article:published_time" content="([\d-]+T[\d:]+)', page)
    if not pub:
        return None
    published = datetime.fromisoformat(pub.group(1))
    date, dated = crash_date(text, published)

    clock = CLOCK.search(text)
    when = ""
    if clock:
        hour = int(clock.group(1)) % 12
        if clock.group(3).lower().startswith("p"):
            hour += 12
        when = f"{hour:02d}:{clock.group(2) or '00'}"

    address = ADDRESS.search(text)
    vehicle = VEHICLE.search(text)
    # Earliest mention wins, so the neighborhood named in the lede beats one
    # that turns up later in a "this keeps happening" paragraph.
    hits = [(m.start(), a) for a in AREAS
            for m in [re.search(r"\b%s\b" % re.escape(a), text)] if m]
    area = min(hits)[1] if hits else "Columbus"

    lede = re.split(r"(?<=[.!?]) ", text)[0][:180] if text else ""

    haystack = title + " " + text[:900]
    return {
        "date": date.isoformat(), "time": when,
        "name": title, "address": address.group(1) if address else "",
        "area": area,
        "kind": first_match(KINDS, haystack) or "other",
        "cause": first_match(CAUSES, text) or "unknown",
        "vehicle": " ".join(p for p in vehicle.groups() if p) if vehicle else "",
        "note": lede, "source": "614NOW", "url": url,
        "review": True, "dated": dated,
    }


def main():
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    known = {i.get("url") for i in incidents}
    # Same crash, different outlet: date plus street address is enough to tell.
    seen_scene = {(i["date"], i["address"].lower()) for i in incidents if i.get("address")}

    print("walking the archive")
    links = article_links()
    print(f"{len(links)} articles in the category, {len(known)} already known")

    added = 0
    for url in links:
        if url in known:
            continue
        slug = url.rstrip("/").rsplit("/", 1)[-1][:80] + ".html"
        try:
            page = fetch(url, slug)
        except Exception as e:
            print(f"  skip {url}: {e}", file=sys.stderr)
            continue
        record = parse(url, page)
        if not record:
            continue
        scene = (record["date"], record["address"].lower())
        if record["address"] and scene in seen_scene:
            print(f'  dup  {record["date"]}  {record["name"][:46]} (already have it)')
            continue
        if record["address"]:
            seen_scene.add(scene)
        incidents.append(record)
        known.add(url)
        added += 1
        print(f'  {record["date"]}  {record["area"]:16} {record["name"][:52]}')

    incidents.sort(key=lambda i: (i["date"], i.get("time") or ""), reverse=True)
    DATA.write_text(json.dumps(incidents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"added {added}, {len(incidents)} total")
    return 0


if __name__ == "__main__":
    sys.exit(main())
