#!/bin/bash
# Debian/Ubuntu dependencies. Set INSTALL_AWG=1 to build AmneziaWG from the
# official upstream repositories; otherwise only distro packages are installed.
# Detection is *functional*: a binary named `wg` is accepted only if it really
# accepts AmneziaWG obfuscation keys, and is exposed as `/usr/local/bin/awg`.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 openssl curl iproute2 iptables qrencode ca-certificates git \
  build-essential make pkg-config golang-go

export PYTHONPATH="$REPO_DIR/src${PYTHONPATH:+:$PYTHONPATH}"

if python3 "$REPO_DIR/src/awgdetect.py" --quiet; then
  info 'AmneziaWG CLI already installed and functional; skipping rebuild'
else
  info 'No functional AmneziaWG CLI found'
  if [[ ${INSTALL_AWG:-0} == 1 ]]; then
    info 'Building amneziawg-tools'
    [[ -d /usr/local/src/amneziawg-tools ]] || \
      git clone --depth 1 https://github.com/amnezia-vpn/amneziawg-tools.git /usr/local/src/amneziawg-tools
    make -C /usr/local/src/amneziawg-tools/src -j"$(nproc)"
    make -C /usr/local/src/amneziawg-tools/src install

    info 'Building amneziawg-go'
    [[ -d /usr/local/src/amneziawg-go ]] || \
      git clone --depth 1 https://github.com/amnezia-vpn/amneziawg-go.git /usr/local/src/amneziawg-go
    make -C /usr/local/src/amneziawg-go
    install -m 755 /usr/local/src/amneziawg-go/amneziawg-go /usr/local/bin/amneziawg-go
  else
    echo '[warn] Set INSTALL_AWG=1 to build AmneziaWG, or install it manually from:'
    echo '       https://github.com/amnezia-vpn/amneziawg-tools'
    echo '       https://github.com/amnezia-vpn/amneziawg-go'
  fi
fi

# Final gate: check the *behaviour* of the tool, not merely the filename, and
# make `awg` available even when upstream installed it as `wg`.
info 'Testing AmneziaWG engine (obfuscated config on a throwaway interface)'
python3 "$REPO_DIR/src/awgdetect.py" --link || \
  fail 'AmneziaWG is not functional. Re-run with INSTALL_AWG=1 or fix the manual install.'

[[ -x /usr/local/bin/amneziawg-go ]] || command -v amneziawg-go >/dev/null 2>&1 || \
  fail 'amneziawg-go userspace engine is missing; install it before running fresh.'

ok "AmneziaWG tools verified: awg -> $(readlink -f /usr/local/bin/awg 2>/dev/null || command -v awg)"
