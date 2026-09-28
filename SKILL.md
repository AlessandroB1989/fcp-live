---
name: fcp-live
description: Edit videos in Final Cut Pro from Claude — import footage (Higgsfield, Kling, HeyGen, camera), cut it, lay out titles and motion-design text styled from a project brand kit (fonts, colours, safe zones), add a voice-over, and verify the result visually. Default path is Raccord (formerly SpliceKit Safe) (official FCP, MCP `raccord`, human approval, no injection); the patched-FCP SpliceKit bridge is a reserve tool only. Trigger on "edit this video", "put it in Final Cut", "make the reel", "add the titles / motion design", "brand this video", "voice-over", "captions in FCP", any mention of Final Cut, FCP, SpliceKit, timeline, brand kit video — and their French equivalents (« monte cette vidéo », « mets-la dans Final Cut », « fais le montage », « ajoute les textes », « reel baair », « habille cette vidéo »). Export stays manual.
---

# fcp-live — Claude edits Final Cut Pro, in your brand

## Two paths, one default

| | **Raccord (default)** | SpliceKit bridge (reserve) |
|---|---|---|
| FCP | the official App Store app | a patched copy in `~/Applications/SpliceKit/` |
| MCP | `raccord` (13 tools) | `splicekit` (~220 tools) |
| Injection | none | dylib injected (CleanMyMac / EDR alerts) |
| Writes | new FCPXML, **approved by the user** in the companion app, then imported by FCP | direct, in-process |
| Reads | panel state, playhead, window screenshot | everything |
| Use for | producing reels and motion design from a brief (the normal job) | retouching an existing hand-made timeline when the user explicitly asks |

Never launch the patched copy on your own. If a task needs it, say so and let the user decide.

**Raccord is the primary tool for editing jobs (decision of 2026-09-28).** The procedure is model-independent; it was written to take advantage of Claude Opus 5.5 (`claude-opus-5-5`), whose faster output and more economical tool use make several propose → import → capture → correct iterations per reel practical. Two things do not change with the model: the user approves every import in Raccord's destination dialog, and every title is checked on a viewer capture before handover.

## What this skill does
1. **Editing** of generated or shot footage: clips on lanes, cuts by frame ranges, markers.
2. **Motion design / text**: hooks, lines, labels, CTAs as connected Basic Title clips styled from the project's **brand kit** (`brandkits/<project>.json`), with linear keyframes (position, scale, rotation, opacity).
3. **Brand transfer**: same brief, another brand kit, same workflow.
4. **Voice-over / music**: audio clips on negative lanes with dB gain; clip audio ducked.
5. **Export: never automated.** The user exports (File > Share).

## Safe path — prerequisites
- App installed: `/Applications/Raccord.app` (companion + MCP server + Workflow Extension), built from `MCP & Skills/Raccord` with `python3 build.py install`.
- MCP `raccord` registered in Claude Code (user scope). Session dir is stable: `~/Library/Application Support/Raccord/session`.
- Companion running with a media folder and a target library chosen (remembered in its config). Exports land in `~/Movies/Raccord/`.
- In FCP: **Fenêtre > Extensions > Raccord** panel open (gives playhead control + state). Screen Recording granted to Raccord (for `raccord_capture_viewer`).
- Brand fonts installed in `~/Library/Fonts` (baair: Fraunces, Instrument Serif, Inter, JetBrains Mono).

## Safe path — workflow (9:16 reel)
0. **Profile window (dialog 1)** — at the start of every video job, unless the user says the profile is already confirmed: call `raccord_setup(profile: <project id>, brandkits: [ids in brandkits/*.json], prefill: {...})`. Prefill from ClaudeVault `list_characters` (character handle, HeyGen avatar id, HeyGen voice id, ElevenLabs voice id when present), the project's `profiles/<id>.json` (brand kit, default event) and the media folder. Raccord opens a form on the user's screen; the call blocks until they save or cancel and returns the saved profile. Use its values for the job (brand kit id, avatar/voice ids for HeyGen/ElevenLabs, media directory). Never pass or store API keys: the schema has no field for them; keys stay in ClaudeVault (`get_api_key`) and the connectors.
   - *Destination*: put a suggestion in the spec's `destination` (from `raccord_list_libraries` or the profile's default event). The user confirms or changes it in dialog 2.
1. **Brief**: brand kit, source clip(s) already copied into the companion's media folder (flat, no subfolders), message (hook, 2–4 lines, CTA), length, voice-over yes/no.
2. **Check**: `raccord_capabilities` (Raccord runs as a menu-bar item; `capture` and `playhead` are true when the FCP panel is open and Screen Recording granted). `raccord_list_media`, `raccord_probe_media(<file>)` for durations and sizes; copy source clips into the profile's media folder first.
3. **Spec** (see format below): frames at the project fps, brand kit inline (copy the values from `brandkits/<id>.json`), titles in frame pixels, `destination` hint. Run `raccord_validate_edit` until it passes; read `summary.titleLanes` / `fonts` / `destinationHint`.
4. **Propose (dialog 2)**: `raccord_propose_edit` → Raccord immediately shows "Importer « <name> » dans Final Cut Pro" with the library and event popups (libraries open in FCP), prefilled from the spec's `destination`. The user clicks *Importer* (= approval + export + hand-off to FCP) or *Annuler* (= rejected). Poll `raccord_get_proposal(id)` until `status` is `approved` with `imported == true`, or `rejected`/`expired` (15 min); `destination` in the answer is what the user chose. Never claim the import happened before `imported` is true.
5. **Open the project**: ask the user to double-click the imported project (event *Raccord* in the target library). FCP exposes no API to open a project.
6. **Verify visually**: for each title moment, `raccord_seek_playhead(seconds)` then `raccord_capture_viewer()` and **read the PNG**: font really loaded, no overflow, contrast, one accent element only, safe zones.
7. **Iterate**: fix the spec and propose again (each approval = a new project version; ask the user to delete the old one if they want).
8. **Handover**: summary, captures, "prêt à exporter".

## Safe spec format (`raccord_validate_edit` / `raccord_propose_edit` → `edit`)
```json
{ "name": "Reel baair — hook", "width": 1080, "height": 1920, "fps": "24", "durationFrames": 192,
  "destination": { "library": "Perso", "event": "Reels 2026" },
  "brandkit": { "id": "baair", "templateScale": 2.0,
    "colors": [{"name":"ink_paper","hex":"#FAFAF7"},{"name":"purple","hex":"#8C57E9"},{"name":"grey_body_dark","hex":"#C9C9C2"}],
    "fonts": [{"role":"title","family":"Fraunces","face":"Bold"},{"role":"signature","family":"Instrument Serif","face":"Italic"},
              {"role":"body","family":"Inter","face":"Regular"},{"role":"label","family":"JetBrains Mono","face":"Regular"}] },
  "clips": [ {"media":"clip.mp4","name":"Plan 1","offsetFrames":0,"sourceStartFrames":0,"durationFrames":192,"lane":1,"audioOnly":false,"volumeDB":-12},
             {"media":"voix.wav","name":"Voix","offsetFrames":7,"sourceStartFrames":0,"durationFrames":160,"lane":-1,"audioOnly":true} ],
  "titles": [ {"text":"■","offsetFrames":7,"durationFrames":70,"role":"body","size":56,"color":"purple","position":{"x":0,"y":760}},
              {"runs":[{"text":"Tools, ","role":"title"},{"text":"not decks.","role":"signature"}],"offsetFrames":7,"durationFrames":70,"size":84,"color":"ink_paper","position":{"x":0,"y":620}},
              {"text":"BAAIR.SOLUTIONS","offsetFrames":82,"durationFrames":77,"role":"label","size":30,"color":"grey_body_dark","position":{"x":0,"y":-680},
               "keyframes":[{"frame":0,"x":0,"y":0,"scale":1,"rotation":0,"opacity":0},{"frame":8,"x":0,"y":0,"scale":1,"rotation":0,"opacity":1}]} ],
  "markers": [ {"frame":7,"text":"Hook"} ] }
```
Rules: video clips on positive lanes, audio-only on negative lanes; everything sits above an empty base (not a magnetic storyline); titles without `lane` get the lowest free lane automatically; `size` and `position` are **frame pixels from centre, y up** (the engine divides by `templateScale`, 2.0 on FCP 12.3); `color` is a brand-kit colour name or `#RRGGBB`; a title needs `text` or `runs`, and `size` (or legacy `fontSize`). Keyframes are clip-relative frames, strictly increasing. Fonts must be installed on the Mac; a missing font silently becomes Helvetica.

## Brand kit → FCP (calibrated 2026-09-03, FCP 12.3, 1080×1920)
- `brandkits/<id>.json` holds colours, fonts per role (title / signature / body / label), safe zones and motion style; copy its colours and fonts into the spec's `brandkit`.
- Reel safe zones: hook at y ≈ +620, accent square at +760, body/label at y ≈ −560 / −680. Nothing below −760.
- Simultaneous titles must be on distinct lanes (automatic). Mixed styles on one line: `runs`.
- Accent square: title "■" (U+25A0) in `purple`, 56 px.

## Reserve path — SpliceKit bridge
Only on explicit request. Procedure, tool names and calibration are in `docs/SKILL.splicekit.md`. Rules: quit the stock FCP first, one FCP at a time, sandbox library, quit the patched copy when done, never export.

## Troubleshooting (Safe)
- `Raccord is not running` / connection refused: `open -a Raccord` (menu-bar item, no window).
- `panel unreachable`: open Fenêtre > Extensions > Raccord in FCP (the panel must stay open).
- `Capture failed … TCC`: grant Screen Recording to Raccord (System Settings > Privacy & Security), relaunch the app.
- `Open a project in the timeline first`: the user must open a project; the panel only controls the active timeline.
- `raccord_list_libraries` fails with an Automation message: the user must allow Raccord to control Final Cut Pro (System Settings > Privacy & Security > Automation), once. The approval dialog still works without it (fallback library + typed event).
- Import landed in the wrong place: the user picks library and event in the dialog at every approval; the previous choice is prefilled.
