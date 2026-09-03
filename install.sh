#!/usr/bin/env bash
# fcp-live installer — sets up SpliceKit (patched copy of Final Cut Pro), the
# MCP server, the Claude Code skill, and optional brand fonts.
#
#   bash install.sh            # everything
#   bash install.sh --no-fonts # skip Google Fonts download
#   bash install.sh --skill    # only (re)install the Claude Code skill symlink
#
# Idempotent: re-run after a Final Cut Pro update to re-patch.
set -euo pipefail

SK_DIR="${SK_DIR:-$HOME/.local/share/splicekit/SpliceKit}"
SK_REPO="https://github.com/elliotttate/SpliceKit.git"
SK_REF="${SK_REF:-v3.3.9}"            # tag this project was validated against
MCP_VENV="$HOME/.venvs/splicekit-mcp"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PATCH="$HERE/splicekit-patches/0001-build-without-braw-sdk-and-fix-patch_fcp.sh.patch"
FONTS=1; ONLY_SKILL=0
for a in "$@"; do case "$a" in --no-fonts) FONTS=0;; --skill) ONLY_SKILL=1;; esac; done

log(){ printf '\033[0;32m[+]\033[0m %s\n' "$*"; }
warn(){ printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
die(){ printf '\033[0;31m[x]\033[0m %s\n' "$*" >&2; exit 1; }

install_skill() {
  mkdir -p "$HOME/.claude/skills"
  ln -sfn "$HERE" "$HOME/.claude/skills/fcp-live"
  log "Claude Code skill linked: ~/.claude/skills/fcp-live -> $HERE"
}

if [[ $ONLY_SKILL == 1 ]]; then install_skill; exit 0; fi

# --- prerequisites -----------------------------------------------------------
[[ "$(uname)" == Darwin ]] || die "macOS only"
[[ -d "/Applications/Final Cut Pro.app" ]] || die "Final Cut Pro not found in /Applications"
xcode-select -p >/dev/null 2>&1 || die "Xcode Command Line Tools missing: xcode-select --install"
for t in git make clang codesign python3 ffmpeg; do command -v "$t" >/dev/null || die "missing tool: $t (ffmpeg: brew install ffmpeg)"; done
command -v claude >/dev/null || warn "claude CLI not found: the MCP server will not be registered automatically"
if ! security find-identity -v -p codesigning 2>/dev/null | grep -q '"'; then
  warn "no codesigning identity: SpliceKit will fall back to ad-hoc signing (may be blocked by macOS)"
fi
free_gb=$(df -g / | awk 'NR==2{print $4}'); [[ $free_gb -ge 12 ]] || die "need ~12 GB free (FCP copy), have ${free_gb} GB"

# --- telemetry off before first launch --------------------------------------
mkdir -p "$HOME/Library/Application Support/SpliceKit"
cat > "$HOME/Library/Application Support/SpliceKit/SpliceKitSentryConfig.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict><key>Enabled</key><false/></dict></plist>
EOF
log "SpliceKit crash telemetry disabled (Sentry)"

# --- SpliceKit source --------------------------------------------------------
if [[ ! -d "$SK_DIR/.git" ]]; then
  mkdir -p "$(dirname "$SK_DIR")"
  git clone --quiet "$SK_REPO" "$SK_DIR"
  log "cloned SpliceKit into $SK_DIR"
fi
cd "$SK_DIR"
git fetch --quiet --tags origin
git checkout --quiet "$SK_REF" 2>/dev/null || { warn "ref $SK_REF not found, staying on $(git rev-parse --abbrev-ref HEAD)"; }
if git apply --check "$PATCH" 2>/dev/null; then
  git apply "$PATCH"; log "applied local build fixes ($(basename "$PATCH"))"
elif git apply --reverse --check "$PATCH" 2>/dev/null; then
  log "build fixes already applied"
else
  warn "patch does not apply cleanly (upstream may have merged it: https://github.com/elliotttate/SpliceKit/pull/87)"
fi
bash Scripts/ensure_sentry_framework.sh

# --- patch FCP (copy, build, inject, sign) -----------------------------------
if pgrep -x "Final Cut Pro" >/dev/null; then
  warn "Final Cut Pro is running; the stock app is only copied, but quit it before launching the patched copy"
fi
./patcher/patch_fcp.sh
log "patched FCP ready: ~/Applications/SpliceKit/Final Cut Pro.app"

# --- MCP server --------------------------------------------------------------
make mcp-setup >/dev/null
if command -v claude >/dev/null; then
  claude mcp remove splicekit -s user >/dev/null 2>&1 || true
  claude mcp add splicekit -s user -- "$MCP_VENV/bin/python" "$SK_DIR/mcp/server.py" >/dev/null
  log "MCP server 'splicekit' registered (user scope)"
fi

# --- fonts (example brand kit: baair) ---------------------------------------
if [[ $FONTS == 1 ]]; then
  B="https://raw.githubusercontent.com/google/fonts/main/ofl"
  mkdir -p "$HOME/Library/Fonts"; cd "$HOME/Library/Fonts"
  for u in "fraunces/Fraunces%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf" "fraunces/Fraunces-Italic%5BSOFT%2CWONK%2Copsz%2Cwght%5D.ttf" \
           "instrumentserif/InstrumentSerif-Regular.ttf" "instrumentserif/InstrumentSerif-Italic.ttf" \
           "inter/Inter%5Bopsz%2Cwght%5D.ttf" "inter/Inter-Italic%5Bopsz%2Cwght%5D.ttf" \
           "jetbrainsmono/JetBrainsMono%5Bwght%5D.ttf" "jetbrainsmono/JetBrainsMono-Italic%5Bwght%5D.ttf"; do
    f=$(python3 -c "import sys,urllib.parse;print(urllib.parse.unquote(sys.argv[1]))" "$(basename "$u")")
    [[ -f "$f" ]] || curl -sfL "$B/$u" -o "$f" || warn "font download failed: $u"
  done
  log "brand fonts installed in ~/Library/Fonts (Fraunces, Instrument Serif, Inter, JetBrains Mono — OFL)"
fi

install_skill

cat <<EOF

Done. Next:
  1. Quit the stock Final Cut Pro (it must not run alongside the patched copy).
  2. open "$HOME/Applications/SpliceKit/Final Cut Pro.app" and open a library.
  3. Accept the macOS permission prompts FCP shows (Downloads, microphone…).
  4. Restart Claude Code; ask it to edit a video. The bridge listens on 127.0.0.1:9876.
EOF
