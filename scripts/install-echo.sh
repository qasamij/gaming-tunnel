#!/bin/bash
# Install the UDP echo responder on the exit server.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
command -v python3 >/dev/null || fail 'python3 is required'

PORT="${PROBE_PORT:-5355}"
HOST="${ECHO_HOST:-0.0.0.0}"
install -d -m 755 "$PREFIX"
install -m 644 "$REPO_DIR/src/udp_echo.py" "$PREFIX/udp_echo.py"

sed -e "s|Environment=ECHO_HOST=0.0.0.0|Environment=ECHO_HOST=$HOST|" \
    -e "s|Environment=ECHO_PORT=5355|Environment=ECHO_PORT=$PORT|" \
  "$REPO_DIR/systemd/1mobile-udp-echo.service" > "$ECHO_UNIT"
systemctl daemon-reload
systemctl enable 1mobile-udp-echo.service
systemctl restart 1mobile-udp-echo.service
sleep 1
systemctl is-active --quiet 1mobile-udp-echo.service || fail 'Echo service failed'
ok "UDP echo listening on 0.0.0.0:$PORT/udp"
echo 'Allow this port only from the Iran tunnel IP in your firewall.'
