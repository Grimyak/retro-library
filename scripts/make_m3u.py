#!/usr/bin/env python3
"""Create .m3u playlists for multi-disc games in the ROM library.

Groups disc images by their filename with the "(Disc n)" tag removed, then
writes one playlist per set, listing the discs in numeric order. Playlists use
CRLF line endings and bare filenames, matching the ones already in the library.

Deliberately conservative — it will not:
  * overwrite an existing playlist,
  * write a playlist whose name collides with an existing ROM (which would show
    up twice in the frontend),
  * or write one for a set with only a single disc actually present.

Dry run by default; pass --write to create anything.

    python3 scripts/make_m3u.py                     # show what is missing
    python3 scripts/make_m3u.py --write             # create it
    python3 scripts/make_m3u.py --systems saturn --write
"""
import os, re, argparse, collections

ROMS = "/mnt/games/Roms"

DISC = re.compile(r'\s*\((?:Dis[ck])\s*(\d+)\)', re.I)
# .bin is deliberately absent: a multi-track rip ships one .bin per track and
# the .cue is the real entry point, so matching .bin would invent bogus sets.
# Dolphin parses .m3u playlists but requires Unix line endings - a trailing \r
# ends up in the filename and the disc fails to open. Everything else in this
# library (and the RetroArch cores) is happy with CRLF, so only these differ.
LF_SYSTEMS = {"gc", "wii"}

EXT = ('.chd', '.cue', '.iso', '.cso', '.ccd', '.mds', '.gdi', '.cdi',
       '.rvz', '.gcm', '.gcz', '.ciso', '.wbfs', '.nrg')

def sets_in(d):
    """-> {stem: [(disc number, filename), ...]} for every file carrying a disc tag."""
    groups = collections.defaultdict(list)
    for f in sorted(os.listdir(d)):
        if not f.lower().endswith(EXT): continue
        base = os.path.splitext(f)[0]
        m = DISC.search(base)
        if not m: continue
        stem = re.sub(r'\s{2,}', ' ', DISC.sub('', base)).strip()
        groups[stem].append((int(m.group(1)), f))
    return {k: sorted(v) for k, v in groups.items()}

def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roms", default=ROMS, help=f"library root (default {ROMS})")
    ap.add_argument("--systems", nargs="*", help="limit to these system folders")
    ap.add_argument("--write", action="store_true", help="create the files (otherwise dry run)")
    a = ap.parse_args()

    systems = a.systems or sorted(d for d in os.listdir(a.roms)
                                  if os.path.isdir(os.path.join(a.roms, d)))
    made = skipped = lone = collide = 0
    for sysid in systems:
        d = os.path.join(a.roms, sysid)
        if not os.path.isdir(d):
            print(f"  ??  {sysid}  (no such folder)"); continue
        for stem, discs in sorted(sets_in(d).items()):
            if len(discs) == 1:
                print(f"  --  {sysid}/{stem}  (only disc {discs[0][0]} present, not a set)")
                lone += 1; continue
            if os.path.exists(os.path.join(d, stem + ".m3u")):
                skipped += 1; continue
            clash = [e for e in EXT if os.path.exists(os.path.join(d, stem + e))]
            if clash:
                print(f"  !!  {sysid}/{stem}  (a {clash[0]} of the same name exists - skipped)")
                collide += 1; continue
            eol = "\n" if sysid in LF_SYSTEMS else "\r\n"
            if a.write:
                with open(os.path.join(d, stem + ".m3u"), "w", newline="") as fh:
                    fh.write("".join(f + eol for _, f in discs))
            print(f"  {'++' if a.write else '>>'}  {sysid}/{stem}.m3u  "
                  f"[{len(discs)} discs: {', '.join(str(n) for n, _ in discs)}]")
            made += 1

    print(f"\n{'created' if a.write else 'would create'} {made} playlist(s); "
          f"{skipped} already existed; {lone} incomplete set(s) and "
          f"{collide} name clash(es) skipped")
    if not a.write and made:
        print("re-run with --write to create them")

if __name__ == "__main__":
    main()
