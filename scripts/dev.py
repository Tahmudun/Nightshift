#!/usr/bin/env python3
"""Run the API, the ARQ worker, and the Next.js dev server together.

This exists instead of a JS `concurrently` dependency because the process group
spans two toolchains, and because the shutdown behaviour matters: Ctrl-C must
terminate all three children and not leave an orphaned uvicorn holding port 8000
or a worker holding a Redis connection. That is fiddly enough to be worth real
code and boring enough to keep in one file.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_DIR = ROOT / "services" / "api"
WEB_DIR = ROOT / "apps" / "web"
VENV_BIN = API_DIR / ".venv" / "bin"

# ANSI colours so three interleaved log streams stay readable.
COLOURS = {"api": "\033[36m", "worker": "\033[35m", "web": "\033[32m"}
RESET = "\033[0m"
DIM = "\033[2m"


class Service:
    def __init__(self, name: str, argv: list[str], cwd: Path) -> None:
        self.name = name
        self.argv = argv
        self.cwd = cwd
        self.proc: subprocess.Popen[str] | None = None

    def start(self) -> None:
        self.proc = subprocess.Popen(
            self.argv,
            cwd=self.cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            # Own process group, so we can signal the whole tree. Next.js spawns
            # children; killing only the parent leaves them running.
            start_new_session=True,
            env=os.environ.copy(),
        )
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self) -> None:
        assert self.proc is not None and self.proc.stdout is not None
        prefix = f"{COLOURS.get(self.name, '')}{self.name:>6}{RESET} {DIM}|{RESET} "
        for line in self.proc.stdout:
            sys.stdout.write(prefix + line)
            sys.stdout.flush()

    def stop(self) -> None:
        if self.proc is None or self.proc.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(self.proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            return
        try:
            self.proc.wait(timeout=8)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
            except ProcessLookupError:
                pass


def main() -> int:
    if not VENV_BIN.exists():
        print("no virtualenv — run `make setup` first", file=sys.stderr)
        return 1

    api_host = os.environ.get("API_HOST", "127.0.0.1")
    api_port = os.environ.get("API_PORT", "8000")

    services = [
        Service(
            "api",
            [
                str(VENV_BIN / "uvicorn"),
                "citysignal.api.main:app",
                "--host",
                api_host,
                "--port",
                api_port,
                "--reload",
                "--reload-dir",
                "citysignal",
                "--no-access-log",
            ],
            API_DIR,
        ),
        Service(
            "worker",
            [str(VENV_BIN / "arq"), "citysignal.workers.main.WorkerSettings", "--watch", "citysignal"],
            API_DIR,
        ),
        Service("web", ["npm", "run", "dev"], WEB_DIR),
    ]

    stopping = threading.Event()

    def shutdown(*_: object) -> None:
        if stopping.is_set():
            return
        stopping.set()
        print(f"\n{DIM}shutting down…{RESET}")
        for service in reversed(services):
            service.stop()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    for service in services:
        service.start()

    print(f"\n  api  {DIM}→{RESET} http://{api_host}:{api_port}/docs")
    print(f"  web  {DIM}→{RESET} http://localhost:3000")
    print(f"\n{DIM}ctrl-c to stop all three{RESET}\n")

    exit_code = 0
    try:
        # If any one service dies, bring the rest down rather than leaving a
        # half-running stack that looks fine in the browser.
        while not stopping.is_set():
            for service in services:
                assert service.proc is not None
                code = service.proc.poll()
                if code is not None:
                    print(f"\n{DIM}{service.name} exited with {code}{RESET}")
                    exit_code = code or 1
                    shutdown()
                    break
            time.sleep(0.4)
    except KeyboardInterrupt:
        shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
