// Seeded randomness for motion-reel. The only source of variation allowed in the renderer.
(function (MR) {
  "use strict";

  // mulberry32: returns the n-th value (0 <= v < 1) of the sequence for `seed`, without keeping a generator
  // around. Indexing instead of advancing keeps every call a pure function.
  function mulberry32(seed, n) {
    let a = (seed + Math.imul(n + 1, 0x6D2B79F5)) >>> 0;
    a = Math.imul(a ^ (a >>> 15), a | 1);
    a ^= a + Math.imul(a ^ (a >>> 7), a | 61);
    return ((a ^ (a >>> 14)) >>> 0) / 4294967296;
  }

  // 1D value noise in [-1, 1]: seeded random values on integer lattice points, smoothly interpolated.
  // x is usually t * frequency; `channel` separates independent streams (e.g. x and y jitter of one layer).
  function valueNoise1D(seed, channel, x) {
    const i = Math.floor(x), f = x - i;
    const a = mulberry32(seed ^ Math.imul(channel + 1, 0x9E3779B1), i) * 2 - 1;
    const b = mulberry32(seed ^ Math.imul(channel + 1, 0x9E3779B1), i + 1) * 2 - 1;
    const s = f * f * (3 - 2 * f);
    return a + (b - a) * s;
  }

  MR.noise = { mulberry32, valueNoise1D };
})(window.MR = window.MR || {});
