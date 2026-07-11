from __future__ import annotations

import os
import signal
import subprocess
import sys
import time


def main() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True)
    port = os.getenv("PORT", "7860")
    children = [
        subprocess.Popen([sys.executable, "-m", "app.workers.runner"]),
        subprocess.Popen(
            [
                sys.executable,
                "-m",
                "uvicorn",
                "app.main:app",
                "--host",
                "0.0.0.0",
                "--port",
                port,
            ]
        ),
    ]

    def stop_children(signum: int, frame: object) -> None:
        del signum, frame
        for child in children:
            if child.poll() is None:
                child.terminate()

    signal.signal(signal.SIGTERM, stop_children)
    signal.signal(signal.SIGINT, stop_children)
    try:
        while all(child.poll() is None for child in children):
            time.sleep(0.2)
    finally:
        stop_children(0, None)
        for child in children:
            try:
                child.wait(timeout=10)
            except subprocess.TimeoutExpired:
                child.kill()
        failed = next((child.returncode for child in children if child.returncode), 0)
    raise SystemExit(failed)


if __name__ == "__main__":
    main()
