#!/usr/bin/env python3
"""Render assets/og.png: the share card, with today's day count baked in.

Regenerated on every scrape run so a shared link always shows a live number
instead of a screenshot from whenever the site was built.
"""
import datetime as dt, json, pathlib, sys, urllib.request
from PIL import Image, ImageDraw, ImageFont

ROOT  = pathlib.Path(__file__).resolve().parent.parent
DATA  = ROOT / "data" / "incidents.json"
OUT   = ROOT / "assets" / "og.png"
FONTS = ROOT / ".fonts"

W, H = 1200, 630
INK, PANEL, HAZARD, ALERT, MUTED = "#1A1813", "#FBF8F0", "#F0B400", "#D2401E", "#6E6A5C"

# Bungee for the display type, JetBrains Mono for everything else — same pair
# the site uses. JetBrains ships as a variable font; we pick a weight below.
FACES = {
    "display": "https://github.com/google/fonts/raw/main/ofl/bungee/Bungee-Regular.ttf",
    "body":    "https://github.com/google/fonts/raw/main/ofl/jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf",
}
FALLBACK = ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"]

def face(kind, size, weight=600):
    FONTS.mkdir(exist_ok=True)
    local = FONTS / f"{kind}.ttf"
    if not local.exists():
        try:
            req = urllib.request.Request(FACES[kind], headers={"User-Agent": "og-card"})
            with urllib.request.urlopen(req, timeout=30) as r:
                local.write_bytes(r.read())
        except Exception as e:
            print(f"font download failed ({kind}): {e}", file=sys.stderr)
    for path in [local, *map(pathlib.Path, FALLBACK)]:
        if path.exists():
            try:
                font = ImageFont.truetype(str(path), size)
            except Exception:
                continue
            if kind == "body":
                try:
                    font.set_variation_by_axes([weight])
                except Exception:
                    pass   # static fallback face, nothing to vary
            return font
    return ImageFont.load_default()

def main():
    incidents = json.loads(DATA.read_text(encoding="utf-8"))
    incidents.sort(key=lambda i: (i["date"], i.get("time") or ""), reverse=True)
    latest = incidents[0]
    when = dt.datetime.fromisoformat(latest["date"] + "T" + (latest.get("time") or "12:00") + ":00")
    days = max(0, (dt.datetime.now() - when).days)

    img = Image.new("RGB", (W, H), PANEL)
    d = ImageDraw.Draw(img)

    # hazard tape, top and bottom
    for y0, y1 in ((0, 26), (H - 26, H)):
        d.rectangle([0, y0, W, y1], fill=HAZARD)
        for x in range(-80, W + 80, 72):
            d.polygon([(x, y1), (x + 36, y1), (x + 36 + 26, y0), (x + 26, y0)], fill=INK)

    d.text((64, 74), "ACCIDENTALDRIVETHRU.COM", font=face("body", 30), fill=MUTED)
    d.text((64, 116), "Days since a car crashed", font=face("display", 54), fill=INK)
    d.text((64, 180), "into a building in Columbus", font=face("display", 54), fill=ALERT)

    # the number, on odometer tiles
    digits, tile, gap, top = f"{min(days, 999):03d}", 132, 14, 268
    big = face("display", 132)
    for n, ch in enumerate(digits):
        x = 64 + n * (tile + gap)
        d.rounded_rectangle([x, top, x + tile, top + 176], radius=8, fill=INK)
        box = d.textbbox((0, 0), ch, font=big)
        d.text((x + (tile - (box[2] - box[0])) / 2 - box[0],
                top + (176 - (box[3] - box[1])) / 2 - box[1]), ch, font=big, fill=HAZARD)
        d.line([x, top + 88, x + tile, top + 88], fill=PANEL, width=2)

    body, small = face("body", 34), face("body", 27)
    tx = 64 + 3 * (tile + gap) + 26
    d.text((tx, top + 24), "Last one:", font=small, fill=MUTED)
    d.text((tx, top + 56), latest["name"][:26], font=body, fill=INK)
    d.text((tx, top + 98), when.strftime("%b %-d, %Y"), font=small, fill=MUTED)
    if latest.get("area"):
        d.text((tx, top + 130), latest["area"][:26], font=small, fill=MUTED)

    d.text((64, 476), f"{len(incidents)} logged here · Columbus Fire answers one "
                      f"every 1.3 days", font=face("body", 24), fill=MUTED)
    # same ladder the site's Crashcon bar uses
    level, name, color = ((1, "IMPACT", ALERT)                  if days < 1  else
                          (2, "GLASS ON THE SIDEWALK", "#E2711D") if days < 2  else
                          (3, "NORMAL COLUMBUS", HAZARD)          if days <= 7 else
                          (4, "QUIET", "#8FA31E")                 if days <= 21 else
                          (5, "SUSPICIOUSLY CALM", "#4C8577"))
    chip = face("display", 30)
    label = f"CRASHCON {level}"
    wlab = d.textbbox((0, 0), label, font=chip)[2]
    d.rounded_rectangle([64, 518, 64 + wlab + 34, 570], radius=6, fill=color)
    d.text((81, 528), label, font=chip, fill=INK)
    d.text((64 + wlab + 52, 530), name, font=body, fill=INK)

    OUT.parent.mkdir(exist_ok=True)
    img.save(OUT, "PNG", optimize=True)
    print(f"wrote {OUT.relative_to(ROOT)} ({OUT.stat().st_size // 1024} KB) — {days} days")
    return 0

if __name__ == "__main__":
    sys.exit(main())
