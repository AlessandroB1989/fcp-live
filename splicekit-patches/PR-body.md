## Summary

Building v3.3.9 from a fresh clone fails on a Mac without the Blackmagic RAW SDK, and `patcher/patch_fcp.sh` cannot complete even once the build is fixed. This PR makes the documented terminal path (`./patcher/patch_fcp.sh`) work again on a clean machine.

## Changes

1. **`Sources/SpliceKitBRAW.mm`** — add stubs for `SpliceKit_bootstrapBRAWAtLaunchPhase` and `SpliceKit_handleBRAWAVProbe` in the `#else` (no SDK) branch. Both are called unconditionally from `SpliceKit.m` / `SpliceKitServer.m`, so the Makefile's undefined-`SpliceKit_*` check aborts the link:
   ```
   ERROR: undefined SpliceKit_* symbols in build/SpliceKit:
     _SpliceKit_bootstrapBRAWAtLaunchPhase
     _SpliceKit_handleBRAWAVProbe
   ```
2. **`patcher/patch_fcp.sh`** — build through `make all` instead of the inline `clang` invocation. That line predates the Sentry integration (no `-F patcher/Frameworks -framework Sentry`, no Metal/Vision/C++ flags) and dies on `fatal error: 'Sentry/Sentry.h' file not found`.
3. **`patcher/patch_fcp.sh`** — detect an existing injection by matching the `@rpath/SpliceKit.framework/Versions/A/SpliceKit` load command. The previous `grep -q SpliceKit` also matches otool's header line, which contains the default install path `~/Applications/SpliceKit/`, so injection was always reported as "Already injected (skipping)" on a fresh copy and FCP launched without the dylib.
4. **`patcher/patch_fcp.sh`** — `detect_sign_identity` printed two hashes when an "Apple Development" certificate exists (awk still runs `END` after `exit`), so `codesign` failed with `no identity found` and silently fell back to ad-hoc signing.

The GUI patcher already does 2–4 correctly; this aligns the shell script with it.

## Test plan

- macOS 26.5.2, FCP 12.3 (App Store), Xcode 26 / clang 21, Apple Development identity, no BRAW SDK.
- `bash Scripts/ensure_sentry_framework.sh && ./patcher/patch_fcp.sh` completes: build, framework install, `LC_LOAD_DYLIB` injected (verified with `otool -L`), signature valid with the developer identity, entitlements applied.
- Patched FCP launches, bridge answers `system.version` (`splicekit_version 3.3.9`), `fcpxml.import`, `project.open`, `viewer.capture` and title tools work from the MCP server.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
