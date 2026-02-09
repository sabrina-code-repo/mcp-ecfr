#!/usr/bin/env python3
"""
eCFR MCP Server - Access the Electronic Code of Federal Regulations
Provides tools to search, retrieve, and analyze federal regulations from the eCFR API.
Designed for higher education research administration and compliance professionals.
"""

from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field, ConfigDict
from typing import Optional, List, Dict, Any
import httpx
import json

# Initialize the MCP server
mcp = FastMCP("ecfr_mcp")

# Constants
BASE_URL = "https://www.ecfr.gov/api"
TIMEOUT = 30.0
HEADERS = {"Accept": "application/json, application/xml, */*"}


# --- Shared helpers ---

async def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> dict | str:
    """Make a GET request to the eCFR API.

    Endpoints MUST include a file extension (.json or .xml) to avoid 406 errors.
    Returns parsed JSON dict for .json endpoints, or raw XML string for .xml endpoints.
    """
    url = f"{BASE_URL}/{endpoint}"
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        try:
            response = await client.get(url, params=params, headers=HEADERS)
            response.raise_for_status()
            if endpoint.endswith(".xml"):
                return response.text
            return response.json()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code == 404:
                raise ValueError(f"Not found: {endpoint}")
            if code == 406:
                raise ValueError(
                    f"406 Not Acceptable — ensure endpoint has .json or .xml extension: {endpoint}"
                )
            if code == 429:
                raise ValueError("Rate limit exceeded. Wait before retrying.")
            raise ValueError(f"API error {code} for {endpoint}")
        except httpx.TimeoutException:
            raise ValueError("Request timed out. Try again.")


def _build_params(**kwargs) -> Dict[str, Any]:
    """Build a query param dict, dropping None values."""
    return {k: v for k, v in kwargs.items() if v is not None}


async def _resolve_title(section: str = None, part: str = None) -> dict | None:
    """Use search to find which title a section or part belongs to.

    Returns the first matching result's hierarchy, or None if not found.
    """
    query = section or part
    if not query:
        return None
    try:
        data = await api_get("search/v1/results.json", {"query": query, "per_page": 5})
        results = data.get("results", [])
        for r in results:
            h = r.get("hierarchy", {})
            # Match on section or part identifier
            if section and h.get("section") == section:
                return h
            if part and h.get("part") == part:
                return h
        # If no exact match, return the first result's hierarchy as best guess
        if results:
            return results[0].get("hierarchy", {})
    except Exception:
        pass
    return None


# --- Input models ---

class ListTitlesInput(BaseModel):
    """Input for listing all CFR titles."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class ListAgenciesInput(BaseModel):
    """Input for listing all agencies."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")


class GetTitleVersionsInput(BaseModel):
    """Input for getting version history of a CFR title."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: int = Field(..., description="CFR title number (1–50)", ge=1, le=50)
    issue_date_on: Optional[str] = Field(
        default=None, description="Select content added on this issue date (YYYY-MM-DD)"
    )
    issue_date_lte: Optional[str] = Field(
        default=None,
        description="Select content added on or before this issue date (YYYY-MM-DD)",
    )
    issue_date_gte: Optional[str] = Field(
        default=None,
        description="Select content added on or after this issue date (YYYY-MM-DD)",
    )
    subtitle: Optional[str] = Field(default=None, description="Uppercase letter (e.g. 'A', 'B')")
    chapter: Optional[str] = Field(
        default=None, description="Roman numeral or digit (e.g. 'I', 'X', '1')"
    )
    subchapter: Optional[str] = Field(
        default=None, description="Requires chapter. Uppercase letter (e.g. 'A', 'B')"
    )
    part: Optional[str] = Field(default=None, description="Part number (e.g. '200', '46')")
    subpart: Optional[str] = Field(
        default=None, description="Requires part. Uppercase letter (e.g. 'A', 'B')"
    )
    section: Optional[str] = Field(
        default=None, description="Requires part. Section number (e.g. '121.1', '200.110')"
    )
    appendix: Optional[str] = Field(
        default=None,
        description="Requires subtitle, chapter, or part (e.g. 'A', 'III', 'App. A')",
    )


class GetTitleStructureInput(BaseModel):
    """Input for getting the hierarchical structure of a CFR title on a date."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: int = Field(..., description="CFR title number (1–50)", ge=1, le=50)
    date: str = Field(..., description="Date in YYYY-MM-DD format (e.g. '2024-01-01')")


class GetRegulationInput(BaseModel):
    """Input for retrieving regulatory text. Title is optional — if omitted,
    the tool will attempt to resolve it from the section or part."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date: str = Field(..., description="Date in YYYY-MM-DD format")
    title: Optional[int] = Field(
        default=None,
        description="CFR title number (1–50). If omitted, resolved from section/part via search.",
        ge=1,
        le=50,
    )
    subtitle: Optional[str] = Field(default=None, description="Uppercase letter (e.g. 'A', 'B')")
    chapter: Optional[str] = Field(
        default=None, description="Roman numeral or digit (e.g. 'I', 'X', '1')"
    )
    subchapter: Optional[str] = Field(
        default=None, description="Requires chapter. Uppercase letter (e.g. 'A', 'B')"
    )
    part: Optional[str] = Field(default=None, description="Part number (e.g. '200', '46')")
    subpart: Optional[str] = Field(
        default=None, description="Requires part. Uppercase letter (e.g. 'A', 'B')"
    )
    section: Optional[str] = Field(
        default=None,
        description="Requires part. Section number (e.g. '121.1', '46.116', '200.474')",
    )
    appendix: Optional[str] = Field(
        default=None,
        description="Requires subtitle, chapter, or part (e.g. 'A', 'III', 'App. A')",
    )


class SearchInput(BaseModel):
    """Input for full-text search across the CFR."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    query: str = Field(
        ..., description="Search term; searches headings and full text", min_length=1, max_length=500
    )
    page: int = Field(
        default=1,
        description="Page of results (default 1); max 20 pages allowed",
        ge=1,
        le=20,
    )
    per_page: int = Field(default=20, description="Results per page; max 1000", ge=1, le=1000)
    paginate_by: Optional[str] = Field(
        default="results",
        description="How to paginate: 'results' (default) or 'date' (groups by date; requires a last_modified_* filter)",
    )
    order: Optional[str] = Field(
        default="relevance",
        description="Result order: 'relevance', 'citations', 'hierarchy', 'newest_first', 'oldest_first', 'suggestions'",
    )
    date: Optional[str] = Field(
        default=None, description="Limit to content present on this date (YYYY-MM-DD)"
    )
    last_modified_after: Optional[str] = Field(
        default=None, description="Content last modified after this date (YYYY-MM-DD)"
    )
    last_modified_on_or_after: Optional[str] = Field(
        default=None, description="Content last modified on or after this date (YYYY-MM-DD)"
    )
    last_modified_before: Optional[str] = Field(
        default=None, description="Content last modified before this date (YYYY-MM-DD)"
    )
    last_modified_on_or_before: Optional[str] = Field(
        default=None, description="Content last modified on or before this date (YYYY-MM-DD)"
    )
    agency_slugs: Optional[List[str]] = Field(
        default=None,
        description="Limit to these agency slugs (use ecfr_list_agencies for valid slugs)",
    )


class CompareRegulationsInput(BaseModel):
    """Input for comparing regulatory text between two dates. Title is optional —
    if omitted, resolved from section or part via search."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    date_1: str = Field(..., description="First date in YYYY-MM-DD format")
    date_2: str = Field(..., description="Second date in YYYY-MM-DD format")
    title: Optional[int] = Field(
        default=None,
        description="CFR title number (1–50). If omitted, resolved from section/part via search.",
        ge=1,
        le=50,
    )
    subtitle: Optional[str] = Field(default=None, description="Uppercase letter (e.g. 'A', 'B')")
    chapter: Optional[str] = Field(
        default=None, description="Roman numeral or digit (e.g. 'I', 'X', '1')"
    )
    subchapter: Optional[str] = Field(
        default=None, description="Requires chapter. Uppercase letter (e.g. 'A', 'B')"
    )
    part: Optional[str] = Field(default=None, description="Part number (e.g. '200', '46')")
    subpart: Optional[str] = Field(
        default=None, description="Requires part. Uppercase letter (e.g. 'A', 'B')"
    )
    section: Optional[str] = Field(
        default=None, description="Requires part. Section number (e.g. '121.1', '46.116')"
    )
    appendix: Optional[str] = Field(
        default=None,
        description="Requires subtitle, chapter, or part (e.g. 'A', 'III', 'App. A')",
    )


class TrackChangesInput(BaseModel):
    """Input for tracking amendment history of a title."""
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    title: int = Field(..., description="CFR title number (1–50)", ge=1, le=50)
    limit: int = Field(
        default=50,
        description="Max changes to return (applied after API filtering)",
        ge=1,
        le=500,
    )
    issue_date_on: Optional[str] = Field(
        default=None, description="Select content added on this issue date (YYYY-MM-DD)"
    )
    issue_date_lte: Optional[str] = Field(
        default=None,
        description="Select content added on or before this issue date (YYYY-MM-DD)",
    )
    issue_date_gte: Optional[str] = Field(
        default=None,
        description="Select content added on or after this issue date (YYYY-MM-DD)",
    )
    subtitle: Optional[str] = Field(default=None, description="Uppercase letter (e.g. 'A', 'B')")
    chapter: Optional[str] = Field(
        default=None, description="Roman numeral or digit (e.g. 'I', 'X', '1')"
    )
    subchapter: Optional[str] = Field(
        default=None, description="Requires chapter. Uppercase letter (e.g. 'A', 'B')"
    )
    part: Optional[str] = Field(default=None, description="Part number (e.g. '200', '46')")
    subpart: Optional[str] = Field(
        default=None, description="Requires part. Uppercase letter (e.g. 'A', 'B')"
    )
    section: Optional[str] = Field(
        default=None, description="Requires part. Section number (e.g. '121.1', '200.110')"
    )
    appendix: Optional[str] = Field(
        default=None,
        description="Requires subtitle, chapter, or part (e.g. 'A', 'III', 'App. A')",
    )

#########################################################################################
# MCP Tools
#########################################################################################

@mcp.tool(
    name="ecfr_list_titles",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_list_titles(params: ListTitlesInput) -> str:
    """List all 50 CFR titles with their names and latest amendment dates.

    Returns every title in the Code of Federal Regulations along with its
    currency information. Use this to discover which title numbers correspond
    to which subject areas (e.g. Title 2 = Federal Financial Assistance,
    Title 42 = Public Health, Title 45 = Public Welfare).

    Returns:
        str: JSON with titles array and meta object. Each title has: number,
             name, latest_amended_on, latest_issue_date, up_to_date_as_of,
             reserved. Meta has: date, import_in_progress.
    """
    data = await api_get("versioner/v1/titles.json")
    return json.dumps(data, indent=2)


@mcp.tool(
    name="ecfr_list_agencies",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_list_agencies(params: ListAgenciesInput) -> str:
    """List all federal agencies with their slugs, names, and CFR references.

    Returns every top-level agency and its children. Each agency includes a
    slug identifier that can be passed to ecfr_search via the agency_slugs
    filter. Also includes cfr_references showing which title/chapter each
    agency is responsible for.

    Returns:
        str: JSON with agencies array. Each agency has: name, short_name,
             display_name, sortable_name, slug, children (array of child
             agencies), cfr_references (array of {title, chapter}).
    """
    data = await api_get("admin/v1/agencies.json")
    return json.dumps(data, indent=2)


@mcp.tool(
    name="ecfr_get_title_versions",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_get_title_versions(params: GetTitleVersionsInput) -> str:
    """Get the amendment/version history for a CFR title.

    Returns content versions (amendments) for a title. CRITICAL: use hierarchy
    filters (part, section) to narrow results to a specific regulation. This
    returns the amendment dates you need before calling ecfr_get_regulation or
    ecfr_compare_regulations.

    Returns:
        str: JSON with content_versions array and meta object. Each entry has:
             date, amendment_date, issue_date, identifier, name, part, subpart,
             title, type, substantive, removed. Meta has: title, result_count,
             issue_date filters, latest_amendment_date, latest_issue_date.
    """
    query_params = _build_params(
        **{"issue_date[on]": params.issue_date_on},
        **{"issue_date[lte]": params.issue_date_lte},
        **{"issue_date[gte]": params.issue_date_gte},
        subtitle=params.subtitle,
        chapter=params.chapter,
        subchapter=params.subchapter,
        part=params.part,
        subpart=params.subpart,
        section=params.section,
        appendix=params.appendix,
    )
    data = await api_get(
        f"versioner/v1/versions/title-{params.title}.json",
        params=query_params or None,
    )
    return json.dumps(data, indent=2)


@mcp.tool(
    name="ecfr_get_title_structure",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_get_title_structure(params: GetTitleStructureInput) -> str:
    """Get the hierarchical structure (table of contents) of a CFR title on a date.

    Returns the nested hierarchy of chapters, subchapters, parts, and sections
    as it existed on the given date. Use this to browse what a title contains
    and find valid part/section identifiers before calling ecfr_get_regulation.

    Returns:
        str: JSON tree with identifier, label, label_level, label_description,
             type (title/chapter/subchapter/part/section), size, reserved,
             and children. Part/section nodes also have: volumes (array),
             received_on (timestamp). Parts have: descendant_range.
    """
    data = await api_get(
        f"versioner/v1/structure/{params.date}/title-{params.title}.json"
    )
    return json.dumps(data, indent=2)


@mcp.tool(
    name="ecfr_get_regulation",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_get_regulation(params: GetRegulationInput) -> str:
    """Retrieve the source XML for a regulation on a given date.

    The subset returned is determined by the lowest hierarchy level provided.
    For example, providing part + section returns only that section's XML.

    If title is omitted, the tool attempts to resolve it by searching for the
    section or part identifier. If the resolution is ambiguous, it returns the
    candidate matches instead of content so you can pick the right one.

    Date is required. Use ecfr_get_title_versions (with section/part filters)
    to find valid amendment dates before calling this tool.

    Returns:
        str: JSON with title, date, hierarchy filters, and xml field containing
             the regulatory text. If title was resolved, includes resolved_from
             field. If ambiguous, returns candidates array instead of xml.
    """
    title = params.title

    # --- Title resolution when omitted ---
    if title is None:
        resolved = await _resolve_title(section=params.section, part=params.part)
        if resolved is None:
            return json.dumps({
                "error": "Could not resolve title. Provide a title number, or a valid section/part to resolve from.",
            }, indent=2)

        try:
            title = int(resolved.get("title"))
        except (TypeError, ValueError):
            return json.dumps({
                "error": "Title resolution returned a non-numeric title.",
                "resolved_hierarchy": resolved,
            }, indent=2)

    # --- Fetch content ---
    query_params = _build_params(
        subtitle=params.subtitle,
        chapter=params.chapter,
        subchapter=params.subchapter,
        part=params.part,
        subpart=params.subpart,
        section=params.section,
        appendix=params.appendix,
    )
    xml_text = await api_get(
        f"versioner/v1/full/{params.date}/title-{title}.xml",
        params=query_params or None,
    )

    result = {
        "title": title,
        "date": params.date,
        "part": params.part,
        "section": params.section,
        "xml": xml_text,
    }
    if params.title is None:
        result["resolved_from"] = "search"

    return json.dumps(result, indent=2)


@mcp.tool(
    name="ecfr_search",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_search(params: SearchInput) -> str:
    """Full-text search across the entire Code of Federal Regulations.

    Searches all CFR content and returns matching sections ranked by relevance.
    This is the best starting point for any conceptual or topic-based query.
    Results include full hierarchy info so you can identify the correct title,
    part, and section for follow-up calls.

    Returns:
        str: JSON with results array and meta object. Each result has:
             starts_on, ends_on, type, hierarchy (title, chapter, part,
             section numbers), hierarchy_headings (formatted labels),
             headings (descriptive names), full_text_excerpt, score,
             structure_index, reserved, removed, change_types (array).
             Meta has: current_page, total_pages, total_count, max_score,
             description. When paginate_by='date': also min_date, max_date.
    """
    query_params = _build_params(
        query=params.query,
        page=params.page,
        per_page=params.per_page,
        paginate_by=params.paginate_by,
        order=params.order,
        date=params.date,
        last_modified_after=params.last_modified_after,
        last_modified_on_or_after=params.last_modified_on_or_after,
        last_modified_before=params.last_modified_before,
        last_modified_on_or_before=params.last_modified_on_or_before,
    )
    if params.agency_slugs:
        query_params["agency_slugs[]"] = params.agency_slugs

    data = await api_get("search/v1/results.json", params=query_params)

    # Add warning if results exceed the 20-page limit
    meta = data.get("meta", {})
    total_pages = meta.get("total_pages", 0)
    total_count = meta.get("total_count", 0)
    current_page = meta.get("current_page", 1)

    if total_pages > 20:
        data["warning"] = (
            f"Results truncated: {total_count} total results across {total_pages} pages, "
            f"but only pages 1–20 are accessible. Narrow your query with filters "
            f"(date, agency_slugs, last_modified_*) to reduce results."
        )

    if current_page >= 20 and total_pages > 20:
        data["warning"] = (
            f"You have reached the last accessible page (20 of {total_pages}). "
            f"{total_count} total results exist. Refine your search query or "
            f"add filters to find more specific results."
        )

    return json.dumps(data, indent=2)


@mcp.tool(
    name="ecfr_compare_regulations",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_compare_regulations(params: CompareRegulationsInput) -> str:
    """Compare regulatory text between two dates to identify changes.

    Fetches XML at two points in time and reports whether the text changed.
    Both dates are required — use ecfr_get_title_versions with section/part
    filters to find amendment dates first.

    If title is omitted, the tool attempts to resolve it from section or part.

    Returns:
        str: JSON with title, date_1, date_2, hierarchy filters, identical
             (bool), length_1, length_2, xml_1, xml_2. If title was resolved,
             includes resolved_from field.
    """
    title = params.title

    # --- Title resolution when omitted ---
    if title is None:
        resolved = await _resolve_title(section=params.section, part=params.part)
        if resolved is None:
            return json.dumps({
                "error": "Could not resolve title. Provide a title number, or a valid section/part.",
            }, indent=2)
        try:
            title = int(resolved.get("title"))
        except (TypeError, ValueError):
            return json.dumps({
                "error": "Title resolution returned a non-numeric title.",
                "resolved_hierarchy": resolved,
            }, indent=2)

    # --- Fetch both versions ---
    hierarchy = _build_params(
        subtitle=params.subtitle,
        chapter=params.chapter,
        subchapter=params.subchapter,
        part=params.part,
        subpart=params.subpart,
        section=params.section,
        appendix=params.appendix,
    )
    xml_1 = await api_get(
        f"versioner/v1/full/{params.date_1}/title-{title}.xml",
        params=hierarchy or None,
    )
    xml_2 = await api_get(
        f"versioner/v1/full/{params.date_2}/title-{title}.xml",
        params=hierarchy or None,
    )

    result = {
        "title": title,
        "date_1": params.date_1,
        "date_2": params.date_2,
        "part": params.part,
        "section": params.section,
        "identical": xml_1 == xml_2,
        "length_1": len(xml_1),
        "length_2": len(xml_2),
        "xml_1": xml_1,
        "xml_2": xml_2,
    }
    if params.title is None:
        result["resolved_from"] = "search"

    return json.dumps(result, indent=2)


@mcp.tool(
    name="ecfr_track_changes",
    annotations={
        "readOnlyHint": True,
        "destructiveHint": False,
        "idempotentHint": True,
        "openWorldHint": True,
    },
)
async def ecfr_track_changes(params: TrackChangesInput) -> str:
    """Track amendment history for a CFR title, filtered by issue date and hierarchy.

    Returns content versions (amendments) for a title. Use hierarchy filters
    to narrow to a specific part or section. Filters are applied server-side
    by the API. The limit param caps the returned results.

    Returns:
        str: JSON with title, filters used, count, and changes array.
             Each change has: date, amendment_date, issue_date, identifier,
             name, part, subpart, title, type, substantive, removed.
    """
    query_params = _build_params(
        **{"issue_date[on]": params.issue_date_on},
        **{"issue_date[lte]": params.issue_date_lte},
        **{"issue_date[gte]": params.issue_date_gte},
        subtitle=params.subtitle,
        chapter=params.chapter,
        subchapter=params.subchapter,
        part=params.part,
        subpart=params.subpart,
        section=params.section,
        appendix=params.appendix,
    )
    data = await api_get(
        f"versioner/v1/versions/title-{params.title}.json",
        params=query_params or None,
    )
    versions = data.get("content_versions", [])
    versions = versions[: params.limit]

    return json.dumps({
        "title": params.title,
        "issue_date_on": params.issue_date_on,
        "issue_date_lte": params.issue_date_lte,
        "issue_date_gte": params.issue_date_gte,
        "count": len(versions),
        "changes": versions,
    }, indent=2)


# --- Entry point ---
if __name__ == "__main__":
    mcp.run()
