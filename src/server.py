#!/usr/bin/env python3
"""
eCFR MCP Server - Access the Electronic Code of Federal Regulations
Provides tools to search, retrieve, and analyze federal regulations from the eCFR API.
Designed for higher education research administration and compliance professionals,
with a primary focus on Uniform Guidance (2 CFR Part 200) and related research regulations.
"""

from mcp.server.fastmcp import FastMCP
from pydantic import Field
from typing import Annotated, Optional, List, Dict, Any
import asyncio
import difflib
import httpx
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, date

# Initialize the MCP server
mcp = FastMCP("ecfr_mcp")

# Constants
BASE_URL = "https://www.ecfr.gov/api"
ECFR_SITE = "https://www.ecfr.gov"
TIMEOUT = 30.0
HEADERS = {"Accept": "application/json, application/xml, */*"}
MAX_RESPONSE_BYTES = 1 * 1024 * 1024  # 1MB hard limit
SOFT_RESPONSE_BYTES = 800_000         # warn at 800KB
DEFAULT_SEARCH_RESULTS = 5
MAX_SEARCH_RESULTS = 25
MAX_DIFF_LINES = 100
DEFAULT_STRUCTURE_DEPTH = 2

# Today's date as a valid default for version lookups
TODAY = date.today().isoformat()

# =============================================================================
# RESOURCE CACHE — built on first access, memoized for process lifetime
# =============================================================================
_resource_cache: Optional[Dict[str, Any]] = None

# Module-level HTTP client for connection reuse
_http_client: Optional[httpx.AsyncClient] = None


def _get_http_client() -> httpx.AsyncClient:
    global _http_client
    if _http_client is None or _http_client.is_closed:
        _http_client = httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True)
    return _http_client


# =============================================================================
# HTTP HELPERS
# =============================================================================

async def api_get(
    endpoint: str,
    params: Optional[Dict[str, Any]] = None,
    *,
    max_retries: int = 2,
) -> dict | str:
    """GET request to the eCFR API with exponential backoff."""
    url = f"{BASE_URL}/{endpoint}"
    client = _get_http_client()
    for attempt in range(1 + max_retries):
        try:
            response = await client.get(url, params=params, headers=HEADERS)
            response.raise_for_status()
            if endpoint.endswith(".xml"):
                return response.text
            return response.json()
        except httpx.HTTPStatusError as e:
            code = e.response.status_code
            if code in (429,) or 500 <= code < 600:
                if attempt < max_retries:
                    await asyncio.sleep(2 ** attempt)
                    continue
                if code == 429:
                    raise ValueError("Rate limit exceeded. Wait before retrying.")
                raise ValueError(f"Server error {code} for {endpoint} after {max_retries} retries")
            if code == 404:
                raise ValueError(f"Not found: {endpoint}. Check that the title, part, section, and date are valid.")
            if code == 406:
                raise ValueError(f"406 Not Acceptable — endpoint must end in .json or .xml: {endpoint}")
            raise ValueError(f"API error {code} for {endpoint}")
        except httpx.TimeoutException:
            if attempt < max_retries:
                await asyncio.sleep(2 ** attempt)
                continue
            raise ValueError(f"Request timed out for {endpoint} after {max_retries} retries.")


def _build_params(**kwargs) -> Dict[str, Any]:
    return {k: v for k, v in kwargs.items() if v is not None}


# =============================================================================
# RESPONSE HELPERS
# =============================================================================

def _make_error(message: str, **extra) -> Dict[str, Any]:
    error = {"message": message}
    error.update({k: v for k, v in extra.items() if v is not None})
    return error


def _add_warning(data: Dict[str, Any], message: str) -> None:
    data.setdefault("warnings", []).append(message)


def _make_citation(
    *,
    title: Optional[int] = None,
    part: Optional[str] = None,
    section: Optional[str] = None,
    appendix: Optional[str] = None,
) -> Optional[str]:
    if title is None:
        return None
    if section:
        return f"{title} CFR § {section}"
    if appendix and part:
        return f"{title} CFR Part {part}, Appendix {appendix}"
    if appendix:
        return f"{title} CFR Appendix {appendix}"
    if part:
        return f"{title} CFR Part {part}"
    return f"{title} CFR"


def _make_source_url(
    *,
    title: Optional[int] = None,
    date: Optional[str] = None,
    part: Optional[str] = None,
    section: Optional[str] = None,
) -> Optional[str]:
    if title is None:
        return None
    if section:
        return f"{ECFR_SITE}/current/title-{title}/section-{section}"
    if part:
        return f"{ECFR_SITE}/current/title-{title}/part-{part}"
    if date:
        return f"{ECFR_SITE}/on/{date}/title-{title}"
    return f"{ECFR_SITE}/current/title-{title}"


def _add_canonical_fields(
    data: Dict[str, Any],
    *,
    title: Optional[int] = None,
    part: Optional[str] = None,
    section: Optional[str] = None,
    appendix: Optional[str] = None,
    date: Optional[str] = None,
) -> Dict[str, Any]:
    data["citation"] = _make_citation(title=title, part=part, section=section, appendix=appendix)
    data["title"] = title
    data["part"] = part
    data["section"] = section
    data["date"] = date
    data["source_url"] = _make_source_url(title=title, date=date, part=part, section=section)
    return data


def _finalize_response(data: Dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False, indent=2)
    if len(payload.encode("utf-8")) <= MAX_RESPONSE_BYTES:
        return payload
    fallback = {
        "error": _make_error("Response exceeds 1MB limit."),
        "hint": "Narrow the request: add section=, subpart=, or lower depth/per_page.",
    }
    return json.dumps(fallback, ensure_ascii=False, indent=2)


def _validate_date_str(value: Optional[str], field_name: str) -> None:
    if value is None:
        return
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as e:
        raise ValueError(f"{field_name} must be YYYY-MM-DD") from e


# =============================================================================
# TITLE AUTO-RESOLUTION
# =============================================================================

async def _resolve_title(section: str = None, part: str = None) -> dict | list | None:
    query = section or part
    if not query:
        return None
    try:
        data = await api_get("search/v1/results.json", {"query": query, "per_page": 10})
        results = data.get("results", [])
    except Exception:
        return None

    seen_titles: Dict[int, dict] = {}
    for result in results:
        hierarchy = result.get("hierarchy", {})
        try:
            title_number = int(hierarchy.get("title"))
        except (TypeError, ValueError):
            continue
        h_section = (hierarchy.get("section") or "").strip()
        h_part = (hierarchy.get("part") or "").strip()
        if section and h_section == section:
            seen_titles.setdefault(title_number, hierarchy)
        elif part and h_part == part:
            seen_titles.setdefault(title_number, hierarchy)

    if not seen_titles:
        return None
    if len(seen_titles) == 1:
        return next(iter(seen_titles.values()))
    return list(seen_titles.values())


# =============================================================================
# XML → PLAIN TEXT
# =============================================================================

def _xml_to_text(xml_str: str) -> str:
    try:
        root = ET.fromstring(xml_str)
    except ET.ParseError:
        return xml_str

    parts: List[str] = []

    def _inner_text(elem: ET.Element) -> str:
        return re.sub(r"\s+", " ", "".join(elem.itertext())).strip()

    def _paragraph_prefix(elem: ET.Element) -> str:
        for key in ("N", "n", "label"):
            value = elem.attrib.get(key)
            if value:
                return value.strip()
        for child in elem:
            if child.tag in ("E", "ENUM"):
                text = _inner_text(child)
                if text:
                    return text.strip()
        return ""

    def _process_table(table_elem: ET.Element) -> str:
        rows = []
        for row in table_elem.iter():
            if row.tag in ("ROW", "TR"):
                cells = [_inner_text(c) for c in row if c.tag in ("ENT", "TD", "TH")]
                if cells:
                    rows.append("| " + " | ".join(cells) + " |")
        if rows:
            if len(rows) > 1:
                col_count = rows[0].count("|") - 1
                rows.insert(1, "| " + " | ".join(["---"] * col_count) + " |")
            return "\n".join(rows)
        return ""

    def _walk(elem: ET.Element):
        tag = elem.tag
        if tag == "SECTNO":
            text = _inner_text(elem)
            if text:
                parts.append(f"\n{'=' * 60}")
                parts.append(f"§ {text}")
            return
        if tag in ("SUBJECT", "HEAD"):
            text = _inner_text(elem)
            if text:
                parts.append(text)
                parts.append("=" * 60)
            return
        if tag == "HD":
            text = _inner_text(elem)
            if text:
                parts.append(f"\n--- {text} ---")
            return
        if tag in ("TABLE", "GPOTABLE"):
            table_text = _process_table(elem)
            if table_text:
                parts.append(f"\n{table_text}\n")
            return
        if tag in ("P", "FP"):
            text = _inner_text(elem)
            if text:
                prefix = _paragraph_prefix(elem)
                parts.append(f"{prefix} {text}" if prefix and not text.startswith(prefix) else text)
            return
        if tag in ("AUTH", "SOURCE"):
            text = _inner_text(elem)
            if text:
                parts.append(f"[{tag}] {text}")
            return
        if elem.text and elem.text.strip():
            parts.append(re.sub(r"\s+", " ", elem.text).strip())
        for child in elem:
            _walk(child)
            if child.tail and child.tail.strip():
                parts.append(re.sub(r"\s+", " ", child.tail).strip())

    _walk(root)

    cleaned: List[str] = []
    seen_blank = False
    for p in parts:
        v = p.strip()
        if not v:
            if not seen_blank:
                cleaned.append("")
                seen_blank = True
        else:
            cleaned.append(v)
            seen_blank = False

    return "\n\n".join(cleaned)


# =============================================================================
# MISC HELPERS
# =============================================================================

def _prune_tree(node: dict, max_depth: int, current_depth: int = 1) -> dict:
    if not isinstance(node, dict):
        return node
    result = {k: v for k, v in node.items() if k != "children"}
    children = node.get("children", [])
    if children:
        result["child_count"] = len(children)
        if current_depth >= max_depth:
            result["truncated_children_count"] = len(children)
        else:
            result["children"] = [
                _prune_tree(child, max_depth, current_depth + 1) for child in children
            ]
    return result


def _slim_search_result(result: dict, include_excerpts: bool) -> dict:
    hierarchy = result.get("hierarchy", {})
    headings = result.get("headings", {})
    slim = {
        "type": result.get("type"),
        "hierarchy": hierarchy,
        "headings": {k: headings.get(k) for k in ("title", "chapter", "part", "subpart", "section", "appendix")},
        "score": result.get("score"),
        "change_types": result.get("change_types", []),
        "starts_on": result.get("starts_on"),
        "ends_on": result.get("ends_on"),
        "reserved": result.get("reserved"),
        "removed": result.get("removed"),
        "citation": _make_citation(
            title=int(hierarchy["title"]) if hierarchy.get("title") not in (None, "") else None,
            part=hierarchy.get("part"),
            section=hierarchy.get("section"),
            appendix=hierarchy.get("appendix"),
        ),
        "source_url": _make_source_url(
            title=int(hierarchy["title"]) if hierarchy.get("title") not in (None, "") else None,
            part=hierarchy.get("part"),
            section=hierarchy.get("section"),
        ),
    }
    if include_excerpts:
        slim["full_text_excerpt"] = result.get("full_text_excerpt")
    return slim


# =============================================================================
# STARTUP RESOURCE
# =============================================================================

async def _build_resource() -> Dict[str, Any]:
    grants_titles = {2, 7, 20, 29, 34, 42, 45, 49}
    title_2_versions = await api_get("versioner/v1/versions/title-2.json", params={"part": "200"})
    agencies_data = await api_get("admin/v1/agencies.json")

    agencies = []
    for agency in agencies_data.get("agencies", []):
        refs = agency.get("cfr_references", [])
        if {ref.get("title") for ref in refs} & grants_titles:
            agencies.append({
                "slug": agency.get("slug"),
                "name": agency.get("name"),
                "short_name": agency.get("short_name"),
                "cfr_references": refs,
            })
        for child in agency.get("children", []):
            child_refs = child.get("cfr_references", [])
            if {ref.get("title") for ref in child_refs} & grants_titles:
                agencies.append({
                    "slug": child.get("slug"),
                    "name": child.get("name"),
                    "short_name": child.get("short_name"),
                    "parent_slug": agency.get("slug"),
                    "cfr_references": child_refs,
                })

    meta = title_2_versions.get("meta", {})
    content_versions = title_2_versions.get("content_versions", [])
    starter_citations = []
    for item in content_versions:
        if not item.get("identifier") or item.get("type") != "section":
            continue
        starter_citations.append({
            "citation": f"2 CFR § {item['identifier']}",
            "identifier": item["identifier"],
            "name": item.get("name"),
            "part": item.get("part"),
            "subpart": item.get("subpart"),
            "date": item.get("date"),
            "source_url": _make_source_url(title=2, part=item.get("part"), section=item["identifier"]),
        })
        if len(starter_citations) >= 15:
            break

    latest_date = meta.get("latest_amendment_date") or meta.get("latest_issue_date")
    return {
        "generated_from": "live ecfr api",
        "today": TODAY,
        "uniform_guidance": {
            "citation": "2 CFR Part 200",
            "title": 2,
            "part": "200",
            "latest_amendment_date": latest_date,
            "source_url": _make_source_url(title=2, part="200"),
            "starter_citations": starter_citations,
        },
        "grants_relevant_agencies": agencies,
        "usage_notes": [
            "Call ecfr_get_title_versions(title, part, section) BEFORE ecfr_get_regulation to get a valid date.",
            "Use ecfr_search for topic/concept discovery. Results include title+part+section for follow-up calls.",
            "Always provide title= explicitly; part numbers are NOT unique across titles (e.g. Part 46 exists in Title 45 AND other titles).",
            "Prefer section-level over part-level requests — part-level fetches can be very large.",
            f"Use latest_amendment_date ({latest_date}) as a safe default date for Title 2 Part 200 lookups.",
        ],
    }


async def _get_resource() -> Dict[str, Any]:
    global _resource_cache
    if _resource_cache is None:
        _resource_cache = await _build_resource()
    return _resource_cache


# =============================================================================
# MCP RESOURCE
# =============================================================================

@mcp.resource("ecfr://regulatory-index")
async def regulatory_index() -> str:
    """
    Compact API-derived metadata for Uniform Guidance and research administration.
    READ THIS BEFORE CALLING TOOLS. Contains:
      uniform_guidance — live Title 2 Part 200 metadata and latest_amendment_date
      starter_citations — section-level starting points for 2 CFR Part 200
      grants_relevant_agencies — agency slugs for search filtering
      usage_notes — key rules for valid tool calls
    """
    data = await _get_resource()
    return _finalize_response(data)


# =============================================================================
# MCP TOOLS — parameters are flat/unwrapped so agents see the full schema
# =============================================================================

_READ_ONLY_ANNOTATIONS = {
    "readOnlyHint": True,
    "destructiveHint": False,
    "idempotentHint": True,
    "openWorldHint": True,
}


@mcp.tool(name="ecfr_get_title_versions", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_get_title_versions(
    title: Annotated[int, Field(description="CFR title number (1–50)", ge=1, le=50)],
    part: Annotated[Optional[str], Field(default=None, description="Narrow to a specific part (e.g. '200' for Uniform Guidance, '46' for Common Rule)")] = None,
    section: Annotated[Optional[str], Field(default=None, description="Narrow to a specific section (e.g. '200.474'). Requires part.")] = None,
    limit: Annotated[int, Field(default=25, description="Max versions to return. Default 25 is sufficient for most use cases.", ge=1, le=200)] = 25,
    issue_date_on: Annotated[Optional[str], Field(default=None, description="Content added on this date (YYYY-MM-DD)")] = None,
    issue_date_lte: Annotated[Optional[str], Field(default=None, description="Content added on or before (YYYY-MM-DD)")] = None,
    issue_date_gte: Annotated[Optional[str], Field(default=None, description="Content added on or after (YYYY-MM-DD)")] = None,
    subtitle: Annotated[Optional[str], Field(default=None, description="Uppercase letter, e.g. 'A'")] = None,
    chapter: Annotated[Optional[str], Field(default=None, description="Roman numeral, e.g. 'I'")] = None,
    subchapter: Annotated[Optional[str], Field(default=None, description="Requires chapter. Uppercase letter.")] = None,
    subpart: Annotated[Optional[str], Field(default=None, description="Requires part. Uppercase letter.")] = None,
    appendix: Annotated[Optional[str], Field(default=None, description="Requires subtitle, chapter, or part.")] = None,
) -> str:
    """Get the amendment/version history for a CFR title.

    CALL THIS FIRST before ecfr_get_regulation or ecfr_compare_regulations.
    Use part= and section= filters to narrow to a specific regulation.
    Each returned version has a "date" field — use that value as date= in ecfr_get_regulation.
    Pick the most recent date unless a historical lookup is specifically needed.

    Example: ecfr_get_title_versions(title=2, part="200", section="200.474")
    → each content_version has a "date" → pass that as date= to ecfr_get_regulation.
    """
    _validate_date_str(issue_date_on, "issue_date_on")
    _validate_date_str(issue_date_lte, "issue_date_lte")
    _validate_date_str(issue_date_gte, "issue_date_gte")
    if subchapter and not chapter:
        return _finalize_response({"error": _make_error("subchapter requires chapter")})
    if subpart and not part:
        return _finalize_response({"error": _make_error("subpart requires part")})
    if section and not part:
        return _finalize_response({"error": _make_error("section requires part")})
    if appendix and not (subtitle or chapter or part):
        return _finalize_response({"error": _make_error("appendix requires subtitle, chapter, or part")})

    query_params = _build_params(
        subtitle=subtitle,
        chapter=chapter,
        subchapter=subchapter,
        part=part,
        subpart=subpart,
        section=section,
        appendix=appendix,
    )
    if issue_date_on:
        query_params["issue_date[on]"] = issue_date_on
    if issue_date_lte:
        query_params["issue_date[lte]"] = issue_date_lte
    if issue_date_gte:
        query_params["issue_date[gte]"] = issue_date_gte
    data = await api_get(
        f"versioner/v1/versions/title-{title}.json",
        params=query_params or None,
    )
    versions = data.get("content_versions", [])
    total = len(versions)
    data["content_versions"] = versions[:limit]
    _add_canonical_fields(data, title=title, part=part, section=section, appendix=appendix,
                          date=issue_date_on or issue_date_lte or issue_date_gte)
    if total > limit:
        _add_warning(data, f"Truncated: {total} versions available, returned {limit}. "
                           f"Use date or hierarchy filters to narrow results.")
    return _finalize_response(data)


@mcp.tool(name="ecfr_get_regulation", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_get_regulation(
    date: Annotated[str, Field(description="Date in YYYY-MM-DD format. Must be a valid eCFR amendment date — use ecfr_get_title_versions to find one. Do not guess.")],
    title: Annotated[Optional[int], Field(default=None, description="CFR title number (1–50). Provide explicitly for unambiguous results. If omitted, resolved from section/part via search — but ambiguous parts (e.g. Part 46, Part 50) will return an error requiring you to specify title.", ge=1, le=50)] = None,
    part: Annotated[Optional[str], Field(default=None, description="Part number, e.g. '200', '46'")] = None,
    section: Annotated[Optional[str], Field(default=None, description="Section number, e.g. '200.474', '46.116'. Requires part. Prefer this over part-only.")] = None,
    subpart: Annotated[Optional[str], Field(default=None, description="Requires part. E.g. 'A', 'B'")] = None,
    subtitle: Annotated[Optional[str], Field(default=None, description="Uppercase letter")] = None,
    chapter: Annotated[Optional[str], Field(default=None, description="Roman numeral, e.g. 'I'")] = None,
    subchapter: Annotated[Optional[str], Field(default=None, description="Requires chapter.")] = None,
    appendix: Annotated[Optional[str], Field(default=None, description="Requires subtitle, chapter, or part.")] = None,
    text_only: Annotated[bool, Field(default=True, description="True (default): returns clean paragraph text — sufficient for policy analysis. False: returns raw XML — only needed for structural parsing.")] = True,
) -> str:
    """Retrieve regulatory text for a specific section or part on a given date.

    IMPORTANT: Call ecfr_get_title_versions first to get a valid date.
    Provide section= whenever possible — part-only requests return very large responses and will be blocked unless subpart= is also specified.
    Always provide title= explicitly for Parts 46 and 50, which exist in multiple titles.

    Examples:
      ecfr_get_regulation(title=2, date="2024-10-01", part="200", section="200.474")
      ecfr_get_regulation(title=45, date="2024-06-21", part="46", section="46.116")
    """
    _validate_date_str(date, "date")
    if subchapter and not chapter:
        return _finalize_response({"error": _make_error("subchapter requires chapter")})
    if subpart and not part:
        return _finalize_response({"error": _make_error("subpart requires part")})
    if section and not part:
        return _finalize_response({"error": _make_error("section requires part")})
    if appendix and not (subtitle or chapter or part):
        return _finalize_response({"error": _make_error("appendix requires subtitle, chapter, or part")})

    if not section and not part and not appendix:
        return _finalize_response({"error": _make_error(
            "Must provide at least part= or section=. Fetching an entire title is too large. "
            "Use ecfr_get_title_structure to find valid identifiers."
        )})
    if part and not section and not subpart and not appendix:
        return _finalize_response({"error": _make_error(
            f"Part {part} without section= or subpart= would return a very large response. "
            f"Add section= to narrow the request. "
            f"Use ecfr_get_title_structure(title=<N>, date=...) to find valid section identifiers."
        )})

    resolved_title = title
    if resolved_title is None:
        resolved = await _resolve_title(section=section, part=part)
        if resolved is None:
            return _finalize_response({"error": _make_error(
                "Could not resolve title from section/part. Provide title= explicitly."
            )})
        if isinstance(resolved, list):
            return _finalize_response({"error": _make_error(
                "Ambiguous: this part/section exists in multiple titles. Provide title= explicitly.",
                candidates=[{
                    "title": h.get("title"),
                    "part": h.get("part"),
                    "section": h.get("section"),
                    "chapter": h.get("chapter"),
                } for h in resolved],
                hint="Re-call with title= set to the correct title number.",
            )})
        try:
            resolved_title = int(resolved.get("title"))
        except (TypeError, ValueError):
            return _finalize_response({"error": _make_error("Title resolution returned non-numeric value.", resolved=resolved)})

    query_params = _build_params(
        subtitle=subtitle,
        chapter=chapter,
        subchapter=subchapter,
        part=part,
        subpart=subpart,
        section=section,
        appendix=appendix,
    )
    xml_text = await api_get(
        f"versioner/v1/full/{date}/title-{resolved_title}.xml",
        params=query_params or None,
    )
    content_value = _xml_to_text(xml_text) if text_only else xml_text
    content_key = "text" if text_only else "xml"
    result = {content_key: content_value}
    _add_canonical_fields(result, title=resolved_title, part=part, section=section, appendix=appendix, date=date)
    if title is None:
        result["resolved_from"] = "search"
    content_bytes = len(content_value.encode("utf-8"))
    if content_bytes > SOFT_RESPONSE_BYTES:
        _add_warning(result, f"Response is {content_bytes:,} bytes (soft limit: 800KB). "
                             f"Narrow to section= if you only need a specific provision.")
    return _finalize_response(result)


@mcp.tool(name="ecfr_search", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_search(
    query: Annotated[str, Field(description="Search term. Examples: 'indirect costs', 'subaward monitoring', 'conflict of interest', 'prior approval', 'procurement standards'.", min_length=1, max_length=500)],
    page: Annotated[int, Field(default=1, description="Page of results (max 20)", ge=1, le=20)] = 1,
    per_page: Annotated[int, Field(default=DEFAULT_SEARCH_RESULTS, description="Results per page (default 5). Increase to 10-15 only when broader coverage needed.", ge=1, le=MAX_SEARCH_RESULTS)] = DEFAULT_SEARCH_RESULTS,
    include_excerpts: Annotated[bool, Field(default=False, description="Include full_text_excerpt snippets. Useful to confirm relevance before fetching full text.")] = False,
    order: Annotated[Optional[str], Field(default="relevance", description="Sort order: 'relevance' (default), 'newest_first', 'oldest_first', 'hierarchy'")] = "relevance",
    date: Annotated[Optional[str], Field(default=None, description="Limit to content present on this date (YYYY-MM-DD)")] = None,
    last_modified_after: Annotated[Optional[str], Field(default=None, description="Modified after this date (YYYY-MM-DD)")] = None,
    last_modified_on_or_after: Annotated[Optional[str], Field(default=None, description="Modified on or after (YYYY-MM-DD)")] = None,
    last_modified_before: Annotated[Optional[str], Field(default=None, description="Modified before (YYYY-MM-DD)")] = None,
    last_modified_on_or_before: Annotated[Optional[str], Field(default=None, description="Modified on or before (YYYY-MM-DD)")] = None,
    agency_slugs: Annotated[Optional[List[str]], Field(default=None, description="Filter by agency slug(s). For Uniform Guidance use 'office-of-management-and-budget'. Use ecfr_list_agencies to find slugs for other agencies.")] = None,
) -> str:
    """Full-text search across the entire Code of Federal Regulations.

    START HERE for topic or concept questions where you don't have a specific citation.
    Returns sections ranked by relevance with title/part/section hierarchy for follow-up calls.
    For Uniform Guidance topics, filter with agency_slugs=['office-of-management-and-budget'].
    Results include citation and source_url fields for each match.

    NEXT STEP: Take the title/part/section from a result → call ecfr_get_title_versions to get
    a valid date → then ecfr_get_regulation to fetch the full text.
    """
    for field_name, field_val in [
        ("date", date),
        ("last_modified_after", last_modified_after),
        ("last_modified_on_or_after", last_modified_on_or_after),
        ("last_modified_before", last_modified_before),
        ("last_modified_on_or_before", last_modified_on_or_before),
    ]:
        _validate_date_str(field_val, field_name)

    query_params = _build_params(
        query=query,
        page=page,
        per_page=per_page,
        paginate_by="results",
        order=order,
        date=date,
        last_modified_after=last_modified_after,
        last_modified_on_or_after=last_modified_on_or_after,
        last_modified_before=last_modified_before,
        last_modified_on_or_before=last_modified_on_or_before,
    )
    if agency_slugs:
        query_params["agency_slugs[]"] = agency_slugs

    data = await api_get("search/v1/results.json", params=query_params)
    results = data.get("results", [])
    meta = data.get("meta", {})
    response = {
        "results": [_slim_search_result(r, include_excerpts) for r in results],
        "meta": meta,
        "source_url": f"{ECFR_SITE}/search?query={query}",
    }
    total_pages = meta.get("total_pages", 0)
    total_count = meta.get("total_count", 0)
    current_page = meta.get("current_page", 1)
    if total_pages > 20:
        _add_warning(response, f"{total_count} total results across {total_pages} pages; only pages 1–20 accessible. "
                               f"Narrow with agency_slugs, date, or last_modified_* filters.")
    if current_page >= 20 and total_pages > 20:
        _add_warning(response, f"Reached last accessible page (20/{total_pages}). Refine the query to find more specific results.")
    return _finalize_response(response)


@mcp.tool(name="ecfr_get_title_structure", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_get_title_structure(
    title: Annotated[int, Field(description="CFR title number (1–50)", ge=1, le=50)],
    date: Annotated[str, Field(description="Date in YYYY-MM-DD format. Use latest_amendment_date from ecfr_get_title_versions or the regulatory_index resource rather than guessing.")],
    depth: Annotated[int, Field(default=DEFAULT_STRUCTURE_DEPTH, description="Hierarchy depth: 1=title, 2=subtitle/chapter, 3=parts, 4=sections. Depth 4 on broad titles (2, 42, 45) is blocked — use depth 3 then narrow.", ge=1, le=4)] = DEFAULT_STRUCTURE_DEPTH,
) -> str:
    """Get the hierarchical table of contents for a CFR title on a given date.

    Use this to discover valid part and section identifiers before calling ecfr_get_regulation.
    Start with depth=2 or depth=3; depth=4 on broad titles (2, 42, 45) is blocked due to response size.
    """
    _validate_date_str(date, "date")
    if depth == 4 and title in {2, 42, 45}:
        return _finalize_response({"error": _make_error(
            f"Depth 4 for Title {title} exceeds the 1MB response limit. "
            f"Use depth=3 to find parts, then call ecfr_get_regulation with a specific part or section."
        )})
    data = await api_get(f"versioner/v1/structure/{date}/title-{title}.json")
    pruned = _prune_tree(data, max_depth=depth)
    _add_canonical_fields(pruned, title=title, date=date)
    if len(json.dumps(pruned, ensure_ascii=False).encode("utf-8")) > SOFT_RESPONSE_BYTES:
        _add_warning(pruned, "Structure response is large (>800KB). Lower depth or use ecfr_search to find a specific section first.")
    return _finalize_response(pruned)


@mcp.tool(name="ecfr_compare_regulations", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_compare_regulations(
    date_1: Annotated[str, Field(description="Earlier date (YYYY-MM-DD) — from ecfr_get_title_versions")],
    date_2: Annotated[str, Field(description="Later date (YYYY-MM-DD) — from ecfr_get_title_versions")],
    title: Annotated[Optional[int], Field(default=None, description="CFR title number. Provide explicitly to avoid ambiguity. See ecfr_get_regulation notes on ambiguous parts.", ge=1, le=50)] = None,
    part: Annotated[Optional[str], Field(default=None, description="Part number, e.g. '200'")] = None,
    section: Annotated[Optional[str], Field(default=None, description="Section number. Requires part.")] = None,
    subpart: Annotated[Optional[str], Field(default=None, description="Requires part.")] = None,
    subtitle: Annotated[Optional[str], Field(default=None, description="Uppercase letter")] = None,
    chapter: Annotated[Optional[str], Field(default=None, description="Roman numeral")] = None,
    subchapter: Annotated[Optional[str], Field(default=None, description="Requires chapter.")] = None,
    appendix: Annotated[Optional[str], Field(default=None, description="Requires subtitle, chapter, or part.")] = None,
    include_full_text: Annotated[bool, Field(default=False, description="Include full plain text of both versions alongside the diff. Default False.")] = False,
) -> str:
    """Compare regulatory text between two dates to identify changes.

    WORKFLOW: Use ecfr_get_title_versions to find valid amendment dates first,
    then pass two of those dates here. Returns a structured diff of added/removed paragraphs.
    Set include_full_text=True to also receive the full text of both versions.
    """
    _validate_date_str(date_1, "date_1")
    _validate_date_str(date_2, "date_2")
    if subchapter and not chapter:
        return _finalize_response({"error": _make_error("subchapter requires chapter")})
    if subpart and not part:
        return _finalize_response({"error": _make_error("subpart requires part")})
    if section and not part:
        return _finalize_response({"error": _make_error("section requires part")})
    if appendix and not (subtitle or chapter or part):
        return _finalize_response({"error": _make_error("appendix requires subtitle, chapter, or part")})

    resolved_title = title
    if resolved_title is None:
        resolved = await _resolve_title(section=section, part=part)
        if resolved is None:
            return _finalize_response({"error": _make_error(
                "Could not resolve title. Provide title= explicitly."
            )})
        if isinstance(resolved, list):
            return _finalize_response({"error": _make_error(
                "Ambiguous: part/section exists in multiple titles. Provide title= explicitly.",
                candidates=[{"title": h.get("title"), "part": h.get("part"), "section": h.get("section")} for h in resolved],
                hint="Re-call with title= specified.",
            )})
        try:
            resolved_title = int(resolved.get("title"))
        except (TypeError, ValueError):
            return _finalize_response({"error": _make_error("Non-numeric title resolved.", resolved=resolved)})

    hierarchy = _build_params(
        subtitle=subtitle,
        chapter=chapter,
        subchapter=subchapter,
        part=part,
        subpart=subpart,
        section=section,
        appendix=appendix,
    )
    xml_1 = await api_get(f"versioner/v1/full/{date_1}/title-{resolved_title}.xml", params=hierarchy)
    xml_2 = await api_get(f"versioner/v1/full/{date_2}/title-{resolved_title}.xml", params=hierarchy)
    text_1 = _xml_to_text(xml_1)
    text_2 = _xml_to_text(xml_2)
    identical = text_1 == text_2

    result: Dict[str, Any] = {
        "date_1": date_1,
        "date_2": date_2,
        "identical": identical,
        "length_1": len(text_1),
        "length_2": len(text_2),
    }
    _add_canonical_fields(result, title=resolved_title, part=part, section=section, appendix=appendix, date=date_2)
    if title is None:
        result["resolved_from"] = "search"

    if identical:
        result["diff"] = {"summary": "No changes detected.", "added_lines": [], "removed_lines": []}
    else:
        lines_1 = text_1.splitlines()
        lines_2 = text_2.splitlines()
        differ = difflib.unified_diff(
            lines_1, lines_2,
            fromfile=f"Date: {date_1}",
            tofile=f"Date: {date_2}",
            lineterm="",
        )
        added, removed = [], []
        for line in differ:
            if line.startswith("+") and not line.startswith("+++"):
                added.append(line[1:].strip())
            elif line.startswith("-") and not line.startswith("---"):
                removed.append(line[1:].strip())
        added = [l for l in added if l]
        removed = [l for l in removed if l]

        t_added, omit_added = added[:MAX_DIFF_LINES], max(0, len(added) - MAX_DIFF_LINES)
        t_removed, omit_removed = removed[:MAX_DIFF_LINES], max(0, len(removed) - MAX_DIFF_LINES)
        result["diff"] = {
            "summary": f"{len(added)} paragraph(s) added, {len(removed)} paragraph(s) removed",
            "added_lines": t_added,
            "removed_lines": t_removed,
        }
        if omit_added or omit_removed:
            _add_warning(result, f"Diff truncated to {MAX_DIFF_LINES} lines each. "
                                 f"Omitted {omit_added} added and {omit_removed} removed lines.")

    if include_full_text:
        result["text_1"] = text_1
        if not identical:
            result["text_2"] = text_2
        else:
            result["note"] = "Texts identical — only text_1 included."

    return _finalize_response(result)


@mcp.tool(name="ecfr_list_agencies", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_list_agencies(
    name_filter: Annotated[Optional[str], Field(default=None, description="Case-insensitive substring filter on agency name or slug. E.g. 'health', 'nsf', 'education'.")] = None,
    include_children: Annotated[bool, Field(default=False, description="Include sub-agency children arrays. Default False keeps response compact.")] = False,
) -> str:
    """List federal agencies with slugs and CFR references.

    Use name_filter to find a specific agency quickly (e.g. 'health', 'nsf').
    Slugs can be passed to ecfr_search via agency_slugs= to scope results.
    Common slugs: 'office-of-management-and-budget' (Uniform Guidance),
    'national-science-foundation', 'national-institutes-of-health'.
    """
    data = await api_get("admin/v1/agencies.json")
    agencies = data.get("agencies", [])
    if name_filter:
        needle = name_filter.lower()
        agencies = [
            a for a in agencies
            if needle in (a.get("name") or "").lower()
            or needle in (a.get("slug") or "").lower()
            or needle in (a.get("short_name") or "").lower()
        ]

    def _slim(agency: dict) -> dict:
        r = {
            "name": agency.get("name"),
            "short_name": agency.get("short_name"),
            "slug": agency.get("slug"),
            "cfr_references": agency.get("cfr_references", []),
        }
        if include_children:
            r["children"] = [_slim(c) for c in agency.get("children", [])]
        return r

    return _finalize_response({"agencies": [_slim(a) for a in agencies]})


@mcp.tool(name="ecfr_list_titles", annotations=_READ_ONLY_ANNOTATIONS)
async def ecfr_list_titles(
    summary_only: Annotated[bool, Field(default=True, description="True (default): returns number, name, latest_amended_on, source_url only — sufficient for navigation and well within the 1MB limit. False: full API response including reserved/up_to_date_as_of fields.")] = True,
) -> str:
    """List all 50 CFR titles with names and latest amendment dates.

    Use summary_only=True (default) to get a compact list sufficient for identifying
    which title number covers a given topic area.
    """
    data = await api_get("versioner/v1/titles.json")
    if summary_only:
        data = {"titles": [
            {
                "citation": f"{t['number']} CFR",
                "title": t["number"],
                "name": t["name"],
                "latest_amended_on": t.get("latest_amended_on"),
                "source_url": _make_source_url(title=t["number"]),
            }
            for t in data.get("titles", [])
        ]}
    return _finalize_response(data)


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    mcp.run()