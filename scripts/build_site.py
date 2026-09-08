#!/usr/bin/env python3
"""Emit the compact games.json the site loads."""
import json, os, collections, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "docs")

# long name -> compact key used in games.json
FIELDS = {"sys":"s", "title":"t", "sk":"k", "file":"f", "year":"y", "genre":"g",
          "dev":"d", "pub":"p", "players":"pl", "rating":"r", "region":"rg",
          "series":"se", "size":"z", "desc":"x", "discs":"dc"}
MEDIA  = {"cover":"c", "box3d":"b", "shot":"i", "title":"n", "disc":"m", "logo":"l"}

def main():
    data  = json.load(open(os.path.join(SITE, "data", "_raw.json")))
    games = data["games"]

    dropped = 0
    for g in games:
        for k, rel in list(g.get("img", {}).items()):
            if not os.path.isfile(os.path.join(SITE, "img", rel)):
                del g["img"][k]; dropped += 1

    out = []
    for g in games:
        rec = {v: g[k] for k, v in FIELDS.items() if g.get(k) not in (None, "", 0)}
        rec.update({v: g["img"][k] for k, v in MEDIA.items() if k in g.get("img", {})})
        out.append(rec)

    counts  = collections.Counter(g["s"] for g in out)
    systems = [{"id": sid, "name": m[0], "short": m[1], "era": m[2], "n": counts[sid]}
               for sid, m in data["systems"].items() if counts.get(sid)]
    systems.sort(key=lambda s: (s["era"], s["name"]))
    genres  = [g for g, _ in collections.Counter(x["g"] for x in out if x.get("g")).most_common()]

    payload = {
        "generated": datetime.date.today().isoformat(),
        "systems": systems, "genres": genres,
        "stats": {
            "games":  len(out),
            "bytes":  sum(x.get("z", 0) for x in out),
            "rated":  sum(1 for x in out if x.get("r")),
            "covers": sum(1 for x in out if x.get("c")),
        },
        "games": out,
    }
    p = os.path.join(SITE, "data", "games.json")
    json.dump(payload, open(p, "w"), separators=(",", ":"), ensure_ascii=False)

    st = payload["stats"]
    if dropped: print(f"  dropped {dropped} refs to artwork that failed to convert")
    print(f"games.json: {os.path.getsize(p)/1024:.0f} KB")
    print(f"  {st['games']} games / {len(systems)} systems / {st['bytes']/2**30:.0f} GB"
          f" / {st['rated']} rated / {len(genres)} genres")
    for k, v in MEDIA.items():
        print(f"    {k:<6}{sum(1 for x in out if x.get(v)):>6}")

if __name__ == "__main__":
    main()
