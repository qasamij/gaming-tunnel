#!/bin/bash
# Shared network settings (obfuscation, subnet, ports) must exist BEFORE
# either `fresh iran` or `fresh exit` runs. Generate once, paste the printed
# OMAWG_SHARED=... line on the other server, then import it there.
set -euo pipefail
source "$(dirname "$0")/common.sh"

export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
FILE="${FRESH_CONFIG_FILE:-$DATA_DIR/network.json}"
CMD="${1:-}"

usage() {
  cat <<'EOF'
Usage: bash scripts/fresh-config.sh <init|show|import|obfuscation>

  init         Generate network.json once (honours JUNK_COUNT), print the line
               to copy to the other server.
  show         Print the copyable line from the local network.json.
  import LINE  Restore the shared settings from the other server's line.
  obfuscation  Print the nine normalized `Key = value` lines.

Set FRESH_CONFIG_FILE to use a different path (default: /etc/1mobile-panel/network.json).
EOF
}

prepare_dir() {
  if [[ $FILE == "$DATA_DIR/network.json" ]]; then
    install -d -m 700 "$DATA_DIR"
  else
    mkdir -p "$(dirname "$FILE")"
  fi
}

case "$CMD" in
  init)
    [[ ! -e $FILE ]] || { echo "Shared config already exists: $FILE" >&2; echo "Use 'show' to copy it, or set FORCE=1 to regenerate." >&2; [[ ${FORCE:-0} == 1 ]] || exit 1; }
    prepare_dir
    python3 - "${JUNK_COUNT:-3}" "$FILE" <<'PY'
import sys
from keyutil import new_shared_config, obfuscation_lines, shared_line, write_shared_config
cfg = new_shared_config(sys.argv[1])
write_shared_config(cfg, sys.argv[2])
print('[ok] Shared config written to ' + sys.argv[2])
print('Copy this line to the other server:')
print(shared_line(cfg))
print('Obfuscation values (for reference):')
print(obfuscation_lines(cfg['obfuscation']))
PY
    ;;
  show)
    python3 - "$FILE" <<'PY'
import sys
from keyutil import read_shared_config, shared_line
print(shared_line(read_shared_config(sys.argv[1])))
PY
    ;;
  import)
    LINE="${2:-}"
    [[ -n $LINE ]] || { echo "Usage: fresh-config.sh import 'OMAWG_SHARED=...'" >&2; exit 1; }
    prepare_dir
    OMAWG_SHARED="$LINE" python3 - "$FILE" <<'PY'
import os
import sys
from keyutil import obfuscation_lines, parse_shared_line, write_shared_config
cfg = parse_shared_line(os.environ['OMAWG_SHARED'])
write_shared_config(cfg, sys.argv[1])
print('[ok] Shared config restored to ' + sys.argv[1])
print(obfuscation_lines(cfg['obfuscation']))
PY
    ;;
  obfuscation)
    python3 - "$FILE" <<'PY'
import sys
from keyutil import obfuscation_lines, read_shared_config
print(obfuscation_lines(read_shared_config(sys.argv[1])['obfuscation']))
PY
    ;;
  -h|--help|help|'')
    usage
    ;;
  *)
    echo "Unknown fresh-config command: $CMD" >&2
    usage
    exit 1
    ;;
esac
