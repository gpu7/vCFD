# Wire vCFD to Grok Voice Agent Builder

No-code path: [Voice Agent Builder](https://x.ai/news/grok-voice-agent-builder) (beta) on Grok Voice.  
Code path: Speech-to-Speech WebSocket (`wss://api.x.ai/v1/realtime`) with remote MCP — see `voice/session.example.json` and `scripts/voice_session_snippet.py`.

## Prerequisites

1. **Public MCP URL** (HTTPS preferred). After EC2 launch:
   - `http://PUBLIC_IP/mcp` works for many tests
   - Voice clients often require **HTTPS** — use a domain with Caddy (`./deploy/aws/launch-ec2.sh --domain …`) or a tunnel
2. **Bearer token** from `deploy/aws/out/latest.token` (or launch output)
3. xAI account with Voice / Agent Builder access

## Voice Agent Builder (console) steps

1. Open Voice Agent Builder in the xAI / Grok Voice console.
2. Create agent **vCFD**.
3. Paste system instructions from `prompts/voice_agent_system.md` (body only, no markdown title required).
4. Add **Remote MCP** tool / connector:
   - **Server URL:** `https://YOUR_HOST/mcp` (or `http://IP/mcp` if allowed)
   - **Server label:** `vcfd`
   - **Authorization:** `Bearer YOUR_VCFD_AUTH_TOKEN`
   - **Description (optional):** OpenFOAM CFD case control for laminar pipe flow
5. Voice: e.g. `eve` or `leo`.
6. Guardrails (optional): block unrelated topics; keep focus on CFD.
7. Save and **Test** in the builder playground, or attach a phone number (SIP) if offered.

### What to say in the test call

- “List my CFD templates.”
- “Create a Hagen–Poiseuille pipe case called voice_pipe.”
- “Set default pipe parameters and generate the mesh.”
- “Start the solver and tell me when it finishes.”
- “Compare the results to the analytical solution.”

## Speech-to-Speech API (code) equivalent

```json
{
  "type": "session.update",
  "session": {
    "voice": "eve",
    "instructions": "<paste voice_agent_system.md>",
    "turn_detection": { "type": "server_vad" },
    "tools": [
      {
        "type": "mcp",
        "server_url": "https://YOUR_HOST/mcp",
        "server_label": "vcfd",
        "server_description": "OpenFOAM CFD via vCFD MCP",
        "authorization": "Bearer YOUR_VCFD_AUTH_TOKEN"
      }
    ]
  }
}
```

Full example files:

- `voice/session.example.json`
- `scripts/voice_session_snippet.py` (prints a ready-to-paste session.update; optional live WebSocket if `XAI_API_KEY` is set)

## After EC2 relaunch

```bash
./deploy/aws/launch-ec2.sh
source deploy/aws/out/latest.env
echo "URL:  $MCP_URL_HTTP"
echo "Token: $VCFD_AUTH_TOKEN"
```

Copy those into the Builder MCP fields.

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Builder cannot reach MCP | Instance running? SG 80/443 open? Correct `/mcp` path? |
| Unauthorized | Exact `Bearer <token>` matching `/etc/vcfd/vcfd.env` on the host |
| HTTPS required | Launch with `--domain` + DNS, or Cloudflare Tunnel / ngrok to port 80 |
| Tools not called | Improve system prompt; confirm MCP tools list in doctor/playground |
| Long silence during solve | Agent should start job async and poll — already in system prompt |

## Docs

- [Speech to Speech](https://docs.x.ai/developers/model-capabilities/audio/speech-to-speech)
- [Remote MCP tools](https://docs.x.ai/developers/tools/remote-mcp) (if linked from voice docs)
- [Voice Agent Builder announcement](https://x.ai/news/grok-voice-agent-builder)
