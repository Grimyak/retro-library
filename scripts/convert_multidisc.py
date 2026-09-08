#!/usr/bin/env python3
"""Convert multi-disc games to ES-DE's "directories interpreted as files" layout.

Turns this:

    psx/Xenogears (USA) (Disc 1).chd     <- three separate entries in ES-DE
    psx/Xenogears (USA) (Disc 2).chd
    psx/Xenogears (USA).m3u

into this:

    psx/Xenogears (USA).m3u/                          <- one entry
    psx/Xenogears (USA).m3u/Xenogears (USA) (Disc 1).chd
    psx/Xenogears (USA).m3u/Xenogears (USA) (Disc 2).chd
    psx/Xenogears (USA).m3u/Xenogears (USA).m3u       <- what gets launched

A directory whose name ends in a supported extension is interpreted by ES-DE as
a file, and the file inside matching the directory name is what gets passed to
the emulator.

Two things about this were non-obvious and cost some digging, so they are worth
recording:

1.  MEDIA NAMING. ES-DE builds media paths as
        <system>/<mediaType>/<getDisplayName()>
    and getDisplayName() is getStem(path) -- but getStem() explicitly skips
    extension-stripping when the path is a directory:

        if (!Utils::FileSystem::isDirectory(path)) { ...erase the extension... }

    So a folder named "Xenogears (USA).m3u" looks for its cover at
    "covers/Xenogears (USA).m3u.png" -- extension included. Media scraped
    against the old name is hardlinked to that name here, so nothing needs
    re-downloading and no scraper calls are made. (SystemData.cpp separately
    strips the extension off the *metadata name*, which is why the game still
    displays as "Xenogears".)

2.  DISC TAGS ARE NOT ALWAYS LAST. "Grandia (Japan) (Disc 1) [T-En by ...].chd"
    puts the tag mid-filename, so media has to be located from the real disc
    filenames rather than a reconstructed "<stem> (Disc 1)".

It also removes redundant single-disc playlists -- an .m3u pointing at exactly
one image does nothing for disc swapping and just doubles the entry in ES-DE.
Metadata is migrated onto the surviving entry before any file is deleted, since
some games carry their scrape only on the .m3u entry.

Dry run by default. Gamelists are backed up before being touched, ROM moves are
renames within one filesystem, and media are hardlinks, so originals are never
at risk.

    python3 scripts/convert_multidisc.py                    # preview
    python3 scripts/convert_multidisc.py --write            # apply
    python3 scripts/convert_multidisc.py --systems saturn --write
    python3 scripts/convert_multidisc.py --write --skip-cleanup
"""
import os, re, sys, shutil, argparse, collections, datetime
import xml.etree.ElementTree as ET

ROMS = "/mnt/games/Roms"
GL   = os.path.expanduser("~/ES-DE/gamelists")
MED  = os.path.expanduser("~/ES-DE/downloaded_media")
DISC = re.compile(r'\s*\((?:Dis[ck])\s*\d+\)', re.I)
# Dolphin parses .m3u playlists but requires Unix line endings - a trailing \r
# ends up in the filename and the disc fails to open. Everything else in this
# library (and the RetroArch cores) is happy with CRLF, so only these differ.
LF_SYSTEMS = {"gc", "wii"}

ROMEXT = ('.chd','.cue','.iso','.cso','.ccd','.mds','.gdi','.cdi','.rvz','.gcm','.gcz','.ciso')
META = ('name','desc','rating','releasedate','developer','publisher','genre','players')

def load(sysid):
    p = f"{GL}/{sysid}/gamelist.xml"
    if not os.path.isfile(p): return None, None, {}
    tree = ET.parse(p); root = tree.getroot()
    return tree, root, {(g.findtext('path') or ''): g for g in root.findall('game')}

def score(g):
    return 0 if g is None else sum(1 for f in META if (g.findtext(f) or '').strip())

def link_media(sysid, stem, dirname, discs, write, log):
    """Hardlink the game's media to <dirname>.<ext> for every media type.

    Prefers media scraped against the playlist stem; falls back to whichever
    disc actually has media, using the real disc filenames (the disc tag is not
    always at the end, e.g. "Grandia (Japan) (Disc 1) [T-En ...]").
    """
    base = f"{MED}/{sysid}"
    if not os.path.isdir(base): return 0
    n = 0
    for kind in sorted(os.listdir(base)):
        kd = f"{base}/{kind}"
        if not os.path.isdir(kd): continue
        src = None
        for cand in [stem] + [os.path.splitext(x)[0] for x in discs]:
            hits = [f for f in os.listdir(kd)
                    if os.path.splitext(f)[0] == cand and os.path.isfile(f"{kd}/{f}")]
            if hits: src = f"{kd}/{hits[0]}"; break
        if not src: continue
        dst = f"{kd}/{dirname}{os.path.splitext(src)[1]}"
        if os.path.exists(dst): continue
        if write:
            try: os.link(src, dst)
            except OSError: shutil.copy2(src, dst)
        n += 1
    log.append(f"        media: {n} type(s) linked as {dirname}.*")
    return n

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--systems", nargs="*", default=["psx","saturn","dreamcast"])
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--skip-cleanup", action="store_true",
                    help="do not delete redundant single-disc playlists")
    a = ap.parse_args()
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    totals = collections.Counter()

    for sysid in a.systems:
        d = f"{ROMS}/{sysid}"
        if not os.path.isdir(d): continue
        tree, root, byp = load(sysid)
        changed = False
        print(f"\n=== {sysid}")

        # ---- 1. multi-disc sets -> directories interpreted as files ----
        groups = collections.defaultdict(list)
        for f in sorted(os.listdir(d)):
            if not f.lower().endswith(ROMEXT): continue
            b = os.path.splitext(f)[0]
            if DISC.search(b):
                groups[re.sub(r'\s{2,}',' ', DISC.sub('', b)).strip()].append(f)
        for stem, discs in sorted(groups.items()):
            if len(discs) < 2: continue
            dirname = f"{stem}.m3u"
            if os.path.isdir(f"{d}/{dirname}"):
                totals['already'] += 1; continue
            log = [f"    {stem}  [{len(discs)} discs]"]
            m3u = f"{d}/{dirname}"
            has_m3u = os.path.isfile(m3u)
            if a.write:
                tmp = f"{d}/.{dirname}.tmp"
                if has_m3u: os.rename(m3u, tmp)
                os.mkdir(m3u)
                for f in discs: os.rename(f"{d}/{f}", f"{m3u}/{f}")
                if has_m3u: os.rename(tmp, f"{m3u}/{dirname}")
                else:
                    eol = "\n" if sysid in LF_SYSTEMS else "\r\n"
                    with open(f"{m3u}/{dirname}", "w", newline="") as fh:
                        fh.write("".join(x + eol for x in discs))
            log.append(f"        {'moved' if has_m3u else 'moved + created playlist'}")
            link_media(sysid, stem, dirname, discs, a.write, log)
            # make sure the folder entry carries metadata (clone disc 1's if absent)
            if byp is not None and score(byp.get(f"./{dirname}")) < 4:
                donor = max((byp.get(f"./{x}") for x in discs), key=score, default=None)
                if score(donor) >= 4:
                    if a.write:
                        e = byp.get(f"./{dirname}")
                        if e is None:
                            e = ET.SubElement(root, 'game')
                            ET.SubElement(e, 'path').text = f"./{dirname}"
                        for f in META:
                            v = donor.findtext(f)
                            if v and e.find(f) is None: ET.SubElement(e, f).text = v
                        changed = True
                    log.append("        metadata: cloned from disc 1")
            print("\n".join(log)); totals['converted'] += 1

        # ---- 2. redundant single-disc playlists ----
        if not a.skip_cleanup:
            for f in sorted(os.listdir(d)):
                if not f.endswith(".m3u") or os.path.isdir(f"{d}/{f}"): continue
                lines = [l for l in open(f"{d}/{f}", newline="").read().splitlines() if l.strip()]
                if len(lines) != 1 or not os.path.isfile(f"{d}/{lines[0]}"): continue
                tgt, src_e = f"./{lines[0]}", byp.get(f"./{f}")
                if score(byp.get(tgt)) < 4 and score(src_e) >= 4:
                    if a.write:
                        e = byp.get(tgt)
                        if e is None:
                            e = ET.SubElement(root, 'game')
                            ET.SubElement(e, 'path').text = tgt
                        for fld in META:
                            v = src_e.findtext(fld)
                            if v and e.find(fld) is None: ET.SubElement(e, fld).text = v
                        changed = True
                    print(f"    metadata migrated to {lines[0]}")
                if a.write: os.remove(f"{d}/{f}")
                totals['removed'] += 1

        if changed and a.write:
            p = f"{GL}/{sysid}/gamelist.xml"
            shutil.copy2(p, f"{p}.bak-{stamp}")
            tree.write(p, encoding="UTF-8", xml_declaration=True)
            print(f"    gamelist updated (backup: gamelist.xml.bak-{stamp})")

    print(f"\n{'APPLIED' if a.write else 'DRY RUN'}: "
          f"{totals['converted']} set(s) to folder layout, "
          f"{totals['already']} already done, "
          f"{totals['removed']} redundant playlist(s) removed")
    if not a.write: print("re-run with --write to apply")

if __name__ == "__main__":
    main()
