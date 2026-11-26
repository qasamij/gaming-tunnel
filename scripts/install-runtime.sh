#!/bin/bash
# Install the tunnel supervisor on an existing AmneziaWG host.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
[[ -s "$RUNTIME_DIR/role" && -x /opt/1mobile-runtime/runtime.sh ]] || \
  fail 'Runtime role file and runtime.sh are required'
[[ -f $RUNTIME_UNIT ]] || install -m 644 "$REPO_DIR/systemd/1mobile-runtime.service" "$RUNTIME_UNIT"

ROLE=$(cat "$RUNTIME_DIR/role")
case "$ROLE" in
  iran) interfaces=(omawg0 omclient0) ;;
  exit) interfaces=(omawg0) ;;
  *) fail "Unknown role: $ROLE" ;;
esac

info "Saving live interface configs before touching the service"
for i in "${interfaces[@]}"; do
  awg showconf "$i" > "$RUNTIME_DIR/$i.conf.pending"
  test -s "$RUNTIME_DIR/$i.conf.pending"
done
for i in "${interfaces[@]}"; do
  mv "$RUNTIME_DIR/$i.conf.pending" "$RUNTIME_DIR/$i.conf"
  # `awg showconf` does not include Address; keep it for reboot recovery.
  if [[ ! -s "$RUNTIME_DIR/$i.addr" ]]; then
    addr=$(ip -o -4 addr show dev "$i" 2>/dev/null | awk '{print $4}' | head -1)
    [[ -n $addr ]] && printf '%s\n' "$addr" > "$RUNTIME_DIR/$i.addr"
  fi
done

[[ -e "$RUNTIME_DIR/pre-v14.service" ]] || cp -a "$RUNTIME_UNIT" "$RUNTIME_DIR/pre-v14.service"
install -d -m 700 /opt/1mobile-runtime
install -m 700 "$REPO_DIR/scripts/runtime-supervise.sh" /opt/1mobile-runtime/supervise.sh
install -m 700 "$REPO_DIR/scripts/apply-iface.sh" /opt/1mobile-runtime/apply-iface.sh
install -m 644 "$REPO_DIR/systemd/1mobile-runtime.service" "$RUNTIME_UNIT"

systemctl daemon-reload
systemctl enable 1mobile-runtime.service
systemctl restart 1mobile-runtime.service
sleep 2
systemctl is-active --quiet 1mobile-runtime.service || fail 'Runtime service is not active'
for i in "${interfaces[@]}"; do
  awg show "$i" public-key >/dev/null || fail "Interface $i is unavailable"
done
ok "Runtime supervisor active for role=$ROLE"
systemctl status 1mobile-runtime.service --no-pager
