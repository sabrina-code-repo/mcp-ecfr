---
title: eCFR MCP Server
emoji: 📜
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: Federal regulations via MCP from the eCFR API
tags:
  - mcp-server-track
---

# eCFR MCP Server

Access the Electronic Code of Federal Regulations through MCP tools.
Built for research administrators, compliance officers, and policy analysts.

## Connect to Claude

1. Go to [claude.ai](https://claude.ai) > **Settings** > **Connectors**
2. Click **Add custom connector**
3. Paste the MCP endpoint URL:
   ```
   https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/sse
   ```
4. Set all 7 tools to **Always allow**
5. Open a new conversation and ask about federal regulations

See [CONNECTING_TO_CLAUDE.md](CONNECTING_TO_CLAUDE.md) for detailed instructions.

## Available Tools

| Tool in Claude | Description |
|------|-------------|
| `ecfr_mcp_server_ecfr_search` | Full-text search across all CFR titles |
| `ecfr_mcp_server_ecfr_list_titles` | List all 50 CFR titles |
| `ecfr_mcp_server_ecfr_list_agencies` | List federal agencies with CFR references |
| `ecfr_mcp_server_ecfr_get_title_versions` | Get amendment history for a CFR title |
| `ecfr_mcp_server_ecfr_get_regulation` | Retrieve regulatory text for a specific section |
| `ecfr_mcp_server_ecfr_get_title_structure` | Get table of contents for a CFR title |
| `ecfr_mcp_server_ecfr_compare_regulations` | Compare regulatory text between two dates |

## Duplicate This Space

To avoid shared rate limits, click **Duplicate this Space** to get your own instance.

---

## Local Development

### Setup

```bash
python -m venv venv
source venv/bin/activate   # macOS/Linux
# venv\Scripts\activate    # Windows
pip install -r requirements.txt
```

### Run locally

```bash
# Gradio MCP server (same as HF Spaces)
python app.py

# FastMCP stdio server (for local MCP clients)
mcp run src/server.py
```
