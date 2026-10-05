#!/usr/bin/env python3
"""Optional MCP bridge for the OLYMPUS shared memory.

Run this as a local stdio MCP server from Claude, ChatGPT-compatible clients
or another MCP host. The host identity is intentionally supplied by the
environment, never by model arguments, so a model cannot switch tenant/user
scope through a tool call.

Required environment:
  OLYMPUS_MEMORY_TENANT_ID
  OLYMPUS_MEMORY_USER_ID

Storage follows the normal OLYMPUS selection rules:
  OLYMPUS_MEMORY_DATABASE_URL (PostgreSQL cloud, preferred)
  OLYMPUS_MEMORY_DB (SQLite fallback)
"""

from __future__ import annotations

import os
import argparse
from pathlib import Path
from typing import Any, Optional

from olympus.memory import (
    MemoryContextProvider,
    MemoryStatus,
    MemoryType,
    Sensitivity,
    build_memory_store,
    MemoryWriter,
)

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:  # pragma: no cover - exercised by installation gate
    FastMCP = None  # type: ignore[assignment,misc]
    _MCP_IMPORT_ERROR = exc


def _required_scope(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError("%s must be configured before starting the MCP bridge" % name)
    return value


def _store():
    root = Path(__file__).resolve().parents[1]
    return build_memory_store(
        os.environ.get("OLYMPUS_MEMORY_DATABASE_URL")
        or os.environ.get("OLYMPUS_MEMORY_DB", str(root / "olympus_memory.db"))
    )


def _view(memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "type": memory.type.value,
        "key": memory.key,
        "value": memory.value,
        "sensitivity": memory.sensitivity.value,
        "status": memory.status.value,
        "project_id": memory.project_id,
        "source": memory.source,
        "created_at": memory.created_at,
        "updated_at": memory.updated_at,
    }


def create_server():
    if FastMCP is None:
        raise RuntimeError(
            "MCP bridge is optional. Install scripts/requirements-mcp.txt first: %s"
            % _MCP_IMPORT_ERROR
        )
    tenant_id = _required_scope("OLYMPUS_MEMORY_TENANT_ID")
    user_id = _required_scope("OLYMPUS_MEMORY_USER_ID")
    store = _store()
    writer = MemoryWriter(store)
    context = MemoryContextProvider(store)
    server = FastMCP("OLYMPUS Memory Core")

    @server.tool()
    def memory_search(task: str, project_id: Optional[str] = None) -> dict[str, Any]:
        """Search confirmed OLYMPUS memory relevant to a task."""
        text = context.relevant(task, tenant_id, user_id, project_id)
        return {"context": text, "has_context": bool(text), "project_id": project_id}

    @server.tool()
    def memory_save(
        memory_type: str,
        key: str,
        value: dict[str, Any],
        project_id: Optional[str] = None,
        sensitivity: str = "medium",
    ) -> dict[str, Any]:
        """Propose a memory; medium/high sensitivity is not auto-confirmed."""
        memory = writer.propose(
            tenant_id,
            user_id,
            MemoryType(memory_type),
            key,
            value,
            Sensitivity(sensitivity),
            project_id,
            "mcp",
        )
        return _view(memory)

    @server.tool()
    def memory_confirm(memory_id: str) -> dict[str, Any]:
        """Confirm a proposed memory after explicit user authorization."""
        memory = store.update(
            memory_id,
            tenant_id,
            user_id,
            status=MemoryStatus.CONFIRMED,
        )
        if memory is None:
            return {"found": False, "memory_id": memory_id}
        return {"found": True, "memory": _view(memory)}

    @server.tool()
    def memory_forget(memory_id: str) -> dict[str, Any]:
        """Delete one memory in the current user scope."""
        return {"deleted": store.delete(memory_id, tenant_id, user_id), "memory_id": memory_id}

    return server


def run_http(server, host: str, port: int) -> None:
    """Expose MCP over Streamable HTTP for hosted builders and IDEs."""
    token = _required_scope("OLYMPUS_MCP_BEARER_TOKEN")
    try:
        import uvicorn
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.responses import JSONResponse
    except ImportError as exc:
        raise RuntimeError("Install backend requirements plus uvicorn for HTTP MCP") from exc

    app = server.streamable_http_app()

    class BearerMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request, call_next):
            authorization = request.headers.get("authorization", "")
            if authorization != "Bearer " + token:
                return JSONResponse({"detail": "unauthorized"}, status_code=401)
            return await call_next(request)

    app.add_middleware(BearerMiddleware)
    uvicorn.run(app, host=host, port=port, log_level="warning")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OLYMPUS Memory Core MCP bridge")
    parser.add_argument("--transport", choices=("stdio", "streamable-http"), default=os.environ.get("OLYMPUS_MCP_TRANSPORT", "stdio"))
    parser.add_argument("--host", default=os.environ.get("OLYMPUS_MCP_HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("OLYMPUS_MCP_PORT", "8787")))
    args = parser.parse_args()
    server = create_server()
    if args.transport == "stdio":
        server.run(transport="stdio")
    else:
        run_http(server, args.host, args.port)
