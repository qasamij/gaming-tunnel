#!/bin/bash
# Idempotently apply a saved AWG interface config: keys, address, link up.
# `awg setconf` does not handle Address/DNS/MTU/Table directives (wg-quick
# normally does that), so we strip them and assign the address ourselves.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

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
  amneziawg-go "$IFACE"
fi

TMP=$(mktemp "$D/.apply.XXXXXX")
trap 'rm -f "$TMP"' EXIT
awk '!/^[[:space:]]*(Address|DNS|MTU|Table)[[:space:]]*=/' "$CONF" > "$TMP"
chmod 600 "$TMP"
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
