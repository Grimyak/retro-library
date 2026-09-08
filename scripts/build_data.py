#!/usr/bin/env python3
"""Parse the ES-DE gamelists + downloaded_media tree into one intermediate JSON.

ES-DE keeps metadata in ~/ES-DE/gamelists/<system>/gamelist.xml and artwork in
~/ES-DE/downloaded_media/<system>/<type>/<rom basename>.png. The ROM files
themselves stay under ROMS and are only consulted for on-disk size.
"""
import xml.etree.ElementTree as ET, os, json, glob, re, sys
from collections import Counter

ROMS      = "/mnt/games/Roms"
GAMELISTS = os.path.expanduser("~/ES-DE/gamelists")
MEDIA     = os.path.expanduser("~/ES-DE/downloaded_media")
OUT       = os.path.join(os.path.dirname(__file__), "..", "docs", "data")

SYSTEMS = {
    "nes":          ("Nintendo Entertainment System", "NES",      1983),
    "snes":         ("Super Nintendo",                "SNES",     1990),
    "n64":          ("Nintendo 64",                   "N64",      1996),
    "gb":           ("Game Boy",                      "GB",       1989),
    "gbc":          ("Game Boy Color",                "GBC",      1998),
    "gba":          ("Game Boy Advance",              "GBA",      2001),
    "nds":          ("Nintendo DS",                   "NDS",      2004),
    "mastersystem": ("Sega Master System",            "SMS",      1985),
    "megadrive":    ("Sega Mega Drive / Genesis",     "Genesis",  1988),
    "saturn":       ("Sega Saturn",                   "Saturn",   1994),
    "dreamcast":    ("Sega Dreamcast",                "Dreamcast",1998),
    "gc":           ("Nintendo GameCube",             "GameCube", 2001),
    "psx":          ("Sony PlayStation",              "PS1",      1994),
    "ps2":          ("Sony PlayStation 2",            "PS2",      2000),
    "pcengine":     ("PC Engine / TurboGrafx-16",     "PCE",      1987),
    "pcenginecd":   ("PC Engine CD / TurboGrafx-CD",  "PCE-CD",   1988),
    "neogeo":       ("SNK Neo Geo",                   "Neo Geo",  1990),
}
# site key -> ES-DE downloaded_media subdirectory
MEDIA_KINDS = {"cover":"covers", "box3d":"3dboxes", "shot":"screenshots",
               "title":"titlescreens", "disc":"physicalmedia", "logo":"marquees"}

ROM_EXT = {".zip",".chd",".7z",".nds",".gba",".gb",".gbc",".n64",".z64",".v64",
           ".sfc",".smc",".nes",".iso",".cso",".pce",".md",".gen",".sms",".m3u",".pbp",
           ".rvz",".gcm",".gcz",".ciso",".gdi",".cdi",".wbfs"}

ARTICLE = re.compile(r"^(.+?),\s+(The|A|An|Le|La|Les|Der|Die|Das|El|Los)\b(\s*[-–].*)?$", re.I)
REGION_MAP = [("USA","USA"),("World","World"),("Europe","Europe"),("Japan","Japan"),
              ("Australia","Australia"),("Korea","Korea"),("Brazil","Brazil"),("Asia","Asia")]
REGION_TAG = re.compile(
    r"\s*\((USA|Europe|Japan|World|Australia|Korea|Brazil|Asia|Canada|Germany|France|Spain|"
    r"Italy|Netherlands|Sweden|Taiwan|China|Hong Kong)([,\s][^)]*)?\)", re.I)
LANG_TAG = re.compile(r"\s*\((?:En|Ja|Fr|De|Es|It|Pt|Ru|Ko|Zh|Nl|Sv|Da|No|Fi|Pl)"
                      r"(?:,\s?[A-Za-z]{2})*\)", re.I)
REV_TAG  = re.compile(r"\s*\((?:Rev|v)\s?[\d.]+[^)]*\)", re.I)
DISC_TAG = re.compile(r"\s*\(Disc\s*\d+\)(\s*\([^)]*\))*\s*$", re.I)

def strip_tags(t):
    t = re.sub(r"[\[\(]\s*T-En[^\]\)]*[\]\)]", "(English patch)", t, flags=re.I)
    t = re.sub(r"\s*\[[^\]]*\]", "", t)
    t = REGION_TAG.sub("", t); t = LANG_TAG.sub("", t); t = REV_TAG.sub("", t)
    return re.sub(r"\s{2,}", " ", t).strip()

def norm_title(name, base):
    t = (name or "").strip() or re.sub(r"\s*[\(\[].*$", "", base).strip()
    t = strip_tags(t)
    t = re.sub(r"\s+([:;!?])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    m = ARTICLE.match(t)
    if m: t = f"{m.group(2)} {m.group(1)}{m.group(3) or ''}"
    return t

def sort_key(t): return re.sub(r"^(the|a|an)\s+", "", t.lower()).lstrip("'\"")

def region_of(base):
    for needle, label in REGION_MAP:
        if f"({needle}" in base or f", {needle}" in base: return label
    return "Unknown"

def year_of(rd):
    m = re.match(r"(\d{4})", rd or "")
    y = int(m.group(1)) if m else None
    return y if y and 1970 <= y <= 2015 else None

# The two scrapers disagree on spelling; fold the collisions together.
GENRE_ALIAS = {
    "role-playing": "Role Playing Game",
    "role playing": "Role Playing Game",
    "rpg": "Role Playing Game",
    "shoot'em up": "Shoot'em Up",
    "beat'em up": "Beat'em Up",
}

def clean_genre(g):
    """Keep the primary genre only.

    Both scrapers separate genres with "/" or "," ("Action, Adventure",
    "Shooter / Vehicle, TPV"). Hyphens are *not* separators — "Role-Playing"
    and "Party-Based RPG" are single genres — so splitting on them was wrong.
    """
    g = (g or "").strip()
    if not g: return None
    primary = re.split(r"\s*[/,]\s*", g)[0].strip()
    return GENRE_ALIAS.get(primary.lower(), primary) or None

def rom_size(sysdir, base, ext=""):
    # a folder-layout game ("<game>.m3u/" holding the discs) is sized by its contents
    d = os.path.join(sysdir, base + ext)
    if ext and os.path.isdir(d):
        return sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)
                   if os.path.isfile(os.path.join(d, f))
                   and os.path.splitext(f)[1].lower() in ROM_EXT - {".m3u"})
    tot = 0
    for f in glob.glob(glob.escape(os.path.join(sysdir, base)) + "*"):
        if os.path.isfile(f) and os.path.splitext(f)[1].lower() in ROM_EXT - {".m3u"}:
            tot += os.path.getsize(f)
    if not tot:
        stem = DISC_TAG.sub("", base)
        for f in glob.glob(glob.escape(os.path.join(sysdir, stem)) + "*"):
            if os.path.isfile(f) and os.path.splitext(f)[1].lower() in ROM_EXT - {".m3u"}:
                tot += os.path.getsize(f)
    return tot

def find_media(sysid, names):
    """First name in `names` that has a file wins, per media kind.

    ES-DE resolves media through getStem(), which does *not* strip the extension
    when the path is a directory — so a folder-layout game "Game.m3u" stores its
    artwork as "Game.m3u.png". Both spellings are tried.
    """
    out = {}
    for key, sub in MEDIA_KINDS.items():
        for n in names:
            for ext in (".png", ".jpg"):
                p = os.path.join(MEDIA, sysid, sub, n + ext)
                if os.path.isfile(p): out[key] = p; break
            if key in out: break
    return out

def legacy_series(sysid):
    """The older gamelists next to the ROMs carried a <family> field the new
    ES-DE scrape drops. Salvage it, keyed by ROM basename."""
    p = os.path.join(ROMS, sysid, "gamelist.xml")
    out = {}
    if os.path.isfile(p):
        try:
            for g in ET.parse(p).getroot().findall("game"):
                b = os.path.splitext(os.path.basename(g.findtext("path") or ""))[0]
                fam = (g.findtext("family") or "").strip()
                if b and fam: out[b] = fam
        except Exception: pass
    return out

def main():
    games, skipped, merged, stale = [], Counter(), Counter(), Counter()
    for sysid, (full, short, era) in SYSTEMS.items():
        gl = os.path.join(GAMELISTS, sysid, "gamelist.xml")
        if not os.path.isfile(gl): continue
        sysdir = os.path.join(ROMS, sysid)
        series = legacy_series(sysid)

        # group entries that are the same game (multi-disc sets, .chd next to .m3u)
        groups = {}
        for g in ET.parse(gl).getroot().findall("game"):
            path = (g.findtext("path") or "").strip()
            base = os.path.splitext(os.path.basename(path))[0]
            if not base: continue
            ext = os.path.splitext(path)[1].lower()
            # gamelists keep rows for files that no longer exist (discs moved into
            # a folder-layout game, deleted playlists); ES-DE skips them, so do we
            if not os.path.exists(os.path.join(sysdir, base + ext)):
                stale[sysid] += 1; continue
            groups.setdefault(DISC_TAG.sub("", base), []).append((base, ext, g))

        for key, members in sorted(groups.items(), key=lambda kv: kv[0].lower()):
            if len(members) > 1: merged[sysid] += len(members) - 1
            # a playlist entry represents the whole set; else richest metadata
            def rank(m):
                base, ext, g = m
                meta = sum(1 for f in ("desc","rating","genre","developer") if (g.findtext(f) or "").strip())
                return (ext == ".m3u", meta, -len(base))
            base, ext, g = max(members, key=rank)
            gt = lambda k: (g.findtext(k) or "").strip()

            name = gt("name")
            if "(notgame)" in (name or base).lower():
                skipped[sysid] += 1; continue

            title = norm_title(name, base)
            rating = gt("rating")
            games.append({
                "id": f"{sysid}/{base}", "sys": sysid, "title": title, "sk": sort_key(title),
                "file": base,
                "region":  region_of(base),
                "year":    year_of(gt("releasedate")),
                "genre":   clean_genre(gt("genre")),
                "dev":     gt("developer") or None,
                "pub":     gt("publisher") or None,
                "players": gt("players") or None,
                "series":  series.get(base) or None,
                "rating":  round(float(rating) * 100) if rating else None,
                "desc":    re.sub(r"\s+", " ", gt("desc")).strip() or None,
                "size":    rom_size(sysdir, base, ext),
                "discs":   len([m for m in members if "(Disc" in m[0]]) or None,
                "_media":  find_media(sysid, [n for m in sorted(members, key=rank, reverse=True)
                                              for n in (m[0] + m[1], m[0])]),
            })

    games.sort(key=lambda x: (x["sys"], x["sk"]))
    os.makedirs(OUT, exist_ok=True)
    json.dump({"systems": SYSTEMS, "games": games}, open(os.path.join(OUT, "_raw.json"), "w"))

    kinds = list(MEDIA_KINDS)
    print(f"{'system':<14}{'games':>6}" + "".join(f"{k:>7}" for k in kinds) + f"{'rated':>7}")
    for sysid in SYSTEMS:
        gs = [g for g in games if g["sys"] == sysid]
        if not gs: continue
        print(f"{sysid:<14}{len(gs):>6}" + "".join(f"{sum(1 for g in gs if k in g['_media']):>7}" for k in kinds)
              + f"{sum(1 for g in gs if g['rating']):>7}")
    print(f"{'TOTAL':<14}{len(games):>6}" + "".join(f"{sum(1 for g in games if k in g['_media']):>7}" for k in kinds)
          + f"{sum(1 for g in games if g['rating']):>7}")
    print(f"on disk: {sum(g['size'] for g in games)/2**30:.0f} GB"
          f" | series salvaged: {sum(1 for g in games if g['series'])}")
    if stale: print("stale gamelist rows skipped:", dict(stale))
    if merged: print("multi-disc/duplicate entries merged:", dict(merged))
    if skipped: print("skipped non-games:", dict(skipped))

if __name__ == "__main__":
    main()
