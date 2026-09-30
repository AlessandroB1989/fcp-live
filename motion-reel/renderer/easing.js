// Easings for motion-reel. Pure functions of (elapsed, span): no state, no clock.
// Only three exist on purpose: cut, linear and an analytic spring. There is no default ease-in-out.
(function (MR) {
  "use strict";

  // Step response of a damped harmonic oscillator, normalised to go from 0 to 1.
  // zeta: damping ratio (1 = critical, no overshoot; < 1 overshoots). omega: natural frequency (rad/s).
  // Closed form, evaluated directly at tau seconds: no step-by-step simulation.
  function spring(tau, zeta, omega) {
    if (tau <= 0) return 0;
    if (zeta < 1) {
      const wd = omega * Math.sqrt(1 - zeta * zeta);
      return 1 - Math.exp(-zeta * omega * tau) * (Math.cos(wd * tau) + (zeta * omega / wd) * Math.sin(wd * tau));
    }
    if (zeta === 1) return 1 - Math.exp(-omega * tau) * (1 + omega * tau);
    const s = omega * Math.sqrt(zeta * zeta - 1);
    const r1 = -zeta * omega + s, r2 = -zeta * omega - s;
    return 1 - (r2 * Math.exp(r1 * tau) - r1 * Math.exp(r2 * tau)) / (r2 - r1);
  }

  // Progress in [0, 1] (a spring may overshoot) of a state that started `elapsed` seconds ago and lasts `span`.
  // After the state ends every easing holds exactly 1, so the end value is always reached on t1.
  function progress(easing, elapsed, span) {
    if (elapsed < 0) return 0;
    if (easing.type === "cut" || span <= 0 || elapsed >= span) return 1;
    if (easing.type === "linear") return elapsed / span;
    if (easing.type === "spring") return spring(elapsed, easing.zeta, easing.omega);
    throw new Error("Unknown easing: " + easing.type);
  }

  MR.easing = { spring, progress };
})(window.MR = window.MR || {});
