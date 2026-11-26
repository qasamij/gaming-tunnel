#!/bin/bash
# Health-aware supervisor. Never restarts a healthy interface: it only
# recreates missing links and softly re-applies a saved config when the tunnel
# peer has no fresh handshake or the end-to-end UDP probe keeps failing.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
D="${RUNTIME_DATA:-/etc/1mobile-runtime}"
export RUNTIME_DATA="$D"
export PANEL_DATA="${PANEL_DATA:-/etc/1mobile-panel}"
PANEL_PREFIX="${PANEL_PREFIX:-/opt/1mobile-web-v13}"
HEALTH_BIN="$PANEL_PREFIX/healthcheck.py"
INTERVAL="${SUPERVISE_INTERVAL:-15}"
HEALTH_EVERY="${HEALTH_EVERY:-60}"
STRIKES_MAX="${HEALTH_STRIKES:-3}"
COOLDOWN="${HEALTH_COOLDOWN:-600}"
GRACE="${HEALTH_GRACE:-120}"

role=$(cat "$D/role")
case "$role" in
  iran) interfaces=(omawg0 omclient0) ;;
  exit) interfaces=(omawg0) ;;
  *) echo "Unknown role: $role" >&2; exit 1 ;;
esac

repair=1
boot=$(date +%s)
last_health=0
last_repair=0
strikes=0

soft_repair() {
  local reason=$1
  echo "Health repair ($reason) at $(date -Is)" >&2
  # apply-iface.sh merges live peers that are absent from the saved config,
  # so a client added by the panel is not dropped by this re-apply.
  bash /opt/1mobile-runtime/apply-iface.sh omawg0 || {
    echo 'Soft repair failed to re-apply omawg0' >&2
    return 1
  }
  /opt/1mobile-runtime/runtime.sh || {
    echo 'Soft repair failed to re-apply routing/NAT' >&2
    return 1
  }
}

while true; do
  now=$(date +%s)
  for i in "${interfaces[@]}"; do
    if ! awg show "$i" public-key >/dev/null 2>&1; then
      if ip link show "$i" >/dev/null 2>&1; then
        echo "Interface $i exists but AWG is unavailable; refusing destructive removal" >&2
        exit 1
      fi
      test -s "$D/$i.conf" || { echo "Missing saved config for $i" >&2; exit 1; }
      repair=1
      echo "Recreating $i at $(date -Is)" >&2
      if ! bash /opt/1mobile-runtime/apply-iface.sh "$i"; then
        echo "Failed to restore $i from saved config" >&2
        exit 1
      fi
    fi
  done
  if [[ $repair == 1 ]]; then
    /opt/1mobile-runtime/runtime.sh
    repair=0
    last_health=$now
    strikes=0
  fi

  # A live link is not proof of a working tunnel. Check handshake freshness
  # and (on Iran) a real UDP echo round trip on a slower cadence. Require
  # consecutive failures so a single slow probe cannot flap the tunnel.
  if [[ -f $HEALTH_BIN ]] && (( now - last_health >= HEALTH_EVERY )); then
    last_health=$now
    if (( now - boot < GRACE )); then
      echo "Skipping health check during startup grace" >&2
    elif output=$(python3 "$HEALTH_BIN" 2>&1); then
      strikes=0
    else
      strikes=$((strikes + 1))
      reason=$(printf '%s\n' "$output" | tail -1)
      echo "Tunnel unhealthy ($reason): strike $strikes/$STRIKES_MAX" >&2
      if (( strikes >= STRIKES_MAX && now - last_repair >= COOLDOWN )); then
        if soft_repair "$reason"; then
          last_repair=$now
          strikes=0
        fi
      fi
    fi
  fi
  sleep "$INTERVAL"
done
