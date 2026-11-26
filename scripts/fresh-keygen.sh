#!/bin/bash
# Generate AWG keypairs on a fresh server. Run once on each server.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

need_awg
ROLE="${1:-}"
[[ $ROLE == iran || $ROLE == exit ]] || { echo "Usage: fresh-keygen.sh iran|exit" >&2; exit 1; }

K="$RUNTIME_DIR/keys"
install -d -m 700 "$K"

gen() {
  local name=$1
  if [[ ! -s "$K/$name.key" ]]; then
    awg genkey > "$K/$name.key"
  fi
  chmod 600 "$K/$name.key"
  awg pubkey < "$K/$name.key" > "$K/$name.pub"
  chmod 644 "$K/$name.pub"
  printf '%-14s %s\n' "$name" "$(cat "$K/$name.pub")"
}

echo "[$ROLE] public keys (copy these to the other server):"
if [[ $ROLE == iran ]]; then
  gen omawg0      # Iran -> exit tunnel
  gen omclient0   # clients -> Iran
else
  gen omawg0      # exit -> Iran tunnel
fi
ok "Keys stored in $K (private keys never leave this server)"
