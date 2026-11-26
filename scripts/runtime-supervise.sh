#!/bin/bash
# Recreation-only supervisor. Never restarts a healthy interface.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
D="${RUNTIME_DATA:-/etc/1mobile-runtime}"
INTERVAL="${SUPERVISE_INTERVAL:-15}"

role=$(cat "$D/role")
case "$role" in
  iran) interfaces=(omawg0 omclient0) ;;
  exit) interfaces=(omawg0) ;;
  *) echo "Unknown role: $role" >&2; exit 1 ;;
esac

repair=1
while true; do
  for i in "${interfaces[@]}"; do
    if ! awg show "$i" public-key >/dev/null 2>&1; then
      if ip link show "$i" >/dev/null 2>&1; then
        echo "Interface $i exists but AWG is unavailable; refusing destructive removal" >&2
        exit 1
      fi
      test -s "$D/$i.conf" || { echo "Missing saved config for $i" >&2; exit 1; }
      repair=1
      echo "Recreating $i at $(date -Is)" >&2
      amneziawg-go "$i"
      if ! awg setconf "$i" "$D/$i.conf"; then
        ip link delete "$i" || true
        exit 1
      fi
    fi
  done
  if [[ $repair == 1 ]]; then
    /opt/1mobile-runtime/runtime.sh
    repair=0
  fi
  sleep "$INTERVAL"
done
