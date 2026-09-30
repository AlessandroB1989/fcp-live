#!/usr/bin/env python3
"""motion-reel — render a spec to ProRes 4444 (alpha) + H.264 control + contact sheet.

  python3 scripts/render.py examples/baair-hook.json                      full render in the spec's format
  python3 scripts/render.py examples/baair-hook.json --format 1x1         adapted to another aspect ratio
  python3 scripts/render.py examples/baair-hook.json --brandkit ia-pilotes   brand transfer (same colour names/roles)
  python3 scripts/render.py examples/baair-hook.json --contact-sheet      only the contact sheet (fast critique loop)
  python3 scripts/render.py examples/baair-hook.json --frames DIR         only the PNG frames (used by check.py)

Outputs: <Raccord media dir>/<slug>-<format>.mov (flat: Raccord refuses sub-folders) and
~/Movies/Raccord/motion/<slug>-<format>/ with the .mp4, contact-sheet.png and the resolved spec.json.
Headless Chromium on local files only (every other request is aborted); ffmpeg for encoding. No network.
"""
import argparse
import asyncio
import base64
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mr_core  # noqa: E402

RENDERER = mr_core.SKILL / "renderer"
CHROMIUM_ARGS = ["--disable-gpu", "--force-color-profile=srgb", "--disable-lcd-text", "--disable-background-networking",
                 "--disable-extensions", "--no-first-run"]
FFMPEG = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"


def media_dir():
    config = Path.home() / "Library/Application Support/Raccord/config.json"
    try:
        return Path(json.loads(config.read_text())["mediaDirectory"])
    except (OSError, KeyError, ValueError):
        return Path.home() / "Movies/Raccord/media"


def font_payload(fonts):
    payload = []
    for role, f in fonts.items():
        payload.append({"alias": f["alias"], "data": base64.b64encode(f["path"].read_bytes()).decode(),
                        "weight": f["weight"], "weightRange": "1 1000" if f["variable"] else str(f["weight"]),
                        "style": f["style"], "label": "%s %s (%s, %s)" % (f["family"], f["face"], role, f["path"].name)})
    return payload


def kit_payload(kit, fonts):
    return {"colors": mr_core.kit_colors(kit),
            "fonts": {role: {"alias": f["alias"], "weight": f["weight"], "style": f["style"]} for role, f in fonts.items()}}


class Renderer:
    """One headless page holding the spec; seek(t) returns the PNG bytes of frame t."""

    def __init__(self, spec, kit, fonts):
        self.spec, self.kit, self.fonts = spec, kit, fonts

    async def __aenter__(self):
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(args=CHROMIUM_ARGS)
        page = await self._browser.new_page(viewport={"width": 64, "height": 64}, device_scale_factor=1)
        allowed = RENDERER.as_uri() + "/"
        await page.route("**/*", lambda route: route.continue_() if route.request.url.startswith(allowed) else route.abort())
        await page.goto((RENDERER / "index.html").as_uri())
        await page.evaluate("args => init(args)", {"spec": self.spec, "kit": kit_payload(self.kit, self.fonts),
                                                   "fonts": font_payload(self.fonts)})
        self.page = page
        return self

    async def __aexit__(self, *exc):
        await self._browser.close()
        await self._pw.stop()

    async def frame(self, index):
        url = await self.page.evaluate("t => seek(t)", index / self.spec["fps"])
        return base64.b64decode(url.split(",", 1)[1])

    async def audit(self, indices):
        return await self.page.evaluate("ts => audit(ts)", [i / self.spec["fps"] for i in indices])

    async def contact_sheet(self, safe, background):
        spec, n = self.spec, frame_count(self.spec)
        picks = sorted({round(i * (n - 1) / 11) for i in range(12)})
        shot = lambda t: next((s["name"] for s in spec["shots"] if s["t0"] - 1e-9 <= t < s["t1"] - 1e-9), spec["shots"][-1]["name"])
        labels = ["%.2fs  f%d  %s" % (i / spec["fps"], i, shot(i / spec["fps"])) for i in picks]
        width, cols = {"9x16": (260, 6), "1x1": (340, 4), "16x9": (400, 4)}[spec["format"]]
        url = await self.page.evaluate("a => contactSheet(a)", {"times": [i / spec["fps"] for i in picks], "cols": cols,
                                                               "thumbWidth": width, "background": background, "safe": safe, "labels": labels})
        return base64.b64decode(url.split(",", 1)[1])


def frame_count(spec):
    return round(spec["duration"] * spec["fps"])


def audit_errors(report, spec, safe):
    """Text (and accent) boxes must stay inside the safe zone on every frame."""
    limits = (safe["left"], safe["top"], spec["width"] - safe["right"], spec["height"] - safe["bottom"])
    kinds = {l["id"]: l for l in spec["layers"]}
    seen, errors, warnings = set(), [], []
    for entry in report:
        for box in entry["boxes"]:
            out = box["x0"] < limits[0] - 0.5 or box["y0"] < limits[1] - 0.5 or box["x1"] > limits[2] + 0.5 or box["y1"] > limits[3] + 0.5
            if not out or box["id"] in seen:
                continue
            seen.add(box["id"])
            layer = kinds[box["id"]]
            message = "%s hors zone sûre à %.2f s (boîte %d,%d → %d,%d ; zone %d,%d → %d,%d)" % (
                box["id"], entry["t"], box["x0"], box["y0"], box["x1"], box["y1"], *limits)
            (errors if layer["type"] == "text" or layer.get("accent") else warnings).append(message)
    return errors, warnings


def hex_of(kit, name):
    return name if name.startswith("#") else mr_core.kit_colors(kit)[name]


def encode(frames_dir, spec, mov, mp4, backdrop):
    fps, w, h = str(spec["fps"]), spec["width"], spec["height"]
    pattern = str(frames_dir / "%05d.png")
    tags = ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    subprocess.run([FFMPEG, "-v", "error", "-y", "-framerate", fps, "-i", pattern,
                    "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuva444p10le",
                    "-c:v", "prores_ks", "-profile:v", "4444", "-alpha_bits", "16", "-vendor", "apl0", *tags, str(mov)], check=True)
    subprocess.run([FFMPEG, "-v", "error", "-y", "-framerate", fps, "-i", pattern,
                    "-f", "lavfi", "-i", "color=c=0x%s:s=%dx%d:r=%s" % (backdrop.lstrip("#"), w, h, fps),
                    "-filter_complex", "[1:v][0:v]overlay=shortest=1,scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
                    "-c:v", "libx264", "-crf", "16", "-preset", "medium", "-movflags", "+faststart", *tags, str(mp4)], check=True)


async def render(spec_path, fmt=None, brandkit=None, contact_only=False, frames_out=None):
    started = time.monotonic()
    raw = json.loads(Path(spec_path).read_text())
    spec, kit, fonts, warnings = mr_core.resolve(raw, fmt, brandkit)
    slug = "%s-%s" % (spec["name"], spec["format"])
    safe = mr_core.safe_rect(kit, spec["format"])
    backdrop_name = spec.get("background") or spec.get("preview", {}).get("background")
    backdrop = hex_of(kit, backdrop_name) if backdrop_name else "#808080"
    work = Path.home() / "Movies/Raccord/motion" / slug
    n = frame_count(spec)
    result = {"spec": slug, "format": spec["format"], "fps": spec["fps"], "frames": n, "brandkit": spec["brandkit"],
              "fonts": {r: f["path"].name for r, f in fonts.items()}, "warnings": warnings}

    async with Renderer(spec, kit, fonts) as r:
        if frames_out:
            out = Path(frames_out); out.mkdir(parents=True, exist_ok=True)
            digests = []
            for i in range(n):
                data = await r.frame(i)
                (out / ("%05d.png" % i)).write_bytes(data)
                digests.append(hashlib.sha256(data).hexdigest())
            result.update(framesDir=str(out), digest=hashlib.sha256("".join(digests).encode()).hexdigest())
            return result
        errors, audit_warnings = audit_errors(await r.audit(range(n)), spec, safe)
        result["warnings"] += audit_warnings
        work.mkdir(parents=True, exist_ok=True)
        sheet = work / "contact-sheet.png"
        sheet.write_bytes(await r.contact_sheet(safe, backdrop))
        result["contactSheet"] = str(sheet)
        if errors:
            result["errors"] = errors
            return result
        if contact_only:
            return result
        with tempfile.TemporaryDirectory(prefix="motion-reel-") as tmp:
            digests = []
            for i in range(n):
                data = await r.frame(i)
                (Path(tmp) / ("%05d.png" % i)).write_bytes(data)
                digests.append(hashlib.sha256(data).hexdigest())
            target = media_dir(); target.mkdir(parents=True, exist_ok=True)
            mov, mp4 = target / (slug + ".mov"), work / (slug + ".mp4")
            encode(Path(tmp), spec, mov, mp4, backdrop)
    resolved = dict(spec, framesDigest=hashlib.sha256("".join(digests).encode()).hexdigest(),
                    brandkitSha256=hashlib.sha256((mr_core.REPO / "brandkits" / (spec["brandkit"] + ".json")).read_bytes()).hexdigest())
    (work / "spec.json").write_text(json.dumps(resolved, indent=2, ensure_ascii=False))
    result.update(mov=str(mov), mp4=str(mp4), specJson=str(work / "spec.json"), seconds=round(time.monotonic() - started, 1))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec")
    parser.add_argument("--format", choices=sorted(mr_core.FORMATS))
    parser.add_argument("--brandkit")
    parser.add_argument("--contact-sheet", action="store_true", help="only render the contact sheet")
    parser.add_argument("--frames", metavar="DIR", help="only write the PNG frames to DIR")
    args = parser.parse_args()
    try:
        result = asyncio.run(render(args.spec, args.format, args.brandkit, args.contact_sheet, args.frames))
    except mr_core.SpecError as error:
        print(json.dumps({"errors": error.errors}, indent=2, ensure_ascii=False))
        sys.exit(2)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(3 if result.get("errors") else 0)


if __name__ == "__main__":
    main()
