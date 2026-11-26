#!/bin/bash
# Shared paths for all installer scripts.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/opt/1mobile-web-v13}"
DATA_DIR="${PANEL_DATA:-/etc/1mobile-panel}"
RUNTIME_DIR="${RUNTIME_DATA:-/etc/1mobile-runtime}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

PANEL_UNIT="$SYSTEMD_DIR/1mobile-panel.service"
RUNTIME_UNIT="$SYSTEMD_DIR/1mobile-runtime.service"
ECHO_UNIT="$SYSTEMD_DIR/1mobile-udp-echo.service"

need_root() { [[ $EUID -eq 0 ]] || { echo "Run as root" >&2; exit 1; }; }

# Some amneziawg-tools builds install the CLI as `wg`, not `awg`. Verify the
# real engine (including obfuscation keys) and provide a stable `awg` path.
need_awg() {
  PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$REPO_DIR/src/awgdetect.py" --link --quiet || \
    fail 'AmneziaWG CLI missing or not functional. Run: sudo bash install.sh awg-check'
}

ok() { printf '\n[ok] %s\n' "$*"; }
info() { printf '\n[*] %s\n' "$*"; }
fail() { printf '\n[!] %s\n' "$*" >&2; exit 1; }
