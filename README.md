---
title: eCFR MCP Server
emoji: 📜
colorFrom: blue
colorTo: indigo
sdk: gradio
app_file: app.py
pinned: false
license: mit
short_description: Search and retrieve federal regulations from the eCFR API via MCP
tags:
  - mcp-server-track
---

# eCFR MCP Server

Access the Electronic Code of Federal Regulations through MCP tools.
Built for research administrators, compliance officers, and policy analysts.

## MCP Connector

Add this server as a connector in Claude:
1. Go to **Settings > Connectors > Add custom connector**
2. Enter the MCP endpoint URL: `https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/sse`

## Available Tools

| Tool | Description |
|------|-------------|
| `ecfr_search` | Full-text search across all CFR titles |
| `ecfr_list_titles` | List all 50 CFR titles |
| `ecfr_list_agencies` | List federal agencies with CFR references |
| `ecfr_get_title_versions` | Get amendment history for a CFR title |
| `ecfr_get_regulation` | Retrieve regulatory text for a specific section |
| `ecfr_get_title_structure` | Get table of contents for a CFR title |
| `ecfr_compare_regulations` | Compare regulatory text between two dates |

## Duplicate This Space

To avoid shared rate limits, click **Duplicate this Space** to get your own instance.

---

# Local Development

# Basic MCP Server Structure

An MCP server typically includes:

- **Server Configuration**: Setup port, authentication, and other settings
- **Resources**: Data and context made available to LLMs
- **Tools**: Functionality that models can invoke
- **Prompts**: Templates for generating or structuring text


# Instructions

## -0- Create a virtual environment

```bash
python -m venv venv
```

## -1- Activate the virtual environment

```bash
venv\Scripts\activate
```

## -2- Install the dependencies

```bash
pip install "mcp[cli]"
pip install requirements.txt
```

## -3- Run the sample

```bash
mcp run server.py
```
