# vCFD Architecture

## Layers

1. **Voice** — Grok Speech-to-Speech or Voice Agent Builder.
2. **MCP** — FastMCP tools with speakable `summary` + structured `data`.
3. **Job manager** — Async process supervision for mesh/solver.
4. **Foam runner** — mock / docker / native OpenFOAM invocation.
5. **Cases workspace** — isolated directory tree under `VCFD_CASES_ROOT`.
6. **Visualization** — export to VTK/zip for ParaView on the client machine.

## Tool result contract

Every tool returns:

```json
{
  "summary": "Speakable sentence.",
  "success": true,
  "job_id": null,
  "data": {},
  "warnings": []
}
```

## Safety

- Case names validated; paths jailing under cases root.
- Destructive tools require `confirm=true`.
- Concurrent job limit (`VCFD_MAX_CONCURRENT_JOBS`).
- Optional bearer token for HTTP transport.
