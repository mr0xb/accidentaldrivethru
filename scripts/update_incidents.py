#!/usr/bin/env python3
"""Pull new car-into-building incidents from 614NOW's dedicated RSS category feed.

New entries are appended to data/incidents.json with review:true, because the
article's publish date is not always the crash date and the feed title rarely
carries the address. A human fills in the blanks and drops the review flag.
"""
import json, pathlib, re, sys, urllib.request
from email.utils import parsedate_to_datetime
from xml.etree import ElementTree as ET

FEEDS = [
    "https://614now.com/category/hot-topics/car-crashing-into-building/feed",
]
UA = "accidentaldrivethru.com incident bot (+https://accidentaldrivethru.com)"
ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "incidents.json"

# Titles that match the feed but are not a crash (roundups, explainers).
SKIP = re.compile(r"\b(roundup|year in review|explain|why do|list of)\b", re.I)

KINDS = [
    ("restaurant", r"restaurant|pizza|diner|bbq|taco|cafe|coffee|bakery|kitchen"),
    ("bar",        r"\bbar\b|brewery|pub|wine|beer|tavern"),
    ("medical",    r"pharmacy|clinic|mammogram|dental|hospital|medical|urgent care"),
    ("bank",       r"bank|credit union"),
    ("home",       r"\bhome\b|house|garage|apartment|porch|residence"),
    ("retail",     r"store|shop|storefront|salon|boutique|market|grocery"),
    ("school",     r"school|library|daycare"),
    ("nonprofit",  r"nonprofit|church|arts hub|community center"),
]

def classify(title):
    low = title.lower()
    for kind, pat in KINDS:
        if re.search(pat, low):
            return kind
    return "other"

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()

def clean(title):
    title = re.sub(r"\s+", " ", title).strip()
    # Feed titles often lead with a quoted pull-quote; keep the crash clause.
    m = re.search(r"[:’\"]\s*(car|driver|watch|suv|truck)\b.*", title, re.I)
    return (m.group(0).lstrip(":’\" ") if m else title).strip()

def main():
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    seen = {i.get("url") for i in incidents}
    added = []

    for feed in FEEDS:
        try:
            root = ET.fromstring(fetch(feed))
        except Exception as e:
            print(f"feed failed: {feed}: {e}", file=sys.stderr)
            continue

        for item in root.iter("item"):
            link = (item.findtext("link") or "").strip()
            title = (item.findtext("title") or "").strip()
            if not link or link in seen or SKIP.search(title):
                continue
            try:
                pub = parsedate_to_datetime(item.findtext("pubDate")).date().isoformat()
            except Exception:
                continue
            incidents.append({
                "date": pub, "time": "", "name": clean(title), "address": "",
                "area": "Columbus", "kind": classify(title), "cause": "unknown",
                "note": "", "source": "614NOW", "url": link, "review": True,
            })
            seen.add(link)
            added.append(f"{pub}  {title[:70]}")

    if not added:
        print("no new incidents")
        return 0

    incidents.sort(key=lambda i: (i["date"], i.get("time") or ""), reverse=True)
    DATA.write_text(json.dumps(incidents, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"added {len(added)}:")
    for line in added:
        print("  " + line)
    return 0

if __name__ == "__main__":
    sys.exit(main())
