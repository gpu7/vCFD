#!/usr/bin/env python3
"""Print a Speech-to-Speech session.update JSON for vCFD remote MCP.

Usage:
  python scripts/voice_session_snippet.py
  python scripts/voice_session_snippet.py --url http://IP/mcp --token "$(cat deploy/aws/out/latest.token)"

Optional live WebSocket smoke (needs XAI_API_KEY):
  python scripts/voice_session_snippet.py --live --url http://IP/mcp --token ...
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPT_PATH = ROOT / "prompts" / "voice_agent_system.md"


def load_instructions() -> str:
    text = PROMPT_PATH.read_text(encoding="utf-8")
    # Strip markdown title lines for a cleaner system prompt
    lines = [ln for ln in text.splitlines() if not ln.startswith("#")]
    return "\n".join(lines).strip()


def build_session(url: str, token: str, voice: str = "eve") -> dict:
    auth = token if token.lower().startswith("bearer ") else f"Bearer {token}"
    return {
        "type": "session.update",
        "session": {
            "voice": voice,
            "instructions": load_instructions(),
            "turn_detection": {
                "type": "server_vad",
                "threshold": 0.85,
                "silence_duration_ms": 700,
            },
            "audio": {
                "input": {
                    "format": {"type": "audio/pcm", "rate": 24000},
                    "transcription": {
                        "keyterms": [
                            "OpenFOAM",
                            "Hagen-Poiseuille",
                            "blockMesh",
                            "simpleFoam",
                            "ParaView",
                            "vCFD",
                        ]
                    },
                },
                "output": {"format": {"type": "audio/pcm", "rate": 24000}},
            },
            "tools": [
                {
                    "type": "mcp",
                    "server_url": url,
                    "server_label": "vcfd",
                    "server_description": "OpenFOAM CFD via vCFD MCP",
                    "authorization": auth,
                }
            ],
        },
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--url", default=os.environ.get("VCFD_MCP_URL", "https://YOUR_HOST/mcp"))
    p.add_argument("--token", default=os.environ.get("VCFD_AUTH_TOKEN", "YOUR_VCFD_AUTH_TOKEN"))
    p.add_argument("--voice", default="eve")
    p.add_argument(
        "--from-latest",
        action="store_true",
        help="Read URL/token from deploy/aws/out/latest.env if present",
    )
    p.add_argument(
        "--live",
        action="store_true",
        help="Open realtime WebSocket and send session.update (needs XAI_API_KEY)",
    )
    args = p.parse_args()

    url, token = args.url, args.token
    if args.from_latest:
        env_path = ROOT / "deploy" / "aws" / "out" / "latest.env"
        if env_path.is_file():
            data = {}
            for line in env_path.read_text(encoding="utf-8").splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    data[k.strip()] = v.strip()
            url = data.get("MCP_URL_HTTP") or data.get("MCP_URL_HTTPS") or url
            token = data.get("VCFD_AUTH_TOKEN") or token
            print(f"# loaded from {env_path}", file=sys.stderr)
        else:
            print(f"# no {env_path}; using defaults", file=sys.stderr)

    session = build_session(url, token, voice=args.voice)
    print(json.dumps(session, indent=2))

    if not args.live:
        print(
            "\n# Voice Agent Builder: paste instructions + MCP URL/token from above.",
            file=sys.stderr,
        )
        print("# Code path: send this JSON as the first message on wss://api.x.ai/v1/realtime", file=sys.stderr)
        return 0

    api_key = os.environ.get("XAI_API_KEY")
    if not api_key:
        print("XAI_API_KEY not set; cannot --live", file=sys.stderr)
        return 1

    try:
        import asyncio

        import websockets
    except ImportError:
        print("Install websockets: uv add websockets", file=sys.stderr)
        return 1

    async def run() -> None:
        uri = "wss://api.x.ai/v1/realtime?model=grok-voice-latest"
        async with websockets.connect(
            uri,
            additional_headers={"Authorization": f"Bearer {api_key}"},
        ) as ws:
            await ws.send(json.dumps(session))
            print("sent session.update", file=sys.stderr)
            # Wait for a few server events
            for _ in range(10):
                raw = await asyncio.wait_for(ws.recv(), timeout=30)
                event = json.loads(raw)
                et = event.get("type")
                print(f"event: {et}", file=sys.stderr)
                if et in {"session.updated", "error"}:
                    print(json.dumps(event, indent=2)[:2000])
                    if et == "error":
                        return
                    break

    asyncio.run(run())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
