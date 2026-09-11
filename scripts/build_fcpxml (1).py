#!/usr/bin/env python3
"""Build a minimal, valid FCPXML 1.11 document from source clips plus branded
titles, ready for SpliceKit `fcpxml.import` (internal, no dialog).

Design goals:
  * exact rational timing (frame-accurate, no float drift)
  * titles as connected clips (lane 1) over the primary storyline
  * brand kit drives font / colour / size (see ../brandkits/*.json)

Usage:
  build_fcpxml.py spec.json > out.fcpxml

spec.json:
{
  "event": "SpliceKit Test",
  "project": "Reel test",
  "width": 1080, "height": 1920, "fps": 24,      # fps: 24, 25, 30, 23.976, 29.97, 60
  "brandkit": "baair",                             # optional, file in ../brandkits
  "clips": [ {"path": "/abs/clip.mp4", "in": 0.0, "duration": 8.0, "volume_db": -12} ],  # volume_db ducks the clip's own audio
  "audio": [                                       # optional voice-over / music, connected below the storyline
     {"path": "/abs/voiceover.wav", "start": 0.3, "role": "dialogue", "volume_db": 0},
     {"path": "/abs/music.mp3",     "start": 0.0, "role": "music",    "volume_db": -12, "duration": 8}
  ],
  "titles": [
     {"text": "Hook line", "start": 0.5, "duration": 2.5,
      "role": "title",            # brandkit font role: title | signature | body | label
      "size": 96,                 # FRAME pixels (em height); divided by template_scale (2.0)
      "position": "0 800",        # FRAME pixels from centre, y up (lower third of a reel: "0 -700")
      "color": "ink_paper", "align": "center",
      "font": "Helvetica Neue", "face": "Bold"},  # explicit font overrides the brandkit
     {"start": 3, "duration": 2, "size": 88, "position": "0 600",
      "runs": [ {"text": "Tools, ", "role": "title"},               # mixed styles on one line
                {"text": "not decks.", "role": "signature"} ]}
  ]
}
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import uuid
from fractions import Fraction
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

HERE = Path(__file__).resolve().parent
BRANDKITS = HERE.parent / "brandkits"

FPS_TABLE = {
    "24": (Fraction(100, 2400), "FFVideoFormatRateUndefined"),
    "25": (Fraction(100, 2500), "FFVideoFormatRateUndefined"),
    "30": (Fraction(100, 3000), "FFVideoFormatRateUndefined"),
    "23.976": (Fraction(1001, 24000), "FFVideoFormatRateUndefined"),
    "29.97": (Fraction(1001, 30000), "FFVideoFormatRateUndefined"),
    "60": (Fraction(100, 6000), "FFVideoFormatRateUndefined"),
}

BASIC_TITLE_UID = (".../Titles.localized/Bumper:Opener.localized/"
                   "Basic Title.localized/Basic Title.moti")


def rational(t: Fraction) -> str:
    """FCPXML rational time string: '19400/2400s'. Integer seconds stay '8s'."""
    if t.denominator == 1:
        return f"{t.numerator}s"
    return f"{t.numerator}/{t.denominator}s"


def frames(seconds: float, fd: Fraction) -> Fraction:
    """Snap a float second value to a whole number of frames."""
    n = round(Fraction(seconds).limit_denominator(100000) / fd)
    return n * fd


def probe(path: str) -> dict:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries",
         "stream=codec_type,width,height,r_frame_rate,channels:format=duration",
         "-of", "json", path], capture_output=True, text=True, check=True).stdout
    d = json.loads(out)
    info = {"duration": float(d["format"]["duration"]), "hasVideo": 0, "hasAudio": 0,
            "width": 0, "height": 0, "channels": 0, "fps": None}
    for s in d.get("streams", []):
        if s.get("codec_type") == "video" and not info["hasVideo"]:
            info["hasVideo"] = 1
            info["width"], info["height"] = s.get("width", 0), s.get("height", 0)
            num, den = s.get("r_frame_rate", "24/1").split("/")
            info["fps"] = Fraction(int(num), int(den))
        elif s.get("codec_type") == "audio" and not info["hasAudio"]:
            info["hasAudio"] = 1
            info["channels"] = int(s.get("channels", 2))
    return info


def hex_to_fcp(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    return f"{r:.4f} {g:.4f} {b:.4f} 1"


def load_brandkit(name: str | None) -> dict:
    if not name:
        return {}
    with open(BRANDKITS / f"{name}.json", encoding="utf-8") as fh:
        return json.load(fh)


def resolve_style(t: dict, kit: dict) -> dict:
    role = t.get("role", "title")
    kit_font = (kit.get("fonts") or {}).get(role, {})
    font = t.get("font") or kit_font.get("family") or "Helvetica Neue"
    face = t.get("face") or kit_font.get("face") or "Bold"
    color = t.get("color", "#FFFFFF")
    if not color.startswith("#"):
        color = ((kit.get("colors") or {}).get(color) or {}).get("hex", "#FFFFFF")
    return {"font": font, "face": face, "fontColor": hex_to_fcp(color),
            "size": int(t.get("size", 72)), "align": t.get("align", "center")}


def build(spec: dict) -> str:
    fps_key = str(spec.get("fps", 24))
    if fps_key not in FPS_TABLE:
        raise SystemExit(f"unsupported fps {fps_key}; use one of {list(FPS_TABLE)}")
    fd, _ = FPS_TABLE[fps_key]
    width, height = int(spec.get("width", 1080)), int(spec.get("height", 1920))
    kit = load_brandkit(spec.get("brandkit"))

    resources = [
        f'<format id="r1" name="FFVideoFormatRateUndefined" frameDuration="{rational(fd)}" '
        f'width="{width}" height="{height}" colorSpace="1-1-1 (Rec. 709)"/>',
        f'<effect id="rTitle" name="Basic Title" uid={quoteattr(BASIC_TITLE_UID)}/>',
    ]
    spine: list[str] = []
    timeline_pos = Fraction(0)
    clip_entries = []  # (start, duration) on the timeline, to anchor titles

    for i, c in enumerate(spec.get("clips", []), start=2):
        path = os.path.abspath(os.path.expanduser(c["path"]))
        if not os.path.exists(path):
            raise SystemExit(f"clip not found: {path}")
        info = probe(path)
        asset_dur = frames(info["duration"], fd)
        clip_in = frames(float(c.get("in", 0.0)), fd)
        clip_dur = frames(float(c.get("duration", info["duration"] - float(c.get("in", 0.0)))), fd)
        if clip_in + clip_dur > asset_dur:
            clip_dur = asset_dur - clip_in
        rid = f"r{i}"
        name = escape(Path(path).stem)
        audio_attrs = (f' audioSources="1" audioChannels="{info["channels"] or 2}" audioRate="48000"'
                       if info["hasAudio"] else "")
        resources.append(
            f'<asset id="{rid}" name="{name}" uid="{uuid.uuid4().hex.upper()}" start="0s" '
            f'duration="{rational(asset_dur)}" hasVideo="{info["hasVideo"]}" '
            f'hasAudio="{info["hasAudio"]}" format="r1"{audio_attrs}>'
            f'<media-rep kind="original-media" src={quoteattr(Path(path).as_uri())}/></asset>')
        clip_entries.append((timeline_pos, clip_dur, rid, name, clip_in))
        timeline_pos += clip_dur

    # Titles are connected clips over the clip under their start time.
    # Overlapping titles MUST sit in distinct lanes (FCP silently renders only
    # one of several items sharing a lane at the same time), so lanes are
    # assigned automatically: 1 for the first, 2 for one overlapping it, etc.
    #
    # Coordinate/size space: the Basic Title's Motion template is measured in
    # a space twice as coarse as frame pixels (measured on FCP 12.3, 1080x1920:
    # Position "0 300" lands 600 px above centre, fontSize 54 renders ~108 px).
    # Spec values are therefore given in FRAME PIXELS and divided by
    # TEMPLATE_SCALE here. Use "size_raw" / "position_raw" to bypass.
    TEMPLATE_SCALE = float(spec.get("template_scale", 2.0))
    titles_by_clip: dict[int, list[str]] = {}
    active: list[tuple[Fraction, Fraction, int]] = []  # (start, end, lane)
    for n, t in enumerate(sorted(spec.get("titles", []), key=lambda x: float(x["start"]))):
        st = frames(float(t["start"]), fd)
        du = frames(float(t.get("duration", 2.0)), fd)
        style = resolve_style(t, kit)
        if "size_raw" in t:
            style["size"] = int(t["size_raw"])
        else:
            style["size"] = max(1, round(style["size"] / TEMPLATE_SCALE))
        active = [a for a in active if a[1] > st]
        used = {a[2] for a in active}
        lane = t.get("lane") or next(l for l in range(1, 50) if l not in used)
        active.append((st, st + du, lane))
        target = None
        for idx, (cs, cd, *_rest) in enumerate(clip_entries):
            if cs <= st < cs + cd:
                target = idx
                break
        if target is None:
            raise SystemExit(f"title '{t['text']}' starts at {t['start']}s, outside the clips")
        cs = clip_entries[target][0]
        offset = st - cs  # connected-item offset, relative to the parent clip's timeline start
        ts_id = f"ts{n + 1}"
        pos_raw = t.get("position_raw")
        if not pos_raw and "position" in t:
            px, py = (float(v) for v in str(t["position"]).split())
            pos_raw = f"{px / TEMPLATE_SCALE:.0f} {py / TEMPLATE_SCALE:.0f}"
        # Basic Title: Transform > Position of the text layer. Must precede <text>.
        pos_param = (f'<param name="Position" key="9999/999166631/999166633/1/100/101" value="{pos_raw}"/>'
                     if pos_raw else "")
        # start="3600s" is FCP's convention for Motion titles (media start).
        # A title is one or more styled runs. "runs" lets one line mix styles
        # (baair: Fraunces + the signature word in Instrument Serif italic).
        runs = t.get("runs") or [{"text": t["text"]}]
        text_xml, defs_xml = "", ""
        for k, run in enumerate(runs):
            rs = resolve_style({**t, **run}, kit)
            rs["size"] = int(run["size_raw"]) if "size_raw" in run else style["size"]
            rid_ts = f"{ts_id}_{k}"
            text_xml += f'<text-style ref="{rid_ts}">{escape(run["text"])}</text-style>'
            defs_xml += (f'<text-style-def id="{rid_ts}"><text-style font={quoteattr(rs["font"])} '
                         f'fontSize="{rs["size"]}" fontFace={quoteattr(rs["face"])} '
                         f'fontColor="{rs["fontColor"]}" alignment="{style["align"]}"/></text-style-def>')
        label = t.get("text") or "".join(r["text"] for r in runs)
        titles_by_clip.setdefault(target, []).append(
            f'<title ref="rTitle" lane="{lane}" offset="{rational(offset)}" name={quoteattr(label[:40])} '
            f'duration="{rational(du)}" start="3600s">{pos_param}'
            f'<text>{text_xml}</text>{defs_xml}</title>')

    # Audio (voice-over, music) as connected audio clips in negative lanes,
    # anchored to the clip under their start time. Volume via <adjust-volume>.
    audio_by_clip: dict[int, list[str]] = {}
    for j, a in enumerate(spec.get("audio", [])):
        path = os.path.abspath(os.path.expanduser(a["path"]))
        if not os.path.exists(path):
            raise SystemExit(f"audio not found: {path}")
        info = probe(path)
        a_dur = frames(info["duration"], fd)
        st = frames(float(a.get("start", 0.0)), fd)
        du = frames(float(a["duration"]), fd) if "duration" in a else a_dur
        du = min(du, a_dur)
        rid = f"ra{j + 1}"
        name = escape(Path(path).stem)
        resources.append(
            f'<asset id="{rid}" name="{name}" uid="{uuid.uuid4().hex.upper()}" start="0s" '
            f'duration="{rational(a_dur)}" hasVideo="0" hasAudio="1" audioSources="1" '
            f'audioChannels="{info["channels"] or 2}" audioRate="48000">'
            f'<media-rep kind="original-media" src={quoteattr(Path(path).as_uri())}/></asset>')
        target = None
        for idx, (cs, cd, *_rest) in enumerate(clip_entries):
            if cs <= st < cs + cd:
                target = idx
                break
        if target is None:
            raise SystemExit(f"audio '{name}' starts at {a.get('start', 0)}s, outside the clips")
        offset = st - clip_entries[target][0]
        lane = -(len(audio_by_clip.get(target, [])) + 1)
        vol = float(a.get("volume_db", 0))
        vol_xml = f'<adjust-volume amount="{vol:g}dB"/>' if abs(vol) > 0.01 else ""
        audio_by_clip.setdefault(target, []).append(
            f'<asset-clip ref="{rid}" lane="{lane}" offset="{rational(offset)}" name="{name}" '
            f'start="0s" duration="{rational(du)}" audioRole="{a.get("role", "dialogue")}">{vol_xml}</asset-clip>')

    for idx, (cs, cd, rid, name, clip_in) in enumerate(clip_entries):
        vol = float(spec["clips"][idx].get("volume_db", 0))
        vol_xml = f'<adjust-volume amount="{vol:g}dB"/>' if abs(vol) > 0.01 else ""
        inner = vol_xml + "".join(audio_by_clip.get(idx, [])) + "".join(titles_by_clip.get(idx, []))
        spine.append(
            f'<asset-clip ref="{rid}" offset="{rational(cs)}" name="{name}" start="{rational(clip_in)}" '
            f'duration="{rational(cd)}" format="r1" tcFormat="NDF" audioRole="dialogue">{inner}</asset-clip>')

    seq_dur = rational(timeline_pos)
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE fcpxml>\n<fcpxml version="1.11">\n'
        "<resources>\n" + "\n".join(resources) + "\n</resources>\n"
        f'<event name={quoteattr(spec.get("event", "SpliceKit"))}>\n'
        f'<project name={quoteattr(spec.get("project", "Untitled"))}>\n'
        f'<sequence duration="{seq_dur}" format="r1" tcStart="0s" tcFormat="NDF" '
        'audioLayout="stereo" audioRate="48k">\n<spine>\n' + "\n".join(spine) +
        "\n</spine>\n</sequence>\n</project>\n</event>\n</fcpxml>\n")
    return xml


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    with open(sys.argv[1], encoding="utf-8") as fh:
        spec = json.load(fh)
    sys.stdout.write(build(spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
