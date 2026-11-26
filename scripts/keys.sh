#!/bin/bash
# Simple, reboot-safe AmneziaWG key entry on either server.
#   bash install.sh keys show
#   bash install.sh keys import iran   (or: import exit)
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
command -v awg >/dev/null || fail 'amneziawg-tools (awg) is required'

K="$RUNTIME_DIR/keys"
install -d -m 700 "$K"

usage() {
  cat <<'EOF'
Usage: bash install.sh keys <show|import> [iran|exit]

  show             Print the public keys stored on this server
  import <role>    Paste/import keys on Iran or Exit; re-running is safe

Non-interactive (optional): OMAWG0_KEY, OMCLIENT0_KEY, PEER_PUB

Examples:
  sudo bash install.sh keys show
  sudo bash install.sh keys import exit
  echo 'BASE64KEY=' | OMAWG0_KEY="$(cat)" PEER_PUB='BASE64KEY=' \
    sudo -E bash install.sh keys import iran
EOF
}

validate_key() {
  PYTHONPATH="$REPO_DIR/src" python3 -c \
    'import sys; from keyutil import clean_key; print(clean_key(sys.argv[1]))' "$1"
}

ask_key() {
  local prompt=$1 env_value=$2 existing=$3 value=''
  if [[ -n $env_value ]]; then
    printf '%s\n' "$env_value"
    return
  fi
  if [[ -s $existing ]]; then
    read -rp "$prompt [Enter=keep existing]: " value || true
  else
    read -rp "$prompt [Enter=generate new]: " value || true
  fi
  if [[ -z $value ]]; then
    if [[ -s $existing ]]; then cat "$existing"; else awg genkey; fi
  else
    printf '%s\n' "$value"
  fi
}

store_key() {
  local name=$1 value=$2 tmp="$K/$1.key.tmp" key
  key=$(validate_key "$value")
  printf '%s\n' "$key" > "$tmp"
  chmod 600 "$tmp"
  mv -f "$tmp" "$K/$name.key"
  awg pubkey < "$K/$name.key" > "$K/$name.pub.tmp"
  mv -f "$K/$name.pub.tmp" "$K/$name.pub"
  chmod 644 "$K/$name.pub"
}

ask_peer() {
  local value="${PEER_PUB:-}"
  if [[ -z $value ]]; then
    read -rp 'Peer public key (the other server, Enter=keep existing): ' value || true
  fi
  if [[ -z $value && -s "$K/peer.pub" ]]; then
    cat "$K/peer.pub"
  else
    printf '%s\n' "$value"
  fi
}

update_conf() {
  local iface=$1 priv=${2:-} peer=${3:-} conf="$RUNTIME_DIR/$1.conf"
  [[ -f $conf ]] || fail "Missing $conf — run 'install.sh fresh $ROLE' once first"
  if [[ ! -s "$RUNTIME_DIR/$iface.addr" ]]; then
    local addr
    addr=$(ip -o -4 addr show dev "$iface" 2>/dev/null | awk '{print $4}' | head -1)
    [[ -n $addr ]] && printf '%s\n' "$addr" > "$RUNTIME_DIR/$iface.addr"
  fi
  PYTHONPATH="$REPO_DIR/src" python3 - "$conf" "$priv" "$peer" <<'PY'
import sys
from pathlib import Path
from keyutil import rewrite_conf
path, priv, peer = sys.argv[1:4]
text = Path(path).read_text()
out = rewrite_conf(text, private=priv or None, peer_public=peer or None)
tmp = Path(path + '.tmp')
tmp.write_text(out)
tmp.replace(path)
PY
  if awg show "$iface" public-key >/dev/null 2>&1; then
    bash "$REPO_DIR/scripts/apply-iface.sh" "$iface" || fail "Could not apply keys to $iface"
  fi
  chmod 600 "$conf"
}

action=${1:-show}
case "$action" in
  show)
    info "Role on this server: $(cat "$RUNTIME_DIR/role" 2>/dev/null || echo unknown)"
    for name in omawg0 omclient0; do
      [[ -s "$K/$name.key" ]] || continue
      printf '%-14s %s\n' "$name" "$(awg pubkey < "$K/$name.key")"
    done
    ok "Private keys stay in $K (mode 600); public keys can be pasted anywhere"
    ;;
  import)
    ROLE="${2:-$(cat "$RUNTIME_DIR/role" 2>/dev/null || true)}"
    [[ $ROLE == iran || $ROLE == exit ]] || fail 'Usage: keys import iran|exit'
    printf '%s\n' "$ROLE" > "$RUNTIME_DIR/role.tmp"
    mv -f "$RUNTIME_DIR/role.tmp" "$RUNTIME_DIR/role"

    info "Paste keys below. Press Enter to keep the existing key, or to generate a new one."
    OMAWG0=$(ask_key 'omawg0 private key (this server)' "${OMAWG0_KEY:-}" "$K/omawg0.key")
    store_key omawg0 "$OMAWG0"
    PEER=$(ask_peer)
    PEER=$(validate_key "$PEER")
    printf '%s\n' "$PEER" > "$K/peer.pub.tmp"
    mv -f "$K/peer.pub.tmp" "$K/peer.pub"
    chmod 644 "$K/peer.pub"

    update_conf omawg0 "$OMAWG0" "$PEER"

    if [[ $ROLE == iran ]]; then
      OMCLIENT0=$(ask_key 'omclient0 private key (clients connect here)' \
                  "${OMCLIENT0_KEY:-}" "$K/omclient0.key")
      store_key omclient0 "$OMCLIENT0"
      update_conf omclient0 "$OMCLIENT0" ''
      install -d -m 700 /etc/1mobile-client
      install -m 644 "$K/omclient0.pub" /etc/1mobile-client/server.pub
    fi

    bash "$REPO_DIR/scripts/persist.sh"

    ok "Keys imported. Public key to give to the other side:"
    printf '%-14s %s\n' omawg0 "$(awg pubkey < "$K/omawg0.key")"
    [[ $ROLE == iran ]] && \
      printf '%-14s %s\n' omclient0 "$(awg pubkey < "$K/omclient0.key")" || true
    ;;
  *)
    usage
    exit 1
    ;;
esac
