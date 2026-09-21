from __future__ import annotations

import socket
import sys
import time


def wait_for_listener(host: str, port: int, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: OSError | None = None
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.25):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(0.1)
    detail = type(last_error).__name__ if last_error else "unknown error"
    raise TimeoutError(f"listener {host}:{port} was not ready within {timeout_seconds}s ({detail})")


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit("usage: wait_for_listener.py HOST PORT TIMEOUT_SECONDS")
    wait_for_listener(sys.argv[1], int(sys.argv[2]), float(sys.argv[3]))


if __name__ == "__main__":
    main()
