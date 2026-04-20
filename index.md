---
layout: default
title: Connecting the eCFR MCP Server to Claude
---

# Connecting the eCFR MCP Server to Claude

**[📄 Download PDF version](CONNECTING_TO_CLAUDE.pdf)**

## Prerequisites

- A Claude Pro, Team, or Enterprise account at [claude.ai](https://claude.ai)
- The eCFR MCP Server running on Hugging Face Spaces

## Step-by-Step Setup

### 1. Open Claude Settings

Go to [claude.ai](https://claude.ai) and click on your profile icon in the bottom-left corner, then select **Settings**.

### 2. Navigate to Connectors

In the Settings menu, click on **Connectors** in the left sidebar.

### 3. Add a Custom Connector

Click **Add custom connector** (or the **+** button).

### 4. Enter the MCP Endpoint URL

In the URL field, enter:

```
https://n8layman-ecfr-mcp-server.hf.space/gradio_api/mcp/sse
```

### 5. Save and Enable

Click **Save**. The connector should show as connected with 7 available tools.

### 6. Start Using It

Open a new conversation in Claude and ask a question about federal regulations. For example:

> "What are the requirements for indirect cost rates under the Uniform Guidance?"

Claude will automatically use the eCFR tools to search and retrieve the relevant regulatory text.

## Available Tools

Once connected, Claude has access to these 7 tools (prefixed with `ecfr_mcp_server_` in Claude):

| Tool | What It Does |
|------|-------------|
| **ecfr_mcp_server_ecfr_search** | Search across all federal regulations by keyword |
| **ecfr_mcp_server_ecfr_list_titles** | List all 50 CFR titles |
| **ecfr_mcp_server_ecfr_list_agencies** | Find federal agencies and their regulation references |
| **ecfr_mcp_server_ecfr_get_title_versions** | Check amendment history and find valid dates |
| **ecfr_mcp_server_ecfr_get_regulation** | Retrieve the actual text of a regulation |
| **ecfr_mcp_server_ecfr_get_title_structure** | Browse the table of contents of a CFR title |
| **ecfr_mcp_server_ecfr_compare_regulations** | See what changed between two dates |

Set all tools to **Always allow** in the connector settings for the best experience.

## Example Prompts

- "Search for regulations about informed consent in human subjects research"
- "What does 2 CFR 200.474 say about travel costs?"
- "Compare the Common Rule (45 CFR 46) between 2018 and 2024"
- "List all agencies related to health research"
- "What are the procurement standards under the Uniform Guidance?"

## Troubleshooting

**Connector won't connect:**
- Make sure the HF Space is running (visit the Space URL in a browser)
- The Space may need a moment to start up if it's been idle

**Rate limit errors:**
- The eCFR API may throttle requests from shared IPs
- Consider duplicating the HF Space to get your own instance: click **Duplicate this Space** on the Space page

**Tools not appearing:**
- Try removing and re-adding the connector
- Refresh the Claude page
