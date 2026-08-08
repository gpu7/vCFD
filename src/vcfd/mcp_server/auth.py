"""Optional bearer-token gate for HTTP MCP access."""

from __future__ import annotations

from typing import Any

from fastmcp.server.dependencies import get_http_headers
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext


class BearerTokenMiddleware(Middleware):
    """Require Authorization: Bearer <token> when a token is configured.

    Stdio transport has no HTTP headers — checks are skipped (local trusted use).
    When VCFD_AUTH_TOKEN is unset/empty, auth is disabled (dev convenience).
    """

    def __init__(self, token: str | None) -> None:
        self.token = (token or "").strip() or None

    async def on_message(
        self, context: MiddlewareContext[Any], call_next: CallNext[Any, Any]
    ) -> Any:
        if not self.token:
            return await call_next(context)

        headers = get_http_headers(include_all=True)
        if not headers:
            # stdio / no HTTP request context
            return await call_next(context)

        auth = headers.get("authorization") or headers.get("Authorization") or ""
        expected = f"Bearer {self.token}"
        if auth.strip() != expected:
            raise PermissionError(
                "Unauthorized: provide Authorization: Bearer <VCFD_AUTH_TOKEN> header."
            )
        return await call_next(context)
