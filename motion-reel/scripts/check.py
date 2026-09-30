#!/usr/bin/env python3
"""motion-reel checks. Exit 0 when everything passes.

  python3 scripts/check.py

1. renderer purity: no timers, clock, unseeded randomness, network or eval in renderer/
2. every example validates: closed schema + house rules (beat grid = duration, frames, fades, accents, springs)
3. the brand fonts of every example are installed (no silent fallback)
4. negative cases are rejected (spec off the grid, missing font, ease-in-out, emoji)
5. determinism: two renders of examples/baair-hook.json give identical frames, and seek(t) does not depend
   on the frames drawn before it
"""
import asyncio
import copy
import hashlib
import json
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mr_core  # noqa: E402
import render  # noqa: E402

FORBIDDEN = re.compile(r"\b(setTimeout|setInterval|requestAnimationFrame|Date\.now|new Date|performance\.now|Math\.random|"
                       r"eval|Function\(|fetch|XMLHttpRequest|WebSocket|importScripts|import\()")
EXAMPLES = sorted((mr_core.SKILL / "examples").glob("*.json"))
results = []


def check(name, ok, detail=""):
    results.append(ok)
    print("%s  %s%s" % ("PASS" if ok else "FAIL", name, ("  — " + detail) if detail else ""))


def purity():
    hits = []
    for path in sorted((mr_core.SKILL / "renderer").iterdir()):
        for n, line in enumerate(path.read_text().splitlines(), 1):
            code = line.split("//")[0]
            if FORBIDDEN.search(code):
                hits.append("%s:%d" % (path.name, n))
    check("renderer sans timer, horloge, aléa non seedé ni réseau", not hits, ", ".join(hits))


def examples():
    for path in EXAMPLES:
        spec = json.loads(path.read_text())
        try:
            resolved, kit, fonts, warnings = mr_core.resolve(spec)
            frames = resolved["duration"] * resolved["fps"]
            check("%s : schéma + règles" % path.name, True, "%d images à %d i/s%s" % (round(frames), resolved["fps"],
                  ("; " + "; ".join(warnings)) if warnings else ""))
            check("%s : polices installées" % path.name, True, ", ".join("%s=%s" % (r, f["path"].name) for r, f in fonts.items()))
        except mr_core.SpecError as error:
            check("%s : schéma + règles + polices" % path.name, False, " | ".join(error.errors))


def rejected(name, mutate, expect):
    spec = copy.deepcopy(json.loads((mr_core.SKILL / "examples/baair-hook.json").read_text()))
    mutate(spec)
    try:
        mr_core.resolve(spec)
        check("rejette : " + name, False, "accepté à tort")
    except mr_core.SpecError as error:
        hit = [e for e in error.errors if expect in e]
        check("rejette : " + name, bool(hit), (hit or error.errors)[0])


def negatives():
    rejected("durée ≠ fin de la grille", lambda s: s.update(duration=4.5), "grille de beats")
    rejected("état hors grille", lambda s: s["states"][1].update(t0=0.3), "hors grille")
    rejected("ease-in-out", lambda s: s["states"][2].update(easing={"type": "ease-in-out"}), "schéma")
    rejected("emoji", lambda s: s["layers"][1]["runs"][0].update(text="Tools 🚀"), "emoji")
    rejected("fondu trop court", lambda s: s["states"][1].update(t1=0.375), "fondu linéaire")
    rejected("ressort non arrivé", lambda s: s["states"][2]["easing"].update(omega=4), "ressort")
    rejected("texte en même temps que l'accent", lambda s: s["states"][0].update(t0=0.25, t1=0.25), "l'accent doit apparaître")
    rejected("couleur hors kit", lambda s: s["layers"][1].update(color="red"), "absente du brand kit")
    rejected("contraste < 4,5:1", lambda s: s["layers"][2].update(color="grey_body_light"), "contraste")
    def missing_font(s):
        mr_core.FONT_DIRS[:] = [Path(tempfile.gettempdir()) / "motion-reel-no-fonts"]
    saved = list(mr_core.FONT_DIRS)
    try:
        rejected("police absente (pas de repli)", missing_font, "Police manquante")
    finally:
        mr_core.FONT_DIRS[:] = saved


async def determinism():
    spec_path = mr_core.SKILL / "examples/baair-hook.json"
    with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
        first = await render.render(spec_path, frames_out=a)
        second = await render.render(spec_path, frames_out=b)
    check("déterminisme : 2 rendus = mêmes images", first["digest"] == second["digest"], "%d images, sha256 %s…" % (first["frames"], first["digest"][:12]))
    spec, kit, fonts, _ = mr_core.resolve(json.loads(spec_path.read_text()))
    async with render.Renderer(spec, kit, fonts) as r:
        forward = [hashlib.sha256(await r.frame(i)).hexdigest() for i in (10, 50, 80)]
        backward = [hashlib.sha256(await r.frame(i)).hexdigest() for i in (80, 50, 10)][::-1]
    check("seek(t) pur : l'ordre des images ne change rien", forward == backward)


def main():
    purity()
    examples()
    negatives()
    asyncio.run(determinism())
    print("\n%d/%d vérifications passées" % (sum(results), len(results)))
    sys.exit(0 if all(results) else 1)


if __name__ == "__main__":
    main()
