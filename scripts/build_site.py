#!/usr/bin/env python3
"""Emit the compact games.json the site loads."""
import json, os, glob, collections, datetime

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SITE = os.path.join(ROOT, "docs")

# long name -> compact key used in games.json
FIELDS = {"sys":"s", "title":"t", "sk":"k", "file":"f", "year":"y", "genre":"g",
          "dev":"d", "pub":"p", "players":"pl", "rating":"r", "region":"rg",
          "series":"se", "size":"z", "desc":"x", "discs":"dc", "great":"gg"}
MEDIA  = {"cover":"c", "box3d":"b", "shot":"i", "title":"n", "disc":"m", "logo":"l"}

def main():
    data  = json.load(open(os.path.join(SITE, "data", "_raw.json")))
    games = data["games"]

    # Games ranked by RetroAchievements player count (see scripts/great_games.json).
    # Flagged here so the site can feature them without carrying any RA data or key.
    gg_path = os.path.join(ROOT, "scripts", "great_games.json")
    great = {}
    if os.path.isfile(gg_path):
        great = {e["id"]: i + 1 for i, e in enumerate(json.load(open(gg_path))["games"])}
    matched = 0
    for g in games:
        rank = great.get(f"{g['sys']}/{g['file']}")
        if rank:
            g["great"] = rank; matched += 1

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
            "great":  sum(1 for x in out if x.get("gg")),
        },
        "games": out,
    }
    # Generated artwork nobody references any more - per-disc images left behind by
    # the multi-disc folder conversion, or games removed from the library. These are
    # all reproducible from the ES-DE media tree, so dropping them is safe.
    used = {g[k] for g in out for k in MEDIA.values() if g.get(k)}
    orphans = [f for f in glob.glob(os.path.join(SITE, "img", "*", "*", "*.webp"))
               if os.path.relpath(f, os.path.join(SITE, "img")) not in used]
    freed = sum(os.path.getsize(f) for f in orphans)
    for f in orphans:
        os.remove(f)

    p = os.path.join(SITE, "data", "games.json")
    json.dump(payload, open(p, "w"), separators=(",", ":"), ensure_ascii=False)

    st = payload["stats"]
    if dropped: print(f"  dropped {dropped} refs to artwork that failed to convert")
    if great: print(f"  flagged {matched}/{len(great)} RetroAchievements top-200 games")
    if orphans: print(f"  pruned {len(orphans)} orphaned image(s), {freed/2**20:.1f} MB")
    print(f"games.json: {os.path.getsize(p)/1024:.0f} KB")
    print(f"  {st['games']} games / {len(systems)} systems / {st['bytes']/2**30:.0f} GB"
          f" / {st['rated']} rated / {len(genres)} genres")
    for k, v in MEDIA.items():
        print(f"    {k:<6}{sum(1 for x in out if x.get(v)):>6}")

if __name__ == "__main__":
    main()
