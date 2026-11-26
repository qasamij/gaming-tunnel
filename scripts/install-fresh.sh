#!/bin/bash
# Fresh two-server AmneziaWG gaming tunnel.
#   Run `fresh-keygen.sh iran` on the Iran VPS and `fresh-keygen.sh exit`
#   on the exit VPS first, then exchange the printed public keys.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
for cmd in awg amneziawg-go ip iptables python3 openssl curl qrencode; do
  command -v "$cmd" >/dev/null || fail "Missing command: $cmd"
done

ROLE="${1:-}"
[[ $ROLE == iran || $ROLE == exit ]] || { echo "Usage: install-fresh.sh iran|exit" >&2; exit 1; }
K="$RUNTIME_DIR/keys"
[[ -s "$K/omawg0.key" ]] || fail "Run: bash fresh-keygen.sh $ROLE"

install -d -m 700 "$RUNTIME_DIR"
printf '%s\n' "$ROLE" > "$RUNTIME_DIR/role"

# Obfuscation constants are generated once and shared by both ends + clients.
if [[ ! -f "$DATA_DIR/network.json" && $ROLE == iran ]]; then
  install -d -m 700 "$DATA_DIR"
  python3 - "${JUNK_COUNT:-3}" "$DATA_DIR/network.json" <<'PY'
import json, secrets, sys
from pathlib import Path
jc = int(sys.argv[1]); target = Path(sys.argv[2])
def u32(): return secrets.randbelow(0xFFFFFFFF) + 1
cfg = {
  'endpoint': '0.0.0.0', 'network': '10.7.0.0/24',
  'table': 179, 'priority': 10790,
  'client': 'omclient0', 'tunnel': 'omawg0',
  'probe_host': '', 'probe_port': 5355,
  'probe_interval': 5, 'probe_timeout': 1.0,
  'obfuscation': {'Jc': jc, 'Jmin': 40, 'Jmax': 70,
                  'S1': 32, 'S2': 48,
                  'H1': u32(), 'H2': u32(), 'H3': u32(), 'H4': u32()},
}
tmp = target.with_suffix('.json.tmp'); tmp.write_text(json.dumps(cfg, indent=2)); tmp.replace(target)
PY
fi

OBF=""
if [[ -f "$DATA_DIR/network.json" ]]; then
  OBF=$(python3 - "$DATA_DIR/network.json" <<'PY'
import json, sys
o = json.load(open(sys.argv[1])).get('obfuscation', {})
print(' '.join('{} = {}'.format(k, o[k]) for k in ('Jc','Jmin','Jmax','S1','S2','H1','H2','H3','H4')))
PY
)
fi

write_iface() {
  local name=$1 file=$2 priv=$3 addr=$4 port=$5 peer_pub=$6 allowed=$7 endpoint=$8
  {
    echo '[Interface]'
    echo "PrivateKey = $priv"
    echo "Address = $addr"
    echo "ListenPort = $port"
    echo "$OBF" | tr ' ' '\n'
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
}

start_iface() {
  local iface=$1 file=$2
  if awg show "$iface" public-key >/dev/null 2>&1; then
    info "Applying config to existing $iface"
    awg setconf "$iface" "$file"
  else
    ip link show "$iface" >/dev/null 2>&1 && fail "$iface exists but AWG is unavailable"
    amneziawg-go "$iface"
    awg setconf "$iface" "$file"
  fi
  cp -a "$file" "$RUNTIME_DIR/$iface.conf"
}

install -m 755 "$REPO_DIR/scripts/runtime.sh" /opt/1mobile-runtime/runtime.sh 2>/dev/null || {
  install -d -m 700 /opt/1mobile-runtime
  install -m 755 "$REPO_DIR/scripts/runtime.sh" /opt/1mobile-runtime/runtime.sh
}

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
  bash "$REPO_DIR/scripts/install-runtime.sh"

  ok "Iran side ready"
  echo "Give this omclient0 public key to every client config generator: $(cat "$K/omclient0.pub")"
  echo "Panel: https://$CLIENT_ENDPOINT:9443/"
else
  read -rp 'Iran server public IPv4: ' IRAN_IP
  read -rp 'Iran tunnel public key (omawg0.pub from Iran server): ' IRAN_PUB
  read -rp 'Iran tunnel ListenPort [51821]: ' IRAN_PORT
  IRAN_PORT="${IRAN_PORT:-51821}"
  read -rp 'Client subnet to route/NAT, e.g. 10.7.0.0/24: ' CLIENT_SUBNET
  TUNNEL_LOCAL="${TUNNEL_LOCAL:-10.9.0.1/30}"
  TUNNEL_REMOTE="${TUNNEL_REMOTE:-10.9.0.2}"

  # Reuse the obfuscation values generated on Iran (paste them if on a different host).
  if [[ -z ${OBF:-} || ! -f "$DATA_DIR/network.json" ]]; then
    read -rp 'Obfuscation line from Iran (Jc=... H1=...), paste exactly: ' OBF
  fi
  write_iface omawg0 "$RUNTIME_DIR/omawg0.conf.pending" \
    "$(cat "$K/omawg0.key")" "$TUNNEL_LOCAL" "$IRAN_PORT" \
    "$IRAN_PUB" "$CLIENT_SUBNET" "$IRAN_IP:$IRAN_PORT"
  mv "$RUNTIME_DIR/omawg0.conf.pending" "$RUNTIME_DIR/omawg0.conf"
  start_iface omawg0 "$RUNTIME_DIR/omawg0.conf"

  WAN=$(ip route show default | awk '/default via/{print $5; exit}')
  python3 - "$CLIENT_SUBNET" "$WAN" "$RUNTIME_DIR/exit.json" <<'PY'
import json, sys
from pathlib import Path
subnet, wan, target = sys.argv[1:]
p = Path(target); p.write_text(json.dumps({'client_subnet': subnet, 'wan': wan}, indent=2))
PY
  /opt/1mobile-runtime/runtime.sh
  ECHO_HOST="$TUNNEL_LOCAL" PROBE_PORT=5355 bash "$REPO_DIR/scripts/install-echo.sh"
  bash "$REPO_DIR/scripts/install-runtime.sh"

  ok "Exit side ready"
  echo "Give this public key to the Iran installer: $(cat "$K/omawg0.pub")"
  echo "Allow UDP/5355 from $TUNNEL_REMOTE only."
fi
