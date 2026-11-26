#!/bin/bash
# Fresh panel bootstrap: generates secrets, TLS cert and systemd unit.
# It does NOT create the AmneziaWG tunnel itself; see docs/INSTALL.md.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root
umask 077

for cmd in python3 openssl ip curl; do
  command -v "$cmd" >/dev/null || fail "Missing command: $cmd"
done
command -v awg >/dev/null || echo "[warn] awg not found; peer management will fail until installed"
command -v qrencode >/dev/null || echo "[warn] qrencode not found; QR downloads will fail until installed"

[[ -s "$DATA_DIR/password" && ${FORCE:-0} != 1 ]] && \
  fail "Panel data already exists. Use FORCE=1 only if you know what you are replacing."

mkdir -p "$DATA_DIR" "$DATA_DIR/backup"

ENDPOINT="${ENDPOINT:-}"
if [[ -z $ENDPOINT ]]; then read -rp 'Public IPv4 for client configs: ' ENDPOINT; fi
NETWORK="${NETWORK:-}"
if [[ -z $NETWORK ]]; then
  NETWORK=$(python3 - <<'PY'
import json,subprocess
try:
    a=json.loads(subprocess.check_output(['ip','-j','-4','addr','show','dev','omclient0']))[0]['addr_info'][0]
    print('{}/{}'.format(a['local'],a['prefixlen']))
except Exception:
    print('')
PY
)
  [[ -n $NETWORK ]] && echo "[*] Detected client subnet: $NETWORK"
  [[ -z $NETWORK ]] && read -rp 'Client subnet (/24), e.g. 10.7.0.0/24: ' NETWORK
fi
PROBE_HOST="${PROBE_HOST:-}"
[[ -z $PROBE_HOST ]] && read -rp 'Exit tunnel IP for UDP RTT probe (empty to use ICMP): ' PROBE_HOST
PROBE_PORT="${PROBE_PORT:-5355}"

if [[ -f "$DATA_DIR/network.json" && ${REGENERATE_NETWORK:-0} != 1 ]]; then
  info 'Reusing existing network.json (obfuscation values stay in sync with the tunnel)'
  ENDPOINT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["endpoint"])' "$DATA_DIR/network.json")
  NETWORK=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["network"])' "$DATA_DIR/network.json")
  PROBE_HOST=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("probe_host",""))' "$DATA_DIR/network.json")
  PROBE_PORT=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("probe_port",5355))' "$DATA_DIR/network.json")
else
python3 - "$ENDPOINT" "$NETWORK" "$PROBE_HOST" "$PROBE_PORT" "$DATA_DIR/network.json" <<'PY'
import ipaddress, json, secrets, sys
from pathlib import Path
endpoint, network, probe_host, probe_port, target = sys.argv[1:]
endpoint = str(ipaddress.IPv4Address(endpoint))
net = ipaddress.IPv4Network(network, strict=False)
if net.prefixlen != 24:
    raise SystemExit('Client subnet must be /24')
probe_host = probe_host.strip()
if probe_host:
    probe_host = str(ipaddress.IPv4Address(probe_host))
def u32():
    return secrets.randbelow(0xFFFFFFFF) + 1
cfg = {
    'endpoint': endpoint,
    'network': str(net),
    'table': 179,
    'priority': 10790,
    'client': 'omclient0',
    'tunnel': 'omawg0',
    'probe_host': probe_host,
    'probe_port': int(probe_port),
    'probe_interval': 5,
    'probe_timeout': 1.0,
    'obfuscation': {
        'Jc': 3, 'Jmin': 40, 'Jmax': 70,
        'S1': 32, 'S2': 48,
        'H1': u32(), 'H2': u32(), 'H3': u32(), 'H4': u32(),
    },
}
p = Path(target)
tmp = p.with_suffix('.json.tmp')
tmp.write_text(json.dumps(cfg, indent=2, sort_keys=True))
tmp.replace(p)
PY
fi

PASSWORD="${PANEL_PASSWORD:-}"
if [[ -z $PASSWORD ]]; then
  read -rsp 'Admin password: ' PASSWORD; echo
  read -rsp 'Repeat password: ' PASSWORD2; echo
  [[ $PASSWORD == "$PASSWORD2" ]] || fail 'Passwords do not match'
fi
[[ ${#PASSWORD} -ge 10 ]] || fail 'Password must be at least 10 characters'
# Store a salted Argon2id/scrypt hash, never the plaintext password.
HASHED=$(PYTHONPATH="$REPO_DIR/src" PANEL_PASSWORD="$PASSWORD" python3 - <<'PY'
import os
from passwords import hash_password
print(hash_password(os.environ['PANEL_PASSWORD']))
PY
)
printf '%s\n' "$HASHED" > "$DATA_DIR/password"

TOTP=$(python3 -c 'import base64,secrets; print(base64.b32encode(secrets.token_bytes(20)).decode().rstrip("="))')
printf '%s\n' "$TOTP" > "$DATA_DIR/totp-secret"
printf '%s\n' "${ADMIN_NETWORK:-127.0.0.1/32}" > "$DATA_DIR/admin-network"

info 'Generating self-signed TLS certificate'
openssl req -x509 -newkey rsa:2048 -sha256 -nodes -days 825 \
  -keyout "$DATA_DIR/tls.key" -out "$DATA_DIR/tls.crt" \
  -subj "/CN=$ENDPOINT" -addext "subjectAltName=IP:$ENDPOINT" 2>/dev/null
chmod 600 "$DATA_DIR/tls.key" "$DATA_DIR/tls.crt" "$DATA_DIR/password" "$DATA_DIR/totp-secret"

info 'Installing panel files'
install -d -m 755 "$PREFIX"   # udp-echo runs as DynamicUser; secrets live in $DATA_DIR
install -d -m 755 "$PREFIX/static"
install -m 600 "$REPO_DIR"/src/*.py "$PREFIX/"
chmod 644 "$PREFIX/udp_echo.py"   # read by the DynamicUser echo service
install -m 644 "$REPO_DIR"/src/static/style.css "$REPO_DIR"/src/static/app.js "$PREFIX/static/"

[[ -f $PANEL_UNIT ]] && cp -a "$PANEL_UNIT" "$DATA_DIR/pre-v14.service"
install -m 644 "$REPO_DIR/systemd/1mobile-panel.service" "$PANEL_UNIT"
systemctl daemon-reload
systemctl enable 1mobile-panel.service
systemctl restart 1mobile-panel.service

sleep 2
curl -kfsS --retry 3 --retry-connrefused --max-time 6 https://127.0.0.1:9443/ \
  | grep -q 'ورود امن' || fail 'Smoke check failed; inspect: journalctl -u 1mobile-panel -n 50'

ok "Panel ready: https://$ENDPOINT:9443/"
echo "TOTP secret (add to your authenticator now, shown once): $TOTP"
echo "Restrict TCP/9443 in your firewall to your own IP before exposing it."
