"""motion-reel core: brand-kit resolution, font lookup, spec validation (schema + house rules), format
adaptation. Shared by render.py and check.py. Standard library + jsonschema only; no network."""
import copy
import json
import math
import re
from pathlib import Path

import jsonschema

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent                      # motion-reel/
REPO = SKILL.parent                      # fcp-live/ (brand kits live there, shared with the fcp-live skill)
SCHEMA = json.loads((SKILL / "spec.schema.json").read_text())
FORMATS = {"9x16": (1080, 1920), "1x1": (1080, 1080), "16x9": (1920, 1080)}
# Platform UI, not brand: Instagram/TikTok cover the bottom of a 9:16 frame with captions and buttons.
PLATFORM_BOTTOM_RESERVE = {"9x16": 250}
FONT_DIRS = [Path.home() / "Library/Fonts", Path("/Library/Fonts")]
FACE_WEIGHTS = {"thin": 100, "extralight": 200, "light": 300, "regular": 400, "book": 400, "medium": 500,
                "semibold": 600, "bold": 700, "extrabold": 800, "black": 900, "heavy": 900}
SPRING_RESIDUAL = 0.005
EMOJI = re.compile("[\U0001F000-\U0001FAFF☀-➿️‍]")


class SpecError(Exception):
    def __init__(self, errors):
        super().__init__("\n".join(errors))
        self.errors = errors


# ---- brand kit --------------------------------------------------------------------------------------
def load_kit(kit_id):
    path = REPO / "brandkits" / (kit_id + ".json")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,60}", kit_id) or not path.is_file():
        raise SpecError(["Brand kit introuvable : %s (attendu dans %s)" % (kit_id, REPO / "brandkits")])
    return json.loads(path.read_text())


def kit_colors(kit):
    return {name: value["hex"] for name, value in kit.get("colors", {}).items()}


def kit_fps(kit):
    for section in ("reel", "module", "youtube"):
        fps = kit.get("video", {}).get(section, {}).get("fps")
        if fps:
            return int(fps)
    raise SpecError(["Le brand kit %s ne déclare aucun fps (video.reel.fps) : fixe `fps` dans le spec." % kit["id"]])


def kit_fade_frames(kit, fps):
    durations = kit.get("motion", {}).get("durations", {})
    if "fade_frames" in durations:
        return int(durations["fade_frames"])
    if "fade_s" in durations:
        return round(durations["fade_s"] * fps)
    raise SpecError(["Le brand kit %s ne déclare pas motion.durations.fade_frames ni fade_s." % kit["id"]])


def kit_safe_margin(kit, fmt):
    width, height = FORMATS[fmt]
    sections = list(kit.get("video", {}).values())
    same_shape = [s for s in sections if isinstance(s, dict) and s.get("width") == width and s.get("height") == height]
    for section in same_shape + sections:
        if isinstance(section, dict) and "safe_margin_px" in section:
            return int(section["safe_margin_px"])
    return round(0.05 * min(width, height))   # broadcast title-safe fallback when the kit is silent


def safe_rect(kit, fmt):
    m = kit_safe_margin(kit, fmt)
    # The platform reserve already includes breathing room: it replaces the margin at the bottom, it does not add to it.
    return {"left": m, "right": m, "top": m, "bottom": max(m, PLATFORM_BOTTOM_RESERVE.get(fmt, 0))}


# ---- fonts ------------------------------------------------------------------------------------------
def _norm(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


def parse_face(face):
    key = _norm(face)
    italic = "italic" in key or "oblique" in key
    key = key.replace("italic", "").replace("oblique", "")
    weight = FACE_WEIGHTS.get(key or "regular")
    if weight is None:
        raise SpecError(["Graisse de police non reconnue : %r" % face])
    return weight, italic


def resolve_font(family, face):
    """Finds the installed file for family + face. Never substitutes: a missing face is an error."""
    weight, italic = parse_face(face)
    matches = []
    for folder in FONT_DIRS:
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if path.suffix.lower() not in (".ttf", ".otf"):
                continue
            stem = path.stem
            base, _, style = stem.split("[")[0].partition("-")
            if _norm(base) != _norm(family) or ("italic" in _norm(style)) != italic:
                continue
            variable = "[" in stem and "wght" in stem.lower()
            try:
                static_weight = None if variable else parse_face(style or "Regular")[0]
            except SpecError:
                continue
            if variable or static_weight == weight:
                matches.append((0 if not variable else 1, path, variable))
    if not matches:
        raise SpecError(["Police manquante : %s %s. Installe-la dans ~/Library/Fonts (aucun repli n'est fait)." % (family, face)])
    _, path, variable = sorted(matches)[0]
    return {"path": path, "variable": variable, "weight": weight, "style": "italic" if italic else "normal"}


def roles_used(spec):
    roles = set()
    for layer in spec["layers"]:
        if layer["type"] == "text":
            roles.update([layer["role"]] if "role" in layer else [r["role"] for r in layer["runs"]])
    return sorted(roles)


def fonts_for(spec, kit):
    fonts = {}
    for role in roles_used(spec):
        spec_font = kit.get("fonts", {}).get(role)
        if not spec_font:
            raise SpecError(["Rôle de police absent du brand kit %s : %s" % (kit["id"], role)])
        found = resolve_font(spec_font["family"], spec_font.get("face", "Regular"))
        fonts[role] = dict(found, family=spec_font["family"], face=spec_font.get("face", "Regular"), alias="mr-" + role)
    return fonts


# ---- maths shared with the renderer -----------------------------------------------------------------
def spring(tau, zeta, omega):
    """Same closed form as renderer/easing.js."""
    if tau <= 0:
        return 0.0
    if zeta < 1:
        wd = omega * math.sqrt(1 - zeta * zeta)
        return 1 - math.exp(-zeta * omega * tau) * (math.cos(wd * tau) + (zeta * omega / wd) * math.sin(wd * tau))
    if zeta == 1:
        return 1 - math.exp(-omega * tau) * (1 + omega * tau)
    s = omega * math.sqrt(zeta * zeta - 1)
    r1, r2 = -zeta * omega + s, -zeta * omega - s
    return 1 - (r2 * math.exp(r1 * tau) - r1 * math.exp(r2 * tau)) / (r2 - r1)


def luminance(hex_color):
    def channel(c):
        c = c / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (int(hex_color[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


# ---- validation -------------------------------------------------------------------------------------
def schema_errors(spec):
    validator = jsonschema.Draft202012Validator(SCHEMA)
    return ["schéma : %s : %s" % ("/".join(str(p) for p in e.absolute_path) or "(racine)", e.message)
            for e in sorted(validator.iter_errors(spec), key=lambda e: list(map(str, e.absolute_path)))]


def validate(spec, kit, fps):
    """House rules that a schema cannot express. Returns (errors, warnings)."""
    errors, warnings = [], []
    colors = kit_colors(kit)
    fade = kit_fade_frames(kit, fps)
    duration, beats = spec["duration"], spec["beats"]
    on_frame = lambda t: abs(t * fps - round(t * fps)) < 0.01
    on_beat = lambda t: any(abs(t - b) < 0.5 / fps for b in beats)

    if not on_frame(duration):
        errors.append("durée %.4f s n'est pas un nombre entier d'images à %d i/s" % (duration, fps))
    if abs(beats[0]) > 1e-9 or abs(beats[-1] - duration) > 0.5 / fps:
        errors.append("la grille de beats doit commencer à 0 et finir à la durée (%.4f)" % duration)
    if any(b2 <= b1 for b1, b2 in zip(beats, beats[1:])):
        errors.append("les beats doivent être strictement croissants")
    errors += ["beat %.4f s hors frame entière" % b for b in beats if not on_frame(b)]

    shots = spec["shots"]
    if abs(shots[0]["t0"]) > 1e-9 or abs(shots[-1]["t1"] - duration) > 0.5 / fps:
        errors.append("les plans doivent couvrir [0, durée]")
    for a, b in zip(shots, shots[1:]):
        if abs(a["t1"] - b["t0"]) > 0.5 / fps:
            errors.append("plans non contigus : %s → %s" % (a["name"], b["name"]))
    for shot in shots:
        if not (on_beat(shot["t0"]) and on_beat(shot["t1"])):
            errors.append("plan %s : bornes hors grille de beats" % shot["name"])

    ids = [layer["id"] for layer in spec["layers"]]
    if len(set(ids)) != len(ids):
        errors.append("identifiants de calques en double")
    layers = {layer["id"]: layer for layer in spec["layers"]}

    def check_color(name, where):
        if not name.startswith("#") and name not in colors:
            errors.append("%s : couleur %r absente du brand kit %s" % (where, name, kit["id"]))
    def hex_of(name):
        return name if name.startswith("#") else colors.get(name, "#000000")

    for key in ("background",):
        if key in spec:
            check_color(spec[key], key)
    if "preview" in spec and "background" in spec["preview"]:
        check_color(spec["preview"]["background"], "preview.background")
    backdrop = spec.get("background") or spec.get("preview", {}).get("background")
    if not backdrop:
        warnings.append("aucun fond (`background` ou `preview.background`) : contraste non vérifié")

    for layer in spec["layers"]:
        check_color(layer["color"], layer["id"])
        if layer["type"] != "text":
            continue
        texts = [layer["text"]] if "text" in layer else [r["text"] for r in layer["runs"]]
        if any(EMOJI.search(t) for t in texts):
            errors.append("%s : emoji interdit" % layer["id"])
        text_colors = {layer["color"]} | {r["color"] for r in layer.get("runs", []) if "color" in r}
        for name in text_colors:
            check_color(name, layer["id"])
            if backdrop and contrast(hex_of(name), hex_of(backdrop)) < 4.5:
                errors.append("%s : contraste %.2f:1 < 4,5:1 sur %s" % (layer["id"], contrast(hex_of(name), hex_of(backdrop)), backdrop))

    appear = {}
    for i, state in enumerate(spec["states"]):
        where = "état %d (%s)" % (i, state["layer"])
        if state["layer"] not in layers:
            errors.append("%s : calque inconnu" % where)
            continue
        t0, t1 = state["t0"], state["t1"]
        if t1 < t0 or t1 > duration + 0.5 / fps:
            errors.append("%s : t1 doit être entre t0 et la durée" % where)
        if state["easing"]["type"] != "cut" and t1 <= t0:
            errors.append("%s : un état %s doit durer (t1 > t0)" % (where, state["easing"]["type"]))
        if not on_beat(t0):
            errors.append("%s : t0 = %.4f hors grille de beats" % (where, t0))
        easing = state["easing"]
        if easing["type"] == "spring" and t1 > t0:
            residual = abs(1 - spring(t1 - t0, easing["zeta"], easing["omega"]))
            if residual > SPRING_RESIDUAL:
                errors.append("%s : ressort non arrivé à t1 (écart %.1f %%) : allonge l'état ou augmente omega" % (where, residual * 100))
        appear[state["layer"]] = min(appear.get(state["layer"], t0), t0)

    # Appearances: cut, or a linear fade of exactly fade_frames.
    for layer_id in layers:
        opacity_states = sorted((s for s in spec["states"] if s["layer"] == layer_id and "opacity" in s["to"]), key=lambda s: s["t0"])
        carried = 1.0
        for state in opacity_states:
            start = state.get("from", {}).get("opacity", carried)
            if start == 0 and state["to"]["opacity"] > 0:
                frames = (state["t1"] - state["t0"]) * fps
                if not (state["easing"]["type"] == "cut" or (state["easing"]["type"] == "linear" and abs(frames - fade) < 0.5)):
                    errors.append("%s : apparition à %.3f s par %s de %.1f images ; attendu : cut ou fondu linéaire de %d images"
                                  % (layer_id, state["t0"], state["easing"]["type"], frames, fade))
            carried = state["to"]["opacity"]

    for shot in shots:
        inside = lambda t: shot["t0"] - 1e-9 <= t < shot["t1"] - 1e-9
        morphs = [s for s in spec["states"] if inside(s["t0"]) and ("w" in s["to"] or "h" in s["to"])]
        if len(morphs) > 1:
            errors.append("plan %s : %d morphs de forme (1 maximum)" % (shot["name"], len(morphs)))
        present = [layers[i] for i, t in appear.items() if t < shot["t1"] - 1e-9]
        accents = {layer["color"] for layer in present if layer.get("accent")}
        if len(accents) > 1:
            errors.append("plan %s : %d couleurs d'accent (%s) ; une seule par plan" % (shot["name"], len(accents), ", ".join(sorted(accents))))
        new_text = [appear[l["id"]] for l in spec["layers"] if l["type"] == "text" and l["id"] in appear and inside(appear[l["id"]])]
        new_accent = [appear[l["id"]] for l in spec["layers"] if l.get("accent") and l["id"] in appear and inside(appear[l["id"]])]
        if new_text and new_accent and min(new_accent) >= min(new_text):
            errors.append("plan %s : l'accent doit apparaître avant le texte" % shot["name"])
    return list(dict.fromkeys(errors)), warnings


# ---- formats ----------------------------------------------------------------------------------------
def adapt(spec, target):
    """Starting point for another aspect ratio: positions scale per axis, sizes by the smaller ratio.
    The safe-zone audit and the contact sheet decide whether it holds."""
    if spec["format"] == target:
        return copy.deepcopy(spec)
    (w0, h0), (w1, h1) = FORMATS[spec["format"]], FORMATS[target]
    sx, sy, k = w1 / w0, h1 / h0, min(w1 / w0, h1 / h0)
    out = copy.deepcopy(spec)
    out["format"] = target
    for layer in out["layers"]:
        for key in ("size", "w", "h", "length", "thickness", "radius", "stroke"):
            if key in layer:
                layer[key] = round(layer[key] * k, 2)
        if "drift" in layer:
            layer["drift"]["amplitude"] = round(layer["drift"]["amplitude"] * k, 2)
    for state in out["states"]:
        for values in (state.get("from", {}), state["to"]):
            for key, factor in (("x", sx), ("y", sy), ("w", k), ("h", k)):
                if key in values:
                    values[key] = round(values[key] * factor, 2)
    return out


def resolve(spec, fmt=None, brandkit=None):
    """Schema + rules; returns (resolved spec, kit, fonts, warnings) or raises SpecError."""
    errors = schema_errors(spec)
    if errors:
        raise SpecError(errors)
    spec = adapt(spec, fmt or spec["format"])
    if brandkit:
        spec["brandkit"] = brandkit
    kit = load_kit(spec["brandkit"])
    fps = spec.get("fps") or kit_fps(kit)
    errors, warnings = validate(spec, kit, fps)
    if errors:
        raise SpecError(errors)
    fonts = fonts_for(spec, kit)
    width, height = FORMATS[spec["format"]]
    spec.update(width=width, height=height, fps=fps, seed=spec.get("seed", 1))
    return spec, kit, fonts, warnings
