from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
import webbrowser
from typing import Optional

import uvicorn

from beautycat import __version__
from beautycat.server import AppConfig, create_app


def _parse_args(argv: Optional[list[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="beautycat",
        description="A beautiful web UI for adb logcat.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8099, help="Port to bind (default: 8099)")
    parser.add_argument(
        "--buffer-size",
        type=int,
        default=10_000,
        help="Max log records kept in memory per device (default: 10000)",
    )
    parser.add_argument("--adb-path", default=None, help="Override path to adb binary")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Do not open the system browser on start",
    )
    parser.add_argument(
        "--log-level",
        default="warning",
        choices=["critical", "error", "warning", "info", "debug"],
        help="Server log level (default: warning)",
    )
    parser.add_argument("--version", action="version", version=f"beautycat {__version__}")
    return parser.parse_args(argv)


def _open_browser(url: str) -> None:
    def _open() -> None:
        time.sleep(0.6)
        try:
            webbrowser.open(url)
        except Exception:
            pass

    threading.Thread(target=_open, daemon=True).start()


def main(argv: Optional[list[str]] = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(level=args.log_level.upper())

    config = AppConfig(adb_path=args.adb_path, buffer_size=args.buffer_size)
    app = create_app(config)

    url = f"http://{args.host}:{args.port}"
    print(f"BeautyCat {__version__} listening on {url}", file=sys.stderr)
    print("Press Ctrl+C to quit.", file=sys.stderr)
    if not args.no_browser:
        _open_browser(url)

    # uvicorn handles SIGINT/SIGTERM itself: first press triggers graceful
    # shutdown, second press forces exit. We cap timeout_graceful_shutdown
    # so a single Ctrl+C ends the process promptly even with live websockets
    # and adb logcat subprocesses attached.
    uvicorn_config = uvicorn.Config(
        app,
        host=args.host,
        port=args.port,
        log_level=args.log_level,
        timeout_graceful_shutdown=2,
    )
    server = uvicorn.Server(uvicorn_config)

    try:
        server.run()
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
