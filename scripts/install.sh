#!/bin/bash
# Single entry point. See docs/INSTALL.md for the full workflow.
set -euo pipefail
source "$(dirname "$0")/common.sh"

usage() {
  cat <<'EOF'
Usage: bash install.sh <command>

  deps       Install Debian/Ubuntu packages (INSTALL_AWG=1 builds upstream AWG)
  keygen     Generate AWG keys on this server (usage: install.sh keygen iran|exit)
  keys       Show or paste/import keys on any server (usage: install.sh keys show|import iran|exit)
  fresh      Full from-scratch tunnel (usage: install.sh fresh iran|exit)
  bootstrap  Panel-only bootstrap on an existing AmneziaWG host
  runtime    Install tunnel supervisor on an existing AmneziaWG host
  persist    Re-enable boot services and verify the tunnel is reboot-safe
  monitor    Upgrade an existing v1.0/v1.1 panel to v1.4
  echo       Install UDP echo responder on the exit server
  rollback   Restore the previous panel systemd unit
  rollback-runtime  Restore the previous runtime systemd unit
  uninstall  Stop/disable services (CONFIRM=1 also deletes files)

Examples:
  bash install.sh keygen iran        # on Iran VPS
  bash install.sh keygen exit        # on exit VPS
  bash install.sh keys show          # print public keys to paste elsewhere
  bash install.sh keys import iran   # paste keys on any server
  bash install.sh fresh iran         # after pasting the exit public key
  bash install.sh fresh exit         # after pasting the Iran public key
  bash install.sh bootstrap runtime  # existing tunnel, panel only
  bash install.sh persist            # verify reboot/SSH-logout survival
  bash install.sh echo               # UDP RTT responder on exit
EOF
}

[[ $# -ge 1 ]] || { usage; exit 1; }
for command in "$@"; do
  case "$command" in
    deps)            bash "$REPO_DIR/scripts/install-deps.sh" ;;
    keygen|fresh)
      [[ $# -ge 2 ]] || { echo "$command needs iran or exit" >&2; exit 1; }
      ROLE="$2"; shift
      if [[ $command == keygen ]]; then
        bash "$REPO_DIR/scripts/fresh-keygen.sh" "$ROLE"
      else
        bash "$REPO_DIR/scripts/install-fresh.sh" "$ROLE"
      fi
      break
      ;;
    keys)
      [[ $# -ge 2 ]] || { echo 'keys needs show or import' >&2; usage; exit 1; }
      SUB="$2"; shift 2
      if [[ $SUB == show ]]; then
        bash "$REPO_DIR/scripts/keys.sh" show
      elif [[ $SUB == import ]]; then
        [[ $# -ge 1 ]] || { echo 'keys import needs iran or exit' >&2; exit 1; }
        bash "$REPO_DIR/scripts/keys.sh" import "$1"
      else
        echo "Unknown keys command: $SUB" >&2; usage; exit 1
      fi
      break
      ;;
    bootstrap)       bash "$REPO_DIR/scripts/bootstrap-panel.sh" ;;
    runtime)         bash "$REPO_DIR/scripts/install-runtime.sh" ;;
    persist)         bash "$REPO_DIR/scripts/persist.sh" ;;
    monitor)         bash "$REPO_DIR/scripts/install-monitor.sh" ;;
    echo)            bash "$REPO_DIR/scripts/install-echo.sh" ;;
    rollback)        bash "$REPO_DIR/scripts/rollback.sh" ;;
    rollback-runtime) bash "$REPO_DIR/scripts/rollback-runtime.sh" ;;
    uninstall)       bash "$REPO_DIR/scripts/uninstall.sh" ;;
    -h|--help|help)  usage ;;
    *) echo "Unknown command: $command" >&2; usage; exit 1 ;;
  esac
done
