#!/bin/bash
# Debian/Ubuntu dependencies. Set INSTALL_AWG=1 to build AmneziaWG from the
# official upstream repositories; otherwise only distro packages are installed.
set -euo pipefail
source "$(dirname "$0")/common.sh"
need_root

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends \
  python3 openssl curl iproute2 iptables qrencode ca-certificates git \
  build-essential make pkg-config golang-go

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
  echo "[warn] awg/amneziawg-go not installed automatically."
  echo "       Re-run with INSTALL_AWG=1, or install them from:"
  echo "       https://github.com/amnezia-vpn/amneziawg-tools"
  echo "       https://github.com/amnezia-vpn/amneziawg-go"
fi

command -v awg >/dev/null && command -v amneziawg-go >/dev/null && \
  ok "AmneziaWG tools ready" || echo "[warn] Complete the AWG install before running 'fresh'."
