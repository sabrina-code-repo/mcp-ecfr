#!/usr/bin/env python3
"""
eCFR MCP Server — Gradio deployment for Hugging Face Spaces.
Wraps the existing FastMCP tools as Gradio API endpoints with MCP support.
"""

import gradio as gr

# Import tool functions from the existing server.
# The @mcp.tool() decorators register with the FastMCP instance but the
# functions remain normal callables. The FastMCP instance is inert since
# we never call mcp.run().
from src.server import (
    ecfr_list_titles as _ecfr_list_titles,
    ecfr_list_agencies as _ecfr_list_agencies,
    ecfr_search as _ecfr_search,
    ecfr_get_title_versions as _ecfr_get_title_versions,
    ecfr_get_regulation as _ecfr_get_regulation,
    ecfr_get_title_structure as _ecfr_get_title_structure,
    ecfr_compare_regulations as _ecfr_compare_regulations,
    regulatory_index as _regulatory_index,
)


# -- Type conversion helpers --

def _to_opt_str(value: str) -> str | None:
    """Empty string -> None."""
    return value.strip() if value and value.strip() else None


def _to_opt_int(value: str) -> int | None:
    """Empty string -> None, otherwise int."""
    v = value.strip() if value else ""
    return int(v) if v else None


def _to_int(value: str, default: int) -> int:
    """String to int with fallback."""
    v = value.strip() if value else ""
    return int(v) if v else default


def _to_bool(value: str, default: bool = False) -> bool:
    """'true'/'false' string to bool."""
    v = value.strip().lower() if value else ""
    if v == "true":
        return True
    if v == "false":
        return False
    return default


def _to_opt_str_list(value: str) -> list[str] | None:
    """Comma-separated string to list, or None if empty."""
    v = value.strip() if value else ""
    if not v:
        return None
    return [s.strip() for s in v.split(",") if s.strip()]


# -- Wrapper functions --


async def ecfr_regulatory_index() -> str:
    """Get metadata and usage guide for the eCFR MCP tools. READ THIS FIRST.

    Returns Uniform Guidance (2 CFR Part 200) metadata, latest amendment dates,
    starter citations, grants-relevant agency slugs, and key rules for valid tool calls.

    Key rules:
    - Call ecfr_get_title_versions BEFORE ecfr_get_regulation to get a valid date.
    - Use ecfr_search for topic/concept discovery.
    - Always provide title= explicitly; part numbers are NOT unique across titles.
    - Prefer section-level over part-level requests.

    Tool call workflow:
    - Topic question: ecfr_search -> ecfr_get_title_versions -> ecfr_get_regulation
    - Citation lookup: ecfr_get_title_versions -> ecfr_get_regulation
    - Change history: ecfr_get_title_versions -> ecfr_compare_regulations
    - Browse structure: ecfr_get_title_structure

    Returns:
        JSON with regulatory index metadata, starter citations, and usage notes.
    """
    return await _regulatory_index()


async def ecfr_list_titles(summary_only: str = "true") -> str:
    """List all 50 CFR titles with names and latest amendment dates.

    Args:
        summary_only: 'true' (default) for compact list, 'false' for full API response.

    Returns:
        JSON with all CFR titles.
    """
    return await _ecfr_list_titles(
        summary_only=_to_bool(summary_only, default=True),
    )


async def ecfr_list_agencies(
    name_filter: str = "",
    include_children: str = "false",
) -> str:
    """List federal agencies with slugs and CFR references.

    Args:
        name_filter: Case-insensitive substring filter. E.g. 'health', 'nsf'. Leave empty for all.
        include_children: 'true' or 'false'. Include sub-agency children. Default 'false'.

    Returns:
        JSON with matching agencies and their CFR references.
    """
    return await _ecfr_list_agencies(
        name_filter=_to_opt_str(name_filter),
        include_children=_to_bool(include_children, default=False),
    )


async def ecfr_search(
    query: str,
    page: str = "1",
    per_page: str = "5",
    include_excerpts: str = "false",
    order: str = "relevance",
    date: str = "",
    last_modified_after: str = "",
    last_modified_on_or_after: str = "",
    last_modified_before: str = "",
    last_modified_on_or_before: str = "",
    agency_slugs: str = "",
) -> str:
    """Full-text search across the entire Code of Federal Regulations.

    START HERE for topic or concept questions. Returns sections ranked by relevance.
    For Uniform Guidance topics, use agency_slugs='office-of-management-and-budget'.

    Args:
        query: Search term. Examples: 'indirect costs', 'subaward monitoring', 'informed consent'.
        page: Page number, 1-20. Default '1'.
        per_page: Results per page, 1-25. Default '5'.
        include_excerpts: 'true' or 'false'. Include text excerpts. Default 'false'.
        order: Sort: 'relevance' (default), 'newest_first', 'oldest_first', 'hierarchy'.
        date: Limit to content on this date (YYYY-MM-DD). Leave empty to skip.
        last_modified_after: Modified after date (YYYY-MM-DD). Leave empty to skip.
        last_modified_on_or_after: Modified on or after date (YYYY-MM-DD). Leave empty to skip.
        last_modified_before: Modified before date (YYYY-MM-DD). Leave empty to skip.
        last_modified_on_or_before: Modified on or before date (YYYY-MM-DD). Leave empty to skip.
        agency_slugs: Comma-separated agency slugs. E.g. 'office-of-management-and-budget'. Leave empty for all.

    Returns:
        JSON with search results including citations and source URLs.
    """
    return await _ecfr_search(
        query=query,
        page=_to_int(page, 1),
        per_page=_to_int(per_page, 5),
        include_excerpts=_to_bool(include_excerpts),
        order=_to_opt_str(order) or "relevance",
        date=_to_opt_str(date),
        last_modified_after=_to_opt_str(last_modified_after),
        last_modified_on_or_after=_to_opt_str(last_modified_on_or_after),
        last_modified_before=_to_opt_str(last_modified_before),
        last_modified_on_or_before=_to_opt_str(last_modified_on_or_before),
        agency_slugs=_to_opt_str_list(agency_slugs),
    )


async def ecfr_get_title_versions(
    title: str,
    part: str = "",
    section: str = "",
    limit: str = "25",
    issue_date_on: str = "",
    issue_date_lte: str = "",
    issue_date_gte: str = "",
    subtitle: str = "",
    chapter: str = "",
    subchapter: str = "",
    subpart: str = "",
    appendix: str = "",
) -> str:
    """Get amendment/version history for a CFR title.

    CALL THIS FIRST before ecfr_get_regulation or ecfr_compare_regulations.
    Each returned version has a 'date' field to use in subsequent calls.

    Args:
        title: CFR title number, 1-50. Required.
        part: Part number, e.g. '200'. Leave empty to skip.
        section: Section number, e.g. '200.474'. Requires part. Leave empty to skip.
        limit: Max versions to return, 1-200. Default '25'.
        issue_date_on: Content added on this date (YYYY-MM-DD). Leave empty to skip.
        issue_date_lte: Content added on or before (YYYY-MM-DD). Leave empty to skip.
        issue_date_gte: Content added on or after (YYYY-MM-DD). Leave empty to skip.
        subtitle: Uppercase letter, e.g. 'A'. Leave empty to skip.
        chapter: Roman numeral, e.g. 'I'. Leave empty to skip.
        subchapter: Requires chapter. Uppercase letter. Leave empty to skip.
        subpart: Requires part. Uppercase letter. Leave empty to skip.
        appendix: Requires subtitle, chapter, or part. Leave empty to skip.

    Returns:
        JSON with version history including dates for use in other tools.
    """
    return await _ecfr_get_title_versions(
        title=int(title),
        part=_to_opt_str(part),
        section=_to_opt_str(section),
        limit=_to_int(limit, 25),
        issue_date_on=_to_opt_str(issue_date_on),
        issue_date_lte=_to_opt_str(issue_date_lte),
        issue_date_gte=_to_opt_str(issue_date_gte),
        subtitle=_to_opt_str(subtitle),
        chapter=_to_opt_str(chapter),
        subchapter=_to_opt_str(subchapter),
        subpart=_to_opt_str(subpart),
        appendix=_to_opt_str(appendix),
    )


async def ecfr_get_regulation(
    date: str,
    title: str = "",
    part: str = "",
    section: str = "",
    subpart: str = "",
    subtitle: str = "",
    chapter: str = "",
    subchapter: str = "",
    appendix: str = "",
    text_only: str = "true",
) -> str:
    """Retrieve regulatory text for a specific section on a given date.

    IMPORTANT: Call ecfr_get_title_versions first to get a valid date.
    Provide section whenever possible. Always provide title explicitly for Parts 46 and 50.

    Args:
        date: Date in YYYY-MM-DD format. Must be a valid eCFR amendment date.
        title: CFR title number, 1-50. Provide explicitly to avoid ambiguity. Leave empty for auto-resolve.
        part: Part number, e.g. '200', '46'. Leave empty to skip.
        section: Section number, e.g. '200.474'. Requires part. Prefer this over part-only.
        subpart: Requires part. E.g. 'A', 'B'. Leave empty to skip.
        subtitle: Uppercase letter. Leave empty to skip.
        chapter: Roman numeral, e.g. 'I'. Leave empty to skip.
        subchapter: Requires chapter. Leave empty to skip.
        appendix: Requires subtitle, chapter, or part. Leave empty to skip.
        text_only: 'true' (default) for clean text, 'false' for raw XML.

    Returns:
        JSON with the regulatory text, citation, and source URL.
    """
    return await _ecfr_get_regulation(
        date=date,
        title=_to_opt_int(title),
        part=_to_opt_str(part),
        section=_to_opt_str(section),
        subpart=_to_opt_str(subpart),
        subtitle=_to_opt_str(subtitle),
        chapter=_to_opt_str(chapter),
        subchapter=_to_opt_str(subchapter),
        appendix=_to_opt_str(appendix),
        text_only=_to_bool(text_only, default=True),
    )


async def ecfr_get_title_structure(
    title: str,
    date: str,
    depth: str = "2",
) -> str:
    """Get the hierarchical table of contents for a CFR title on a given date.

    Use to discover valid part and section identifiers before calling ecfr_get_regulation.
    Start with depth 2 or 3. Depth 4 on broad titles (2, 42, 45) is blocked.

    Args:
        title: CFR title number, 1-50. Required.
        date: Date in YYYY-MM-DD format. Use a date from ecfr_get_title_versions.
        depth: Hierarchy depth: 1=title, 2=subtitle/chapter, 3=parts, 4=sections. Default '2'.

    Returns:
        JSON with the hierarchical structure of the title.
    """
    return await _ecfr_get_title_structure(
        title=int(title),
        date=date,
        depth=_to_int(depth, 2),
    )


async def ecfr_compare_regulations(
    date_1: str,
    date_2: str,
    title: str = "",
    part: str = "",
    section: str = "",
    subpart: str = "",
    subtitle: str = "",
    chapter: str = "",
    subchapter: str = "",
    appendix: str = "",
    include_full_text: str = "false",
) -> str:
    """Compare regulatory text between two dates to identify changes.

    Use ecfr_get_title_versions to find valid amendment dates first,
    then pass two of those dates here.

    Args:
        date_1: Earlier date (YYYY-MM-DD) from ecfr_get_title_versions.
        date_2: Later date (YYYY-MM-DD) from ecfr_get_title_versions.
        title: CFR title number, 1-50. Provide explicitly to avoid ambiguity. Leave empty for auto-resolve.
        part: Part number, e.g. '200'. Leave empty to skip.
        section: Section number. Requires part. Leave empty to skip.
        subpart: Requires part. Leave empty to skip.
        subtitle: Uppercase letter. Leave empty to skip.
        chapter: Roman numeral. Leave empty to skip.
        subchapter: Requires chapter. Leave empty to skip.
        appendix: Requires subtitle, chapter, or part. Leave empty to skip.
        include_full_text: 'true' or 'false'. Include full text of both versions. Default 'false'.

    Returns:
        JSON with diff showing added and removed paragraphs.
    """
    return await _ecfr_compare_regulations(
        date_1=date_1,
        date_2=date_2,
        title=_to_opt_int(title),
        part=_to_opt_str(part),
        section=_to_opt_str(section),
        subpart=_to_opt_str(subpart),
        subtitle=_to_opt_str(subtitle),
        chapter=_to_opt_str(chapter),
        subchapter=_to_opt_str(subchapter),
        appendix=_to_opt_str(appendix),
        include_full_text=_to_bool(include_full_text, default=False),
    )


# -- Gradio App --

with gr.Blocks(title="eCFR MCP Server") as demo:
    gr.Markdown("""
# eCFR MCP Server

Access the Electronic Code of Federal Regulations through MCP tools.
Built for research administrators, compliance officers, and policy analysts.

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

## Connect via MCP

Add this server as a connector in Claude or any MCP-compatible client.
MCP endpoint: **`/gradio_api/mcp/sse`**
""")

    gr.api(ecfr_regulatory_index, api_name="ecfr_regulatory_index")
    gr.api(ecfr_list_titles, api_name="ecfr_list_titles")
    gr.api(ecfr_list_agencies, api_name="ecfr_list_agencies")
    gr.api(fn=ecfr_search, api_name="ecfr_search")
    gr.api(ecfr_get_title_versions, api_name="ecfr_get_title_versions")
    gr.api(ecfr_get_regulation, api_name="ecfr_get_regulation")
    gr.api(ecfr_get_title_structure, api_name="ecfr_get_title_structure")
    gr.api(ecfr_compare_regulations, api_name="ecfr_compare_regulations")

if __name__ == "__main__":
    demo.launch(mcp_server=True, server_name="0.0.0.0")
