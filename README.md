# Retro Library

A static, browsable catalogue of a personal retro game collection — **1,651 games across 15
systems**, with box art, 3D boxes, cartridge and disc scans, screenshots, title screens, logos,
community ratings, descriptions and release metadata.

**→ Live site: <https://grimyak.github.io/retro-library/>**

## What it does

- Grid of every game, switchable between **flat box art** and **3D boxes**
- Sort A–Z, by rating, by release year, or by file size
- Filter by system (multi-select) and genre; free-text search across titles,
  developers, publishers and series
- Click any cover for a detail sheet: wheel logo, box art, the actual cartridge or disc,
  rating, full release facts, description, and screenshot + title screen side by side
- Deep-linkable — each game gets its own URL fragment
- No framework, no build step, no tracking. One HTML file, one CSS file, one JS file, one JSON payload.

## Design

A phosphor-terminal treatment: monochrome green on black, monospace throughout, box-drawn rules,
a blinking prompt in the search field, ratings as block meters (`████████████░░░░░░░░ 62/100`)
and facts set with dotted leaders. The chrome carries no colour at all, which leaves the box art
as the only colour on the page.

Two fonts are vendored into `docs/assets/fonts/` (52 KB, latin subset) so the site has no external
requests: **VT323** for display type and **IBM Plex Mono** for everything meant to be read.

The CRT scanline and vignette texture is painted on the **body background, behind the content**,
rather than as an overlay on top of it. Anything that paints an opaque surface — card artwork, the
detail panel — therefore covers it completely, so no scanline ever crosses a piece of box art. The
scanlines are dropped under `prefers-reduced-motion`, as is the blinking prompt.

## Where the data comes from

Everything is read from a local [ES-DE](https://es-de.org/) install that was scraped with
[ScreenScraper](https://www.screenscraper.fr/). Nothing is re-scraped at build time and no API
key is needed.

| Source | Provides |
| --- | --- |
| `~/ES-DE/gamelists/<system>/gamelist.xml` | title, description, rating, genre, developer, publisher, players, release date |
| `~/ES-DE/downloaded_media/<system>/covers/` | flat box art — grid tiles and detail sheet |
| `~/ES-DE/downloaded_media/<system>/3dboxes/` | 3D box renders — alternate grid view |
| `~/ES-DE/downloaded_media/<system>/physicalmedia/` | the cartridge or disc itself |
| `~/ES-DE/downloaded_media/<system>/screenshots/` | in-game capture |
| `~/ES-DE/downloaded_media/<system>/titlescreens/` | title screen |
| `~/ES-DE/downloaded_media/<system>/marquees/` | wheel logo |
| `/mnt/games/Roms/<system>/` | on-disk file sizes, and the `<family>` series field salvaged from the older gamelists |

Media is matched to games by ROM basename, which resolves at 100% across all six artwork types.

**Not included:** `videos/` (9.7 GB), `miximages/` (composites of artwork already present here),
`backcovers/` and `fanart/`. They're all still in ES-DE — see `SPECS` in
`scripts/build_images.py` and `MEDIA_KINDS` in `scripts/build_data.py` to pull any of them in.

**Play statistics and favourites are deliberately not imported.** ES-DE records play count, play
time, last played and a favourite flag, but they all change as you use it, so a static snapshot of
them is stale immediately. Keeping them honest would need an automated rebuild on every session,
which is out of scope here.

## Rebuilding

```bash
python3 scripts/build_data.py    # ES-DE gamelists -> docs/data/_raw.json
python3 scripts/build_images.py  # artwork -> docs/img/**.webp (resumable)
python3 scripts/build_site.py    # -> docs/data/games.json
```

`build_images.py` skips files it has already converted, so re-runs are cheap; delete
`docs/img/<kind>/` to force one kind to rebuild. Serve locally with `python3 -m http.server -d docs`
and open <http://localhost:8000> — the command starts a server but does not open a browser.

### Multi-disc playlists

`scripts/make_m3u.py` is a separate library-maintenance tool — it touches the ROM folders, not
the site. It finds multi-disc games, groups them by filename with the `(Disc n)` tag removed, and
writes one `.m3u` per set with the discs in numeric order, using CRLF endings and bare filenames
to match the playlists already in the library.

```bash
python3 scripts/make_m3u.py                      # dry run: what is missing
python3 scripts/make_m3u.py --write              # create them
python3 scripts/make_m3u.py --systems saturn --write
```

It is deliberately conservative and will refuse to overwrite an existing playlist, to write one
whose name collides with an existing ROM (that would appear twice in the frontend), or to write
one for a set with only a single disc present. `.bin` is excluded on purpose: a multi-track rip
ships one `.bin` per track and the `.cue` is the real entry point.

A note on GameCube — ES-DE accepts `.m3u` for it, but the default emulator is the libretro Dolphin
core, whose disc-control support is unreliable, and standalone Dolphin ignores `.m3u` entirely. Its
sets are reported but left alone unless you ask for them explicitly.

### Multi-disc folder layout

`scripts/convert_multidisc.py` converts multi-disc games to ES-DE's *directories interpreted as
files* layout, so a game shows up once instead of once per disc:

```
psx/Xenogears (USA).m3u/                          <- one entry in ES-DE
psx/Xenogears (USA).m3u/Xenogears (USA) (Disc 1).chd
psx/Xenogears (USA).m3u/Xenogears (USA) (Disc 2).chd
psx/Xenogears (USA).m3u/Xenogears (USA).m3u       <- what gets launched
```

It also deletes redundant single-disc playlists, which do nothing for disc swapping and merely
double the entry. Running it took PS1 from 433 entries to 200, Saturn 62 to 52 and Dreamcast 41
to 32.

```bash
python3 scripts/convert_multidisc.py             # preview
python3 scripts/convert_multidisc.py --write     # apply
```

Two findings are baked into the script because they are easy to get wrong:

- **Media keeps the extension.** ES-DE resolves media through `getDisplayName()`, which is
  `getStem(path)` — and `getStem()` skips extension-stripping when the path is a directory. So the
  folder `Xenogears (USA).m3u` looks for `covers/Xenogears (USA).m3u.png`, extension included. The
  script hardlinks existing artwork to that name, so **no re-scraping and no API calls**.
- **Disc tags are not always last.** `Grandia (Japan) (Disc 1) [T-En by ...].chd` puts it in the
  middle, so media is located from the real disc filenames rather than a reconstructed name.

Metadata is migrated onto the surviving entry before anything is deleted — some games carry their
scrape only on the `.m3u` entry — and gamelists are backed up first.

### Notes on the source data

Quirks the build handles, in case you hit them on your own library:

- The PSX and Saturn gamelists carry **one entry per disc plus a `.m3u` playlist entry** — 433
  PSX entries for 205 actual games. Entries are grouped by basename with `(Disc n)` stripped, and
  the playlist entry wins; multi-disc games report their disc count.
- ScreenScraper writes titles as `Zelda : Link's Awakening` and `Batman & Robin, The` — both are
  normalised, and region/language/dump tags are stripped from display titles but kept as metadata.
- The current ES-DE scrape dropped the `<family>` field, so series names are salvaged from the
  older gamelists still sitting next to the ROMs (1,009 of them).
- `build_site.py` verifies every image path before emitting it, so a failed conversion degrades
  to a placeholder rather than a 404.

## Layout

```
scripts/     build pipeline (3 scripts, plain Python + Pillow)
docs/        the site itself — this is what GitHub Pages serves
  index.html
  assets/    style.css, app.js
  data/      games.json
  img/       cover/ box3d/ shot/ title/ disc/ logo/   (WebP)
```

## Publishing

GitHub Pages serves `main` `/docs`. Rebuild, commit and push, and the site redeploys itself:

```bash
python3 scripts/build_data.py && python3 scripts/build_images.py && python3 scripts/build_site.py
git add -A && git commit -m "Refresh catalogue" && git push
```

Note that this repository is public, so every ROM filename in it is publicly searchable.
