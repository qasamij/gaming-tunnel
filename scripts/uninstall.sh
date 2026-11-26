#!/bin/bash
# Stop services by default; remove files only with CONFIRM=1.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

systemctl disable --now 1mobile-panel.service || true
systemctl disable --now 1mobile-udp-echo.service || true
systemctl disable --now 1mobile-runtime.service || true
ok 'Services stopped and disabled'

if [[ ${CONFIRM:-0} == 1 ]]; then
  rm -rf "$PREFIX"
  rm -rf "$DATA_DIR"
  rm -f /opt/1mobile-runtime/supervise.sh
  ok 'Panel files and secrets deleted'
else
  echo "Files kept. Re-run with CONFIRM=1 to delete $PREFIX and $DATA_DIR"
fi
