#!/usr/bin/env python3
"""Inject data/incidents.json into index.html between the DATA markers.

The page ships its data inline so it works from any host, from file://, and
from a copy pasted anywhere else. index.html stays the only file to deploy.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "incidents.json"
GEO  = ROOT / "data" / "geo.json"
PAGE = ROOT / "index.html"
START, END = "<!-- DATA:START -->", "<!-- DATA:END -->"

def main():
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    incidents.sort(key=lambda i: (i["date"], i.get("time") or ""), reverse=True)
    blob = json.dumps(incidents, separators=(",", ":"), ensure_ascii=False)
    if "</script" in blob:
        print("refusing to inject: data contains a script close tag", file=sys.stderr)
        return 1

    html = PAGE.read_text(encoding="utf-8")
    if START not in html or END not in html:
        print("index.html is missing the DATA markers", file=sys.stderr)
        return 1
    head, rest = html.split(START, 1)
    _, tail = rest.split(END, 1)
    geo = json.loads(GEO.read_text(encoding="utf-8")) if GEO.exists() else {}
    geoblob = json.dumps(geo, separators=(",", ":"))

    block = (f'{START}\n'
             f'<script id="incidents" type="application/json">{blob}</script>\n'
             f'<script id="geo" type="application/json">{geoblob}</script>\n'
             f'{END}')
    PAGE.write_text(head + block + tail, encoding="utf-8")
    placed = sum(1 for i in incidents if i.get("lat"))
    print(f"injected {len(incidents)} incidents ({placed} mapped), newest {incidents[0]['date']}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
