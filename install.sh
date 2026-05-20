#!/usr/bin/env bash
# BeautyCat installer — sets up the `beautycat` command in your PATH.
#
# Strategy:
#   1. If `pipx` is available → `pipx install .` (recommended; isolated venv, on PATH).
#   2. Else → create a dedicated venv at $PREFIX/venv, symlink the entry point
#      into $PREFIX/bin, and tell the user to add $PREFIX/bin to PATH.
#
# Usage:
#   ./install.sh                  # auto-detect, install
#   ./install.sh --venv           # force the venv method (skip pipx)
#   ./install.sh --upgrade        # reinstall, replacing any prior install
#   ./install.sh --uninstall      # remove BeautyCat
#   ./install.sh --prefix DIR     # override install prefix (default: ~/.beautycat)

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PREFIX="${BEAUTYCAT_PREFIX:-$HOME/.beautycat}"
FORCE_VENV=0
UPGRADE=0
UNINSTALL=0
PY_MIN_MAJOR=3
PY_MIN_MINOR=10

while [[ $# -gt 0 ]]; do
  case "$1" in
    --venv) FORCE_VENV=1 ;;
    --upgrade) UPGRADE=1 ;;
    --uninstall) UNINSTALL=1 ;;
    --prefix) PREFIX="$2"; shift ;;
    -h|--help)
      awk 'NR>1 && /^#/ { sub(/^# ?/, ""); print; next } NR>1 { exit }' "$0"
      exit 0 ;;
    *) echo "Unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

# ---------- pretty output ----------
if [[ -t 1 ]]; then
  C_RESET=$'\033[0m'; C_DIM=$'\033[2m'; C_OK=$'\033[32m'
  C_WARN=$'\033[33m'; C_ERR=$'\033[31m'; C_HEAD=$'\033[1;38;5;215m'
else
  C_RESET=""; C_DIM=""; C_OK=""; C_WARN=""; C_ERR=""; C_HEAD=""
fi

say()   { printf "%s%s%s\n" "$C_DIM" "$1" "$C_RESET"; }
ok()    { printf "%s✓%s %s\n" "$C_OK" "$C_RESET" "$1"; }
warn()  { printf "%s!%s %s\n" "$C_WARN" "$C_RESET" "$1"; }
fail()  { printf "%s✗%s %s\n" "$C_ERR" "$C_RESET" "$1" >&2; exit 1; }
head()  { printf "\n%s%s%s\n" "$C_HEAD" "$1" "$C_RESET"; }

head "🐾 BeautyCat installer"

# ---------- uninstall ----------
if [[ $UNINSTALL -eq 1 ]]; then
  if command -v pipx >/dev/null 2>&1 && pipx list 2>/dev/null | grep -q "package beautycat"; then
    say "Removing via pipx…"
    pipx uninstall beautycat || true
  fi
  if [[ -d "$PREFIX" ]]; then
    say "Removing $PREFIX…"
    rm -rf "$PREFIX"
  fi
  # Clean symlink if it was installed into ~/.local/bin
  for link in "$HOME/.local/bin/beautycat" "$PREFIX/bin/beautycat"; do
    if [[ -L "$link" ]]; then rm -f "$link"; fi
  done
  ok "Uninstalled."
  exit 0
fi

# ---------- detect Python ----------
PY=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    if "$candidate" -c "import sys; raise SystemExit(0 if sys.version_info >= ($PY_MIN_MAJOR,$PY_MIN_MINOR) else 1)"; then
      PY="$candidate"
      break
    fi
  fi
done
[[ -n "$PY" ]] || fail "Python ${PY_MIN_MAJOR}.${PY_MIN_MINOR}+ not found. Install with: brew install python@3.12"
ok "Using $($PY -V 2>&1) at $(command -v "$PY")"

# ---------- detect adb (warn-only, not required to install) ----------
if command -v adb >/dev/null 2>&1; then
  ok "adb found at $(command -v adb)"
elif [[ -x "$HOME/Library/Android/sdk/platform-tools/adb" ]]; then
  ok "adb found at $HOME/Library/Android/sdk/platform-tools/adb (will be auto-detected)"
else
  warn "adb not found on PATH. Install Android platform-tools, or pass --adb-path when running."
fi

# ---------- install ----------
INSTALLED_VIA=""
BEAUTYCAT_BIN=""

install_via_pipx() {
  say "Installing with pipx (recommended path)…"
  local args=("install" "$PROJECT_DIR")
  if [[ $UPGRADE -eq 1 ]]; then args=("install" "--force" "$PROJECT_DIR"); fi
  pipx "${args[@]}"
  BEAUTYCAT_BIN="$(command -v beautycat || true)"
  if [[ -z "$BEAUTYCAT_BIN" ]]; then
    # pipx puts binaries under ~/.local/bin by default; surface it explicitly
    BEAUTYCAT_BIN="$HOME/.local/bin/beautycat"
  fi
  INSTALLED_VIA="pipx"
}

install_via_venv() {
  say "Installing into dedicated venv at $PREFIX/venv…"
  if [[ -d "$PREFIX/venv" && $UPGRADE -eq 0 ]]; then
    warn "Existing install detected at $PREFIX/venv. Re-run with --upgrade to replace it."
    exit 1
  fi
  rm -rf "$PREFIX/venv"
  mkdir -p "$PREFIX/bin"
  "$PY" -m venv "$PREFIX/venv"
  # shellcheck disable=SC1091
  "$PREFIX/venv/bin/pip" install --quiet --upgrade pip
  "$PREFIX/venv/bin/pip" install --quiet "$PROJECT_DIR"
  ln -sf "$PREFIX/venv/bin/beautycat" "$PREFIX/bin/beautycat"
  BEAUTYCAT_BIN="$PREFIX/bin/beautycat"
  INSTALLED_VIA="venv"
}

if [[ $FORCE_VENV -eq 1 ]] || ! command -v pipx >/dev/null 2>&1; then
  install_via_venv
else
  install_via_pipx
fi

ok "Installed via $INSTALLED_VIA → $BEAUTYCAT_BIN"

# ---------- verify ----------
if [[ -x "$BEAUTYCAT_BIN" ]]; then
  VERSION="$("$BEAUTYCAT_BIN" --version 2>/dev/null || echo unknown)"
  ok "Verified: $VERSION"
else
  warn "Could not exec $BEAUTYCAT_BIN — check the install above."
fi

# ---------- PATH hint ----------
BIN_DIR="$(dirname "$BEAUTYCAT_BIN")"
case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    warn "$BIN_DIR is not on your PATH yet."
    echo "  Add this to your shell profile (~/.zshrc or ~/.bashrc):"
    printf '    %sexport PATH="%s:$PATH"%s\n' "$C_HEAD" "$BIN_DIR" "$C_RESET"
    ;;
esac

head "Done. Run: beautycat"
say "  --port 8099                # change port"
say "  --no-browser               # don't open the browser"
say "  --buffer-size 20000        # keep more logs in memory"
say "  --adb-path /path/to/adb    # override adb location"
