---
name: motion-reel
description: Deterministic motion design rendered from code — animated hooks, title cards, intros, lower thirds, end cards — styled from a project brand kit (baair, ia-explorateurs, ia-pilotes), rendered headless to ProRes 4444 with alpha and dropped into Raccord's media folder so fcp-live can lay it over footage in Final Cut Pro. Trigger on "motion design", "animated title", "title animation", "intro", "end card", "lower third", "kinetic text", "animate this hook", and in French « motion design », « animation de titre », « intro animée », « générique », « lower third », « bandeau nom », « fais un motion », « anime le hook ». Not for editing footage (that is fcp-live) nor for generative video (Higgsfield, Kling, HeyGen).
---

# motion-reel — motion design in deterministic code

Read `CLAUDE.md` (house rules) before writing anything. It is short and it wins over taste.

A spec (`spec.schema.json`) lists **layers** (text, square, rect, line) and **states** (`from` → `to` between `t0` and `t1`, easing `cut` | `linear` | `spring{zeta, omega}`) on a **beat grid**. `renderer/draw.js` paints any time `t` from scratch; `scripts/render.py` drives it in headless Chromium, frame by frame, and encodes with ffmpeg. Same spec → same pixels (checked).

Coordinates are Raccord's: frame pixels from the centre, y up. Colours are brand-kit colour **names**, fonts are brand-kit **roles** (`title`, `signature`, `body`, `label`) — the same vocabulary as fcp-live's Raccord specs, from the same `../brandkits/<id>.json`.

## Workflow
1. **Brief → spec.** Start from `examples/baair-hook.json` (9:16 hook) or `examples/baair-lower-third.json` (16:9). Set `fps` to the **timeline's** fps (probe the footage: `raccord_probe_media`, or `ffprobe`); the brand kit's fps is only the default. Declare the beats first, then the shots, then the states.
2. **Critique loop** (mandatory, max 3 passes):
   `python3 scripts/render.py <spec> --contact-sheet` → **Read** `~/Movies/Raccord/motion/<slug>-<format>/contact-sheet.png` → answer the checklist in `CLAUDE.md` in writing → fix the spec. Errors (schema, grid, fades, springs, contrast, fonts, safe zone) come back as JSON with exit code 2 or 3: fix them, never work around them.
3. **Render**: `python3 scripts/render.py <spec>` (~5 s for 4 s of 9:16). Outputs:
   - `<Raccord media dir>/<slug>-<format>.mov` — ProRes 4444, alpha, bt709. Flat in the media folder so Raccord accepts it.
   - `~/Movies/Raccord/motion/<slug>-<format>/` — `<slug>-<format>.mp4` (H.264 over the preview background), `contact-sheet.png`, `spec.json` (resolved spec + frames digest + brand-kit hash).
4. **Hand over to fcp-live**: in the Raccord spec, add the `.mov` as a clip on a positive lane **above** the footage, same fps:
   `{"media": "baair-hook-9x16.mov", "name": "Hook motion", "offsetFrames": 0, "sourceStartFrames": 0, "durationFrames": 96, "lane": 2, "audioOnly": false}`
   then follow fcp-live (validate → propose → the user clicks *Importer*).
5. **Verify in FCP**: after the user opens the imported project, for each beat: `raccord_seek_playhead(seconds)` + `raccord_capture_viewer()`, **read** the PNG: motion over footage with transparency (no black box), legible on the brightest frame of the footage, fonts right. Fix the spec, re-render, re-propose.

## Options
- `--format 9x16|1x1|16x9` — renders another aspect ratio by scaling positions per axis and sizes by the smaller ratio. A starting point: read the contact sheet, the safe-zone audit fails anything that no longer fits.
- `--brandkit <id>` — brand transfer; works when the target kit has the same colour names (otherwise copy the spec and rename colours).
- `--frames DIR` — PNG frames only.

## Checks
`python3 scripts/check.py` — renderer purity (no timers/clock/unseeded random/network/eval), examples valid, fonts installed, negative cases rejected, determinism (two renders identical, frame order irrelevant). Run it after touching `renderer/` or `scripts/`.

## Requirements
`/opt/homebrew/bin/python3.12` with `playwright` + `jsonschema` (user site), Playwright's Chromium, `ffmpeg` (Homebrew), brand fonts in `~/Library/Fonts`. No network at render time: every request other than the local renderer files is aborted.
