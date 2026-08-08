"""Command-line entry points for vCFD."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="vcfd",
        description="vCFD — Voice CFD via MCP + OpenFOAM + ParaView",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="Run the MCP server")
    serve.add_argument(
        "--transport",
        choices=["stdio", "http", "sse", "streamable-http"],
        default="stdio",
        help="MCP transport (default: stdio)",
    )
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    sub.add_parser("version", help="Print version")

    args = parser.parse_args(argv)
    if args.command == "version" or args.command is None and len(sys.argv) == 1:
        from vcfd import __version__

        print(f"vcfd {__version__}")
        if args.command is None:
            parser.print_help()
        return

    if args.command == "serve":
        import os

        from vcfd.mcp_server.server import main as serve_main

        if args.transport:
            os.environ["VCFD_TRANSPORT"] = (
                "http" if args.transport == "streamable-http" else args.transport
            )
        if args.host:
            os.environ["VCFD_HOST"] = args.host
        if args.port:
            os.environ["VCFD_PORT"] = str(args.port)
        serve_main()
        return

    parser.print_help()
