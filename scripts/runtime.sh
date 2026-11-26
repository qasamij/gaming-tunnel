#!/bin/bash
# Applied by the supervisor after any interface recreation.
# Iran: dedicated routing table for clients. Exit: forwarding + NAT to WAN.
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

D="${PANEL_DATA:-/etc/1mobile-panel}"
R="${RUNTIME_DATA:-/etc/1mobile-runtime}"
role=$(cat "$R/role")

sysctl -w net.ipv4.ip_forward=1 >/dev/null

if [[ $role == iran ]]; then
  python3 - "$D/network.json" <<'PY'
import json, subprocess, sys
from pathlib import Path
cfg = json.loads(Path(sys.argv[1]).read_text())
table = str(cfg.get('table', 179))
priority = str(cfg.get('priority', 10790))
net = cfg['network']
client = cfg.get('client', 'omclient0')
tunnel = cfg.get('tunnel', 'omawg0')
subprocess.check_call(['ip', 'route', 'replace', 'unreachable', 'default',
                       'metric', '32767', 'table', table])
subprocess.check_call(['ip', 'route', 'replace', net, 'dev', client, 'table', table])
subprocess.check_call(['ip', 'route', 'replace', 'default', 'dev', tunnel,
                       'metric', '0', 'table', table])
rules = subprocess.check_output(['ip', 'rule', 'show'], text=True)
if not any(line.startswith(priority + ':') for line in rules.splitlines()):
    subprocess.check_call(['ip', 'rule', 'add', 'priority', priority,
                           'from', net, 'lookup', table])
PY
elif [[ $role == exit ]]; then
  STATE="$R/exit.json"
  [[ -f $STATE ]] || exit 0
  SUBNET=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["client_subnet"])' "$STATE")
  WAN=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("wan",""))' "$STATE")
  PEER=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("tunnel_peer",""))' "$STATE")
  [[ -n $WAN ]] || WAN=$(ip route show default | awk '/default via/{print $5; exit}')
  [[ -n $WAN ]] || exit 0
  # Without these routes, return traffic (including UDP echo replies) exits
  # through the WAN instead of going back into the tunnel.
  ip route replace "$SUBNET" dev omawg0
  [[ -n $PEER ]] && ip route replace "$PEER/32" dev omawg0
  iptables -t nat -C POSTROUTING -s "$SUBNET" -o "$WAN" -j MASQUERADE 2>/dev/null || \
    iptables -t nat -A POSTROUTING -s "$SUBNET" -o "$WAN" -j MASQUERADE
  iptables -C FORWARD -s "$SUBNET" -o "$WAN" -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -s "$SUBNET" -o "$WAN" -j ACCEPT
  iptables -C FORWARD -i "$WAN" -d "$SUBNET" -m state --state RELATED,ESTABLISHED -j ACCEPT 2>/dev/null || \
    iptables -A FORWARD -i "$WAN" -d "$SUBNET" -m state --state RELATED,ESTABLISHED -j ACCEPT
else
  echo "Unknown role: $role" >&2
  exit 1
fi
