#!/bin/bash
# Make sure the tunnel returns after a reboot or an SSH logout.
# Safe to run any time: healthy interfaces are never removed or restarted.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[[ -s "$RUNTIME_DIR/role" ]] || fail 'No role file yet: run keygen/keys import/fresh first'
ROLE=$(cat "$RUNTIME_DIR/role")

install -d -m 700 /opt/1mobile-runtime
install -m 755 "$REPO_DIR/scripts/runtime.sh" /opt/1mobile-runtime/runtime.sh
install -m 700 "$REPO_DIR/scripts/runtime-supervise.sh" /opt/1mobile-runtime/supervise.sh
install -m 700 "$REPO_DIR/scripts/apply-iface.sh" /opt/1mobile-runtime/apply-iface.sh

case "$ROLE" in
  iran) interfaces=(omawg0 omclient0) ;;
  exit) interfaces=(omawg0) ;;
  *) fail "Unknown role: $ROLE" ;;
esac

for i in "${interfaces[@]}"; do
  [[ -s "$RUNTIME_DIR/$i.conf" ]] || fail "Missing saved config $RUNTIME_DIR/$i.conf"
done

info 'Enabling services at boot'
systemctl daemon-reload
systemctl enable 1mobile-runtime.service
[[ -f $PANEL_UNIT ]] && systemctl enable 1mobile-panel.service || true
[[ $ROLE == exit && -f $ECHO_UNIT ]] && systemctl enable 1mobile-udp-echo.service || true

# The supervisor only recreates interfaces that are actually missing, so a
# restart here is harmless for a healthy live tunnel.
systemctl restart 1mobile-runtime.service
sleep 2
systemctl is-enabled --quiet 1mobile-runtime.service || fail 'Runtime service is not enabled at boot'
systemctl is-active --quiet 1mobile-runtime.service || fail 'Runtime service is not active'

for i in "${interfaces[@]}"; do
  awg show "$i" public-key >/dev/null 2>&1 || fail "Interface $i is not up"
done

ok "Persistent tunnel active for role=$ROLE (survives reboot and SSH logout)"
systemctl status 1mobile-runtime.service --no-pager | head -8 || true
