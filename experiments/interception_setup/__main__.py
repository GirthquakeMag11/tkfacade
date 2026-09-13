"""CLI entry point. Parsing only -- all behaviour lives in ``flow``.

Exit codes:
    0  success
    1  failed
    2  restart required
    3  UAC declined
    4  not Windows
"""

import argparse
import sys

from . import flow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="tkfacade-interception",
        description="Install and verify the Interception input driver.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("install", help="install the driver (requires admin)")
    sub.add_parser("verify", help="post-restart reachability check")
    sub.add_parser("status", help="report recorded and live driver state")

    remove = sub.add_parser("uninstall", help="remove the driver (requires admin)")
    remove.add_argument(
        "--force",
        action="store_true",
        help="remove even if the driver was present before we installed",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    match args.command:
        case "install":
            return flow.run_install()
        case "verify":
            return flow.run_verify()
        case "uninstall":
            return flow.run_uninstall(force=args.force)
        case "status":
            return flow.run_status()
        case _:
            return flow.EXIT_FAILED


if __name__ == "__main__":
    sys.exit(main())
