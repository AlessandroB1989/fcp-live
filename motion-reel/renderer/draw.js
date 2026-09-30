// motion-reel renderer: draw(ctx, t, spec, kit) paints frame t from scratch. It is a pure function of its
// arguments: no module state, no clock, no unseeded randomness. `spec` is the resolved spec written by
// scripts/render.py (width, height, fps set); `kit` maps colour names to hex and font roles to the
// FontFace aliases loaded by index.html.
//
// Coordinates follow Raccord: frame pixels from the centre, y up. Rotation in degrees, counter-clockwise.
(function (MR) {
  "use strict";

  const SHAPE_SIZE = { square: (l) => [l.size, l.size], rect: (l) => [l.w, l.h], line: (l) => [l.length, l.thickness] };

  function defaults(layer) {
    const [w, h] = layer.type === "text" ? [0, 0] : SHAPE_SIZE[layer.type](layer);
    return { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, reveal: 1, w, h };
  }

  function statesOf(spec, id) {
    return spec.states.map((s, i) => [s, i]).filter(([s]) => s.layer === id)
      .sort((a, b) => a[0].t0 - b[0].t0 || a[1] - b[1]).map(([s]) => s);
  }

  // Value of one property at time t. States that mention the property are chained in t0 order: a state
  // without `from` starts where the previous one stood at its t0, so states can overlap (a spring move
  // plus a linear fade) as long as they animate different properties.
  function value(spec, layer, name, t) {
    const segs = statesOf(spec, layer.id).filter((s) => (s.from && name in s.from) || (s.to && name in s.to));
    const fallback = defaults(layer)[name];
    if (!segs.length) return fallback;
    const at = (p, time) => p.start + (p.end - p.start) * MR.easing.progress(p.seg.easing, time - p.seg.t0, p.seg.t1 - p.seg.t0);
    let prev = null;
    for (const seg of segs) {
      if (seg.t0 > t) break;
      const start = seg.from && name in seg.from ? seg.from[name] : (prev ? at(prev, seg.t0) : fallback);
      const end = seg.to && name in seg.to ? seg.to[name] : start;
      prev = { seg, start, end };
    }
    if (!prev) return segs[0].from && name in segs[0].from ? segs[0].from[name] : fallback;
    return at(prev, t);
  }

  function color(kit, name) {
    if (/^#[0-9A-Fa-f]{6}$/.test(name)) return name;
    const hex = kit.colors[name];
    if (!hex) throw new Error("Colour not in brand kit: " + name);
    return hex;
  }

  function font(kit, role, size) {
    const f = kit.fonts[role];
    if (!f) throw new Error("Font role not in brand kit: " + role);
    return `${f.style} ${f.weight} ${size}px "${f.alias}"`;
  }

  // Text block laid out around its anchor: lines split on "\n", runs keep their own role and colour.
  function layoutText(ctx, layer, kit) {
    const size = layer.size, tracking = (layer.tracking || 0) * size;
    const runs = layer.runs || [{ text: layer.text, role: layer.role }];
    const lines = [[]];
    for (const run of runs) {
      const text = layer.case === "upper" ? run.text.toUpperCase() : run.text;
      text.split("\n").forEach((part, i) => {
        if (i > 0) lines.push([]);
        if (part) lines[lines.length - 1].push({ text: part, font: font(kit, run.role, size), color: color(kit, run.color || layer.color) });
      });
    }
    ctx.save();
    ctx.letterSpacing = tracking + "px";
    const measured = lines.map((line) => {
      const parts = line.map((r) => { ctx.font = r.font; return { ...r, width: ctx.measureText(r.text).width }; });
      return { parts, width: parts.reduce((sum, r) => sum + r.width, 0) };
    });
    ctx.restore();
    const lineHeight = (layer.lineHeight || 1.15) * size;
    const width = Math.max(0, ...measured.map((l) => l.width));
    const align = layer.align || "center";
    const left = (w) => (align === "left" ? 0 : align === "right" ? -w : -w / 2);
    return { lines: measured, lineHeight, tracking, left, box: [left(width), -lineHeight * measured.length / 2, width, lineHeight * measured.length] };
  }

  function localBox(ctx, layer, kit, v) {
    if (layer.type === "text") return layoutText(ctx, layer, kit).box;
    return [-v.w / 2, -v.h / 2, v.w, v.h];
  }

  function frameState(spec, layer, index, t) {
    const v = {};
    for (const name of ["x", "y", "scale", "rotation", "opacity", "reveal", "w", "h"]) v[name] = value(spec, layer, name, t);
    if (layer.drift) {
      const seed = spec.seed || 1;
      v.x += layer.drift.amplitude * MR.noise.valueNoise1D(seed, index * 2, t * layer.drift.frequency);
      v.y += layer.drift.amplitude * MR.noise.valueNoise1D(seed, index * 2 + 1, t * layer.drift.frequency);
    }
    v.opacity = Math.min(1, Math.max(0, v.opacity));
    v.reveal = Math.min(1, Math.max(0, v.reveal));
    return v;
  }

  function visible(spec, layer, t) {
    const states = statesOf(spec, layer.id);
    return states.length > 0 && t >= states[0].t0;
  }

  function place(ctx, spec, v) {
    ctx.translate(spec.width / 2 + v.x, spec.height / 2 - v.y);
    ctx.rotate(-v.rotation * Math.PI / 180);
    ctx.scale(v.scale, v.scale);
  }

  function clipReveal(ctx, layer, box, reveal) {
    if (reveal >= 1) return;
    const [x, y, w, h] = box, from = layer.revealFrom || "left";
    ctx.beginPath();
    if (from === "left") ctx.rect(x, y, w * reveal, h);
    else if (from === "right") ctx.rect(x + w * (1 - reveal), y, w * reveal, h);
    else if (from === "top") ctx.rect(x, y, w, h * reveal);
    else ctx.rect(x, y + h * (1 - reveal), w, h * reveal);
    ctx.clip();
  }

  function paintLayer(ctx, layer, kit, v) {
    if (layer.type === "text") {
      const lay = layoutText(ctx, layer, kit);
      clipReveal(ctx, layer, lay.box, v.reveal);
      ctx.letterSpacing = lay.tracking + "px";
      ctx.textBaseline = "middle";
      ctx.textAlign = "left";
      lay.lines.forEach((line, i) => {
        let x = lay.left(line.width);
        const y = lay.box[1] + lay.lineHeight * (i + 0.5);
        for (const part of line.parts) {
          ctx.font = part.font; ctx.fillStyle = part.color;
          ctx.fillText(part.text, x, y);
          x += part.width;
        }
      });
      return;
    }
    const box = [-v.w / 2, -v.h / 2, v.w, v.h];
    clipReveal(ctx, layer, box, v.reveal);
    ctx.beginPath();
    const r = Math.min(layer.radius || 0, Math.abs(v.w) / 2, Math.abs(v.h) / 2);
    if (r > 0) ctx.roundRect(box[0], box[1], box[2], box[3], r); else ctx.rect(box[0], box[1], box[2], box[3]);
    if (layer.stroke) { ctx.lineWidth = layer.stroke; ctx.strokeStyle = color(kit, layer.color); ctx.stroke(); }
    else { ctx.fillStyle = color(kit, layer.color); ctx.fill(); }
  }

  function draw(ctx, t, spec, kit) {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, spec.width, spec.height);
    if (spec.background) { ctx.fillStyle = color(kit, spec.background); ctx.fillRect(0, 0, spec.width, spec.height); }
    spec.layers.forEach((layer, index) => {
      if (!visible(spec, layer, t)) return;
      const v = frameState(spec, layer, index, t);
      if (v.opacity <= 0 || v.reveal <= 0) return;
      ctx.save();
      ctx.globalAlpha = v.opacity;
      place(ctx, spec, v);
      paintLayer(ctx, layer, kit, v);
      ctx.restore();
    });
    ctx.restore();
  }

  // Axis-aligned boxes (canvas pixels, origin top-left) of the layers visible at t, for the safe-zone audit.
  function bounds(ctx, t, spec, kit) {
    const out = [];
    spec.layers.forEach((layer, index) => {
      if (!visible(spec, layer, t)) return;
      const v = frameState(spec, layer, index, t);
      if (v.opacity <= 0.01 || v.reveal <= 0) return;
      const [x, y, w, h] = localBox(ctx, layer, kit, v);
      const a = -v.rotation * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
      const pts = [[x, y], [x + w, y], [x, y + h], [x + w, y + h]].map(([px, py]) => [
        spec.width / 2 + v.x + v.scale * (px * c - py * s),
        spec.height / 2 - v.y + v.scale * (px * s + py * c)]);
      out.push({ id: layer.id, type: layer.type, opacity: v.opacity,
        x0: Math.min(...pts.map((p) => p[0])), y0: Math.min(...pts.map((p) => p[1])),
        x1: Math.max(...pts.map((p) => p[0])), y1: Math.max(...pts.map((p) => p[1])) });
    });
    return out;
  }

  MR.draw = draw;
  MR.bounds = bounds;
})(window.MR = window.MR || {});
