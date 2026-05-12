# eCFR MCP Server

Developed by Anthropic in late 2024, the Model Context Protocol (MCP) is an open, standardized interface that allows Large Language Models (LLMs) to interact with external tools. This pilot project creates a local MCP server designed to provide structured access to policies within Uniform Guidance (2 CFR 200) via the **Electronic Code of Federal Regulations (eCFR)** application programming interface (API). The eCFR API is maintained by the National Archives and the Office of the Federal Register and provides a data feed of tracked and updated federal regulations. The eCFR API can retrieve specific sections of regulatory text without manual searching or downloading static documents. When combined with MCP, the eCFR API becomes a source of up-to-date compliance information for AI-driven systems. 

This project exposes a suite of tools for searching, retrieving, and comparing federal regulatory text — designed for higher education research administration and compliance professionals, with a primary focus on the Uniform Guidance (2 CFR Part 200) and related research regulations.

## About

This is a sub-project of the University of Idaho's Artificial Intelligence for Research Administration ([AI4RA](https://ai4ra.uidaho.edu/)). AI4RA is an NSF-funded project creating impactful tools using AI and data science to improve research administration workflows.

## How It Works

1. **Serve MCP tools**; `src/server.py` starts a FastMCP server named `ecfr_mcp` and exposes one MCP resource plus seven read-only tools.
2. **Query the live eCFR API**; the server calls `https://www.ecfr.gov/api` for title metadata, agency metadata, search results, version history, structure, and full XML regulation text.
3. **Normalize responses**; helper functions validate dates, enforce response-size limits, add citations and source URLs, and convert XML into plain text.
4. **Support point-in-time lookups**; version history is used to find valid amendment dates before full text is retrieved or compared.
5. **Response Size Management** — All responses are capped at 1MB, with soft warnings at 800KB and built-in hints to narrow requests if needed.
6. **Validate Behavior**; `src/test_api.py` checks raw eCFR API endpoints.

## Project Structure

```
ecfr-mcp-server/
│
├── documentation/
        ├── MCP Evaluation Data and Stats.xlsx                     # Excel workbook containing raw evaluation data, notes, and stats run on the eval data
        ├── MCP Evaluation Data Clean.xlsx                         # Clean evaluation data, 1 paired question and response per row
        ├── MCP Evaluation Visuals.pbix                            # Uses the clean evaluation data to create visuals for presentation. Needs Data Clean.xlsx to work.
        ├── Model Context Protocol Executive Summary.docx          # An executive summary describing this project.
        ├── RA Summit 2026 - Model Context Protocol.pdf            # Presentation given at the REACH Summit 2026, PDF format.
        ├── RA Summit 2026 - Model Context Protocol.ppt            # Presentation given at the REACH Summit 2026, ppt format.
├── src/
        ├── server.py          # FastMCP server with all seven eCFR tools and helper functions.
        ├── test_api.py        # Test script validating all eCFR API endpoints.
        ├── SKILL.md           # Prompting skill for AI assistants using this MCP server.
├── .gitignore
├── README.md
└── requirements.txt           # Package requirements for this project.
```

## Available MCP Resource and Tools

### Resource

- `ecfr://regulatory-index`; compact metadata for Uniform Guidance and related research administration workflows.


### Tools

The `ecfr_mcp` server provides exactly these seven tools:

| Tool | Purpose | When to use |
|---|---|---|
| `ecfr_search` | Full-text keyword search across all CFR titles. Returns matching sections with hierarchy, headings, and relevance scores. | **Start here** for topic-based or conceptual questions where the user hasn't given a specific CFR citation. Results include `title`, `part`, and `section` for follow-up calls. |
| `ecfr_get_title_versions` | Amendment history for a title, filterable by `part` and `section`. Each version has a `date` field. | **Call this before `ecfr_get_regulation` or `ecfr_compare_regulations`** to get a valid amendment date. Never guess a date. |
| `ecfr_get_regulation` | Fetches regulatory text for a title subset on a given date. Requires at least `part` + `section`; part-only requests are blocked. Auto-resolves `title` if omitted but ambiguous parts (46, 50) will error — always provide `title` explicitly. | To retrieve the authoritative text of a specific provision. |
| `ecfr_compare_regulations` | Compares regulatory text between two dates. Returns a structured diff of added/removed paragraphs. Auto-resolves `title` if omitted. | When the user asks what changed between two points in time. |
| `ecfr_get_title_structure` | Table of contents for a title on a given date, pruned to a configurable depth. | To browse what a title contains and verify that a part/section identifier exists before fetching it. |
| `ecfr_list_agencies` | Lists federal agencies with slugs and CFR references. Supports `name_filter`. | When filtering searches by agency, or the user asks which agency owns a regulation. Common slugs: `office-of-management-and-budget`, `national-science-foundation`, `national-institutes-of-health`. |
| `ecfr_list_titles` | Lists all 50 CFR titles with names and latest amendment dates. | When you need to identify which title number covers a topic. |

## Getting Started

### Prerequisites

- Python 3.11+
- An MCP-compatible AI client (e.g., [Claude Desktop](https://claude.ai/download), [Claude Code](https://claude.ai/code))
- Access to install Python packages locally
- Internet access, because the server calls the live eCFR API

### Setup

1. **Clone the repository** and change into the project directory.

2. **Create and activate a virtual environment:**

   ```bash
   python -m venv venv
   source venv/bin/activate   # macOS/Linux
   venv\Scripts\activate      # Windows
   ```

   On Windows:

   ```bash
   venv\Scripts\activate
   ```

3. **Install dependencies:**

   ```bash
   pip install "mcp[cli]"
   pip install requirements.txt
   ```
  
## Running the Server Locally

Run the MCP server with the MCP CLI:

```bash
mcp run src/server.py
```

You can also run the server module directly:

```bash
python src/server.py
```

### Connecting a Local MCP Server to an AI Client (Claude)

Configure Claude Desktop to automatically start the server by editing the claude_desktop_config.json file, which tells Claude Desktop which servers to run and how to connect to them. After saving the config, fully quit and restart Claude Desktop. You should see the mcp-ecfr in the Connectors section in the chat input box (click the "+" button). For full setup instructions, see Anthropic's official guide: [Getting Started with Local MCP Servers on Claude Desktop](https://support.claude.com/en/articles/10949351-getting-started-with-local-mcp-servers-on-claude-desktop).

To use with **Claude Desktop**, add an entry to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "ecfr": {
      "command": "python",
      "args": ["/src/server.py"]  #You will need to find the exact path on your desktop to this project's server.py
    }
  }
}
```

To use with **Claude Code**:

```bash
claude mcp add ecfr python /src/server.py #You will need to find the exact path on your desktop to this project's server.py
```

### Add a Skill to Claude

For best results, use the accompanying `SKILL.md` as a system prompt or skill to guide the AI through the correct tool-call workflow. For full instructions on packaging and uploading custom Skills, see [Anthropic's guide](https://support.claude.com/en/articles/12512198-how-to-create-custom-skills) on creating custom Skills. 

### Running the API Tests (Optional)

To verify all eCFR API endpoints are reachable and returning expected results:

```bash
python test_api.py
```

Test output (JSON and logs) is saved to `../test_outputs/api_tests/<timestamp>/`.

## Usage

Once the server is connected to Claude Desktop, you can ask questions about federal regulations in natural language. The AI will use the MCP tools to fetch live regulatory text and return cited, dated answers. Example queries:

- *"Can an institution charge salary to a federal award based on an employee’s full institutional salary?"*
- *"I’m working with a PI in Plant Sciences who would like to purchase equipment that was not included in the original approved budget. Could you let me know what prior approval documentation is required and what steps we need to complete before the purchase?"*
- *"What expenses must be excluded from the Modified Total Direct Cost base when calculating indirect costs?"*
- *"What happens if a project cannot be completed by the end date and a no-cost extension is denied?"*



## Future Considerations

- Remove ecfr_list_titles and integrate ecfr_list_agencies into the existing tools, since these are less likely to be called directly by the agent. This would also reduce context usage. 
- Design tools around specific purposes while allowing each tool to support multiple related API methods. This aligns with Anthropic’s guidance to limit context overhead and streamline tool use. Based on initial testing, the final tool structure performed better than tools optimized for narrow case examples; however, further testing is recommended to identify the most effective tool configuration. 
- Add user-facing prompt templates to the server to give users a clear starting point for common workflows. 
- Review the regulatory index, which is currently highly specific to Uniform Guidance, and adjust it to support other CFR sections based on the server’s intended use case. This resource is optional and can be removed if context limits become a concern. 
- Consider cloud hosting the server, with authentication added as needed for enterprise or restricted-use environments. 
- Test the server across different AI clients to evaluate compatibility, consistency, and tool-calling performance. 
- Conduct broader stress testing to assess API reliability, avoid rate limits, and reduce the risk of triggering anti-bot behavior. 
- Add additional structured human evaluations for refined MCP servers to assess accuracy, usefulness, citation quality, and overall workflow performance. 

## Authors

Sabrina Woo, University of Idaho — swoo@uidaho.edu

## Acknowledgments

Thanks to Nathan Layman, Sarah Martonick, and Barrie Robison from the University of Idaho for advising on this project.

This material is based upon work supported by the National Science Foundation under Grant Number 2427549.