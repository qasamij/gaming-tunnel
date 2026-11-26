#!/bin/bash
# Restore the panel service unit that existed before this version.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

UNIT=""
for candidate in "$DATA_DIR/pre-v14.service" "$DATA_DIR/pre-v11.service"; do
  if [[ -f $candidate ]]; then UNIT=$candidate; break; fi
done
[[ -n $UNIT ]] || fail 'No previous panel unit backup found'
cp -a "$UNIT" "$PANEL_UNIT"
systemctl daemon-reload
systemctl restart 1mobile-panel.service
ok "Panel unit restored from $UNIT"
echo "Python files remain in $PREFIX; restore from backup/ manually if needed."
