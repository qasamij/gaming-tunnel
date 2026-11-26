"""Tiny UDP echo responder for accurate tunnel RTT / jitter measurements.

Run on the exit server. It only echoes the first 8 bytes (a monotonic token),
so no clock synchronisation between servers is needed.
"""

from __future__ import annotations

import os
import socket
import sys
import time

HOST = os.getenv("ECHO_HOST", "0.0.0.0")
PORT = int(os.getenv("ECHO_PORT", "5355"))


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))
    print("udp-echo listening on {}:{}".format(HOST, PORT), flush=True)
    while True:
        try:
            data, addr = sock.recvfrom(256)
            if len(data) >= 8:
                sock.sendto(data[:8], addr)
        except KeyboardInterrupt:
            break
        except Exception as exc:
            print("udp-echo:", type(exc).__name__, flush=True)
            time.sleep(0.1)
    sock.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
