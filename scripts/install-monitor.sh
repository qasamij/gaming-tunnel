#!/bin/bash
# Upgrade an existing v1.0/v1.1 panel to this v1.4 monitor build.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

OLD="${OLD_PREFIX:-/opt/1mobile-web-v11}"
[[ -f "$OLD/web.py" && -s "$DATA_DIR/password" ]] || fail 'Existing v1 panel data not found'
grep -qE '/opt/1mobile-web-v(1|11)/web\.py' "$PANEL_UNIT" || \
  fail 'Expected old panel path in 1mobile-panel.service'

PYTHONPATH="$REPO_DIR/src" python3 -m py_compile \
  "$REPO_DIR/src/web.py" "$REPO_DIR/src/backend.py" \
  "$REPO_DIR/src/ops.py" "$REPO_DIR/src/monitor.py" "$REPO_DIR/src/udp_echo.py"

STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP="$DATA_DIR/backup/upgrade-$STAMP"
mkdir -p "$BACKUP"
cp -a "$OLD"/web.py "$OLD"/backend.py "$OLD"/ops.py "$BACKUP/" 2>/dev/null || true
for f in monitor.py monitor.js; do
  [[ ! -e "$OLD/$f" ]] || cp -a "$OLD/$f" "$BACKUP/"
done
[[ ! -f "$DATA_DIR/network.json" ]] || cp -a "$DATA_DIR/network.json" "$BACKUP/"
cp -a "$PANEL_UNIT" "$BACKUP/1mobile-panel.service"

info 'Migrating network.json (adding probe/obfuscation defaults)'
PYTHONPATH="$REPO_DIR/src" python3 - "$DATA_DIR/network.json" <<'PY'
import json, sys
from pathlib import Path
import ops
p = Path(sys.argv[1])
cfg = ops.settings(p.parent) if p.is_file() else {}
tmp = p.with_suffix('.json.tmp')
tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True))
tmp.replace(p)
PY

info 'Installing v1.4 files'
install -d -m 755 "$PREFIX"
install -d -m 755 "$PREFIX/static"
install -m 600 "$REPO_DIR"/src/web.py "$REPO_DIR"/src/backend.py \
  "$REPO_DIR"/src/ops.py "$REPO_DIR"/src/monitor.py "$PREFIX/"
install -m 644 "$REPO_DIR"/src/udp_echo.py "$PREFIX/udp_echo.py"
install -m 644 "$REPO_DIR"/src/static/style.css "$REPO_DIR"/src/static/app.js "$PREFIX/static/"

sed -E "s|/opt/1mobile-web-v1(1)?/web\.py|$PREFIX/web.py|" "$BACKUP/1mobile-panel.service" > "$PANEL_UNIT"
grep -q "$PREFIX/web.py" "$PANEL_UNIT" || { cp -a "$BACKUP/1mobile-panel.service" "$PANEL_UNIT"; fail 'Unit rewrite failed'; }

systemctl daemon-reload
if ! systemctl restart 1mobile-panel.service || \
   ! curl -kfsS --retry 3 --retry-connrefused --max-time 6 https://127.0.0.1:9443/ \
     | grep -q 'ورود امن'; then
  cp -a "$BACKUP/1mobile-panel.service" "$PANEL_UNIT"
  for f in web.py backend.py ops.py; do
    [[ ! -f "$BACKUP/$f" ]] || cp -a "$BACKUP/$f" "$OLD/$f"
  done
  cp -a "$BACKUP/network.json" "$DATA_DIR/network.json" 2>/dev/null || true
  systemctl daemon-reload
  systemctl restart 1mobile-panel.service || true
  fail 'Upgrade failed; previous files restored'
fi

ok "Upgraded to v1.4. Backup: $BACKUP"
echo 'This smoke check reached the login page only. Verify login + one test client manually.'
