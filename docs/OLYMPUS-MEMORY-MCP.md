# OLYMPUS Memory Core via MCP

The bridge exposes the same shared memory used by missions through MCP. It is
optional and does not change the normal OLYMPUS runtime.

Install the optional dependency:

```bash
python3 -m pip install -r scripts/requirements-mcp.txt
```

Configure the identity scope without placing credentials in prompts:

```bash
export OLYMPUS_MEMORY_TENANT_ID="tenant-id"
export OLYMPUS_MEMORY_USER_ID="user-id"
export OLYMPUS_MEMORY_DATABASE_URL="postgresql://..."
```

The MCP host can launch `scripts/memory_mcp_server.py` over stdio. Available
tools are `memory_search`, `memory_save`, `memory_confirm` and
`memory_forget`.

## Hosted builders and IDEs

For Base44, Lovable, a remote Cursor environment or another MCP host that
requires a URL, use Streamable HTTP behind HTTPS and a reverse proxy:

```bash
export OLYMPUS_MCP_TRANSPORT=streamable-http
export OLYMPUS_MCP_HOST=127.0.0.1
export OLYMPUS_MCP_PORT=8787
export OLYMPUS_MCP_BEARER_TOKEN="use-a-long-random-token"
python3 scripts/memory_mcp_server.py
```

Publish only the HTTPS reverse-proxy URL, for example
`https://memory.example.com/mcp`, and send the token as an `Authorization:
Bearer ...` header. Do not expose port 8787 directly to the internet.

Only confirmed memories are returned by search. New medium/high-sensitivity
memories remain proposed until explicitly confirmed.
