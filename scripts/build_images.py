#!/usr/bin/env python3
"""Resize the ES-DE artwork into web-sized WebP under docs/img/<kind>/<system>/."""
import json, os, re, unicodedata
from concurrent.futures import ProcessPoolExecutor
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "docs")
IMG  = os.path.join(SITE, "img")

# kind -> (max width, webp quality). Nothing is ever upscaled.
SPECS = {"cover": (400, 80), "box3d": (400, 80), "shot": (480, 75),
         "title": (480, 75), "disc":  (300, 80), "logo":  (320, 78)}

def slug(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^\w\s-]", "", s).strip().lower()
    return re.sub(r"[\s_-]+", "-", s)[:80] or "x"

def convert(args):
    src, dst, width, quality = args
    # Resumable, but only while the source has not changed underneath us. A
    # re-scrape rewrites the artwork in place under the same filename, so
    # skipping purely on existence would silently keep the old picture.
    if (os.path.isfile(dst) and os.path.getsize(dst) > 200
            and os.path.getmtime(dst) >= os.path.getmtime(src)):
        return dst, os.path.getsize(dst), None
    try:
        with Image.open(src) as im:
            im.load()
            if im.mode in ("RGBA", "LA", "P"):
                im = im.convert("RGBA")
                im = Image.alpha_composite(Image.new("RGBA", im.size, (0, 0, 0, 0)), im)
            else:
                im = im.convert("RGB")
            if im.width > width:
                im = im.resize((width, max(1, round(im.height * width / im.width))), Image.LANCZOS)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            im.save(dst, "WEBP", quality=quality, method=6)
        return dst, os.path.getsize(dst), None
    except Exception as e:
        return dst, 0, f"{os.path.basename(src)}: {e}"

def main():
    data  = json.load(open(os.path.join(SITE, "data", "_raw.json")))
    games = data["games"]

    jobs, used = [], set()
    for g in games:
        stem = f"{g['sys']}/{slug(g['file'])}"
        n, key = 1, stem
        while key in used: n += 1; key = f"{stem}-{n}"
        used.add(key)
        g["img"] = {}
        for kind, (w, q) in SPECS.items():
            src = g["_media"].get(kind)
            if not src: continue
            rel = f"{kind}/{key}.webp"
            jobs.append((src, os.path.join(IMG, rel), w, q))
            g["img"][kind] = rel

    print(f"converting {len(jobs)} images across {len(SPECS)} kinds ...")
    total, errs, by = 0, [], {}
    with ProcessPoolExecutor() as ex:
        for i, (dst, size, err) in enumerate(ex.map(convert, jobs, chunksize=16), 1):
            total += size
            by[dst.split(os.sep)[-3]] = by.get(dst.split(os.sep)[-3], 0) + size
            if err: errs.append(err)
            if i % 1500 == 0: print(f"  {i}/{len(jobs)}  {total/2**20:.0f} MB")
    print(f"done: {len(jobs)-len(errs)} images, {total/2**20:.1f} MB")
    for k, v in sorted(by.items(), key=lambda x: -x[1]):
        print(f"    {k:<8}{v/2**20:>7.1f} MB")
    for e in errs[:8]: print("  ERR", e)
    if len(errs) > 8: print(f"  ... and {len(errs)-8} more")

    for g in games: g.pop("_media", None)
    json.dump(data, open(os.path.join(SITE, "data", "_raw.json"), "w"))

if __name__ == "__main__":
    main()
