from __future__ import annotations

import os
import signal
import sys
import threading
from pathlib import Path

PID_FILE = Path("/tmp/ai-cto-cockpit-worker.pid")


def _healthy() -> bool:
    try:
        pid = int(PID_FILE.read_text(encoding="utf-8").strip())
        os.kill(pid, 0)
    except (OSError, ValueError):
        return False
    return True


def _run() -> None:
    stopped = threading.Event()

    def stop(_signum: int, _frame: object) -> None:
        stopped.set()

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    try:
        stopped.wait()
    finally:
        PID_FILE.unlink(missing_ok=True)


def main() -> int:
    if sys.argv[1:] == ["--healthcheck"]:
        return 0 if _healthy() else 1
    if sys.argv[1:]:
        return 2
    _run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
