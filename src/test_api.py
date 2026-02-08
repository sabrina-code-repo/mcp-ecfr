#!/usr/bin/env python3
"""
eCFR API Test Script
Tests all API endpoints used by the MCP server to ensure they're returning results.
"""

import asyncio
import httpx
import json
from typing import Dict, Any, Optional
from datetime import datetime

# Constants
BASE_URL = "https://www.ecfr.gov/api"
TIMEOUT = 30.0

# Test configuration
TEST_TITLE = 1  
TEST_PART = 1  
TEST_SECTION = 1.1
TEST_DATE = "2017-10-20"


class Color:
    """ANSI color codes for terminal output."""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'


import json
import httpx
from typing import Optional, Dict, Any

async def make_api_request(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Make an HTTP request to the eCFR API.
    
    The eCFR API requires file extensions (.json or .xml) on endpoints for content negotiation.
    It returns application/octet-stream but the content is actually JSON or XML.
    """
    
    url = f"{BASE_URL}/{endpoint}"
    
    # use httpx defaults
    headers = {
        "Accept": "application/json, application/xml, application/octet-stream, */*"
    }

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        # rate limiting for agentic scraping
        await asyncio.sleep(0.5)
        
        try:
            response = await client.get(url, params=params, headers=headers)
            response.raise_for_status()
            
            # Parse based on endpoint extension
            if endpoint.endswith('.xml'):
                # For XML responses, parse as XML then convert to dict
                return {"raw_xml": response.text}
            else:
                # Parse as JSON (even though server returns application/octet-stream)
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
    print(f"{Color.GREEN}✓ {message}{Color.END}")


def print_error(message: str):
    """Print an error message."""
    print(f"{Color.RED}✗ {message}{Color.END}")


def print_info(message: str):
    """Print an info message."""
    print(f"{Color.YELLOW}ℹ {message}{Color.END}")


async def test_list_titles():
    """Test: List all CFR titles."""
    print_test_header("List All CFR Titles")
    
    try:
        data = await make_api_request("versioner/v1/titles")
        
        # Validate response structure
        if 'titles' not in data:
            print_error("Response missing 'titles' field")
            return False
        
        titles = data['titles']
        
        if not isinstance(titles, list):
            print_error("'titles' is not a list")
            return False
        
        if len(titles) == 0:
            print_error("No titles returned")
            return False
        
        # Check first title has expected fields
        first_title = titles[0]
        expected_fields = ['number', 'name', 'latest_amended_on', 'latest_issue_date']
        
        for field in expected_fields:
            if field not in first_title:
                print_error(f"Title missing expected field: {field}")
                return False
        
        print_success(f"Retrieved {len(titles)} CFR titles")
        print_info(f"Sample: Title {first_title['number']}: {first_title['name']}")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


async def test_get_title_versions():
    """Test: Get version history for a title."""
    print_test_header(f"Get Version History for Title {TEST_TITLE}")
    
    try:
        data = await make_api_request(f"versioner/v1/versions/title-{TEST_TITLE}.json")
        
        # Validate response structure
        if 'content_versions' not in data:
            print_error("Response missing 'versions' field")
            return False
        
        versions = data['content_versions']
        
        if not isinstance(versions, list):
            print_error("'content_versions' is not a list")
            return False
        
        if len(versions) == 0:
            print_error("No versions returned")
            return False
        
        # Check first version has expected fields
        first_version = versions[0]
        expected_fields = ['date', 'identifier']
        
        for field in expected_fields:
            if field not in first_version:
                print_error(f"Version missing expected field: {field}")
                return False
        
        print_success(f"Retrieved {len(versions)} versions for Title {TEST_TITLE}")
        print_info(f"Latest version: {first_version['date']} ({first_version['identifier']})")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


async def test_get_title_summary():
    """Test: Get summary of titles."""
    print_test_header(f"Get Summary of Titles")
    
    try:
        data = await make_api_request(f"versioner/v1/titles")
        
        # Validate response structure
        if 'titles' not in data:
            print_error("Response missing 'titles' field")
            return False
        
        titles = data['titles']
        
        if not isinstance(titles, list):
            print_error("'titles' is not a list")
            return False
        
        if len(titles) == 0:
            print_error("No structure elements returned")
            return False
        
        # Check first element has expected fields
        first_element = titles[0]
        expected_fields = ['number', 'name']
        
        for field in expected_fields:
            if field not in first_element:
                print_error(f"Structure element missing expected field: {field}")
                return False
        
        print_success(f"Retrieved structure with {len(titles)} top-level elements")
        print_info(f"First element: {first_element['number']} {first_element['name']}")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


async def test_get_title_structure_by_date():
    """Test: Get structure of a title for a specific date."""
    print_test_header(f"Get Structure for Title {TEST_TITLE} on {TEST_DATE}")
    
    try:
        data = await make_api_request(
            "versioner/v1/structure/2017-10-20/title-1.json"
        )

        # Show what we got back
        print_info("Response structure:")
        print_info(f"  Type: {type(data)}")
        print_info(f"  Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        # Check for expected fields
        if 'identifier' not in data:
            print_error("Response missing 'identifier' field")
            print_info(f"Full response: {json.dumps(data, indent=2)[:500]}...")  # First 500 chars
            return False

        # Show identifier info
        print_success(f"Identifier: {data['identifier']}")
        
        # Show children info
        children = data.get('children', [])
        print_success(f"Retrieved structure for {TEST_DATE}")
        print_info(f"Structure has {len(children)} top-level elements")
        
        # Show first few children as examples
        if children:
            print_info(f"\nFirst 3 children:")
            for i, child in enumerate(children[:3]):
                print_info(f"  {i+1}. {child.get('identifier', 'unknown')}: {child.get('label', 'no label')[:50]}")
        
        # Optionally show full response (commented out by default)
        # print_info(f"\nFull response:\n{json.dumps(data, indent=2)}")

        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        print_error(f"Response body: {e.response.text[:500]}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        import traceback
        print_error(traceback.format_exc())
        return False

async def test_get_section_by_date():
    """Test: Get a specific section for a historical date."""
    print_test_header(f"Get Section {TEST_TITLE} CFR {TEST_PART}.{TEST_SECTION} on {TEST_DATE}")
    
    try:
        # Request specific section
        section_id = {
            'section': TEST_SECTION
        }
        data = await make_api_request(
            f"versioner/v1/full/{TEST_DATE}/title-{TEST_TITLE}.xml", 
            params=section_id
        )
        
        # Show what we got back
        print_info("Response structure:")
        print_info(f"  Type: {type(data)}")
        print_info(f"  Keys: {list(data.keys()) if isinstance(data, dict) else 'Not a dict'}")
        
        # Show raw content preview
        if 'raw_xml' in data:
            xml_content = data['raw_xml']
            print_info(f"  XML length: {len(xml_content)} characters")
            print_info(f"  XML preview (first 300 chars):\n{xml_content[:300]}...")
        
        # Validate response structure
        if 'SECTION' not in data and 'raw_xml' not in data:
            print_error("Response missing expected fields")
            print_info(f"Full response preview: {str(data)[:500]}...")
            return False
        
        # Extract content based on response structure
        if 'raw_xml' in data:
            content = data['raw_xml']
        else:
            content = data.get('content', data.get('text', ''))
        
        content_length = len(content)
        
        print_success(f"Retrieved historical section for {TEST_DATE}")
        print_info(f"Content length: {content_length} characters")
        
        # Show content preview
        if content_length > 0:
            print_info(f"\nContent preview (first 200 chars):")
            print_info(f"{content[:200]}...")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        print_error(f"Response body: {e.response.text[:500]}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        import traceback
        print_error(traceback.format_exc())
        return False

async def test_search():
    """Test: Search the CFR."""
    print_test_header("Search CFR for 'informed consent'")
    
    try:
        params = {
            'query': 'informed consent',
            'page': 1 ,
            'per_page': 20
        }
        data = await make_api_request("search/v1/results", params)
        
        content = data.get('content', data.get('text', ''))
        content_length = len(content)
        
        print_success(f"Retrieved historical section for {TEST_DATE}")
        print_info(f"Content length: {content_length} characters")
        
        if content_length > 0:
            first_result = data['results'][0]
            print_info(f"First result: {first_result.get('citation', 'N/A')}")
        
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


async def test_search_pagination():
    """Test: Search with pagination."""
    print_test_header("Search with Pagination (offset)")
    
    try:
        # First page
        params1 = {
            'query': 'research',
            'page': 5,
            'paginate_by': "results"
        }
        data = await make_api_request("search/v1/results", params1)
        
        count = data['results']
        
        print_success(f"Results returned {count} results")
        return True
        
    except httpx.HTTPStatusError as e:
        print_error(f"HTTP error: {e.response.status_code}")
        return False
    except Exception as e:
        print_error(f"Unexpected error: {str(e)}")
        return False


async def test_api_performance():
    """Test: Measure API response time."""
    print_test_header("API Performance Test")
    
    try:
        start_time = datetime.now()
        await make_api_request("versioner/v1/titles.json")
        end_time = datetime.now()
        
        duration = (end_time - start_time).total_seconds()
        
        print_success(f"API response time: {duration:.2f} seconds")
        
        if duration < 2.0:
            print_info("Response time is excellent (< 2s)")
        elif duration < 5.0:
            print_info("Response time is good (< 5s)")
        else:
            print_info("Response time is slow (> 5s)")
        
        return True
        
    except Exception as e:
        print_error(f"Performance test failed: {str(e)}")
        return False


async def run_all_tests():
    """Run all API tests."""
    print(f"\n{Color.BOLD}{'='*70}")
    print(f"eCFR API Test Suite")
    print(f"Testing against: {BASE_URL}")
    print(f"Test Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}{Color.END}\n")
    
    tests = [
        ("List Titles", test_list_titles),
        ("Get Version History", test_get_title_versions),
        ("Get Title Structure", test_get_title_summary),
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
        print(f"\n{Color.GREEN}{Color.BOLD} All tests passed! The eCFR API is working correctly.{Color.END}")
        return 0
    else:
        print(f"\n{Color.RED}{Color.BOLD} Some tests failed. Please check the API or network connection.{Color.END}")
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
