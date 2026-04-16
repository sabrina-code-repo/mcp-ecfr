# Deploying the eCFR MCP Server to Hugging Face Spaces

This document explains how we took the existing FastMCP server and deployed it as a public MCP connector on Hugging Face Spaces using Gradio.

## Background

The original eCFR MCP server (`src/server.py`) uses Anthropic's FastMCP framework and runs locally via `mcp run src/server.py`. For the REACH summit, we needed a publicly hosted version that anyone could connect to from Claude — no local installation required.

**Hugging Face Spaces** provides free hosting for Gradio apps, and Gradio has built-in MCP server support. This means we can wrap our existing tools as Gradio API endpoints and get a public MCP endpoint automatically.

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Hugging Face Space (n8layman/ecfr-mcp-server)       │
│                                                      │
│  app.py (Gradio)                                     │
│    ├─ Thin wrapper functions (str params → native)   │
│    ├─ gr.api() registers each as MCP tool            │
│    └─ demo.launch(mcp_server=True)                   │
│         │                                            │
│         ▼                                            │
│  src/server.py (FastMCP — imported, not run)          │
│    ├─ ecfr_search, ecfr_get_regulation, etc.         │
│    ├─ httpx async client → eCFR API                  │
│    └─ XML parsing, response formatting               │
│                                                      │
│  MCP endpoint: /gradio_api/mcp/sse                   │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌──────────────────┐
│  ecfr.gov API    │
│  (live federal   │
│   regulations)   │
└──────────────────┘
```

## What Was Created

### 1. `src/__init__.py` (empty file)

Makes the `src/` directory a Python package so `app.py` at the project root can do `from src.server import ...`.

### 2. `app.py` (Gradio MCP wrapper)

This is the main file that Hugging Face Spaces runs. It does three things:

**a) Imports the existing tool functions from `src/server.py`**

The `@mcp.tool()` decorators in `server.py` register functions with the FastMCP instance, but the functions themselves remain normal Python callables. Since we never call `mcp.run()`, the FastMCP instance is inert — we just call the functions directly.

```python
from src.server import (
    ecfr_search as _ecfr_search,
    ecfr_get_regulation as _ecfr_get_regulation,
    # ... etc
)
```

**b) Creates wrapper functions with string-typed parameters**

Gradio's MCP schema generation reads function type hints and docstrings. The Gradio MCP docs recommend accepting all parameters as `str` to avoid issues with how different MCP clients handle `None`, `Optional`, and complex types.

Each wrapper:
- Accepts `str` parameters with `""` defaults for optional ones
- Has a docstring with `Args:` block (Gradio reads this for MCP schema)
- Converts types using helpers (`""` → `None`, `"true"` → `True`, `"5"` → `5`)
- Calls the underlying server function with native Python types

```python
async def ecfr_search(
    query: str,
    per_page: str = "5",
    agency_slugs: str = "",
) -> str:
    """Full-text search across the entire Code of Federal Regulations.

    Args:
        query: Search term. Examples: 'indirect costs'.
        per_page: Results per page, 1-25. Default '5'.
        agency_slugs: Comma-separated agency slugs. Leave empty for all.
    """
    return await _ecfr_search(
        query=query,
        per_page=int(per_page) if per_page else 5,
        agency_slugs=agency_slugs.split(",") if agency_slugs.strip() else None,
    )
```

**c) Registers tools with `gr.api()` and launches**

`gr.api()` exposes functions as API-only endpoints (no web UI form needed). With `mcp_server=True`, Gradio automatically creates the MCP SSE endpoint.

```python
with gr.Blocks(title="eCFR MCP Server") as demo:
    gr.Markdown("# eCFR MCP Server ...")  # Landing page
    gr.api(ecfr_search, api_name="ecfr_search")
    # ... 7 more tools

demo.launch(mcp_server=True)
```

**d) Exposes the regulatory index as a tool**

The original server has a `@mcp.resource("ecfr://regulatory-index")` that provides Claude with workflow guidance, starter citations, and agency slugs. Gradio MCP only supports tools (not resources), so we expose it as an 8th tool called `ecfr_regulatory_index`. This gives Claude the correct tool call patterns.

### 3. `requirements.txt` (for HF Spaces)

Minimal dependencies — HF Spaces auto-installs Gradio, so we only need:

```
httpx
mcp
pydantic
```

**Important:** The original `requirements.txt` had UTF-16 encoding with spaces between characters, which caused pip to fail during the HF build. We replaced it with clean ASCII.

### 4. `README.md` (with HF Space metadata)

HF Spaces reads YAML frontmatter from `README.md` to configure the Space:

```yaml
---
title: eCFR MCP Server
emoji: 📜
sdk: gradio
app_file: app.py
license: mit
tags:
  - mcp-server-track    # enables the MCP badge on HF
---
```

## How We Deployed

### Step 1: Created the HF Space

Went to https://huggingface.co/new-space and created `n8layman/ecfr-mcp-server` with:
- SDK: Gradio
- Hardware: Free CPU Basic
- Visibility: Public
- License: MIT

### Step 2: Set up authentication

```bash
# Install HF CLI
uv pip install huggingface_hub[cli]

# Login (the CLI is now `hf`, not `huggingface-cli`)
venv/bin/hf auth login --token <HF_TOKEN>
```

Created a fine-grained access token at https://huggingface.co/settings/tokens with write access to repos.

### Step 3: Uploaded files

```bash
venv/bin/hf upload n8layman/ecfr-mcp-server . . \
    --repo-type=space \
    --exclude="venv/*" \
    --exclude=".git/*" \
    --exclude="test_outputs/*" \
    --exclude=".env"
```

This uploads all project files (excluding dev artifacts) to the Space. HF automatically builds and deploys.

### Step 4: Verified the deployment

- Space URL: https://huggingface.co/spaces/n8layman/ecfr-mcp-server
- MCP schema: `https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/schema`
- MCP endpoint: `https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/sse`

## How Claude Connects

1. In Claude: Settings > Connectors > Add custom connector
2. URL: `https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/sse`
3. Set all tools to "Always allow"

Tools appear in Claude with an `ecfr_mcp_server_` prefix (e.g., `ecfr_mcp_server_ecfr_search`). This prefix comes from the Space name and is added by Gradio automatically.

## Key Design Decisions

### Why Gradio instead of deploying FastMCP directly?

FastMCP uses stdio transport — it's designed for local use where the MCP client spawns the server as a subprocess. There's no built-in way to host it as an HTTP endpoint. Gradio provides:
- HTTP-based MCP transport (SSE) out of the box
- Free hosting on HF Spaces
- Automatic MCP discovery for Claude connectors

### Why thin wrappers instead of refactoring server.py?

We wanted `server.py` to remain untouched so it still works as a standalone FastMCP server for local use (`mcp run src/server.py`). The wrappers only handle type conversion — all business logic stays in `server.py`.

### Why string parameters?

Gradio's MCP schema generation works best with `str` types. Different MCP clients handle `Optional`, `None`, `int`, `bool`, and `List` differently. Using strings with conversion avoids compatibility issues.

### Why expose regulatory_index as a tool?

Gradio MCP only supports tools, not MCP resources. The regulatory index contains critical workflow guidance that tells Claude the correct order to call tools (e.g., always call `get_title_versions` before `get_regulation`). Without it, Claude follows a less efficient pattern.

## Updating the Deployment

After making changes locally:

```bash
# Push to GitHub
git push origin feature/hugging-face-connector-deployment

# Deploy to HF Space
venv/bin/hf upload n8layman/ecfr-mcp-server . . \
    --repo-type=space \
    --exclude="venv/*" \
    --exclude=".git/*" \
    --exclude="test_outputs/*" \
    --exclude=".env"
```

The Space rebuilds automatically after each upload (~1-2 minutes).

## Files Overview

| File | Purpose |
|------|---------|
| `app.py` | Gradio MCP wrapper — entry point for HF Spaces |
| `src/server.py` | Original FastMCP server with all tool logic (unchanged) |
| `src/__init__.py` | Makes `src/` importable as a package |
| `requirements.txt` | Minimal deps for HF Spaces (httpx, mcp, pydantic) |
| `README.md` | HF Space metadata + project docs |
| `CONNECTING_TO_CLAUDE.md` | User guide for connecting the MCP server to Claude |
| `.env` | HF token (gitignored, not deployed) |
| `requirements-hf.txt` | Backup of the HF-specific requirements |
