# fcp-live — Claude edits Final Cut Pro, live, in your brand

A Claude Code skill that drives **Final Cut Pro 12** from the inside (via the
open-source [SpliceKit](https://github.com/elliotttate/SpliceKit) MCP server) to:

1. import generated or shot footage (Higgsfield, Kling, HeyGen, camera),
2. cut it and lay out **titles / motion-design text as connected clips**,
3. style every text element from a **brand kit** (fonts, colours, safe zones) so
   every reel of a project looks like that project,
4. optionally add a voice-over,
5. verify the result **visually** (viewer captures) before handing you the
   timeline. Export stays manual, on purpose.

Everything runs locally. No footage leaves the Mac.

## How it works

```
brief ──► spec.json ──► build_fcpxml.py ──► FCPXML ──► SpliceKit fcpxml.import
                            ▲                                   │
                     brandkits/<id>.json               open_project / blade /
                     (fonts, colours,                  seek / capture_viewer
                      safe zones)                              │
                                                       Claude reads the PNG,
                                                       fixes, repeats
```

* `scripts/build_fcpxml.py` — frame-accurate FCPXML 1.11 generator. Titles are
  Basic Title instances with `<text-style>` runs; sizes and positions are given
  in **frame pixels** and converted to Motion's template space (2× on FCP 12.3).
  Overlapping titles get distinct lanes automatically (FCP silently drops
  overlaps in one lane). Mixed-style runs on one line are supported.
* `scripts/skbridge.py` — tiny JSON-RPC client for the SpliceKit bridge
  (`127.0.0.1:9876`), handy for scripting and for testing without MCP.
* `brandkits/baair.json` — example brand kit (baair.solutions).
* `splicekit-patches/` — the fixes needed to build SpliceKit v3.3.9 from source
  on a Mac without the Blackmagic RAW SDK, plus three `patch_fcp.sh` fixes
  (Makefile build, injection detection, signing identity). Submitted upstream as
  [elliotttate/SpliceKit#87](https://github.com/elliotttate/SpliceKit/pull/87);
  the patch file here is only needed until it is merged.
* `examples/` — calibration and demo specs with the resulting viewer captures.
* `SKILL.md` — the operating procedure Claude follows (French).

## Requirements

macOS 14+, Final Cut Pro 12 (App Store), Xcode command line tools, Python 3.10+,
ffmpeg, a codesigning identity (Apple Development is enough). SpliceKit patches a
**copy** of FCP in `~/Applications/SpliceKit/`; the original is untouched.

## Install (summary)

```bash
git clone https://github.com/elliotttate/SpliceKit ~/.local/share/splicekit/SpliceKit
cd ~/.local/share/splicekit/SpliceKit
git apply /path/to/fcp-live/splicekit-patches/0001-*.patch
bash Scripts/ensure_sentry_framework.sh      # build dependency
./patcher/patch_fcp.sh                       # copy + build + inject + sign
make mcp-setup                               # venv at ~/.venvs/splicekit-mcp
claude mcp add splicekit -s user -- ~/.venvs/splicekit-mcp/bin/python \
    ~/.local/share/splicekit/SpliceKit/mcp/server.py
```

Disable crash telemetry before first launch (it ships with `sendDefaultPii`):

```bash
mkdir -p ~/Library/Application\ Support/SpliceKit
printf '<?xml version="1.0"?><!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd"><plist version="1.0"><dict><key>Enabled</key><false/></dict></plist>' \
  > ~/Library/Application\ Support/SpliceKit/SpliceKitSentryConfig.plist
```

Quit the stock FCP, launch `~/Applications/SpliceKit/Final Cut Pro.app`, open a
library, and Claude can start editing.

## Status

Validated 2026-09-03 on FCP 12.3 / macOS 26.5.2 / SpliceKit 3.3.9: FCPXML import,
brand fonts, mixed-style titles, lanes, positions, viewer verification.
Not yet: voice-over round-trip, caption styling, transitions library.

MIT — see LICENSE. Not affiliated with Apple or SpliceKit.
