#!/bin/bash
# Fresh two-server AmneziaWG gaming tunnel.
#   First run `fresh-config.sh init` on one server and `import` the printed
#   line on the other, then exchange keys with `fresh-keygen.sh iran|exit`.
#   Only after that run `fresh iran` / `fresh exit` in either order.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
for cmd in amneziawg-go ip iptables python3 openssl curl qrencode; do
  command -v "$cmd" >/dev/null || fail "Missing command: $cmd"
done
need_awg

ROLE="${1:-}"
[[ $ROLE == iran || $ROLE == exit ]] || { echo "Usage: install-fresh.sh iran|exit" >&2; exit 1; }

# `fresh` is deliberately destructive: it rewrites saved configs and applies
# them to live interfaces with `awg setconf`. Refuse it on a running tunnel
# so an accidental re-run cannot drop peers added by the panel.
if [[ ${FORCE_FRESH:-0} != 1 ]]; then
  if awg show omawg0 public-key >/dev/null 2>&1 || \
     awg show omclient0 public-key >/dev/null 2>&1 || \
     [[ -s "$RUNTIME_DIR/role" && -s "$RUNTIME_DIR/omawg0.conf" ]]; then
    fail 'An existing tunnel/saved state was detected. Use "install.sh runtime", "install.sh monitor" or "install.sh keys import" instead. Set FORCE_FRESH=1 ONLY for an intentional rebuild on a lab server.'
  fi
fi

K="$RUNTIME_DIR/keys"
[[ -s "$K/omawg0.key" ]] || fail "Run: bash fresh-keygen.sh $ROLE"

install -d -m 700 "$RUNTIME_DIR"
printf '%s\n' "$ROLE" > "$RUNTIME_DIR/role"

# Shared obfuscation/subnet settings are generated ONCE, before either server
# is installed, by `fresh-config init`. Copy the printed OMAWG_SHARED= line to
# the other server with `fresh-config import`. Generating them inside
# `fresh iran` left `fresh exit` without values when Exit was installed first.
[[ -f "$DATA_DIR/network.json" ]] || fail \
  'Shared config is missing. Before either server: sudo bash scripts/install.sh fresh-config init ; copy the OMAWG_SHARED=... line to the other server and run: sudo bash scripts/install.sh fresh-config import "<line>"'

export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"
OBF_LINES=$(python3 - "$DATA_DIR/network.json" <<'PY'
import sys
from keyutil import obfuscation_lines, read_shared_config
print(obfuscation_lines(read_shared_config(sys.argv[1])['obfuscation']))
PY
)
[[ -n $OBF_LINES ]] || fail 'Obfuscation values are missing from the shared config'
printf '%s\n' "$OBF_LINES" > "$RUNTIME_DIR/obfuscation.txt"
chmod 600 "$RUNTIME_DIR/obfuscation.txt"

write_iface() {
  local name=$1 file=$2 priv=$3 addr=$4 port=$5 peer_pub=$6 allowed=$7 endpoint=$8
  {
    echo '[Interface]'
    echo "PrivateKey = $priv"
    echo "Address = $addr"
    echo "ListenPort = $port"
    printf '%s\n' "$OBF_LINES"
    if [[ -n $peer_pub ]]; then
      echo
      echo '[Peer]'
      echo "PublicKey = $peer_pub"
      echo "AllowedIPs = $allowed"
      [[ -n $endpoint ]] && echo "Endpoint = $endpoint"
      echo 'PersistentKeepalive = 25'
    fi
    echo
  } > "$file"
  chmod 600 "$file"
  printf '%s\n' "$addr" > "$RUNTIME_DIR/$name.addr"
  chmod 600 "$RUNTIME_DIR/$name.addr"
}

start_iface() {
  local iface=$1 file=$2
  cp -a "$file" "$RUNTIME_DIR/$iface.conf"
  bash "$REPO_DIR/scripts/apply-iface.sh" "$iface"
  info "$iface up: $(awg show "$iface" public-key)"
}

install -d -m 700 /opt/1mobile-runtime
install -m 755 "$REPO_DIR/scripts/runtime.sh" /opt/1mobile-runtime/runtime.sh
install -m 700 "$REPO_DIR/scripts/apply-iface.sh" /opt/1mobile-runtime/apply-iface.sh
install -m 600 "$REPO_DIR/src/keyutil.py" /opt/1mobile-runtime/keyutil.py
install -m 600 "$REPO_DIR/src/awgdetect.py" /opt/1mobile-runtime/awgdetect.py

if [[ $ROLE == iran ]]; then
  read -rp 'Public IPv4 clients will connect to (Iran): ' CLIENT_ENDPOINT
  read -rp 'Exit server public IPv4: ' EXIT_IP
  read -rp 'Exit tunnel public key (omawg0.pub from exit server): ' EXIT_PUB
  EXIT_PORT="${EXIT_PORT:-51821}"
  CLIENT_PORT="${CLIENT_PORT:-51820}"
  CLIENT_SUBNET="${CLIENT_SUBNET:-10.7.0.1/24}"
  TUNNEL_LOCAL="${TUNNEL_LOCAL:-10.9.0.2/30}"
  TUNNEL_REMOTE="${TUNNEL_REMOTE:-10.9.0.1}"

  python3 - "$CLIENT_ENDPOINT" "$CLIENT_SUBNET" "$TUNNEL_REMOTE" "$DATA_DIR/network.json" <<'PY'
import ipaddress, json, sys
from pathlib import Path
endpoint, subnet, probe, target = sys.argv[1:]
cfg = json.loads(Path(target).read_text())
cfg['endpoint'] = str(ipaddress.IPv4Address(endpoint))
cfg['network'] = str(ipaddress.IPv4Network(subnet, strict=False))
cfg['probe_host'] = str(ipaddress.IPv4Address(probe))
tmp = Path(target).with_suffix('.json.tmp'); tmp.write_text(json.dumps(cfg, indent=2)); tmp.replace(target)
PY

  OBF_JSON=$(python3 -c 'import json,sys; print(json.dumps(json.load(open(sys.argv[1]))["obfuscation"]))' "$DATA_DIR/network.json")
  write_iface omawg0 "$RUNTIME_DIR/omawg0.conf.pending" \
    "$(cat "$K/omawg0.key")" "$TUNNEL_LOCAL" "$EXIT_PORT" \
    "$EXIT_PUB" '0.0.0.0/0' "$EXIT_IP:$EXIT_PORT"
  # Client-facing interface has no peers yet; the panel adds them.
  write_iface omclient0 "$RUNTIME_DIR/omclient0.conf.pending" \
    "$(cat "$K/omclient0.key")" "$CLIENT_SUBNET" "$CLIENT_PORT" '' '' ''
  mv "$RUNTIME_DIR/omawg0.conf.pending" "$RUNTIME_DIR/omawg0.conf"
  mv "$RUNTIME_DIR/omclient0.conf.pending" "$RUNTIME_DIR/omclient0.conf"
  start_iface omawg0 "$RUNTIME_DIR/omawg0.conf"
  start_iface omclient0 "$RUNTIME_DIR/omclient0.conf"
  /opt/1mobile-runtime/runtime.sh

  PASSWORD="${PANEL_PASSWORD:-}"
  if [[ -z $PASSWORD ]]; then
    read -rsp 'Admin password (min 10 chars): ' PASSWORD; echo
  fi
  PANEL_PASSWORD="$PASSWORD" PROBE_HOST="$TUNNEL_REMOTE" PROBE_PORT=5355 \
    bash "$REPO_DIR/scripts/bootstrap-panel.sh"
  install -d -m 700 /etc/1mobile-client
  install -m 644 "$K/omclient0.pub" /etc/1mobile-client/server.pub
  bash "$REPO_DIR/scripts/install-runtime.sh"
  bash "$REPO_DIR/scripts/persist.sh"

  ok "Iran side ready"
  echo "Give this omclient0 public key to every client config generator: $(cat "$K/omclient0.pub")"
  echo "Panel: https://$CLIENT_ENDPOINT:9443/"
else
  read -rp 'Iran server public IPv4: ' IRAN_IP
  read -rp 'Iran tunnel public key (omawg0.pub from Iran server): ' IRAN_PUB
  read -rp 'Iran tunnel ListenPort [51821]: ' IRAN_PORT
  IRAN_PORT="${IRAN_PORT:-51821}"
  DEFAULT_SUBNET=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["network"])' "$DATA_DIR/network.json")
  read -rp "Client subnet to route/NAT [${DEFAULT_SUBNET}]: " CLIENT_SUBNET
  CLIENT_SUBNET="${CLIENT_SUBNET:-$DEFAULT_SUBNET}"
  TUNNEL_LOCAL="${TUNNEL_LOCAL:-10.9.0.1/30}"
  TUNNEL_REMOTE="${TUNNEL_REMOTE:-10.9.0.2}"

  # The peer must accept both client traffic and the tunnel probe address,
  # otherwise the UDP echo reply from 10.9.0.1 cannot be routed back to Iran.
  ALLOWED="$CLIENT_SUBNET, $TUNNEL_REMOTE/32"
  write_iface omawg0 "$RUNTIME_DIR/omawg0.conf.pending" \
    "$(cat "$K/omawg0.key")" "$TUNNEL_LOCAL" "$IRAN_PORT" \
    "$IRAN_PUB" "$ALLOWED" "$IRAN_IP:$IRAN_PORT"
  mv "$RUNTIME_DIR/omawg0.conf.pending" "$RUNTIME_DIR/omawg0.conf"
  start_iface omawg0 "$RUNTIME_DIR/omawg0.conf"

  WAN=$(ip route show default | awk '/default via/{print $5; exit}')
  python3 - "$CLIENT_SUBNET" "$WAN" "$TUNNEL_REMOTE" "$RUNTIME_DIR/exit.json" <<'PY'
import json, sys
from pathlib import Path
subnet, wan, peer, target = sys.argv[1:]
state = {'client_subnet': subnet, 'wan': wan, 'tunnel_peer': peer}
p = Path(target)
tmp = p.with_suffix('.json.tmp')
tmp.write_text(json.dumps(state, indent=2))
tmp.replace(p)
PY
  /opt/1mobile-runtime/runtime.sh
  ECHO_HOST="$TUNNEL_LOCAL" PROBE_PORT=5355 bash "$REPO_DIR/scripts/install-echo.sh"
  bash "$REPO_DIR/scripts/install-runtime.sh"
  bash "$REPO_DIR/scripts/persist.sh"

  ok "Exit side ready"
  echo "Give this public key to the Iran installer: $(cat "$K/omawg0.pub")"
  echo "Allow UDP/5355 from $TUNNEL_REMOTE only."
fi
