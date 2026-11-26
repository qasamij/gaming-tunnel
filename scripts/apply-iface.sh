#!/bin/bash
# Idempotently apply a saved AWG interface config: keys, address, link up.
# `awg setconf` does not handle Address/DNS/MTU/Table directives (wg-quick
# normally does that), so we strip them and assign the address ourselves.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

HERE=$(cd "$(dirname "$0")" && pwd)
MOD="$HERE"
[[ -f "$MOD/keyutil.py" ]] || MOD="$HERE/../src"

# Self-heal a missing CLI (some builds install it as `wg`, not `awg`).
if ! command -v awg >/dev/null 2>&1; then
  PYTHONPATH="$MOD${PYTHONPATH:+:$PYTHONPATH}" \
    python3 "$MOD/awgdetect.py" --link --quiet || {
    echo 'No functional AmneziaWG CLI; run: bash install.sh awg-check' >&2
    exit 1
  }
fi

D="${RUNTIME_DATA:-/etc/1mobile-runtime}"
IFACE="${1:-}"
[[ -n $IFACE ]] || { echo "Usage: apply-iface.sh <interface>" >&2; exit 1; }
CONF="$D/$IFACE.conf"
ADDR_FILE="$D/$IFACE.addr"
[[ -s $CONF ]] || { echo "Missing saved config: $CONF" >&2; exit 1; }

# Create the interface if needed, but never delete a healthy one.
if ! awg show "$IFACE" public-key >/dev/null 2>&1; then
  if ip link show "$IFACE" >/dev/null 2>&1; then
    echo "Interface $IFACE exists but AWG is unavailable; refusing to remove it" >&2
    exit 1
  fi
  command -v amneziawg-go >/dev/null 2>&1 || {
    PYTHONPATH="$MOD${PYTHONPATH:+:$PYTHONPATH}" python3 "$MOD/awgdetect.py" --link --quiet || true
  }
  command -v amneziawg-go >/dev/null 2>&1 || {
    echo 'amneziawg-go is missing; run: sudo bash install.sh awg-check' >&2
    exit 1
  }
  amneziawg-go "$IFACE"
fi

TMP=$(mktemp "$D/.apply.XXXXXX")
TMP2=$(mktemp "$D/.apply.XXXXXX")
trap 'rm -f "$TMP" "$TMP2"' EXIT
awk '!/^[[:space:]]*(Address|DNS|MTU|Table)[[:space:]]*=/' "$CONF" > "$TMP"
chmod 600 "$TMP" "$TMP2"

# If the interface is already live, keep every peer that exists now but is
# missing from the saved config. `awg setconf` replaces the peer list, so
# without this merge a re-run could disconnect clients added by the panel.
if awg show "$IFACE" public-key >/dev/null 2>&1; then
  LIVE=$(awg showconf "$IFACE" 2>/dev/null || true)
  if [[ -n $LIVE ]]; then
    LIVE="$LIVE" BASE="$TMP" OUT="$TMP2" PYTHONPATH="$MOD" python3 - <<'PY'
import os
from pathlib import Path
from keyutil import merge_peers
Path(os.environ['OUT']).write_text(
    merge_peers(Path(os.environ['BASE']).read_text(), os.environ['LIVE']))
PY
    mv -f "$TMP2" "$TMP"
  fi
fi
awg setconf "$IFACE" "$TMP"

# Addresses come from the saved .addr file (survives `awg showconf` snapshots)
# and from any Address lines still present in the config.
addresses=()
if [[ -f $ADDR_FILE ]]; then
  while IFS= read -r line; do
    line=$(printf '%s' "$line" | xargs || true)
    [[ -n $line ]] && addresses+=("$line")
  done < "$ADDR_FILE"
fi
while IFS= read -r line; do
  line=${line#*=}
  line=$(printf '%s' "$line" | xargs || true)
  [[ -n $line ]] && addresses+=("$line")
done < <(grep -E '^[[:space:]]*Address[[:space:]]*=' "$CONF" || true)

for a in "${addresses[@]:-}"; do
  [[ -n $a ]] || continue
  ip addr show dev "$IFACE" | grep -Fq "$a" || ip addr add "$a" dev "$IFACE"
done
ip link set "$IFACE" up
