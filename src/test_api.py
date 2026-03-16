"""
eCFR API Test Script
Tests all API endpoints used by the MCP server to ensure they're returning results.
"""

import asyncio
import httpx
import json
from typing import Dict, Any, Optional
from datetime import datetime
from pathlib import Path
import re

# Constants
BASE_URL = "https://www.ecfr.gov/api"
TIMEOUT = 30.0

# Create an output directory for test artifacts
LOG_DIR = Path("../test_outputs/api_tests")
# Ensure the output directory exists
LOG_DIR.mkdir(parents=True, exist_ok=True)
# Create a timestamp for this run
RUN_TS = datetime.now().strftime("%Y%m%d_%H%M%S")
# Create a run-specific directory
RUN_DIR = LOG_DIR / RUN_TS
# Ensure the run directory exists
RUN_DIR.mkdir(parents=True, exist_ok=True)


# Test configuration
TEST_TITLE = 1
TEST_PART = 1
TEST_SECTION = 1.1
TEST_DATE = "2017-10-20"


class Color:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    BOLD = "\033[1m"
    END = "\033[0m"


async def make_api_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make an HTTP request to the eCFR API.

    The eCFR API requires file extensions (.json or .xml) on endpoints for content negotiation.
    """

    url = f"{BASE_URL}/{endpoint}"

    # Use a broad Accept header to allow the API to return the correct format based on the endpoint extension
    headers = {
        "Accept": "application/json, application/xml, application/octet-stream, */*"
    }

    # Log the request details for debugging
    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        # Add a small delay for agentic use later
        await asyncio.sleep(0.5)

        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()

            # Build a filesystem-safe name for this call
            safe_endpoint = re.sub(r"[^a-zA-Z0-9._-]+", "_", endpoint)
            safe_params = re.sub(r"[^a-zA-Z0-9._-]+", "_", json.dumps(params or {}, sort_keys=True))
            base_name = f"{RUN_TS}__{safe_endpoint}__{safe_params}"

            # Choose file extension for the raw body
            if endpoint.endswith(".xml"):
                body_path = RUN_DIR / f"{base_name}.xml"
                meta_path = RUN_DIR / f"{base_name}.meta.txt"
            else:
                body_path = RUN_DIR / f"{base_name}.json"
                meta_path = RUN_DIR / f"{base_name}.meta.txt"

            # Write metadata describing the response
            meta_text = "\n".join([
                f"url={url}",
                f"params={json.dumps(params or {}, ensure_ascii=False)}",
                f"status_code={response.status_code}",
                f"content_type={response.headers.get('content-type', '')}",
                f"bytes={len(response.content)}",
            ])
            meta_path.write_text(meta_text, encoding="utf-8")

            # Write the full response body
            if endpoint.endswith(".xml"):
                body_path.write_text(response.text, encoding="utf-8")
            else:
                # Try to pretty-print JSON for readability; fall back to raw text
                try:
                    parsed = json.loads(response.content.decode("utf-8"))
                    body_path.write_text(json.dumps(parsed, indent=2, ensure_ascii=False), encoding="utf-8")
                except Exception:
                    body_path.write_text(response.content.decode("utf-8", errors="replace"), encoding="utf-8")

            # Existing parse/return behavior stays the same
            if endpoint.endswith(".xml"):
                return {"raw_xml": response.text}
            else:
                return json.loads(response.content.decode("utf-8"))

        except httpx.HTTPStatusError as e:
            if e.response.status_code == 406:
                raise RuntimeError(
                    f"406 Not Acceptable - ensure endpoint has .json or .xml extension."
                    f"URL: {url}"
                ) from e
            else:
                raise


def print_test_header(test_name: str):
    """Print a formatted test header."""
    print(f"\n{Color.BLUE}{Color.BOLD}{'='*70}{Color.END}")
    print(f"{Color.BLUE}{Color.BOLD}TEST: {test_name}{Color.END}")
    print(f"{Color.BLUE}{Color.BOLD}{'='*70}{Color.END}")


def print_success(message: str):
    """Print a success message."""
    print(f"{Color.GREEN} {message}{Color.END}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Color.RED} {message}{Color.END}")


def print_info(message: str):
    """Print an info message."""
    print(f"{Color.YELLOW} {message}{Color.END}")


async def test_list_titles():
    """Test: List all CFR titles."""
    print_test_header("List All CFR Titles")

    try:
        # Call endpoint with explicit extension to avoid 406 ambiguity
        data = await make_api_request("versioner/v1/titles.json")

        # Validate response structure
        if "titles" not in data:
            print_error("Validation failed: response missing 'titles' field")
            return False

        titles = data["titles"]

        # Validate response types
        if not isinstance(titles, list):
            print_error("Validation failed: 'titles' is not a list")
            return False

        if len(titles) == 0:
            print_error("Validation failed: no titles returned")
            return False

        # Validate expected fields on the first item
        first_title = titles[0]
        expected_fields = ["number", "name", "latest_amended_on", "latest_issue_date"]

        for field in expected_fields:
            if field not in first_title:
                print_error(f"Validation failed: title missing expected field '{field}'")
                return False

        # Print consistent success output
        print_success(f"Retrieved {len(titles)} CFR titles")
        print_info(f"Sample title: {first_title['number']} {first_title['name']}")
        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_list_titles: {str(e)}")
        return False


async def test_get_title_versions():
    """Test: Get version history for a title."""
    print_test_header(f"Get Version History for Title {TEST_TITLE}")

    try:
        # Call endpoint with explicit extension to avoid 406 ambiguity
        data = await make_api_request(f"versioner/v1/versions/title-{TEST_TITLE}.json")

        # Validate response structure
        if "content_versions" not in data:
            print_error("Validation failed: response missing 'content_versions' field")
            return False

        versions = data["content_versions"]

        # Validate response types
        if not isinstance(versions, list):
            print_error("Validation failed: 'content_versions' is not a list")
            return False

        if len(versions) == 0:
            print_error("Validation failed: no versions returned")
            return False

        # Validate expected fields on the first item
        first_version = versions[0]
        expected_fields = ["date", "identifier"]

        for field in expected_fields:
            if field not in first_version:
                print_error(f"Validation failed: version missing expected field '{field}'")
                return False

        # Print consistent success output
        print_success(f"Retrieved {len(versions)} versions for Title {TEST_TITLE}")
        print_info(f"First listed version: {first_version['date']} ({first_version['identifier']})")
        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_get_title_versions: {str(e)}")
        return False


async def test_get_title_summary():
    """Test: Get summary of titles."""
    print_test_header("Get Summary of Titles")

    try:
        # Call endpoint with explicit extension to avoid 406 ambiguity
        data = await make_api_request("versioner/v1/titles.json")

        # Validate response structure
        if "titles" not in data:
            print_error("Validation failed: response missing 'titles' field")
            return False

        titles = data["titles"]

        # Validate response types
        if not isinstance(titles, list):
            print_error("Validation failed: 'titles' is not a list")
            return False

        if len(titles) == 0:
            print_error("Validation failed: no titles returned")
            return False

        # Validate expected fields on the first item
        first_element = titles[0]
        expected_fields = ["number", "name"]

        for field in expected_fields:
            if field not in first_element:
                print_error(f"Validation failed: title missing expected field '{field}'")
                return False

        # Print consistent success output
        print_success(f"Retrieved {len(titles)} titles in summary")
        print_info(f"First title: {first_element['number']} {first_element['name']}")
        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_get_title_summary: {str(e)}")
        return False


async def test_get_title_structure_by_date():
    """Test: Get structure of a title for a specific date."""
    print_test_header(f"Get Structure for Title {TEST_TITLE} on {TEST_DATE}")

    try:
        # Call endpoint with explicit extension to avoid 406 ambiguity
        data = await make_api_request(f"versioner/v1/structure/{TEST_DATE}/title-{TEST_TITLE}.json")

        # Validate response structure
        if "identifier" not in data:
            print_error("Validation failed: response missing 'identifier' field")
            print_info(f"Response preview: {json.dumps(data, indent=2)[:500]}...")
            return False

        children = data.get("children", [])

        # Print consistent success output
        print_success(f"Retrieved structure for {TEST_DATE}")
        print_info(f"Root identifier: {data['identifier']}")
        print_info(f"Top-level children: {len(children)}")

        # Print a small sample consistently
        if children:
            print_info("Sample children (first 3):")
            for i, child in enumerate(children[:3]):
                print_info(f"  {i+1}. {child.get('identifier', 'unknown')}: {child.get('label', 'no label')[:50]}")

        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_get_title_structure_by_date: {str(e)}")
        import traceback
        print_error(traceback.format_exc())
        return False


async def test_get_section_by_date():
    """Test: Get a specific section for a historical date."""
    print_test_header(f"Get Section {TEST_TITLE} CFR {TEST_PART}.{TEST_SECTION} on {TEST_DATE}")

    try:
        # Request a specific section via query params
        section_params = {"section": TEST_SECTION}

        # Call XML endpoint with explicit extension
        data = await make_api_request(
            f"versioner/v1/full/{TEST_DATE}/title-{TEST_TITLE}.xml",
            params=section_params
        )

        # Validate response structure for XML pathway
        if "raw_xml" not in data:
            print_error("Validation failed: XML endpoint did not return 'raw_xml'")
            print_info(f"Response preview: {str(data)[:500]}...")
            return False

        xml_content = data["raw_xml"]

        # Print consistent success output
        print_success(f"Retrieved section content for {TEST_DATE}")
        print_info(f"XML length: {len(xml_content)} characters")
        print_info("XML preview (first 300 chars):")
        print_info(f"{xml_content[:300]}...")

        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_get_section_by_date: {str(e)}")
        import traceback
        print_error(traceback.format_exc())
        return False


async def test_search():
    """Test: Search the CFR."""
    print_test_header("Search CFR for 'informed consent'")

    try:
        # Call endpoint with explicit extension to avoid 406 ambiguity
        params = {"query": "informed consent", "page": 1, "per_page": 20}
        data = await make_api_request("search/v1/results.json", params)

        # Validate response structure
        results = data.get("results")
        if results is None:
            print_error("Validation failed: response missing 'results' field")
            return False

        if not isinstance(results, list):
            print_error("Validation failed: 'results' is not a list")
            return False

        # Print consistent success output
        print_success(f"Search returned {len(results)} results")
        if results:
            first_result = results[0]
            print_info(f"First result citation: {first_result.get('citation', 'N/A')}")
        else:
            print_info("No results returned for query")

        return True

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_search: {str(e)}")
        return False


async def test_search_pagination(max_pages: int = 5, keyword: str = "research"):
    """Test: Search with pagination - fetches up to 5 pages."""
    print_test_header("Search with Pagination (multiple pages)")

    try:
        all_results = []
        max_pages = max_pages or 5  # Default to 5 if not provided
        total_pages = None
        
        for page_num in range(1, max_pages + 1):
            # Call endpoint with explicit extension to avoid 406 error
            params = {"query": keyword, "page": page_num, "paginate_by": "results"}
            data = await make_api_request("search/v1/results.json", params)

            # Extract metadata
            meta = data.get("meta", {})
            total_pages = meta.get("total_pages")
            current_page = meta.get("current_page")
            
            # Validate response structure
            results = data.get("results")
            if results is None:
                print_error(f"Validation failed on page {page_num}: response missing 'results' field")
                break

            if not isinstance(results, list):
                print_error(f"Validation failed on page {page_num}: 'results' is not a list")
                break

            # If no results on this page, we've reached the end
            if not results:
                print_info(f"No more results found at page {page_num}")
                break
            
            all_results.extend(results)
            print_info(f"Page {current_page}/{total_pages}: fetched {len(results)} results")
            
            # Stop if we've reached the last available page
            if total_pages and current_page >= total_pages:
                print_info(f"Reached last available page ({total_pages})")
                break

        # Summary
        if all_results:
            pages_fetched = min(page_num, max_pages) if total_pages and page_num <= total_pages else page_num
            print_success(f"Total results fetched across {pages_fetched} page(s): {len(all_results)}")
            print_info(f"First result hierarchy: {all_results[0].get('hierarchy', {}).get('section', 'N/A')}")
            if total_pages:
                print_info(f"API has {total_pages} total pages available")
            return True
        else:
            print_error("No results were fetched")
            return False

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_search_pagination: {str(e)}")
        return False

    except httpx.HTTPStatusError:
        # make_api_request already printed consistent error context
        return False
    except Exception as e:
        print_error(f"Unexpected error in test_search_pagination: {str(e)}")
        return False


async def test_api_performance():
    """Test: Measure API response time."""
    print_test_header("API Performance Test")

    try:
        # Measure around the request call for a consistent endpoint
        start_time = datetime.now()
        await make_api_request("versioner/v1/titles.json")
        end_time = datetime.now()

        duration = (end_time - start_time).total_seconds()

        # Print consistent success output
        print_success(f"API response time: {duration:.2f} seconds")

        # Print consistent interpretation output
        if duration < 2.0:
            print_info("Response time bucket: excellent (< 2s)")
        elif duration < 5.0:
            print_info("Response time bucket: good (< 5s)")
        else:
            print_info("Response time bucket: slow (> 5s)")

        return True

    except Exception as e:
        print_error(f"Performance test failed: {str(e)}")
        return False

async def run_all_tests():
    """Run all API tests."""
    print(f"\n{Color.BOLD}{'='*70}")
    print("eCFR API Test Suite")
    print(f"Testing against: {BASE_URL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}{Color.END}\n")

    tests = [
        ("List Titles", test_list_titles),
        ("Get Version History", test_get_title_versions),
        ("Get Title Summary", test_get_title_summary),
        ("Get Historical Structure", test_get_title_structure_by_date),
        ("Get Historical Section", test_get_section_by_date),
        ("Search", test_search),
        ("Search Pagination", test_search_pagination),
        ("API Performance", test_api_performance),
    ]

    results = []

    for test_name, test_func in tests:
        try:
            result = await test_func()
            results.append((test_name, result))
        except Exception as e:
            print_error(f"Test crashed: {str(e)}")
            results.append((test_name, False))

    # Print summary
    print(f"\n{Color.BOLD}{'='*70}")
    print("TEST SUMMARY")
    print(f"{'='*70}{Color.END}\n")

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for test_name, result in results:
        status = f"{Color.GREEN}PASS{Color.END}" if result else f"{Color.RED}FAIL{Color.END}"
        print(f"{test_name:.<50} {status}")

    print(f"\n{Color.BOLD}Total: {passed}/{total} tests passed{Color.END}")

    if passed == total:
        print(f"\n{Color.GREEN}{Color.BOLD}All tests passed! The eCFR API is working correctly.{Color.END}")
        return 0

    print(f"\n{Color.RED}{Color.BOLD}Some tests failed. Please check the API or network connection.{Color.END}")
    return 1


def main():
    """Main entry point."""
    try:
        exit_code = asyncio.run(run_all_tests())
        return exit_code
    except KeyboardInterrupt:
        print(f"\n{Color.YELLOW}Tests interrupted by user{Color.END}")
        return 1
    except Exception as e:
        print(f"\n{Color.RED}Unexpected error: {str(e)}{Color.END}")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())