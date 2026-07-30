#!/usr/bin/env python3
"""Check that the host has what the repo needs, and say so precisely.

`make setup` failing with a linker error six layers deep in a pip build is a bad
first experience for a clean clone. This runs first and names the missing thing.
"""

from __future__ import annotations

import shutil
import subprocess
import sys

MIN_PYTHON = (3, 12)
MIN_NODE = 20


def ok(msg: str) -> None:
    print(f"  \033[32m✓\033[0m {msg}")


def bad(msg: str, fix: str) -> None:
    print(f"  \033[31m✗\033[0m {msg}\n      \033[2mfix:\033[0m {fix}")


def version_of(argv: list[str]) -> str:
    try:
        out = subprocess.run(argv, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return (out.stdout + out.stderr).strip().splitlines()[0] if (out.stdout or out.stderr) else ""


def main() -> int:
    print("\nnightshift doctor\n")
    failures = 0

    if sys.version_info[:2] >= MIN_PYTHON:
        ok(f"python {sys.version_info.major}.{sys.version_info.minor}")
    else:
        failures += 1
        bad(
            f"python {sys.version_info.major}.{sys.version_info.minor} (need >= 3.12)",
            "brew install python@3.12, then `make setup PYTHON=python3.12`",
        )

    node = shutil.which("node")
    if node:
        raw = version_of([node, "--version"]).lstrip("v")
        major = int(raw.split(".")[0]) if raw and raw.split(".")[0].isdigit() else 0
        if major >= MIN_NODE:
            ok(f"node {raw}")
        else:
            failures += 1
            bad(f"node {raw} (need >= {MIN_NODE})", "brew install node")
    else:
        failures += 1
        bad("node not found", "brew install node")

    if shutil.which("npm"):
        ok(f"npm {version_of(['npm', '--version'])}")
    else:
        failures += 1
        bad("npm not found", "ships with node — brew install node")

    docker = shutil.which("docker")
    if not docker:
        failures += 1
        bad(
            "no container runtime (docker not on PATH)",
            "brew install --cask orbstack   (or Docker Desktop), then `make up`",
        )
    elif not version_of([docker, "compose", "version"]):
        failures += 1
        bad("docker present but `docker compose` unavailable", "install Compose v2, or upgrade Docker")
    else:
        probe = subprocess.run([docker, "info"], capture_output=True, text=True)
        if probe.returncode == 0:
            ok(f"docker — {version_of([docker, 'compose', 'version'])}")
        else:
            failures += 1
            bad("docker installed but the daemon is not running", "start OrbStack / Docker Desktop")

    print()
    if failures:
        print(f"\033[31m{failures} problem(s) to fix before `make demo` will work.\033[0m\n")
        return 1
    print("\033[32mall good — run `make demo`\033[0m\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
