#!/bin/bash
# Restore the runtime service unit that existed before v1.2/v1.4.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

UNIT=""
for candidate in "$RUNTIME_DIR/pre-v14.service" "$RUNTIME_DIR/pre-v12.service"; do
  if [[ -f $candidate ]]; then UNIT=$candidate; break; fi
done
[[ -n $UNIT ]] || fail 'No previous runtime unit backup found'
systemctl stop 1mobile-runtime.service || true
cp -a "$UNIT" "$RUNTIME_UNIT"
systemctl daemon-reload
systemctl enable --now 1mobile-runtime.service
ok "Runtime unit restored from $UNIT"
